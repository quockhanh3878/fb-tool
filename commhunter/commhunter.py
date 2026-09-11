#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CommHunter AI — Entry point CLI + Orchestrator (Phase 1 MVP).

Đây là file duy nhất khách hàng cần chạy. Các module khác đều là linh kiện.

LỆNH:
    python commhunter.py status --config configs/khach.yaml
    python commhunter.py login  --config configs/khach.yaml --profile scout
    python commhunter.py login  --config configs/khach.yaml --profile shooter
    python commhunter.py run    --config configs/khach.yaml
    python commhunter.py --config configs/khach.yaml            # mặc định = run

PIPELINE của lệnh `run`:

    Scout quét group
      └─> lọc trùng theo content_hash          (DedupStore, ~0 chi phí)
          └─> lọc từ khóa whitelist/blacklist  (local, ~0 chi phí)
              └─> AI chấm điểm relevance       (TỐN TIỀN — nên đứng sau cùng)
                  └─> anti-crowding: bỏ bài đã quá đông người ứng tuyển
                      ├─ semi_auto: bắn Telegram, chờ người bấm nút
                      └─ full_auto: đẩy thẳng vào hàng đợi Shooter
                          └─> Shooter (1 consumer DUY NHẤT, tuần tự)
                              sinh comment → warmup → đăng → báo kết quả

Hàng đợi Shooter cố ý chỉ có MỘT consumer: hai comment không bao giờ được
chạy song song trên cùng một tài khoản Facebook.
"""
__version__ = "1.0.0"

import argparse
import asyncio
import os
import signal
import sys
import unicodedata
from dataclasses import asdict
from pathlib import Path

# ── Bootstrap: các module dùng import phẳng (from models import ...) nên
#    thư mục này phải nằm trong sys.path dù người dùng chạy từ đâu.
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

# Console Windows mặc định là cp1252 -> log tiếng Việt + emoji sẽ crash.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from loguru import logger  # noqa: E402

from browser_manager import BrowserManager, stealth_status  # noqa: E402
from config_loader import load_config  # noqa: E402
from constants import (  # noqa: E402
    CIRCUIT_BREAKER_FAILURES,
    LOG_FORMAT,
    LOG_RETENTION,
    LOG_ROTATION,
    normalize_vi,
)
from dedup_store import DedupStore  # noqa: E402
from models import AppConfig, CommentStatus, DiscoveredPost  # noqa: E402
from scout_worker import ScoutWorker  # noqa: E402
from shooter_worker import ShooterWorker  # noqa: E402
from telegram_bot import TelegramBot  # noqa: E402

LOG_DIR = _SCRIPT_DIR / "data" / "logs"
DAILY_REPORT_INTERVAL_SEC = 6 * 3600


# ═══════════════════════════════════════════════════════════════════════════
# Hạ tầng: logging, env, kiểm tra cấu hình
# ═══════════════════════════════════════════════════════════════════════════
def setup_logging(verbose: bool = False) -> None:
    """Cấu hình loguru: console + file xoay vòng trong data/logs/."""
    logger.remove()
    logger.add(
        sys.stderr,
        format=LOG_FORMAT,
        level="DEBUG" if verbose else "INFO",
        colorize=True,
    )
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger.add(
        LOG_DIR / "commhunter_{time:YYYY-MM-DD}.log",
        format=LOG_FORMAT,
        level="DEBUG",
        rotation=LOG_ROTATION,
        retention=LOG_RETENTION,
        encoding="utf-8",
        enqueue=True,
    )


def load_env() -> None:
    """Nạp file .env (thư mục dự án gốc, rồi tới thư mục commhunter/)."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    for candidate in (_SCRIPT_DIR.parent / ".env", _SCRIPT_DIR / ".env"):
        if candidate.exists():
            load_dotenv(candidate, override=False)
            logger.debug(f"Đã nạp biến môi trường từ {candidate}")


def _account_cdp(account) -> str:
    """CDP endpoint hiệu lực của 1 account (chuỗi rỗng nếu không attach)."""
    return (getattr(account, "cdp_endpoint", None) or "").strip()


def find_config_problems(config: AppConfig) -> list:
    """Trả về danh sách lỗi cấu hình NGHIÊM TRỌNG (phải dừng, không chỉ cảnh báo).

    config_loader._validate_config() chỉ log warning, nên một API key chưa
    resolve vẫn lọt tới runtime rồi mới chết bằng lỗi 401 khó hiểu. Hàm này
    bắt sớm ngay lúc khởi động.
    """
    problems = []

    def unresolved(value) -> bool:
        return isinstance(value, str) and value.strip().startswith("$")

    if not config.groups:
        problems.append("Chưa khai báo group nào trong mục `groups:`")

    key = config.openai.api_key
    if not key:
        problems.append("`openai.api_key` đang trống")
    elif unresolved(key):
        problems.append(
            f"`openai.api_key` = '{key}' — biến môi trường CHƯA được đặt. "
            "Tạo file .env hoặc export biến này."
        )
    elif key.startswith("sk-xxxx"):
        problems.append("`openai.api_key` vẫn là giá trị mẫu 'sk-xxxx...'")

    if config.comment.mode not in ("semi_auto", "full_auto"):
        problems.append(
            f"`comment.mode` = '{config.comment.mode}' không hợp lệ "
            "(chỉ chấp nhận 'semi_auto' hoặc 'full_auto')"
        )

    # Telegram chỉ bắt buộc ở chế độ semi_auto (cần nút bấm để duyệt)
    if config.comment.mode == "semi_auto":
        for field_name, value in (("bot_token", config.telegram.bot_token),
                                  ("chat_id", config.telegram.chat_id)):
            if not value:
                problems.append(f"`telegram.{field_name}` trống — bắt buộc ở chế độ semi_auto")
            elif unresolved(value):
                problems.append(
                    f"`telegram.{field_name}` = '{value}' — biến môi trường CHƯA được đặt"
                )

    for role in ("scout", "shooter"):
        account = config.accounts.get(role)
        if account is None:
            problems.append(f"Thiếu tài khoản `accounts.{role}`")
        elif not account.profile_dir and not _account_cdp(account):
            problems.append(
                f"`accounts.{role}.profile_dir` trống (và không có cdp_endpoint)"
            )

    scout = config.accounts.get("scout")
    shooter = config.accounts.get("shooter")
    # Khi cả hai attach vào cùng một Chrome (test tay) thì dùng chung là bình thường.
    both_attached = (
        scout is not None
        and shooter is not None
        and _account_cdp(scout)
        and _account_cdp(shooter)
    )
    if (
        scout and shooter and not both_attached
        and scout.profile_dir and scout.profile_dir == shooter.profile_dir
    ):
        problems.append(
            "scout và shooter đang dùng CHUNG profile_dir — hai Chrome không thể "
            "khoá cùng một user-data-dir, và mô hình Scout–Shooter mất tác dụng."
        )

    return problems


def keyword_match(text: str, flt) -> tuple:
    """Lọc từ khóa cục bộ, chạy TRƯỚC khi gọi AI để tiết kiệm chi phí.

    So khớp không phân biệt dấu và hoa/thường (xem normalize_vi).

    Returns:
        (đạt, lý_do_loại). đạt=True nghĩa là được phép đưa lên AI chấm điểm.
    """
    haystack = normalize_vi(text)

    for kw in flt.blacklist_keywords or []:
        if kw and normalize_vi(kw) in haystack:
            return False, f"blacklist:{kw}"

    whitelist = [kw for kw in (flt.whitelist_keywords or []) if kw]
    if whitelist and not any(normalize_vi(kw) in haystack for kw in whitelist):
        return False, "no_whitelist_keyword"

    return True, ""


# ═══════════════════════════════════════════════════════════════════════════
# Orchestrator
# ═══════════════════════════════════════════════════════════════════════════
class CommHunterApp:
    """Lắp ráp Scout, AI, Telegram và Shooter thành một vòng chạy hoàn chỉnh."""

    def __init__(self, config: AppConfig):
        self.config = config
        self.browser_mgr = BrowserManager(config)
        self.scout = ScoutWorker(self.browser_mgr, config)
        self.shooter = ShooterWorker(self.browser_mgr, config)
        self.db = DedupStore(config.database.path)
        self.tg = TelegramBot(config.telegram)
        self.ai = None  # khởi tạo trễ: constructor OpenAI ném lỗi nếu key rỗng

        # Kết quả AI không được lưu vào bảng discovered_posts (schema Phase 1
        # chưa có cột ai_extracted), nên giữ tạm trong RAM để luồng Semi-Auto
        # dùng lại khi người dùng bấm nút. Mất khi restart — chấp nhận ở MVP.
        self._ai_cache = {}
        self._comment_cache = {}

        self._shoot_queue = asyncio.Queue()
        self._tasks = []
        self._stopping = False
        self._breaker_tripped = False

    # ── Khởi tạo ────────────────────────────────────────────────────────
    def _ensure_ai(self):
        if self.ai is None:
            from ai_engine import AIEngine
            self.ai = AIEngine(self.config.openai.api_key, self.config.openai.model)
        return self.ai

    # ── Pipeline chính ──────────────────────────────────────────────────
    async def process_new_posts(self, posts: list) -> None:
        """Callback cho Scout: xử lý các bài viết mới vừa quét được."""
        ai = self._ensure_ai()
        flt = self.config.filter

        for post in posts:
            if self._stopping:
                return

            # 1. Lọc từ khóa — miễn phí, chặn phần lớn rác trước khi tốn token
            passed, reason = keyword_match(post.content_text, flt)
            if not passed:
                logger.debug(f"Bỏ qua ({reason}): {post.author_name}")
                self.db.mark_skipped(post, reason)
                continue

            # 2. AI chấm điểm
            try:
                ai_result = await ai.filter_post(post.content_text, flt.ai_filter_prompt)
            except Exception as e:
                logger.error(f"AI filter lỗi, bỏ qua bài này: {e}")
                continue

            try:
                score = float(ai_result.get("relevance_score", 0) or 0)
            except (TypeError, ValueError):
                score = 0.0

            post.ai_relevance_score = score
            post.ai_reason = str(ai_result.get("reason", ""))
            post.ai_extracted = ai_result.get("extracted") or {}

            if score < flt.min_relevance_score:
                logger.info(
                    f"Điểm thấp {score:.2f} < {flt.min_relevance_score}: {post.author_name}"
                )
                self.db.mark_skipped(post, f"low_score:{score:.2f} — {post.ai_reason}")
                continue

            # 3. Anti-crowding: chen vào bài đã đông vừa tốn quota vừa vô ích
            if post.existing_comment_count > flt.max_competitor_comments:
                logger.info(
                    f"Quá đông ({post.existing_comment_count} comment > "
                    f"{flt.max_competitor_comments}): {post.author_name}"
                )
                self.db.mark_skipped(post, f"too_competitive:{post.existing_comment_count}")
                continue

            # 4. Bài phù hợp
            self.db.increment_matched()
            self._ai_cache[post.content_hash] = ai_result
            logger.info(
                f"BÀI PHÙ HỢP (điểm {score:.2f}): {post.author_name} — {post.group_name}"
            )

            if self.config.comment.mode == "semi_auto":
                message_id = await self.tg.send_post_notification(post, ai_result)
                if message_id:
                    self.db.mark_notified(post)
                else:
                    logger.error(
                        "Không gửi được thông báo Telegram — bài vẫn ở trạng thái 'new'"
                    )
            else:
                comment = await self._make_comment(post, ai_result)
                if comment:
                    await self._enqueue_shot(post, comment)

    async def _make_comment(self, post: DiscoveredPost, ai_result: dict) -> str:
        """Sinh comment (có cache để Preview rồi Apply không phải trả tiền 2 lần)."""
        cached = self._comment_cache.get(post.content_hash)
        if cached:
            return cached

        if not getattr(self.config.comment, "use_ai", True):
            # Tuỳ chọn: không dùng AI sinh comment, dùng TemplatePool hoặc câu chào mặc định
            tpl_file = getattr(self.config.comment, "template_file", None)
            if tpl_file and os.path.exists(tpl_file):
                try:
                    from comment_templates import TemplatePool
                    pool = TemplatePool(tpl_file)
                    picked = pool.pick()
                    if picked:
                        self._comment_cache[post.content_hash] = picked
                        return picked
                except Exception as e:
                    logger.warning(f"Không nạp được câu từ template_file: {e}")

            svc = self.config.service
            default_text = f"Chào bạn, bên mình chuyên {svc.specialties or svc.name}. {svc.landing_page_note or ''}".strip()
            self._comment_cache[post.content_hash] = default_text
            return default_text

        ai = self._ensure_ai()
        try:
            comment = await ai.generate_comment(
                post.content_text,
                asdict(self.config.service),  # ServiceInfo là dataclass, AI Engine cần dict
                (ai_result or {}).get("extracted") or {},
            )
        except Exception as e:
            logger.error(f"Sinh comment thất bại: {e}")
            return ""

        comment = (comment or "").strip()
        if not comment:
            logger.error("AI trả về comment rỗng — bỏ qua bài này")
            return ""

        self._comment_cache[post.content_hash] = comment
        return comment

    async def _enqueue_shot(self, post: DiscoveredPost, comment: str) -> None:
        """Đưa 1 lượt comment vào hàng đợi Shooter."""
        used = self.db.get_today_action_count()
        limit = self.config.comment.max_comments_per_day
        if used >= limit:
            logger.warning(
                f"Đã dùng hết quota hôm nay ({used}/{limit}) — không xếp hàng thêm"
            )
            await self.tg.send_text(
                f"Đã đạt trần {limit} comment/ngày. Tạm dừng tới ngày mai."
            )
            return

        await self._shoot_queue.put((post, comment))
        logger.info(
            f"Đã xếp hàng comment (hàng đợi: {self._shoot_queue.qsize()}) — {post.post_url}"
        )

    async def _shooter_consumer(self) -> None:
        """Consumer DUY NHẤT của hàng đợi: đảm bảo mỗi lần chỉ 1 comment chạy."""
        logger.info("Shooter consumer sẵn sàng")
        while True:
            post, comment = await self._shoot_queue.get()
            try:
                failures = self.db.get_consecutive_failures()
                if failures >= CIRCUIT_BREAKER_FAILURES:
                    if not self._breaker_tripped:
                        self._breaker_tripped = True
                        logger.error(
                            f"Circuit Breaker kích hoạt! Đã thất bại {failures} lượt liên tiếp. "
                            "Tạm dừng toàn bộ hàng đợi comment để bảo vệ tài khoản. "
                            "Khởi động lại sau khi xử lý tài khoản."
                        )
                        await self.tg.send_text(
                            f"<b>CIRCUIT BREAKER KÍCH HOẠT</b>\n\n"
                            f"Đã thất bại {failures} lượt comment liên tiếp.\n"
                            f"Hàng đợi Shooter tự động dừng để bảo vệ tài khoản.\n"
                            f"Vui lòng kiểm tra tài khoản shooter trên Facebook rồi khởi động lại hệ thống."
                        )
                    logger.warning(f"Circuit Breaker đang ngắt — huỷ lượt comment: {post.post_url}")
                    continue

                used = self.db.get_today_action_count()
                limit = self.config.comment.max_comments_per_day
                if used >= limit:
                    logger.warning(f"Quota hết ({used}/{limit}) — huỷ lượt trong hàng đợi")
                    continue

                status = await self.shooter.schedule_comment(post, comment, self.db)
                success = status == CommentStatus.SUCCESS
                await self.tg.send_result_notification(
                    post,
                    success=success,
                    comment_text=comment,
                    error="" if success else str(getattr(status, "value", status)),
                )
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.exception(f"Shooter consumer lỗi: {e}")
            finally:
                self._shoot_queue.task_done()

    async def _daily_report_loop(self) -> None:
        """Định kỳ gửi báo cáo trạng thái về Telegram."""
        while True:
            await asyncio.sleep(DAILY_REPORT_INTERVAL_SEC)
            try:
                await self.tg.send_status_report(self.db.get_stats())
            except Exception as e:
                logger.error(f"Gửi báo cáo định kỳ thất bại: {e}")

    # ── Callback từ Inline Keyboard Telegram ────────────────────────────
    async def on_apply(self, post_hash: str) -> None:
        post = self.db.get_post_by_hash(post_hash)
        if post is None:
            logger.warning(f"Không tìm thấy bài với hash {post_hash[:8]}")
            await self.tg.send_text("Không tìm thấy bài viết này trong database.")
            return
        comment = await self._make_comment(post, self._ai_cache.get(post_hash, {}))
        if comment:
            await self._enqueue_shot(post, comment)

    async def on_skip(self, post_hash: str) -> None:
        post = self.db.get_post_by_hash(post_hash)
        if post is None:
            return
        self.db.mark_skipped(post, "user_skipped")
        logger.info(f"Người dùng bỏ qua bài {post_hash[:8]}")

    async def on_preview(self, post_hash: str) -> None:
        post = self.db.get_post_by_hash(post_hash)
        if post is None:
            await self.tg.send_text("Không tìm thấy bài viết này trong database.")
            return
        comment = await self._make_comment(post, self._ai_cache.get(post_hash, {}))
        if comment:
            await self.tg.send_text(f"Bản nháp comment:\n\n{comment}")
        else:
            await self.tg.send_text("Không sinh được comment. Xem log để biết chi tiết.")

    # ── Vòng đời ────────────────────────────────────────────────────────
    async def run(self) -> None:
        mode = self.config.comment.mode
        available, desc = stealth_status()

        logger.info("=" * 62)
        logger.info("CommHunter AI — khởi động")
        logger.info(f"   Chế độ      : {mode}")
        logger.info(f"   Số group    : {len(self.config.groups)}")
        logger.info(f"   Quota/ngày  : {self.config.comment.max_comments_per_day}")
        logger.info(f"   Stealth     : {desc}")
        logger.info("=" * 62)

        if not available:
            logger.warning(
                "Browser sẽ chạy KHÔNG có stealth. Rủi ro bị Facebook phát hiện cao. "
                "Chạy `pip install -r requirements.txt` rồi kiểm tra lại bằng lệnh `status`."
            )

        self._ensure_ai()

        if mode == "semi_auto":
            await self.tg.start_polling(
                on_apply=self.on_apply,
                on_skip=self.on_skip,
                on_preview=self.on_preview,
            )
            await self.tg.send_text("CommHunter đã khởi động và đang giám sát group.")

        self._tasks = [
            asyncio.create_task(self._shooter_consumer(), name="shooter"),
            asyncio.create_task(self._daily_report_loop(), name="report"),
            asyncio.create_task(
                self.scout.run_scout_loop(self.db, callback=self.process_new_posts),
                name="scout",
            ),
        ]
        await asyncio.gather(*self._tasks)

    async def shutdown(self) -> None:
        """Dọn dẹp: huỷ task, dừng bot, đóng browser, đóng DB."""
        if self._stopping:
            return
        self._stopping = True
        logger.info("Đang dừng...")

        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

        try:
            await self.tg.close()
        except Exception as e:
            logger.debug(f"close tg: {e}")

        try:
            await self.browser_mgr.close_all()
        except Exception as e:
            logger.error(f"Đóng browser thất bại: {e}")

        try:
            self.db.close()
        except Exception as e:
            logger.debug(f"Đóng DB: {e}")

        logger.info("Đã dừng sạch.")


# ═══════════════════════════════════════════════════════════════════════════
# Các lệnh CLI
# ═══════════════════════════════════════════════════════════════════════════
async def cmd_run(config: AppConfig) -> int:
    problems = find_config_problems(config)
    if problems:
        logger.error("Cấu hình chưa hợp lệ, không thể chạy:")
        for item in problems:
            logger.error(f"   • {item}")
        logger.error("   Chạy `python commhunter.py status --config ...` để xem chi tiết.")
        return 1

    app = CommHunterApp(config)
    stop_event = asyncio.Event()

    loop = asyncio.get_running_loop()
    for sig_name in ("SIGINT", "SIGTERM"):
        sig = getattr(signal, sig_name, None)
        if sig is None:
            continue
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except (NotImplementedError, RuntimeError):
            # Windows không hỗ trợ add_signal_handler -> dựa vào KeyboardInterrupt
            pass

    run_task = asyncio.create_task(app.run(), name="app")
    stop_task = asyncio.create_task(stop_event.wait(), name="stop")

    exit_code = 0
    try:
        done, _pending = await asyncio.wait(
            {run_task, stop_task}, return_when=asyncio.FIRST_COMPLETED
        )
        if run_task in done:
            exc = run_task.exception()
            if exc is not None:
                logger.exception(f"Vòng chạy chính lỗi: {exc}")
                exit_code = 1
    except KeyboardInterrupt:
        logger.info("Nhận Ctrl+C")
    finally:
        stop_task.cancel()
        run_task.cancel()
        await asyncio.gather(run_task, stop_task, return_exceptions=True)
        await app.shutdown()

    return exit_code


async def cmd_login(config: AppConfig, profile: str) -> int:
    account = config.accounts.get(profile)
    if account is None:
        logger.error(f"Không có `accounts.{profile}` trong file cấu hình")
        return 1

    browser_mgr = BrowserManager(config)
    try:
        logger.info(f"Mở browser để đăng nhập tài khoản '{profile}'")
        logger.info(f"   Profile: {account.profile_dir}")
        ok = await browser_mgr.login_interactive(account.profile_dir, account.proxy)
        if ok:
            logger.info(f"Đã lưu session cho '{profile}'")
            return 0
        logger.error(f"Chưa đăng nhập được cho '{profile}' — thử lại")
        return 1
    finally:
        await browser_mgr.close_all()


async def cmd_status(config: AppConfig, config_path: Path, skip_session: bool) -> int:
    lines = []
    healthy = True

    lines.append("=" * 62)
    lines.append("COMMHUNTER — KIỂM TRA TRẠNG THÁI")
    lines.append("=" * 62)
    lines.append(f"Cấu hình : {config_path}")
    lines.append(f"Chế độ   : {config.comment.mode}")
    lines.append(f"Group    : {len(config.groups)}")
    lines.append("")

    # ── Thư viện ────────────────────────────────────────────────────────
    lines.append("── Thư viện ──")
    for module, label in (
        ("playwright", "playwright"),
        ("openai", "openai"),
        ("telegram", "python-telegram-bot"),
        ("yaml", "pyyaml"),
        ("dotenv", "python-dotenv"),
    ):
        try:
            __import__(module)
            lines.append(f"  [OK] {label}")
        except ImportError:
            lines.append(f"  [LỖI] {label} — CHƯA CÀI (pip install -r requirements.txt)")
            healthy = False

    available, desc = stealth_status()
    if available:
        lines.append(f"  [OK] stealth: {desc}")
    else:
        lines.append(f"  [CẢNH BÁO] stealth: {desc}")
        lines.append("      → Browser sẽ chạy TRẦN. Rủi ro bị phát hiện CAO.")
        healthy = False
    lines.append("")

    # ── Trình duyệt ─────────────────────────────────────────────────────
    lines.append("── Trình duyệt ──")
    br = config.browser
    lines.append(f"  Channel : {br.channel}   Headless: {br.headless}")
    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as _pw:
            try:
                _b = await _pw.chromium.launch(channel=br.channel, headless=True)
                lines.append(f"  [OK] channel '{br.channel}' mở được — {_b.version}")
                await _b.close()
            except Exception as e:
                lines.append(
                    f"  [CẢNH BÁO] channel '{br.channel}' KHÔNG mở được ({str(e)[:60]}…) "
                    f"→ sẽ rơi về Chromium bundled"
                )
    except Exception as e:
        lines.append(f"  [CẢNH BÁO] không kiểm tra được channel: {str(e)[:60]}")
    for role in ("scout", "shooter"):
        acc = config.accounts.get(role)
        if acc is None:
            continue
        cdp = _account_cdp(acc) or (br.attach_cdp or "")
        if cdp:
            lines.append(f"  {role}: ATTACH → {cdp} (không spoof vân tay)")
        else:
            try:
                from fingerprint import read_fingerprint, describe_fingerprint

                fp = read_fingerprint(acc.profile_dir) if acc.profile_dir else None
                if fp:
                    lines.append(f"  {role}: vân tay {describe_fingerprint(fp)}")
                else:
                    lines.append(f"  {role}: vân tay sẽ sinh khi login lần đầu")
            except Exception as e:
                lines.append(f"  {role}: lỗi đọc vân tay: {str(e)[:50]}")
    lines.append("")

    # ── Cấu hình ────────────────────────────────────────────────────────
    lines.append("── Cấu hình ──")
    problems = find_config_problems(config)
    if problems:
        healthy = False
        for item in problems:
            lines.append(f"  [LỖI] {item}")
    else:
        lines.append("  [OK] Không phát hiện lỗi nghiêm trọng")
    lines.append("")

    # ── Database ────────────────────────────────────────────────────────
    lines.append("── Database ──")
    try:
        db = DedupStore(config.database.path)
        stats = db.get_stats()
        db.close()
        lines.append(f"  [OK] {config.database.path}")
        lines.append(
            f"     Bài mới: {stats.get('new', 0)} | Đã báo: {stats.get('notified', 0)} "
            f"| Đã comment: {stats.get('commented', 0)} | Bỏ qua: {stats.get('skipped', 0)}"
        )
        lines.append(
            f"     Hôm nay — quét: {stats.get('today_scanned', 0)} "
            f"| phù hợp: {stats.get('today_matched', 0)}"
        )
        lines.append(
            f"     Lượt hôm nay: {stats.get('today_actions', 0)}/{config.comment.max_comments_per_day} "
            f"| Thành công: {stats.get('today_comments', 0)} "
            f"| Thất bại liên tiếp: {stats.get('consecutive_failures', 0)}"
        )
    except Exception as e:
        lines.append(f"  [LỖI] Không mở được DB: {e}")
        healthy = False
    lines.append("")

    # ── Session Facebook ────────────────────────────────────────────────
    lines.append("── Session Facebook ──")
    if skip_session:
        lines.append("  [BỎ QUA] kiểm tra session (--skip-session)")
    else:
        browser_mgr = BrowserManager(config)
        try:
            for role in ("scout", "shooter"):
                account = config.accounts.get(role)
                if account is None:
                    lines.append(f"  [LỖI] {role}: chưa cấu hình")
                    healthy = False
                    continue
                cdp = _account_cdp(account) or (config.browser.attach_cdp or "")
                if not cdp and not Path(account.profile_dir).exists():
                    lines.append(
                        f"  [CẢNH BÁO] {role}: chưa đăng nhập lần nào "
                        f"→ python commhunter.py login --profile {role} --config ..."
                    )
                    healthy = False
                    continue
                alive = await browser_mgr.check_session(
                    account.profile_dir, cdp_endpoint=cdp or None
                )
                if alive:
                    lines.append(f"  [OK] {role}: session còn sống")
                else:
                    lines.append(
                        f"  [LỖI] {role}: session hỏng/checkpoint "
                        f"→ python commhunter.py login --profile {role} --config ..."
                    )
                    healthy = False
        finally:
            await browser_mgr.close_all()

    lines.append("")
    lines.append("=" * 62)
    lines.append("[OK] SẴN SÀNG CHẠY" if healthy else "[LỖI] CHƯA SẴN SÀNG — xử lý các mục [LỖI] ở trên")
    lines.append("=" * 62)

    print("\n".join(lines))
    return 0 if healthy else 1


# ═══════════════════════════════════════════════════════════════════════════
# Phân tích tham số & main
# ═══════════════════════════════════════════════════════════════════════════
COMMANDS = ("run", "login", "status")


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", "-c", required=True, help="Đường dẫn file YAML cấu hình")
    common.add_argument("--verbose", "-v", action="store_true", help="Bật log DEBUG")

    parser = argparse.ArgumentParser(
        prog="commhunter.py",
        description="CommHunter AI — Săn khách hàng tiềm năng trong group Facebook",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Ví dụ:\n"
            "  python commhunter.py status --config configs/khach.yaml\n"
            "  python commhunter.py login  --config configs/khach.yaml --profile scout\n"
            "  python commhunter.py run    --config configs/khach.yaml\n"
        ),
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("run", parents=[common], help="Chạy vòng lặp giám sát chính")

    login = sub.add_parser("login", parents=[common], help="Đăng nhập Facebook thủ công 1 lần")
    login.add_argument(
        "--profile", "-p", required=True, choices=["scout", "shooter"],
        help="Tài khoản cần đăng nhập",
    )

    status = sub.add_parser("status", parents=[common], help="Kiểm tra tình trạng hệ thống")
    status.add_argument(
        "--skip-session", action="store_true",
        help="Bỏ qua bước mở browser kiểm tra session (nhanh hơn)",
    )

    return parser


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    # Cho phép `python commhunter.py --config x.yaml` (mặc định lệnh `run`)
    if not argv or argv[0].startswith("-"):
        if not any(a in ("-h", "--help") for a in argv):
            argv.insert(0, "run")
    elif argv[0] not in COMMANDS:
        argv.insert(0, "run")

    args = build_parser().parse_args(argv)
    if not getattr(args, "command", None):
        build_parser().print_help()
        return 1

    setup_logging(verbose=getattr(args, "verbose", False))
    load_env()

    config_path = Path(args.config).expanduser().resolve()
    if not config_path.exists():
        logger.error(f"Không tìm thấy file cấu hình: {config_path}")
        return 1

    # Đường dẫn trong file YAML (data/..., configs/...) là tương đối so với
    # thư mục commhunter/. chdir để chúng luôn trỏ đúng chỗ dù chạy từ đâu.
    os.chdir(_SCRIPT_DIR)

    try:
        config = load_config(str(config_path))
    except Exception as e:
        logger.error(f"Không đọc được cấu hình: {e}")
        return 1

    try:
        if args.command == "login":
            return asyncio.run(cmd_login(config, args.profile))
        if args.command == "status":
            return asyncio.run(cmd_status(config, config_path, args.skip_session))
        return asyncio.run(cmd_run(config))
    except KeyboardInterrupt:
        logger.info("Đã dừng theo yêu cầu (Ctrl+C)")
        return 0


if __name__ == "__main__":
    sys.exit(main())
