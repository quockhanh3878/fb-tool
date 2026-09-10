"""
Human Emulator — Mô phỏng hành vi người thật trên Playwright.
Port từ ai-comment-bot/main.py (Selenium) sang Playwright async.
"""
import asyncio
import random

from loguru import logger

from constants import (
    TYPING_DELAY_MIN_MS,
    TYPING_DELAY_MAX_MS,
    TYPO_PROBABILITY,
    FAKE_WORD_PROBABILITY,
    CURSOR_JIGGLE_PROBABILITY,
    WARMUP_HREF_BLOCKLIST,
    WARMUP_LABEL_BLOCKLIST,
    WARMUP_SCROLL_DOWN_BIAS,
    WARMUP_HOVER_PROBABILITY,
    normalize_vi,
)


def is_safe_hover_target(href: str = "", label: str = "", text: str = "") -> bool:
    """Kiểm tra xem link có an toàn để hover khi warmup không.
    
    Hàm thuần, không phụ thuộc browser/Playwright, phục vụ test offline.
    Chặn các URL hoặc nhãn nguy hiểm (đăng xuất, rời nhóm, báo cáo, like, share, v.v.).
    """
    href_norm = (href or "").strip().lower()
    for bad_href in WARMUP_HREF_BLOCKLIST:
        if bad_href.lower() in href_norm:
            return False

    # Chuẩn hoá không dấu để so khớp label và text
    combined_text = f"{label or ''} {text or ''}"
    norm_text = normalize_vi(combined_text)

    for bad_label in WARMUP_LABEL_BLOCKLIST:
        norm_bad = normalize_vi(bad_label)
        if norm_bad in norm_text:
            return False

    return True


async def random_pause(min_time: float = 1.0, max_time: float = 5.0):
    """Tạm dừng ngẫu nhiên giữa min_time và max_time giây."""
    delay = random.uniform(min_time, max_time)
    await asyncio.sleep(delay)
    logger.debug(f"Paused {delay:.2f}s")


async def human_mouse_jiggle(page, x: int, y: int, moves: int = 2):
    """Mô phỏng di chuyển chuột ngẫu nhiên quanh tọa độ (x, y).
    
    Args:
        page: Playwright page.
        x, y: Tọa độ trung tâm.
        moves: Số lần di chuyển ngẫu nhiên.
    """
    try:
        # Di chuyển đến vị trí chính
        await page.mouse.move(x, y)
        await random_pause(0.2, 0.5)

        for _ in range(moves):
            offset_x = random.randint(-15, 15)
            offset_y = random.randint(-15, 15)
            # Clamp để không ra ngoài viewport
            new_x = max(5, min(x + offset_x, 1270))
            new_y = max(5, min(y + offset_y, 890))
            await page.mouse.move(new_x, new_y)
            await random_pause(0.3, 1.0)

        # Quay lại vị trí gốc
        await page.mouse.move(x, y)
        await random_pause(0.3, 1.0)
        logger.debug(f"Mouse jiggle tại ({x}, {y}) với {moves} lần di chuyển")
    except Exception as e:
        logger.error(f"Mouse jiggle thất bại: {e}")


async def human_type(page, text: str, config: dict = None):
    """Gõ text mô phỏng người thật: từng ký tự, có typo, có backspace.
    
    Args:
        page: Playwright page (focus vào ô input).
        text: Nội dung cần gõ.
        config: Dict cấu hình typing (typing_delay_min_ms, typing_delay_max_ms, typo_probability).
    """
    if config is None:
        config = {}

    delay_min = config.get("typing_delay_min_ms", TYPING_DELAY_MIN_MS)
    delay_max = config.get("typing_delay_max_ms", TYPING_DELAY_MAX_MS)
    typo_prob = config.get("typo_probability", TYPO_PROBABILITY)
    fake_prob = config.get("fake_word_probability", FAKE_WORD_PROBABILITY)
    cursor_prob = config.get("cursor_jiggle_probability", CURSOR_JIGGLE_PROBABILITY)

    lines = text.split("\n")
    for l_i, line in enumerate(lines):
        words = line.split()
        for w_i, word in enumerate(words):
            # Xác suất gõ fake word rồi xóa (mô phỏng suy nghĩ lại)
            if random.random() < fake_prob:
                fake = random.choice(["aaa", "hmm", "uhh", "zzz"])
                for c in fake:
                    await page.keyboard.type(c, delay=random.randint(delay_min, delay_max))
                for _ in fake:
                    await page.keyboard.press("Backspace")
                    await asyncio.sleep(random.uniform(0.06, 0.25))

            # Gõ từng ký tự
            for char in word:
                # Xác suất gõ sai rồi sửa
                if random.random() < typo_prob:
                    wrong = random.choice("abcdefghijklmnopqrstuvwxyz")
                    await page.keyboard.type(wrong, delay=random.randint(delay_min, delay_max))
                    await page.keyboard.press("Backspace")
                    await asyncio.sleep(random.uniform(0.06, 0.25))
                await page.keyboard.type(char, delay=random.randint(delay_min, delay_max))

            # Dấu cách giữa các từ trong cùng dòng
            if w_i < len(words) - 1:
                await page.keyboard.type(" ", delay=random.randint(delay_min, 300))

            # Xác suất di chuyển cursor ngẫu nhiên
            if random.random() < cursor_prob:
                await page.keyboard.press("ArrowLeft")
                await asyncio.sleep(random.uniform(0.1, 0.3))
                await page.keyboard.press("ArrowRight")
                await asyncio.sleep(random.uniform(0.1, 0.3))

        # Xuống dòng bằng Shift+Enter để không submit sớm trên Facebook composer
        if l_i < len(lines) - 1:
            await page.keyboard.down("Shift")
            await page.keyboard.press("Enter")
            await page.keyboard.up("Shift")
            await asyncio.sleep(random.uniform(0.2, 0.5))

    await random_pause(0.5, 1.5)
    logger.debug(f"Đã gõ xong {len(text)} ký tự ({len(lines)} dòng)")


async def random_scroll(page):
    """Cuộn trang ngẫu nhiên lên/xuống mô phỏng đọc, ưu tiên cuộn xuống."""
    direction = "down" if random.random() < WARMUP_SCROLL_DOWN_BIAS else "up"
    distance = random.randint(200, 800)

    if direction == "down":
        await page.evaluate(f"window.scrollBy(0, {distance})")
        logger.debug(f"Cuộn xuống {distance}px")
    else:
        await page.evaluate(f"window.scrollBy(0, -{distance})")
        logger.debug(f"Cuộn lên {distance}px")

    await random_pause(1, 3)


async def safe_hover(page):
    """Mô phỏng rê chuột vào link an toàn trong feed, KHÔNG click và KHÔNG rời trang."""
    try:
        links = await page.query_selector_all('[role="feed"] a[href]')
        if not links:
            return

        if random.random() >= WARMUP_HOVER_PROBABILITY:
            return

        sample_links = random.sample(links, min(len(links), 10))
        for link in sample_links:
            try:
                href = await link.get_attribute("href") or ""
                label = await link.get_attribute("aria-label") or ""
                text = (await link.text_content() or "").strip()

                if not is_safe_hover_target(href, label, text):
                    continue

                bbox = await link.bounding_box()
                if bbox and bbox["width"] > 0 and bbox["height"] > 0:
                    await page.mouse.move(
                        bbox["x"] + bbox["width"] / 2,
                        bbox["y"] + bbox["height"] / 2,
                    )
                    logger.debug(f"Hover vào 1 link an toàn trong feed")
                    await random_pause(1, 3)
                    break
            except Exception:
                continue
    except Exception as e:
        logger.debug(f"Safe hover thất bại: {e}")


async def warmup_session(page, duration_min: float = 30, duration_max: float = 60):
    """Warmup: Lướt newsfeed ngẫu nhiên trước khi thao tác quan trọng.
    
    Chỉ cuộn và hover có kiểm soát, KHÔNG click vào bất kỳ đâu.
    """
    duration = random.uniform(duration_min, duration_max)
    logger.info(f"🔥 Warmup: Lướt newsfeed trong {duration:.0f}s")

    await page.goto("https://www.facebook.com/", wait_until="domcontentloaded")
    await random_pause(2, 4)

    loop = asyncio.get_running_loop()
    end_time = loop.time() + duration
    while loop.time() < end_time:
        action = random.choice(["scroll", "hover", "pause"])
        if action == "scroll":
            await random_scroll(page)
        elif action == "hover":
            await safe_hover(page)
        else:
            await random_pause(2, 5)

    logger.info("✅ Warmup hoàn tất")

