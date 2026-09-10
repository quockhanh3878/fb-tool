# PHÂN TÍCH CẤU TRÚC 3 HỆ THỐNG MÃ NGUỒN HIỆN CÓ

Tài liệu này phân tích chi tiết cấu trúc, công nghệ, ưu/nhược điểm và khả năng tái sử dụng của 3 thư mục mã nguồn có sẵn trong dự án:
1. `ai-comment-bot-main` (Bot Selenium tự động bình luận mô phỏng người thật + OpenAI)
2. `fbn-main` (Hệ thống giám sát nhóm Facebook bằng Playwright + SQLite + Apprise Notification)
3. `openclaw-skills-main/facebook-group-monitor` (Skill Playwright giám sát nhóm Facebook với Stealth mode + Stitched Feed Screenshot cho AI Vision)

---

## 1. Thư mục `ai-comment-bot-main`

### 1.1 Tổng quan
- **Mục đích:** Tự động tạo và đăng bình luận dạng "người thật" (human-like) lên một bài viết Facebook chỉ định bằng OpenAI GPT và Selenium.
- **Công nghệ chính:** Python 3.7+, Selenium WebDriver, `webdriver-manager`, `openai==0.28`, `python-dotenv`.

### 1.2 Cấu trúc thư mục
```
ai-comment-bot-main/
├── .env.example              # Mẫu biến môi trường (OPENAI_KEY, MODEL, POST_URL...)
├── .gitignore                # Bỏ qua chrome_data, logs, venv
├── .pre-commit-config.yaml   # Cấu hình flake8, black, isort
├── main.py                   # Script chính (340 dòng code) chứa toàn bộ logic
├── README.md                 # Hướng dẫn cài đặt và sử dụng
└── requirements.txt          # Danh sách thư viện phụ thuộc
```

### 1.3 Cơ chế hoạt động trong `main.py`
1. **Khởi tạo Driver (`setup_driver`):**
   - Sử dụng Google Chrome với cờ `--disable-blink-features=AutomationControlled`, tắt popup và notification.
   - Lưu trữ dữ liệu profile trình duyệt trong thư mục nội bộ `chrome_data/` để giữ phiên đăng nhập (Persistent Profile).
2. **Mô phỏng hành vi người thật (Anti-bot Tactics):**
   - `human_mouse_jiggle(element, moves=2)`: Rê chuột ngẫu nhiên xung quanh phần tử mục tiêu trước khi click.
   - `human_type(element, text)`: Gõ từng ký tự với độ trễ ngẫu nhiên (`80ms - 350ms`), có cơ chế cố tình gõ sai từ/ký tự giả rồi bấm `BACKSPACE` để sửa, giả lập mũi tên trái/phải.
   - `random_scroll()`: Cuộn trang lên/xuống ngẫu nhiên mô phỏng hành vi đọc bài.
   - `random_hover_or_click()`: Rê chuột hoặc click ngẫu nhiên vào các link khác rồi quay lại (`driver.back()`).
3. **Sinh nội dung bình luận (`generate_comment`):**
   - Gọi OpenAI ChatCompletion (`gpt-4o-mini`) theo prompt cấu hình sẵn.
4. **Đăng bình luận (`post_comment`):**
   - Tìm ô nhập cmt qua XPath: `//div[contains(@aria-label, 'Write a comment') and @contenteditable='true']`.
   - Click $\rightarrow$ gõ bằng `human_type` $\rightarrow$ nhấn `ENTER`.

### 1.4 Đánh giá
* **Ưu điểm lớn:** Cơ chế mô phỏng gõ phím (`human_type`) và rê chuột (`human_mouse_jiggle`) rất chi tiết, có giá trị cực cao để tái sử dụng cho module "Tay súng" (Writer/Shooter).
* **Nhược điểm:**
  - Dùng Selenium truyền thống (dễ bị phát hiện hơn Playwright, nặng nề, khó scale).
  - SDK OpenAI cũ (`openai==0.28`).
  - Chưa có bộ lọc bài viết hay cơ chế tự động quét nhóm (chỉ nhận cứng 1 `POST_URL`).

---

## 2. Thư mục `fbn-main` (Facebook Notifier)

### 2.1 Tổng quan
- **Mục đích:** Giám sát liên tục các bài viết mới xuất hiện trong một Facebook Group và gửi thông báo qua Apprise (Telegram, Discord, Email, Pushover...).
- **Công nghệ chính:** Python 3.10+, Playwright (Chromium/Chrome/Edge), SQLite (`state.py`), Apprise, `pydantic`, `dateparser`.
- **Kiến trúc:** Thiết kế theo chuẩn Enterprise/Production package, cực kỳ bài bản và module hóa cao.

### 2.2 Cấu trúc thư mục
```
fbn-main/
├── compose.yaml / Dockerfile # Hỗ trợ đóng gói container chạy server
├── pyproject.toml            # Cấu hình đóng gói package chuẩn PEP 621
├── fbn/                      # Source code chính của package
│   ├── auth.py               # Kiểm tra trạng thái đăng nhập Facebook
│   ├── browser.py            # Quản lý Playwright Browser & Persistent Context (41KB)
│   ├── cli.py                # Giao diện CLI chuyên nghiệp (subcommands: monitor, doctor...)
│   ├── config.py             # Schema cấu hình, validation Pydantic
│   ├── extractor.py          # Bóc tách cấu trúc bài viết, URL, ID, tác giả, thời gian (9KB)
│   ├── models.py             # Data models: GroupRef, Post, Target, SessionState
│   ├── monitor.py            # Vòng lặp giám sát (Polling Loop, Error Backoff)
│   ├── notifications.py      # Bắn thông báo qua Apprise đa nền tảng
│   ├── scheduling.py         # Quản lý chu kỳ quét và giãn cách
│   └── state.py              # SQLite State Store: Quản lý dedup, theo dõi post đã xem (26KB)
└── tests/                    # Bộ kiểm thử đơn vị & tích hợp
```

### 2.3 Cơ chế hoạt động nổi bật
1. **Phân tích cú pháp Facebook chuyên sâu (`extractor.py`):**
   - Chuẩn hóa URL Group, Post ID, Permalink (`/groups/{group_id}/posts/{post_id}`).
   - Phân tích timestamp Facebook (`just now`, `10 m`, `2 h`, `yesterday at...`) thành `datetime` chuẩn qua `dateparser`.
2. **Quản lý Persistent Browser Context (`browser.py`):**
   - Hỗ trợ chạy cả Chromium gốc, Google Chrome hệ thống hoặc Edge.
   - Xử lý lỗi crash, tự động reload và phục hồi session khi gặp sự cố mạng hoặc popup chặn.
3. **Cơ chế chống trùng lặp hoàn hảo (`state.py`):**
   - Dùng SQLite lưu lịch sử `seen_posts` kèm mốc thời gian, đảm bảo không bao giờ bị báo trùng 1 bài nhiều lần ngay cả khi restart tool.
4. **Bắn thông báo đa kênh (`notifications.py`):**
   - Tích hợp thư viện Apprise, chỉ cần truyền chuỗi kết nối (ví dụ: `tgram://bot_token/chat_id`) là bắn tin tức thì về Telegram, Discord...

### 2.4 Đánh giá
* **Ưu điểm lớn:** Kiến trúc mã nguồn sạch nhất, bền bỉ nhất. Có thể dùng làm **bộ khung nền tảng (Engine)** cho việc quản lý Browser Session, Quét feed, Lưu trữ SQLite và Bắn thông báo.
* **Nhược điểm:** Mới chỉ phục vụ mục đích đọc (Read-only / Scraper), chưa có logic tương tác (Write / Comment).

---

## 3. Thư mục `openclaw-skills-main/facebook-group-monitor`

### 3.1 Tổng quan
- **Mục đích:** Skill tự động hóa cho AI Agent (OpenClaw) để cào bài viết mới từ group Facebook bằng Playwright Stealth và trích xuất dữ liệu cho mô hình thị giác (Vision LLM).
- **Công nghệ chính:** Python 3, Playwright, Pillow (PIL), JavaScript DOM Extractor.

### 3.2 Cấu trúc thư mục
```
openclaw-skills-main/facebook-group-monitor/
├── SKILL.md                  # Tài liệu định nghĩa kỹ năng cho AI Agent
├── references/
│   └── SETUP.md              # Hướng dẫn setup session & login thủ công
└── scripts/
    ├── fb-group-monitor.py   # Script thực thi chính (556 dòng code)
    ├── fb-group-monitor.sh   # Bash wrapper
    ├── .browser-data/        # Persistent browser profile
    ├── .seen-posts.json      # File JSON lưu các bài đã đọc
    └── screenshots/          # Thư mục lưu ảnh chụp màn hình feed
```

### 3.3 Cơ chế hoạt động nổi bật
1. **Playwright Stealth Mode:**
   - Cờ `--disable-blink-features=AutomationControlled`, fake User-Agent Mac OS.
   - Tương thích tốt với giao diện Facebook web hiện đại.
2. **Trích xuất trực tiếp trên DOM bằng JavaScript (`EXTRACT_POST_JS`):**
   - Truy vấn trực tiếp các selector `div[dir="auto"]` để bóc tách nội dung văn bản bài viết dài nhất.
   - Nhận diện tác giả qua profile link `a[href*="/user/"]` hoặc `role="link"`.
   - Trích xuất URL bài viết thực qua các định dạng `/posts/`, `/permalink/`, `story_fbid`.
3. **Kỹ thuật Ghép ảnh Feed ("Feed Strip Stitcher"):**
   - Cuộn qua 3 khung nhìn (viewport), chụp ảnh từng khung rồi dùng Pillow ghép thành 1 dải ảnh dài duy nhất.
   - Giúp AI Vision chỉ cần đọc đúng 1 tấm ảnh là nắm trọn toàn bộ nội dung feed, không cần bóc tách DOM phức tạp.

### 3.4 Đánh giá
* **Ưu điểm lớn:** Đoạn mã JavaScript trích xuất bài viết (`EXTRACT_POST_JS`) hoạt động rất thực tế trên cấu trúc DOM của Facebook hiện tại. Quy trình đăng nhập 1 lần (`login`) rồi lưu lại `.browser-data` rất gọn nhẹ.
* **Nhược điểm:** Lưu bài đã xem bằng file JSON cục bộ (`.seen-posts.json`), sẽ chậm khi số lượng bài lên tới hàng chục nghìn (nên đổi sang SQLite như `fbn`).

---

## 4. Bảng tổng hợp so sánh & Kế hoạch tái sử dụng linh kiện

| Thành phần | `ai-comment-bot-main` | `fbn-main` | `openclaw-skills` | Giải pháp cho Nền tảng mới |
| :--- | :--- | :--- | :--- | :--- |
| **Engine Trình duyệt** | Selenium (Cũ) | Playwright (Chuẩn) | Playwright Stealth | **Playwright Stealth (kế thừa `fbn` + `openclaw`)** |
| **Quét bài & Bóc tách DOM** | Không có | `extractor.py` | `EXTRACT_POST_JS` | **Kết hợp `EXTRACT_POST_JS` + Parser của `fbn`** |
| **Lưu trữ & Chống trùng (Dedup)**| Không có | SQLite State Store | JSON File | **SQLite / PostgreSQL (kế thừa `fbn/state.py`)** |
| **Hành vi gõ & Rê chuột (Anti-ban)**| Rất tốt (Typo, Delay, Jiggle) | Không có | Không có | **Port logic gõ phím người thật sang Playwright** |
| **Sinh bình luận (AI Generation)**| OpenAI GPT-4o-mini | Không có | Prompt Vision | **Tích hợp LLM Contextual Commenting** |
| **Bắn thông báo (Alerting)** | Log file | Apprise (Telegram...) | Stdout JSON | **Telegram Bot Webhook / Apprise của `fbn`** |
