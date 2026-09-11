# -*- coding: utf-8 -*-
"""
Smoke test cho pipeline CommHunter — KHÔNG cần Playwright / OpenAI / Telegram.

Chạy:
    python tests/test_pipeline.py

Bộ test này dùng AI Engine và Telegram Bot giả lập, nên chạy được offline,
không tốn tiền API, và không đụng tới Facebook. Nó kiểm tra phần logic thuần
mà lỗi ở đó sẽ âm thầm làm hỏng sản phẩm:
  - biến môi trường trong YAML có resolve đúng không
  - find_config_problems có bắt được cấu hình hỏng không
  - keyword_match có khớp tiếng Việt KHÔNG DẤU không
  - dedup có thật sự chặn bài trùng không
  - đúng thứ tự pipeline (chặn từ khóa TRƯỚC khi gọi AI = tiết kiệm tiền)
  - callback Telegram Preview/Apply/Skip
  - rate limit có chặn xếp hàng không
"""
import asyncio, os, sys, tempfile
from pathlib import Path

ROOT = Path(r"F:\Clone\fb-tool\commhunter")
sys.path.insert(0, str(ROOT))
os.environ.update(
    OPENAI_API_KEY="sk-test-fake-key-for-smoke",
    TELEGRAM_BOT_TOKEN="123456789:AAFakeTokenForSmokeTest",
    TELEGRAM_CHAT_ID="987654321",
)
os.chdir(ROOT)

import commhunter as ch
from models import DiscoveredPost, PostStatus, CommentStatus
from dedup_store import DedupStore, compute_content_hash

ok = fail = 0
def check(label, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1; print(f"  PASS  {label}")
    else:
        fail += 1; print(f"  FAIL  {label} {extra}")

print("\n=== 1. Config resolve bien moi truong ===")
cfg = ch.load_config(str(ROOT / "configs" / "example.yaml"))
problems = ch.find_config_problems(cfg)
check("config sach khi da co env", problems == [], problems)
check("api_key da resolve", cfg.openai.api_key == "sk-test-fake-key-for-smoke")

print("\n=== 2. find_config_problems bat duoc loi ===")
cfg.accounts["shooter"].profile_dir = cfg.accounts["scout"].profile_dir
check("bat scout/shooter trung profile_dir",
      any("CHUNG profile_dir" in p for p in ch.find_config_problems(cfg)))
cfg.accounts["shooter"].profile_dir = "data/browser_profiles/shooter"
cfg.comment.mode = "sai_be_bet"
check("bat mode khong hop le", any("comment.mode" in p for p in ch.find_config_problems(cfg)))
cfg.comment.mode = "semi_auto"

print("\n=== 3. keyword_match ===")
flt = cfg.filter
check("blacklist chan", ch.keyword_match("Bai nay da tim duoc nguoi roi nhe", flt)[0] is False)
check("khong co whitelist -> loai", ch.keyword_match("Hom nay troi dep qua", flt)[0] is False)
check("co whitelist -> qua", ch.keyword_match("Minh dang tim comm viet truyen, budget 500k", flt)[0] is True)
check("hoa thuong khong anh huong", ch.keyword_match("CẦN VIẾT gap", flt)[0] is True)
check("KHONG DAU van khop whitelist", ch.keyword_match("Minh can viet truyen gap qua", flt)[0] is True)
check("KHONG DAU van khop blacklist", ch.keyword_match("can viet nhung da tim duoc roi", flt)[1].startswith("blacklist:"))
check("blacklist neu ly do", ch.keyword_match("đã tìm được", flt)[1].startswith("blacklist:"))

print("\n=== 4. DedupStore + get_post_by_hash (ham moi them) ===")
tmpdb = Path(tempfile.mkdtemp()) / "t.db"
db = DedupStore(str(tmpdb))
h = compute_content_hash("Nguyen Van A", "Minh dang tim comm viet truyen ngon tinh, budget 500k")
post = DiscoveredPost(
    post_id="123", post_url="https://facebook.com/groups/1/posts/123/",
    group_url="https://facebook.com/groups/1", group_name="Nhom Test",
    author_name="Nguyen Van A",
    content_text="Minh dang tim comm viet truyen ngon tinh, budget 500k",
    existing_comment_count=2, content_hash=h,
)
check("insert lan dau OK", db.insert_post(post) is True)
check("insert lan hai bi tu choi (dedup)", db.insert_post(post) is False)
check("is_seen dung", db.is_seen(h) is True)
back = db.get_post_by_hash(h)
check("get_post_by_hash tra ve object", back is not None)
check("  ...dung author", back and back.author_name == "Nguyen Van A")
check("  ...dung url", back and back.post_url == post.post_url)
check("  ...dung status enum", back and back.status is PostStatus.NEW)
check("  ...dung comment count", back and back.existing_comment_count == 2)
check("hash khong ton tai -> None", db.get_post_by_hash("deadbeef" * 4) is None)

print("\n=== 5. Pipeline process_new_posts (AI + Telegram gia lap) ===")
class FakeAI:
    def __init__(self): self.filter_calls = 0; self.gen_calls = 0
    async def filter_post(self, content, prompt, whitelist=None, blacklist=None):
        self.filter_calls += 1
        score = 0.9 if "budget" in content.lower() else 0.2
        return {"relevance_score": score, "reason": "test", "extracted": {"budget": "500k"}}
    async def generate_comment(self, content, service, extracted=None):
        self.gen_calls += 1
        assert isinstance(service, dict), "service phai la dict (asdict cua ServiceInfo)"
        return "Chao ban, minh nhan viet the loai nay nhe."

class FakeTG:
    def __init__(self): self.notifs = []; self.texts = []
    async def send_post_notification(self, post, ai_result):
        self.notifs.append(post); return 111
    async def send_text(self, text, markdown=False): self.texts.append(text); return True
    async def send_result_notification(self, *a, **k): pass
    async def send_status_report(self, stats): pass

cfg.database.path = str(tmpdb)
app = ch.CommHunterApp(cfg)
app.ai = FakeAI(); app.tg = FakeTG()

def mk(author, text, comments=0):
    return DiscoveredPost(
        post_id="x", post_url="https://facebook.com/p/1/", group_url="g", group_name="G",
        author_name=author, content_text=text, existing_comment_count=comments,
        content_hash=compute_content_hash(author, text),
    )

posts = [
    mk("A", "Minh can viet truyen ngon tinh, budget 500k"),          # qua het
    mk("B", "Hom nay troi dep qua di thoi"),                          # rot whitelist
    mk("C", "Can viet gap nhung da tim duoc nguoi roi"),              # rot blacklist
    mk("D", "Can viet bai, khong noi gia"),                           # AI cham diem thap
    mk("E", "Nhan order viet truyen budget 1 trieu", comments=50),    # qua dong
]
for p in posts: db.insert_post(p)
asyncio.run(app.process_new_posts(posts))

check("chi 1 bai duoc thong bao", len(app.tg.notifs) == 1, [p.author_name for p in app.tg.notifs])
check("  ...dung la bai A", app.tg.notifs and app.tg.notifs[0].author_name == "A")
check("AI chi duoc goi 3 lan (B,C bi chan truoc khi ton tien)", app.ai.filter_calls == 3,
      f"thuc te={app.ai.filter_calls}")
check("bai A -> status notified", db.get_post_by_hash(posts[0].content_hash).status is PostStatus.NOTIFIED)
check("bai B -> skipped", db.get_post_by_hash(posts[1].content_hash).status is PostStatus.SKIPPED)
check("bai C -> skipped(blacklist)",
      "blacklist" in (db.get_post_by_hash(posts[2].content_hash).ai_reason or ""))
check("bai D -> skipped(low_score)",
      "low_score" in (db.get_post_by_hash(posts[3].content_hash).ai_reason or ""))
check("bai E -> skipped(too_competitive)",
      "too_competitive" in (db.get_post_by_hash(posts[4].content_hash).ai_reason or ""))

print("\n=== 6. Callback Telegram: Preview / Apply / Skip ===")
asyncio.run(app.on_preview(posts[0].content_hash))
check("preview gui ban nhap", any("ban nhap" in t.lower() or "nháp" in t.lower() for t in app.tg.texts),
      app.tg.texts)
check("preview goi generate_comment 1 lan", app.ai.gen_calls == 1)
asyncio.run(app.on_apply(posts[0].content_hash))
check("apply KHONG sinh lai comment (dung cache)", app.ai.gen_calls == 1, app.ai.gen_calls)
check("apply da xep hang shooter", app._shoot_queue.qsize() == 1)
asyncio.run(app.on_skip(posts[3].content_hash))
check("skip -> user_skipped", db.get_post_by_hash(posts[3].content_hash).ai_reason == "user_skipped")
asyncio.run(app.on_apply("0" * 32))
check("apply hash la -> canh bao, khong crash", any("Không tìm thấy" in t for t in app.tg.texts))

print("\n=== 7. Rate limit chan xep hang ===")
cfg.comment.max_comments_per_day = 0
before = app._shoot_queue.qsize()
asyncio.run(app._enqueue_shot(posts[0], "test"))
check("het quota -> khong xep hang", app._shoot_queue.qsize() == before)
check("het quota -> co canh bao Telegram", any("trần" in t or "tran" in t for t in app.tg.texts))

print("\n=== 8. Warmup safety (N-01) ===")
from human_emulator import is_safe_hover_target
check("chan /logout", not is_safe_hover_target("https://facebook.com/logout", "", ""))
check("chan /leave", not is_safe_hover_target("https://facebook.com/groups/123/leave", "", ""))
check("chan /report", not is_safe_hover_target("https://facebook.com/report/story", "", ""))
check("chan aria Roi khoi nhom", not is_safe_hover_target("https://fb.com", "Rời khỏi nhóm", ""))
check("chan aria Bao cao bai viet", not is_safe_hover_target("https://fb.com", "Báo cáo bài viết", ""))
check("chan label khong dau roi nhom", not is_safe_hover_target("https://fb.com", "roi nhom", ""))
check("chan nut Thich", not is_safe_hover_target("https://fb.com", "Thích", ""))
check("chan nut Like khong dau", not is_safe_hover_target("https://fb.com", "like", ""))
check("cho qua link bai viet hop le", is_safe_hover_target("https://facebook.com/groups/123/posts/456", "Xem bài viết của A", "2 giờ trước"))

print("\n=== 9. Verify 3 chieu & Pick Verify Phrase (N-02 + N-03) ===")
import shooter_worker as shooter_mod
from shooter_worker import _pick_verify_phrase, ShooterWorker

check("pick phrase comment ngan", _pick_verify_phrase("Minh can viet gap") == "Minh can viet gap")
check("pick phrase 1 tu", _pick_verify_phrase("Hello") == "Hello")
long_cmt = "Chào bạn, bên mình chuyên nhận viết content chuẩn SEO và sáng tạo truyện chữ theo yêu cầu của bạn nha"
phrase = _pick_verify_phrase(long_cmt)
check("pick phrase comment dai khong chua 3 tu dau", not phrase.startswith("Chào bạn, bên"))
check("pick phrase comment dai nam trong comment goc", phrase in long_cmt)

class FakeElementHandle:
    def __init__(self, text="", detached=False):
        self._text = text
        self._detached = detached

    async def inner_text(self):
        if self._detached:
            raise RuntimeError("Detached")
        return self._text

    async def text_content(self):
        if self._detached:
            raise RuntimeError("Detached")
        return self._text

class FakePage:
    def __init__(self, outside_texts=None):
        self.outside_texts = outside_texts or []

    async def wait_for_timeout(self, ms):
        pass

    async def evaluate(self, script, args=None):
        if not args or len(args) < 2:
            return False
        composer, search_phrase = args[0], args[1]
        target = " ".join((search_phrase or "").split()).lower()
        if not target:
            return False
        for text in self.outside_texts:
            clean_text = " ".join((text or "").split()).lower()
            if target in clean_text:
                return True
        return False

class BrokenPage:
    async def wait_for_timeout(self, ms):
        raise RuntimeError("Browser crashed")
    async def evaluate(self, s, a=None):
        raise RuntimeError("Browser crashed")

shooter_test = ShooterWorker(app.browser_mgr, cfg)

# Case 1: Ô nhập còn text -> FAILED (enter_did_not_submit) - HỒI QUY N-02
box_not_empty = FakeElementHandle("Con text chua gui")
page_with_text = FakePage(outside_texts=[phrase])
status1 = asyncio.run(shooter_test._verify_comment(page_with_text, box_not_empty, long_cmt))
check("O nhap con text -> FAILED (hoi quy N-02)", status1 == CommentStatus.FAILED)

# Case 2: Ô nhập trống + có text ngoài ô nhập -> SUCCESS
box_empty = FakeElementHandle("")
status2 = asyncio.run(shooter_test._verify_comment(page_with_text, box_empty, long_cmt))
check("O nhap trong + text ngoai -> SUCCESS", status2 == CommentStatus.SUCCESS)

# Case 3: Ô nhập trống + KHÔNG có text ngoài ô nhập -> SHADOWBANNED
page_no_text = FakePage(outside_texts=["Khong co gi"])
status3 = asyncio.run(shooter_test._verify_comment(page_no_text, box_empty, long_cmt))
check("O nhap trong + khong co text ngoai -> SHADOWBANNED", status3 == CommentStatus.SHADOWBANNED)

# Case 4: Lỗi ngoại lệ trong verify -> FAILED (hồi quy N-03)
status4 = asyncio.run(shooter_test._verify_comment(BrokenPage(), box_empty, long_cmt))
check("Loi ngoai le -> FAILED (hoi quy N-03, khong con assume success)", status4 == CommentStatus.FAILED)

# ── HỒI QUY publish_post: permalink + xác nhận bài lên (soi DOM thật 2026-09-10) ──
# Bug: FB đời mới giấu permalink khỏi href -> _find_published_permalink phải
# click mốc thời gian rồi đọc URL; _clean_permalink rút URL sạch khỏi tracking.
_cp = ShooterWorker._clean_permalink
check(
    "clean_permalink: /groups/<id>/posts/<id> + tracking -> URL sach",
    _cp(
        "https://www.facebook.com/groups/1042987808508567/posts/1042994141841267"
        "?__cft__[0]=AbCdEf#?cbb"
    )
    == "https://www.facebook.com/groups/1042987808508567/posts/1042994141841267/",
)
check(
    "clean_permalink: URL da sach -> giu nguyen (chuan hoa dau '/')",
    _cp("https://www.facebook.com/groups/123/posts/456/")
    == "https://www.facebook.com/groups/123/posts/456/",
)
check(
    "clean_permalink: URL feed nhom (khong co /posts/) -> None",
    _cp("https://www.facebook.com/groups/1042987808508567?__cft__[0]=x#?ifb") is None,
)
check("clean_permalink: chuoi rong -> None", _cp("") is None)

# Bug: _post_submitted_ok đếm mọi [role=dialog] -> luôn FAILED giả vì FB giữ
# sẵn dialog thông báo. Giờ chỉ soi ô soạn bài.
class _FakeSubmitPage:
    def __init__(self, body="", composer_visible=False):
        self._body = body
        self._composer_visible = composer_visible

    async def text_content(self, _sel):
        return self._body

    async def wait_for_timeout(self, _ms):
        return None

    async def query_selector(self, _sel):
        if not self._composer_visible:
            return None
        class _El:
            async def is_visible(_self):
                return True
        return _El()

check(
    "_post_submitted_ok: composer da dong -> True (khong con FAILED gia)",
    asyncio.run(shooter_test._post_submitted_ok(_FakeSubmitPage(body="abc"))) is True,
)
# Ngưỡng poll = 0 để test không phải chờ thật; nhánh logic vẫn nguyên vẹn.
_orig_confirm_ms = shooter_mod.POST_SUBMIT_CONFIRM_TIMEOUT_MS
shooter_mod.POST_SUBMIT_CONFIRM_TIMEOUT_MS = 0
check(
    "_post_submitted_ok: composer con mo -> False",
    asyncio.run(
        shooter_test._post_submitted_ok(_FakeSubmitPage(composer_visible=True))
    )
    is False,
)
shooter_mod.POST_SUBMIT_CONFIRM_TIMEOUT_MS = _orig_confirm_ms
check(
    "_post_submitted_ok: co cum tu thanh cong -> True du composer con mo",
    asyncio.run(
        shooter_test._post_submitted_ok(
            _FakeSubmitPage(body="Bài viết của bạn đã được đăng", composer_visible=True)
        )
    )
    is True,
)

# ── HỒI QUY delete_own_post: rollback/cleanup bài mình đã đăng ──────────────
# DOM thật 2026-09-10: nut menu "Hanh dong doi voi bai viet nay cua <nick>"
# -> menu item "Xoa bai viet" -> dialog xac nhan -> nut "Xoa" (khop tuyet doi).
class _DelBtn:
    def __init__(self, page, label):
        self._page = page
        self._label = label
    async def inner_text(self):
        return self._label
    async def _do(self):
        # Chỉ nút xác nhận thật mới xoá bài; bấm "Hủy" thì không.
        if self._label in ("Xóa", "Xoá", "Chuyển"):
            self._page.deleted = True
    async def click(self):
        await self._do()
    async def evaluate(self, _js):
        await self._do()

class _DelMenuItem:
    def __init__(self, label):
        self._label = label
    async def inner_text(self):
        return self._label
    async def click(self):
        pass
    async def evaluate(self, _js):
        pass

class _DelMenu:
    async def query_selector_all(self, _sel):
        return [_DelMenuItem("Chỉnh sửa bài viết"), _DelMenuItem("Xóa bài viết")]

class _DelDialog:
    def __init__(self, page):
        self._page = page
    async def inner_text(self):
        return "Xóa bài viết vĩnh viễn?\nBạn có chắc chắn muốn xóa bài viết này không?"
    async def query_selector_all(self, _sel):
        return [_DelBtn(self._page, "Hủy"), _DelBtn(self._page, "Xóa")]

class _DelMenuBtn:
    async def evaluate(self, _js):
        pass

class _FakeDeletePostPage:
    def __init__(self, has_menu=True, has_dialog=True):
        self._has_menu = has_menu
        self._has_dialog = has_dialog
        self.deleted = False
        self.url = ""
    async def goto(self, url, **k):
        self.url = url
    async def wait_for_timeout(self, ms):
        pass
    async def text_content(self, _sel):
        return "Nội dung không khả dụng" if self.deleted else "Bài viết vẫn bình thường ở đây"
    async def query_selector(self, sel):
        if 'aria-haspopup="menu"' in sel:
            return _DelMenuBtn() if self._has_menu else None
        if 'role="menu"' in sel:
            return _DelMenu()
        return None
    async def query_selector_all(self, sel):
        if 'role="dialog"' in sel and self._has_dialog:
            return [_DelDialog(self)]
        return []

_ok_page = _FakeDeletePostPage()
check(
    "delete_own_post: menu -> item Xoa -> dialog -> nut Xoa -> True",
    asyncio.run(shooter_test.delete_own_post(_ok_page, "https://facebook.com/groups/1/posts/9/")) is True,
)
check(
    "delete_own_post: khong thay nut menu -> False (fail an toan)",
    asyncio.run(
        shooter_test.delete_own_post(_FakeDeletePostPage(has_menu=False), "https://x/posts/1/")
    )
    is False,
)
check(
    "delete_own_post: post_url rong -> False",
    asyncio.run(shooter_test.delete_own_post(_FakeDeletePostPage(), "")) is False,
)

# HỒI QUY 2026-09-11: trang permalink FB chèn bài "được đề xuất" cùng nút
# "Hành động đối với bài viết này..." -> _open_own_post_menu phải chọn ĐÚNG nút
# có tên tài khoản đang đăng nhập, không bấm nút đầu tiên (bài người khác).
class _NamedBtn:
    def __init__(self, label, sink):
        self._label = label
        self._sink = sink
    async def evaluate(self, _js):
        self._sink.append(self._label)

class _MultiPostPage:
    def __init__(self):
        self.clicked = []
    async def query_selector(self, sel):
        if 'của Toi Ngay Ban' in sel:
            return _NamedBtn("mine", self.clicked)
        if 'của ' in sel or 'by ' in sel:
            return None
        if 'aria-haspopup="menu"' in sel:  # nút khớp CHUNG -> bài người lạ
            return _NamedBtn("stranger", self.clicked)
        return None

_mp = _MultiPostPage()
check(
    "_open_own_post_menu: co ten -> bam dung nut cua minh",
    asyncio.run(shooter_test._open_own_post_menu(_mp, "Toi Ngay Ban")) is True
    and _mp.clicked == ["mine"],
    str(_mp.clicked),
)
_mp2 = _MultiPostPage()
check(
    "_open_own_post_menu: khong xac dinh ten -> roi ve nut khop chung",
    asyncio.run(shooter_test._open_own_post_menu(_mp2, None)) is True
    and _mp2.clicked == ["stranger"],
    str(_mp2.clicked),
)

print("\n=== 10. Vong doi luot & DedupStore (N-04) ===")
test_store_dir = tempfile.mkdtemp()
test_db = DedupStore(os.path.join(test_store_dir, "test_lifecycle.db"))

att1 = test_db.record_attempt("hash1", "cmt 1")
check("record_attempt tra ve id > 0", att1 > 0)
cur_st = test_db.conn.execute("SELECT status FROM comment_actions WHERE id = ?", (att1,)).fetchone()[0]
check("status ban dau in_progress", cur_st == "in_progress")

test_db.finish_attempt(att1, CommentStatus.FAILED, "error_test")
cur_st2 = test_db.conn.execute("SELECT status, error_message FROM comment_actions WHERE id = ?", (att1,)).fetchone()
check("finish_attempt cap nhat status failed", cur_st2[0] == "failed")
check("finish_attempt cap nhat error", cur_st2[1] == "error_test")

att2 = test_db.record_attempt("hash2", "cmt 2")
test_db.finish_attempt(att2, CommentStatus.SUCCESS)

check("get_today_action_count dem ca fail + success = 2", test_db.get_today_action_count() == 2)
check("get_today_comment_count chi dem success = 1", test_db.get_today_comment_count() == 1)

post_dummy = mk("Dummy", "Dummy content for dedup test")
test_db.insert_post(post_dummy)
actions_before = test_db.conn.execute("SELECT COUNT(*) FROM comment_actions").fetchone()[0]
test_db.mark_commented(post_dummy, "cmt 2")
actions_after = test_db.conn.execute("SELECT COUNT(*) FROM comment_actions").fetchone()[0]
check("mark_commented khong tao dong dup", actions_after == actions_before)
check("mark_commented cap nhat status bai viet commented",
      test_db.get_post_by_hash(post_dummy.content_hash).status == PostStatus.COMMENTED)

check("consecutive_failures sau success = 0", test_db.get_consecutive_failures() == 0)
for i in range(3):
    aid = test_db.record_attempt(f"fail_hash_{i}", f"fail {i}")
    test_db.finish_attempt(aid, CommentStatus.FAILED, "err")
check("consecutive_failures dem dung 3 fail lien tiep", test_db.get_consecutive_failures() == 3)

print("\n=== 11. Hoi quy N-04: Quota chan khi luot that bai het ===")
cfg_regress = ch.load_config(str(ROOT / "configs" / "example.yaml"))
cfg_regress.comment.max_comments_per_day = 2
app_regress = ch.CommHunterApp(cfg_regress)
app_regress.tg = FakeTG()
app_regress.db = test_db  # test_db đang có 5 actions hôm nay (vượt trần 2)

check("comment thanh cong = 1 (< 2)", test_db.get_today_comment_count() == 1)
check("tong luot thao tac = 5 (>= 2)", test_db.get_today_action_count() >= 2)

q_before = app_regress._shoot_queue.qsize()
asyncio.run(app_regress._enqueue_shot(post_dummy, "Thu enqueue khi het quota"))
check("Hoi quy N-04: _enqueue_shot bi chan do het quota luot", app_regress._shoot_queue.qsize() == q_before)

print("\n=== 12. No ky thuat dot 2: N-05 den N-08 ===")

# --- N-05: AI Engine dynamic service info & safe fallback ---
from ai_engine import AIEngine
ai_test_cfg = ch.load_config(str(ROOT / "configs" / "example.yaml"))
ai_test_cfg.service_info = {
    "name": "Dịch vụ Thiết Kế Website Pro",
    "usp": ["Chuẩn SEO", "Tốc độ cao"],
    "cta": "Inbox để nhận demo"
}
ai_engine_inst = AIEngine(ai_test_cfg)

# 12.1 Kiểm tra fallback khi AI API gặp lỗi: trả về rỗng "", KHÔNG trả về văn bản hardcode "viết truyện"
async def fail_call(system_prompt, user_message, temperature, max_tokens, json_mode=False):
    if json_mode:
        return "{}"
    return ""

ai_engine_inst._call_ai = fail_call
fallback_res = asyncio.run(ai_engine_inst.generate_comment(post_dummy.content_text, ai_test_cfg.service_info))
check("N-05: AI Engine fallback tra ve rong khi loi", fallback_res == "")
check("N-05: Fallback khong chua hardcode viet truyen", "viết truyện" not in fallback_res)

# 12.2 Kiểm tra prompt sinh comment có chứa đúng thông tin service_info từ config
recorded_prompts = []
async def record_call(system_prompt, user_message, temperature, max_tokens, json_mode=False):
    recorded_prompts.append(system_prompt)
    return "Tuyệt vời, liên hệ chúng tôi để nhận demo nhé!"

ai_engine_inst._call_ai = record_call
comment_res = asyncio.run(ai_engine_inst.generate_comment(post_dummy.content_text, ai_test_cfg.service_info))
check("N-05: generate_comment sinh comment thanh cong", len(comment_res) > 0)
check("N-05: Prompt co chua ten dich vu tu config",
      any("Dịch vụ Thiết Kế Website Pro" in p for p in recorded_prompts))
check("N-05: Prompt khong con hardcode 'dịch vụ viết truyện'",
      not any("dịch vụ viết truyện" in p for p in recorded_prompts))

# --- N-06: Trích xuất Facebook post_id bằng Regex ---
from scout_worker import extract_post_id
check("N-06: Parse /posts/<id>/ co dau gach cheo cuoi",
      extract_post_id("https://www.facebook.com/groups/12345/posts/9876543210/") == "9876543210")
check("N-06: Parse /posts/<id> khong co dau gach cheo cuoi",
      extract_post_id("https://www.facebook.com/groups/12345/posts/9876543210") == "9876543210")
check("N-06: Parse /permalink/<id>/",
      extract_post_id("https://facebook.com/groups/12345/permalink/1122334455/") == "1122334455")
check("N-06: Parse story_fbid tu query string",
      extract_post_id("https://m.facebook.com/story.php?story_fbid=55667788&id=100") == "55667788")
check("N-06: Parse fbid tu photo URL",
      extract_post_id("https://www.facebook.com/photo.php?fbid=44332211&set=gm.123") == "44332211")
check("N-06: URL khong chua post_id tra ve chuoi rong",
      extract_post_id("https://facebook.com/groups/feed") == "")

# --- N-07: Telegram Bot singleton & close ---
from telegram_bot import TelegramBot
tg_inst = TelegramBot(cfg.telegram)
bot_a = tg_inst._get_bot()
bot_b = tg_inst._get_bot()
check("N-07: TelegramBot._get_bot() tra ve cung mot instance singleton", bot_a is bot_b)
check("N-07: TelegramBot co ham close", hasattr(tg_inst, "close"))
asyncio.run(tg_inst.close())
check("N-07: close() reset _bot ve None", tg_inst._bot is None)

# --- N-08: Telegram Bot callback security & safe split ---
class FakeChat:
    def __init__(self, cid):
        self.id = cid

class FakeQuery:
    def __init__(self, data):
        self.data = data
        self.answered = False
        self.alert_text = None
        self.message = type("FakeMsg", (), {"text": "Original text"})()
    async def answer(self, text=None, show_alert=False):
        self.answered = True
        if show_alert:
            self.alert_text = text
    async def edit_message_text(self, text):
        self.message.text = text

class FakeUpdate:
    def __init__(self, chat_id, data):
        self.effective_chat = FakeChat(chat_id)
        self.callback_query = FakeQuery(data)

tg_security = TelegramBot(cfg.telegram)  # chat_id = "987654321"

called_actions = []
async def dummy_apply(h): called_actions.append(("apply", h))
async def dummy_skip(h): called_actions.append(("skip", h))
async def dummy_preview(h): called_actions.append(("preview", h))

# Case 1: Chat ID khong khop -> Tu choi va hien alert
bad_chat_update = FakeUpdate(chat_id="111222333", data="apply:somehash123")
asyncio.run(tg_security._handle_callback(
    bad_chat_update, on_apply=dummy_apply, on_skip=dummy_skip, on_preview=dummy_preview
))
check("N-08: Chat ID khong hop le bi tu choi (khong goi on_apply)", len(called_actions) == 0)
check("N-08: Alert canh bao duoc gui ve nguoi dung unauthorized",
      bad_chat_update.callback_query.alert_text is not None)

# Case 2: Chat ID hop le nhung callback data thieu dau : (malformed) -> Khong crash, khong chay action
malformed_update = FakeUpdate(chat_id="987654321", data="invalid_no_colon_here")
asyncio.run(tg_security._handle_callback(
    malformed_update, on_apply=dummy_apply, on_skip=dummy_skip, on_preview=dummy_preview
))
check("N-08: Malformed callback data khong gay crash", len(called_actions) == 0)

# Case 3: Callback data hop le tu dung chat_id -> on_apply duoc goi thanh cong
valid_update = FakeUpdate(chat_id="987654321", data="apply:hash_pass_999")
asyncio.run(tg_security._handle_callback(
    valid_update, on_apply=dummy_apply, on_skip=dummy_skip, on_preview=dummy_preview
))
check("N-08: Callback hop le kich hoat dung action apply voi post_hash",
      len(called_actions) == 1 and called_actions[0] == ("apply", "hash_pass_999"))

# ==============================================================================
# 13. Nợ kỹ thuật đợt 3: N-09 đến N-14, NOTICE & nyatymita.yaml
# ==============================================================================
print("\n=== 13. No ky thuat dot 3: N-09 den N-14, NOTICE & nyatymita.yaml ===")

# --- N-09: human_type bao ton xuong dong voi Shift+Enter ---
from human_emulator import human_type

class FakeKeyboard:
    def __init__(self):
        self.typed_chars = []
        self.pressed_keys = []
        self.shift_down = False
        self.shift_enter_count = 0

    async def type(self, text, delay=0):
        self.typed_chars.append(text)

    async def press(self, key):
        self.pressed_keys.append(key)
        if key == "Enter" and self.shift_down:
            self.shift_enter_count += 1

    async def down(self, key):
        if key == "Shift":
            self.shift_down = True

    async def up(self, key):
        if key == "Shift":
            self.shift_down = False

class FakeTypePage:
    def __init__(self):
        self.keyboard = FakeKeyboard()

fake_page = FakeTypePage()
multiline_comment = "Đoạn 1: Xin chào bạn!\n\nĐoạn 2: Mình chuyên viết thể loại này.\nĐoạn 3: Ghé tường nhà xem portfolio nhé!"
asyncio.run(human_type(fake_page, multiline_comment, config={
    "typo_probability": 0,
    "fake_word_probability": 0,
    "cursor_jiggle_probability": 0,
}))

# multiline_comment có 3 ký tự \n (4 dòng kể cả dòng trống) -> 3 lần bấm Shift+Enter
check("N-09: human_type bam dung 3 lan Shift+Enter cho 3 dau xuong dong", fake_page.keyboard.shift_enter_count == 3)
full_typed = "".join(fake_page.keyboard.typed_chars)
check("N-09: Tu trong doan 1 duoc go", "chào" in full_typed or "Xin" in full_typed)
check("N-09: Tu trong doan 3 duoc go", "portfolio" in full_typed or "nhé!" in full_typed)

# --- N-10: Whitelist _increment_daily_stat phong ngua SQL Injection ---
try:
    test_db._increment_daily_stat("posts_scanned", 2)
    check("N-10: Cot hop le 'posts_scanned' tang gia tri thanh cong", True)
except Exception:
    check("N-10: Cot hop le 'posts_scanned' tang gia tri thanh cong", False)

threw_val_err = False
try:
    test_db._increment_daily_stat("malicious_col; DROP TABLE daily_stats; --", 1)
except ValueError:
    threw_val_err = True
except Exception:
    pass
check("N-10: Cot bat hop le bi chan bang ValueError", threw_val_err)

# --- N-11: Khong con asyncio.get_event_loop() nao trong commhunter/ ---
import glob
commhunter_py_files = [Path(p) for p in glob.glob(str(ROOT / "*.py"))]
event_loop_found = []
for p in commhunter_py_files:
    content = p.read_text(encoding="utf-8")
    if "asyncio.get_event_loop()" in content:
        event_loop_found.append(p.name)
check("N-11: Khong con asyncio.get_event_loop() trong toan bo commhunter/*.py", len(event_loop_found) == 0)

# --- N-12: Constants sync ---
from constants import (
    SCAN_DELAY_MIN_SEC,
    SCAN_DELAY_MAX_SEC,
    DEFAULT_DB_PATH,
    MAX_COMMENTS_PER_DAY as CONST_MAX_COMMENTS,
)
from models import DatabaseConfig as DBConfigCls, CommentConfig as CommConfigCls
check("N-12: SCAN_DELAY_MIN_SEC = 30 va MAX = 90", SCAN_DELAY_MIN_SEC == 30 and SCAN_DELAY_MAX_SEC == 90)
check("N-12: DatabaseConfig default path dung DEFAULT_DB_PATH", DBConfigCls().path == DEFAULT_DB_PATH)
check("N-12: CommentConfig default max_comments dung CONST_MAX_COMMENTS", CommConfigCls().max_comments_per_day == CONST_MAX_COMMENTS)

# --- N-13: DedupStore docstring luu y rang buoc don luong ---
check("N-13: DedupStore co docstring ve rang buoc don luong",
      "LƯU Ý ĐƠN LUỒNG" in (DedupStore.__doc__ or ""))

# --- N-14: Package commhunter/__init__.py ---
sys.path.insert(0, str(ROOT.parent))
import commhunter as ch_pkg
check("N-14: Import commhunter nhu mot package hop le", hasattr(ch_pkg, "__version__"))
check("N-14: Package commhunter export DedupStore", hasattr(ch_pkg, "DedupStore"))
check("N-14: Package commhunter export DiscoveredPost", hasattr(ch_pkg, "DiscoveredPost"))

# --- NOTICE file & configs/nyatymita.yaml ---
notice_file = ROOT.parent / "NOTICE"
check("Phap ly: File NOTICE ton tai o thu muc goc", notice_file.exists())
if notice_file.exists():
    notice_text = notice_file.read_text(encoding="utf-8")
    check("Phap ly: NOTICE ghi nhan ban quyen MIT viseshrp (fbn)", "viseshrp" in notice_text)
    check("Phap ly: NOTICE ghi nhan ban quyen MIT phuc-nt (openclaw)", "phuc-nt" in notice_text)

nyatymita_file = ROOT / "configs" / "nyatymita.yaml"
check("Ban giao: File configs/nyatymita.yaml ton tai", nyatymita_file.exists())
if nyatymita_file.exists():
    nyatymita_cfg = ch.load_config(str(nyatymita_file))
    check("Ban giao: nyatymita.yaml parse thanh cong ten dich vu",
          nyatymita_cfg.service.name == "Nyatymita's Writing Commission")
    check("Ban giao: nyatymita.yaml co du 2 group Facebook", len(nyatymita_cfg.groups) == 2)
    check("Ban giao: nyatymita.yaml database path dung cho khach", "nyatymita" in nyatymita_cfg.database.path)

test_db.close()
db.close()
print(f"\n{'='*50}\nKET QUA: {ok} PASS / {fail} FAIL\n{'='*50}")
sys.exit(1 if fail else 0)
