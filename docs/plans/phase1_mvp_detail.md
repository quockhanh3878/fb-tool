# PHASE 1 — MVP SCRIPT: Chi tiết Triển khai (Tuần 1-2)

> **Mục tiêu:** Bàn giao công cụ CLI chạy được cho khách Nyatymita trong 2 tuần. Khách chỉ cần chạy 1 lệnh duy nhất: `python commhunter.py --config nyatymita.yaml`, hệ thống tự quét group, lọc bài, sinh comment AI và bắn thông báo Telegram.
> **Tham chiếu:** [Master Plan §4](file:///f:/Clone/fb-tool/docs/03_MASTER_PLAN.md) | [Phân tích mã nguồn](file:///f:/Clone/fb-tool/docs/01_EXISTING_SYSTEMS_ANALYSIS.md)

---

## Cấu trúc thư mục Phase 1

```
fb-tool/
└── commhunter/                         # Package MVP mới
    ├── commhunter.py                   # Entry point CLI
    ├── config_loader.py                # Đọc file YAML cấu hình
    ├── scout_worker.py                 # Module quét bài (Scout)
    ├── shooter_worker.py               # Module comment (Shooter)
    ├── ai_engine.py                    # Bộ lọc AI + Sinh comment
    ├── telegram_bot.py                 # Thông báo + Inline Keyboard
    ├── human_emulator.py               # Port human_type, jiggle sang Playwright
    ├── browser_manager.py              # Quản lý Playwright Context + Stealth
    ├── dedup_store.py                  # Lưu bài đã xem (SQLite)
    ├── models.py                       # Data classes
    ├── constants.py                    # Hằng số, ngưỡng an toàn
    ├── requirements.txt                # Dependencies
    ├── configs/
    │   └── nyatymita.yaml              # Cấu hình cho khách đầu tiên
    └── data/                           # Runtime data (tự tạo)
        ├── browser_profiles/           # Thư mục chứa profile cho mỗi clone
        ├── commhunter.db               # SQLite database
        └── logs/                       # Log files
```

---

## Sprint 1 (Ngày 1-5): Nền tảng Core

### Task 1.1: Thiết kế cấu hình YAML và Data Models (Ngày 1 — 4 giờ)

**File:** `configs/nyatymita.yaml`
```yaml
# Cấu hình cho khách Nyatymita's Writing Commission
service:
  name: "Nyatymita's Writing Commission"
  specialties: "Ngôn tình, Cổ trang, Fanfic, Tiểu thuyết đô thị"
  strengths: "Văn phong trau chuốt, giao demo trước, feedback 5 sao"
  landing_page_note: "Portfolio và feedback mình ghim ở đầu trang cá nhân"

groups:
  - url: "https://www.facebook.com/groups/XXXXXX"
    name: "Hội Yêu Tiểu Thuyết"
    scan_interval_minutes: 10
  - url: "https://www.facebook.com/groups/YYYYYY"
    name: "Group Tìm Comm"
    scan_interval_minutes: 15

filter:
  whitelist_keywords:
    - "tìm comm"
    - "cần viết"
    - "nhận viết"
    - "tìm author"
    - "tìm tác giả"
    - "budget"
    - "nhận order"
  blacklist_keywords:
    - "đã tìm được"
    - "tuyển CTV"
    - "nhập mã"
    - "kiếm tiền online"
    - "viết SEO"
    - "dịch thuật"
  ai_filter_prompt: |
    Chỉ lấy các bài tìm người viết truyện chữ, tiểu thuyết, fanfic, 
    tản văn có đề cập hoặc ngầm hiểu là có ngân sách trên 100k.
    Bỏ qua bài tuyển CTV dịch thuật, viết bài SEO web, hoặc bài quảng cáo.
  min_relevance_score: 0.7
  max_competitor_comments: 8

accounts:
  scout:
    cookie_file: "data/browser_profiles/scout/cookies.json"
    profile_dir: "data/browser_profiles/scout"
    proxy: null  # Hoặc "socks5://user:pass@ip:port"
  shooter:
    cookie_file: "data/browser_profiles/shooter/cookies.json"
    profile_dir: "data/browser_profiles/shooter"
    proxy: null

comment:
  mode: "semi_auto"  # "semi_auto" hoặc "full_auto"
  ai_model: "gpt-4o-mini"
  max_comments_per_day: 20
  delay_min_seconds: 300   # 5 phút
  delay_max_seconds: 900   # 15 phút
  typing_delay_min_ms: 80
  typing_delay_max_ms: 350
  typo_probability: 0.05

telegram:
  bot_token: "BOT_TOKEN_HERE"
  chat_id: "CHAT_ID_HERE"

openai:
  api_key: "sk-xxxx"
  model: "gpt-4o-mini"

database:
  path: "data/commhunter.db"
```

**File:** `models.py`
```python
# Data classes cho toàn bộ hệ thống MVP
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

class PostStatus(Enum):
    NEW = "new"
    NOTIFIED = "notified"
    COMMENTED = "commented"
    SKIPPED = "skipped"
    EXPIRED = "expired"

class CommentStatus(Enum):
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"
    SHADOWBANNED = "shadowbanned"

@dataclass
class DiscoveredPost:
    post_id: str
    post_url: str
    group_url: str
    group_name: str
    author_name: str
    content_text: str
    existing_comment_count: int
    ai_relevance_score: float
    ai_reason: str
    ai_extracted: dict
    status: PostStatus
    discovered_at: datetime
    content_hash: str  # MD5 hash for dedup

@dataclass
class CommentAction:
    post: DiscoveredPost
    comment_content: str
    status: CommentStatus
    error_message: Optional[str] = None
    scheduled_at: Optional[datetime] = None
    executed_at: Optional[datetime] = None
```

**Acceptance Criteria:**
- [ ] File YAML validate thành công khi load qua `config_loader.py`
- [ ] Tất cả data classes có type annotation chính xác
- [ ] Unit test cho config loader

---

### Task 1.2: Browser Manager — Playwright Stealth Context (Ngày 1-2 — 8 giờ)

**File:** `browser_manager.py`
**Nguồn tham khảo:** [openclaw/fb-group-monitor.py L233-L254](file:///f:/Clone/fb-tool/openclaw-skills-main/facebook-group-monitor/scripts/fb-group-monitor.py#L233-L254) + [fbn/browser.py](file:///f:/Clone/fb-tool/fbn-main/fbn/browser.py)

**Chức năng:**
1. `create_stealth_context(profile_dir, proxy=None, headless=True)` — Khởi tạo persistent Playwright context với stealth plugin
2. `login_interactive(profile_dir)` — Mở browser có giao diện để login tay 1 lần
3. `check_session(profile_dir)` — Kiểm tra session còn sống không
4. `detect_checkpoint(page)` — Phát hiện checkpoint/security check

**Tham chiếu code cần port:**
```python
# Từ openclaw: create_browser_context (L233-254)
# Các tham số stealth cần giữ nguyên:
BROWSER_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--disable-dev-shm-usage",
]
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) ..."

# Từ fbn: Hỗ trợ thêm cookie auth loading (auth.py)
# load_facebook_cookies(path) -> list[dict]
```

**Acceptance Criteria:**
- [ ] Khởi tạo browser context thành công ở cả chế độ headless và headed
- [ ] Session persist sau khi đóng và mở lại context
- [ ] Phát hiện chính xác checkpoint/login page
- [ ] Hỗ trợ cấu hình proxy (SOCKS5/HTTP)

---

### Task 1.3: Scout Worker — Quét bài từ Group (Ngày 2-3 — 12 giờ)

**File:** `scout_worker.py`
**Nguồn tham khảo:** [openclaw/fb-group-monitor.py L60-L184 (EXTRACT_POST_JS)](file:///f:/Clone/fb-tool/openclaw-skills-main/facebook-group-monitor/scripts/fb-group-monitor.py#L60-L184) + [openclaw/fb-group-monitor.py L389-L500 (cmd_scrape)](file:///f:/Clone/fb-tool/openclaw-skills-main/facebook-group-monitor/scripts/fb-group-monitor.py#L389-L500) + [fbn/extractor.py (URL parsing)](file:///f:/Clone/fb-tool/fbn-main/fbn/extractor.py)

**Chức năng chính:**
1. `scan_group(context, group_url, limit=20)` — Navigate đến group, cuộn feed, chạy EXTRACT_POST_JS để bóc tách bài viết
2. `filter_new_posts(posts, dedup_store)` — So sánh với DB, chỉ trả về bài mới
3. `run_scout_loop(config)` — Vòng lặp chính: Quét tất cả group theo `scan_interval`, gọi AI filter, lưu kết quả

**Chi tiết triển khai:**

```python
# Bước 1: Navigate và chuẩn bị feed
await page.goto(group_url, wait_until="domcontentloaded")
await page.wait_for_timeout(random.randint(2000, 4000))

# Bước 2: Kiểm tra trạng thái trang
if "login" in page.url or "checkpoint" in page.url:
    raise CheckpointError(f"Scout account bị checkpoint tại {page.url}")

# Bước 3: Cuộn feed để load thêm bài (kế thừa openclaw L428-431)
for _ in range(4):
    await page.evaluate("window.scrollBy(0, 1000)")
    await page.wait_for_timeout(random.randint(1500, 2500))

# Bước 4: Chạy EXTRACT_POST_JS trên từng element (kế thừa openclaw L434-449)
feed_children = await page.query_selector_all('[role="feed"] > *')
for child in feed_children:
    data = await child.evaluate(EXTRACT_POST_JS)
    if data and data.get("text"):
        posts.append(data)

# Bước 5: Bổ sung trích xuất số comment hiện tại
# (Cần thêm vào EXTRACT_POST_JS: đếm số comment elements trong post)
```

**Bổ sung EXTRACT_POST_JS:** Cần thêm đoạn đếm số comment hiện có trong bài:
```javascript
// Thêm vào cuối EXTRACT_POST_JS, trước return:
let commentCount = 0;
const commentElements = el.querySelectorAll('[aria-label*="comment"], [aria-label*="bình luận"]');
commentCount = commentElements.length;
// ... return { ...existing, commentCount }
```

**Acceptance Criteria:**
- [ ] Quét thành công ít nhất 1 group thật và trả về danh sách bài viết
- [ ] Mỗi bài viết có đầy đủ: author, text, url, commentCount
- [ ] Dedup hoạt động chính xác (không trả về bài đã thấy trước đó)
- [ ] Phát hiện và xử lý lỗi checkpoint

---

### Task 1.4: Dedup Store — SQLite (Ngày 2 — 3 giờ)

**File:** `dedup_store.py`
**Nguồn tham khảo:** [fbn/state.py](file:///f:/Clone/fb-tool/fbn-main/fbn/state.py) (kế thừa pattern SQLite) + [openclaw/fb-group-monitor.py L194-L209 (post_hash, seen_posts)](file:///f:/Clone/fb-tool/openclaw-skills-main/facebook-group-monitor/scripts/fb-group-monitor.py#L194-L209)

**Schema SQLite cho MVP:**
```sql
CREATE TABLE IF NOT EXISTS discovered_posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content_hash TEXT UNIQUE NOT NULL,       -- MD5 of author:text[:200]
    post_id_fb TEXT,                         -- Facebook post ID (nếu extract được)
    post_url TEXT,
    group_url TEXT NOT NULL,
    group_name TEXT,
    author_name TEXT,
    content_text TEXT,
    existing_comment_count INTEGER DEFAULT 0,
    ai_relevance_score REAL DEFAULT 0.0,
    ai_reason TEXT,
    status TEXT DEFAULT 'new',               -- new/notified/commented/skipped/expired
    discovered_at TEXT NOT NULL,             -- ISO 8601
    notified_at TEXT,
    commented_at TEXT
);

CREATE TABLE IF NOT EXISTS comment_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_hash TEXT NOT NULL,                 -- FK to discovered_posts.content_hash
    comment_content TEXT NOT NULL,
    status TEXT DEFAULT 'queued',            -- queued/in_progress/success/failed/shadowbanned
    error_message TEXT,
    scheduled_at TEXT,
    executed_at TEXT
);

CREATE TABLE IF NOT EXISTS daily_stats (
    date TEXT PRIMARY KEY,                   -- YYYY-MM-DD
    posts_scanned INTEGER DEFAULT 0,
    posts_matched INTEGER DEFAULT 0,
    comments_sent INTEGER DEFAULT 0,
    comments_success INTEGER DEFAULT 0
);
```

**Acceptance Criteria:**
- [ ] Insert/query hoạt động chính xác
- [ ] `is_seen(content_hash)` trả về True/False trong dưới 1ms
- [ ] Tự động tạo DB file nếu chưa tồn tại

---

### Task 1.5: AI Engine — Lọc + Sinh comment (Ngày 3-4 — 8 giờ)

**File:** `ai_engine.py`
**Nguồn tham khảo:** [ai-comment-bot/main.py L223-L239 (generate_comment)](file:///f:/Clone/fb-tool/ai-comment-bot-main/main.py#L223-L239) — Cập nhật lên SDK openai mới nhất

**Chức năng:**
1. `filter_post(post_content, user_prompt, whitelist, blacklist)` → `{score, reason, extracted}`
2. `generate_comment(post_content, service_info, extracted_details)` → `str`

**Chi tiết prompt engineering:**

```python
# ai_engine.py

import openai
import json

class AIEngine:
    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        self.client = openai.OpenAI(api_key=api_key)
        self.model = model

    async def filter_post(self, post_content: str, user_prompt: str) -> dict:
        """Chấm điểm độ phù hợp của bài viết."""
        system_prompt = f"""Bạn là trợ lý lọc bài viết Facebook. 
Tiêu chí của người dùng: {user_prompt}

Trả về JSON duy nhất (không markdown):
{{"relevance_score": 0.0-1.0, "reason": "...", "extracted": {{"genre": "...", "budget": "...", "deadline": "...", "details": "..."}}}}"""

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Bài viết:\n{post_content[:2000]}"}
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
            max_tokens=500,
        )
        return json.loads(response.choices[0].message.content)

    async def generate_comment(self, post_content: str, service_info: dict, extracted: dict) -> str:
        """Sinh bình luận tự nhiên cá nhân hóa."""
        system_prompt = f"""Viết 1 bình luận Facebook ứng tuyển nhận viết commission.

Thông tin dịch vụ:
- Tên: {service_info['name']}
- Chuyên môn: {service_info['specialties']}
- Điểm mạnh: {service_info['strengths']}
- Ghi chú portfolio: {service_info['landing_page_note']}

Quy tắc bắt buộc:
1. KHÔNG dán bất kỳ link nào.
2. Nhắc đến chi tiết cụ thể trong bài (thể loại, couple, bối cảnh...).
3. Giọng văn tự nhiên, thân thiện, như người thật gõ.
4. Độ dài 40-120 từ tiếng Việt.
5. Hướng dẫn xem portfolio ở đầu trang cá nhân.
6. KHÔNG sử dụng emoji quá nhiều (tối đa 1-2).

Chi tiết đã trích xuất: {json.dumps(extracted, ensure_ascii=False)}"""

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Bài viết cần ứng tuyển:\n{post_content[:2000]}"}
            ],
            temperature=0.8,  # Cao hơn để comment đa dạng
            max_tokens=300,
        )
        return response.choices[0].message.content.strip().strip('"')
```

**Acceptance Criteria:**
- [ ] `filter_post` trả về JSON hợp lệ với `relevance_score` trong [0, 1]
- [ ] `generate_comment` sinh bình luận tiếng Việt tự nhiên, không chứa link
- [ ] Xử lý lỗi API gracefully (retry 3 lần, fallback message)
- [ ] Chi phí < 100đ/lần gọi (GPT-4o-mini)

---

## Sprint 2 (Ngày 6-10): Tương tác và Kết nối

### Task 2.1: Human Emulator — Port sang Playwright (Ngày 6-7 — 10 giờ)

**File:** `human_emulator.py`
**Nguồn tham khảo:** [ai-comment-bot/main.py L105-L180](file:///f:/Clone/fb-tool/ai-comment-bot-main/main.py#L105-L180)

**Chức năng cần port:**

| Hàm gốc (Selenium) | Hàm mới (Playwright) | Mô tả thay đổi |
|---|---|---|
| `random_pause(min, max)` | `random_pause(min, max)` | Giữ nguyên `asyncio.sleep` thay `time.sleep` |
| `human_mouse_jiggle(element, moves)` | `human_mouse_jiggle(page, x, y, moves)` | Thay `ActionChains.move_to_element` bằng `page.mouse.move(x, y)` + random offset |
| `human_type(element, text)` | `human_type(page, text)` | Thay `element.send_keys(c)` bằng `page.keyboard.type(c, delay=...)` và `page.keyboard.press("Backspace")` |
| `random_scroll()` | `random_scroll(page)` | Thay `driver.execute_script` bằng `page.evaluate("window.scrollBy(...)") ` |
| `random_hover_or_click()` | `random_browse(page)` | Thay `find_elements(By.TAG_NAME, "a")` bằng `page.query_selector_all("a")` |

**Pseudocode chi tiết cho `human_type` (quan trọng nhất):**
```python
async def human_type(page, text: str, config: dict):
    """Gõ text mô phỏng người thật: từng ký tự, có typo, có backspace."""
    words = text.split()
    for w_i, word in enumerate(words):
        # 5% xác suất gõ fake word rồi xóa
        if random.random() < 0.05:
            fake = random.choice(["aaa", "hmm", "uhh"])
            for c in fake:
                await page.keyboard.type(c, delay=random.randint(80, 350))
            for _ in fake:
                await page.keyboard.press("Backspace")
                await asyncio.sleep(random.uniform(0.06, 0.25))

        # Gõ từng ký tự
        for char in word:
            # 5% xác suất gõ sai ký tự rồi sửa
            if random.random() < config.get("typo_probability", 0.05):
                wrong = random.choice("abcdefghijklmnopqrstuvwxyz")
                await page.keyboard.type(wrong, delay=random.randint(80, 350))
                await page.keyboard.press("Backspace")
                await asyncio.sleep(random.uniform(0.06, 0.25))
            await page.keyboard.type(char, delay=random.randint(
                config.get("typing_delay_min_ms", 80),
                config.get("typing_delay_max_ms", 350)
            ))

        # Thêm dấu cách giữa các từ
        if w_i < len(words) - 1:
            await page.keyboard.type(" ", delay=random.randint(80, 300))

        # 3% di chuyển cursor ngẫu nhiên
        if random.random() < 0.03:
            await page.keyboard.press("ArrowLeft")
            await asyncio.sleep(random.uniform(0.1, 0.3))
            await page.keyboard.press("ArrowRight")
```

**Acceptance Criteria:**
- [ ] `human_type` gõ chính xác nội dung (sau khi trừ typo+backspace)
- [ ] Thời gian gõ 100 ký tự: 10-40 giây (tương đương người thật)
- [ ] `human_mouse_jiggle` di chuyển chuột mượt mà, không bị lỗi out-of-viewport
- [ ] Tất cả hàm đều async

---

### Task 2.2: Shooter Worker — Comment vào bài viết (Ngày 7-8 — 10 giờ)

**File:** `shooter_worker.py`
**Nguồn tham khảo:** [ai-comment-bot/main.py L241-L280 (post_comment)](file:///f:/Clone/fb-tool/ai-comment-bot-main/main.py#L241-L280)

**Luồng xử lý:**
```
1. Nhận job: {post_url, comment_text}
2. Kiểm tra rate limit (đã cmt bao nhiêu hôm nay?)
3. Mở Playwright context cho Shooter account
4. Warmup: Lướt newsfeed 30-60s (random_scroll + random_browse)
5. Navigate đến post_url
6. Kiểm tra bài còn tồn tại
7. Cuộn xuống vùng comment
8. Tìm ô comment: '[aria-label*="Write a comment"], [aria-label*="Viết bình luận"]'
9. human_mouse_jiggle quanh ô comment
10. Click vào ô comment
11. human_type nội dung comment
12. Random pause 0.5-2s
13. Nhấn Enter gửi comment
14. Đợi 2-3s, kiểm tra comment có hiển thị
15. Cập nhật DB: status = success/failed/shadowbanned
16. Cập nhật daily_comment_count
```

**Selector cần tìm ô comment (đa ngôn ngữ):** xem `commhunter/constants.py:COMMENT_BOX_SELECTORS`.
Đã bổ sung `[aria-label*="Viết câu trả lời"]` / `"Write an answer"` sau khi soi DOM thật
10/09/2026 — group kiểu hỏi-đáp/thảo luận dùng nhãn "Viết câu trả lời…" thay vì
"Viết bình luận…".

**Chạy thật 10/09/2026** (nick phụ, CDP 9222, group "Hội BMW"): `post_comment(delete_after=True)`
→ comment vào 1 bài trong nhóm bằng `[aria-label*="Viết bình luận"]`, verify 2 chiều =
`SUCCESS`, `delete_comment` xoá sạch (menu "Chỉnh sửa hoặc xóa bình luận này" → "Xóa" →
xác nhận). Đối chiếu lại feed: không còn comment test.

**Đăng bài — chạy thật 10/09/2026** (group không kiểm duyệt, nick phụ là admin):
`publish_post` ghi được thật; sửa 2 bug ở khâu xác nhận: (1) `_post_submitted_ok`
không đếm mọi `[role="dialog"]` nữa (FB giữ sẵn dialog thông báo → FAILED giả) —
chỉ soi ô soạn bài; (2) FB giấu permalink khỏi mọi `href` trong feed → thêm
`_permalink_by_clicking_timestamp` (đánh dấu thẻ `<a>` mốc thời gian → click →
đọc URL đích `/groups/<gid>/posts/<id>/` → `_clean_permalink`). Hồi quy:
`test_pipeline.py` +7 assertion (nay 111).

**11/09/2026** — `ShooterWorker.delete_own_post(page, post_url)`: xoá bài CHÍNH mình đã đăng, đường rollback / cleanup cho `publish_post`. DOM group thật 2026-09-10: nút menu `[aria-haspopup="menu"][aria-label*="Hành động đối với bài viết này"]` (JS `.click()` tránh overlay) → mục "Xóa bài viết" / "Chuyển vào thùng rác" → hộp thoại xác nhận → nút khớp tuyệt đối `Xóa`/`Xoá`/`Chuyển` (KHÔNG bắt tiêu đề "Xóa bài viết vĩnh viễn?" hay nút "Xác nhận"). Verify: mở lại permalink, khớp `POST_GONE_MARKERS`. Fail an toàn khi không khớp selector. Hằng số mới trong `constants.py`: `OWN_POST_MENU_SELECTORS`, `OWN_POST_DELETE_MENU_TEXTS`, `OWN_POST_DELETE_CONFIRM_HINTS`, `OWN_POST_DELETE_CONFIRM_BUTTON_TEXTS`, `POST_GONE_MARKERS`. `test_pipeline.py` +3 assertion (nay 114).

**11/09/2026 — E2E đường backend Track A Item 3** (burner `1042987808508567`): sửa tiếp 2 bug lộ ra khi chạy `execute_publish` thật. (1) `_post_submitted_ok` giờ POLL tối đa `POST_SUBMIT_CONFIRM_TIMEOUT_MS` = 14s (hộp thoại đóng chậm có spinner → soi 1 lần báo `submit_not_confirmed` giả trong khi bài đã lên feed); bỏ cụm `"đã đăng"` trần khỏi `POST_SUCCESS_PHRASES`. (2) trang permalink FB chèn bài "được đề xuất" cùng nút "Hành động đối với bài viết này..." → `delete_own_post` bấm nhầm bài người khác → thêm `_open_own_post_menu` + `_current_account_name` (bóc tên tài khoản đang đăng nhập từ payload bootstrap qua `CURRENT_ACCOUNT_NAME_RE`, khớp `aria-label` "... của <tên>"; chỉ rơi về nút khớp chung khi không xác định được tên), `delete_own_post(page, post_url, author_name=None)`; `_click_menu_text` + `_confirm_delete_dialog` chuyển sang JS click (overlay chắn click chuột). `test_pipeline.py` +2 assertion (nay 116).

**Acceptance Criteria:**
- [ ] Comment thành công vào 1 bài viết thật trên Facebook (test với bài của chính mình)
- [ ] Rate limit hoạt động: Không vượt quá `max_comments_per_day`
- [ ] Delay giữa các comment nằm trong `[delay_min_seconds, delay_max_seconds]`
- [ ] Phát hiện shadowban (comment không hiển thị cho người khác)

---

### Task 2.3: Telegram Bot — Thông báo Semi-Auto (Ngày 8-9 — 8 giờ)

**File:** `telegram_bot.py`
**Nguồn tham khảo:** [fbn/notifications.py](file:///f:/Clone/fb-tool/fbn-main/fbn/notifications.py) (pattern Notification)

**Chức năng:**
1. `send_post_notification(post, ai_result)` — Bắn tin nhắn với Inline Keyboard
2. `handle_callback(callback_query)` — Xử lý khi user bấm nút
3. `send_result_notification(action)` — Báo kết quả comment

**Mẫu tin nhắn:**
```
🎯 BÀI MỚI PHÙ HỢP!

📌 Nhóm: {group_name}
👤 Người đăng: {author}
📝 Nội dung: "{content[:300]}..."

🤖 AI đánh giá: ⭐ {score}/1.0 — {reason}

Inline Keyboard:
[🚀 Ứng tuyển (AI Comment)]  [📋 Xem trước comment]
[❌ Bỏ qua]                  [🔗 Mở bài viết]
```

**Khi user bấm "Ứng tuyển":**
1. Gọi `ai_engine.generate_comment()` sinh nội dung
2. Hiển thị preview: "Comment sẽ đăng: [nội dung]. Xác nhận?"
3. User bấm "Xác nhận" → Đưa job vào queue → Shooter thực thi
4. Bắn tin nhắn kết quả: "✅ Đã comment thành công!" hoặc "❌ Lỗi: ..."

**Acceptance Criteria:**
- [ ] Bot gửi tin nhắn có Inline Keyboard hoạt động
- [ ] Bấm nút "Ứng tuyển" trigger đúng luồng AI → Preview → Confirm → Comment
- [ ] Bấm "Bỏ qua" cập nhật trạng thái bài viết trong DB
- [ ] Bấm "Mở bài viết" tạo link mở Facebook

---

### Task 2.4: Entry Point CLI + Orchestrator (Ngày 9-10 — 6 giờ)

**File:** `commhunter.py`

**Chức năng:**
```
python commhunter.py --config configs/nyatymita.yaml
python commhunter.py login --profile scout --config configs/nyatymita.yaml
python commhunter.py login --profile shooter --config configs/nyatymita.yaml
python commhunter.py status --config configs/nyatymita.yaml
python commhunter.py run --config configs/nyatymita.yaml    # Chạy vòng lặp chính
```

**Luồng lệnh `run`:**
```python
async def main_loop(config):
    """Vòng lặp chính: Scout quét → AI lọc → Thông báo/Comment → Lặp lại."""
    browser_mgr = BrowserManager(config)
    scout = ScoutWorker(browser_mgr, config)
    shooter = ShooterWorker(browser_mgr, config)
    ai = AIEngine(config.openai.api_key, config.openai.model)
    tg = TelegramBot(config.telegram)
    db = DedupStore(config.database.path)

    while True:
        for group in config.groups:
            # 1. Scout quét group
            posts = await scout.scan_group(group.url, limit=20)
            new_posts = scout.filter_new_posts(posts, db)

            for post in new_posts:
                # 2. Lọc từ khóa whitelist/blacklist
                if not keyword_match(post, config.filter):
                    db.mark_skipped(post, reason="keyword_mismatch")
                    continue

                # 3. AI chấm điểm
                ai_result = await ai.filter_post(post.content_text, config.filter.ai_filter_prompt)
                post.ai_relevance_score = ai_result["relevance_score"]

                if post.ai_relevance_score < config.filter.min_relevance_score:
                    db.mark_skipped(post, reason=f"low_score:{ai_result['reason']}")
                    continue

                # 4. Kiểm tra anti-crowding
                if post.existing_comment_count > config.filter.max_competitor_comments:
                    db.mark_skipped(post, reason="too_competitive")
                    continue

                # 5. Thông báo / Comment
                if config.comment.mode == "semi_auto":
                    await tg.send_post_notification(post, ai_result)
                    db.mark_notified(post)
                else:  # full_auto
                    comment = await ai.generate_comment(
                        post.content_text, config.service, ai_result.get("extracted", {})
                    )
                    await shooter.post_comment(post.post_url, comment)
                    db.mark_commented(post, comment)

            # Giãn cách giữa các group
            await asyncio.sleep(random.uniform(30, 90))

        # Đợi đến chu kỳ quét tiếp theo
        min_interval = min(g.scan_interval_minutes for g in config.groups)
        await asyncio.sleep(min_interval * 60)
```

**Acceptance Criteria:**
- [ ] `commhunter.py login` mở browser để login thành công
- [ ] `commhunter.py status` báo trạng thái session
- [ ] `commhunter.py run` chạy vòng lặp liên tục, quét đúng tần suất, xử lý graceful shutdown (Ctrl+C)

---

## Sprint 3 (Ngày 11-14): Test & Bàn giao

### Task 3.1: Kiểm thử tích hợp (Integration Test) (Ngày 11-12)

| # | Test Case | Mô tả | Expected Result |
|---|---|---|---|
| TC-01 | Scout quét group thật | Chạy scout trên 1 group thật có bài mới | Trả về >= 1 bài viết mới |
| TC-02 | AI Filter chấm điểm | Gửi 5 bài mẫu (3 phù hợp, 2 không) vào AI filter | Score >= 0.7 cho 3 bài phù hợp |
| TC-03 | AI Comment sinh nội dung | Sinh comment cho 3 bài phù hợp | Comment tiếng Việt, không link, 40-120 từ |
| TC-04 | Telegram notification | Bắn thông báo bài phù hợp | Tin nhắn hiển thị đúng format + Inline Keyboard hoạt động |
| TC-05 | Shooter comment thành công | Comment vào bài test (bài của chính mình) | Comment hiển thị trên Facebook |
| TC-06 | Semi-auto full flow | Quét → Lọc → Telegram → Bấm nút → Comment | End-to-end thành công |
| TC-07 | Dedup hoạt động | Chạy scout 2 lần liên tiếp | Lần 2 trả về 0 bài mới |
| TC-08 | Rate limit | Set max_comments_per_day = 2, thử comment 3 lần | Lần 3 bị reject |
| TC-09 | Checkpoint detection | Truy cập Facebook khi session hết hạn | Phát hiện và log cảnh báo |

---

### Task 3.2: Setup cho khách Nyatymita (Ngày 13-14)

- [ ] Nhận cookie/ID-pass của nick clone từ khách
- [ ] Login scout và shooter account
- [ ] Cấu hình `nyatymita.yaml` với danh sách group thực tế
- [ ] Chạy thử 24h trên VPS, giám sát log
- [ ] Hướng dẫn khách sử dụng Telegram Bot
- [ ] Thiết lập thanh toán tháng đầu tiên

---

## Dependencies (requirements.txt)

```
# Browser Automation
playwright>=1.61,<2
playwright-stealth>=1.0

# AI
openai>=1.30

# Telegram
python-telegram-bot>=21.0

# Storage
# (SQLite built-in)

# Config
pyyaml>=6.0
pydantic>=2.0

# Utilities
python-dotenv>=1.0
loguru>=0.7
Pillow>=10.0   # Optional: cho feed strip screenshot
```
