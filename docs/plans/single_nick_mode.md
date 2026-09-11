# Chế độ 1 nick làm toàn bộ tác vụ (desktop)

> Cập nhật: 11/09/2026 — Trạng thái: **Thiết kế, chờ anh Ber duyệt** (chưa có mã).
> Phạm vi: chỉ `RUN_MODE=desktop`, 1 máy của anh Ber. Đường SaaS nhiều nick giữ nguyên.

## 1. Mục tiêu

Một nick Facebook duy nhất đảm nhận mọi việc: quét nhóm (scout), comment (shooter), bump, đăng bài (poster), cào nhóm đã tham gia, warm-up / health-check — chạy an toàn trong nhiều ngày không người trực.

## 2. Hiện trạng (đối chiếu mã 11/09/2026)

**Đã có sẵn, dùng lại:**
- Vai `all` (`CloneRole.ALL`) được chọn ở cả `scout_task._pick_scout_clone`, `shooter_task._pick_shooter`, `publisher_service` → một clone đã đóng được mọi vai về mặt dữ liệu.
- Bump đi qua hàng đợi comment → chịu chung giãn cách `next_comment_at` + trần comment/ngày.
- `SerialJobQueue` tuần tự toàn cục → không có 2 thao tác Facebook song song.
- Attach CDP (`BROWSER_CDP_ENDPOINT`, `BrowserManager._attach_cdp_context`): không spoof vân tay, không proxy, chỉ ngắt kết nối khi dọn — đã chạy thật trên burner (comment, đăng bài, preflight, cào nhóm).
- Trần sẵn có: comment `daily_comment_limit` (20), đăng bài `daily_post_limit` (5), giãn cách comment theo chiến dịch.

**Lỗ hổng chặn chạy thật với 1 nick:**

| # | Mức | Lỗ hổng | Bằng chứng |
|---|---|---|---|
| L1 | nặng | Đường backend chưa bao giờ đăng nhập nick: cookie giải mã ghi plaintext ra `cookies.json` nhưng không mã nào đọc (không có `add_cookies`) | `workers/browser_runtime.py` `write_cookie_file` |
| L2 | nặng | `SerialJobQueue` không chống trùng: scheduler 60s xếp lại nhóm còn "đến hạn" trong khi lượt trước còn nằm trong hàng / đang chạy → 1 nick quét lặp cùng nhóm | `workers/job_queue.py`, `scheduler._dispatch_scout`; `last_scanned_at` chỉ cập nhật sau khi quét xong (`services/pipeline.py`) |
| L3 | nặng | Quét lỗi không dời mốc → nhóm đó bị thử lại mỗi 60s, mỗi lần một lượt mở trang | `scout_task._scan_one` nhánh `except` |
| L4 | vừa | Không có trần tổng lượt quét cho nick. Ví dụ 10 nhóm × chu kỳ 10 phút × 16 giờ ≈ 960 lượt tải trang nhóm/ngày trên chính nick đi comment | `schemas` `scan_interval_minutes` ge=3, không có trần theo nick |
| L5 | vừa | Scheduler chạy 24/7, không có khung giờ hoạt động | `workers/scheduler.py` |
| L6 | vừa | `warmup_task` ép `headless=True`, trái quyết định "không headless" | `workers/warmup_task.py:60` |
| L7 | nhẹ | Nick hỏng thì mọi dispatcher lặng lẽ `skipped`, không có thông báo "toàn hệ thống đã dừng" | `no_active_scout_clone`, `no_available_shooter_clone` |

## 3. Quyết định kiến trúc

### 3.1 Trình duyệt: Chrome thật, thư mục dữ liệu riêng cho tool, attach CDP, KHÔNG spoof

Với 1 nick, lựa chọn khác với nhiều nick:
- **Không vân tay giả.** Spoof chỉ để nhiều nick trên cùng máy trông khác nhau. Một nick → vân tay thật của máy là nhất quán nhất. UA cố định trong `fingerprint.json` còn lệch Client Hints thật khi Chrome tự cập nhật phiên bản.
- **Không proxy.** IP nhà, trùng IP anh Ber vẫn dùng Facebook hằng ngày.
- **Chrome sống lâu.** Mở tab làm việc rồi đóng tab; không bật/tắt Chrome cho mỗi job như chế độ persistent (hàng trăm lần/ngày, không giống người thật).
- **Dùng lại đường attach CDP** đã chạy thật trên burner.

Cách chạy:
- Backend (desktop-only) khởi chạy `chrome.exe` như **tiến trình thường, tách rời** (không qua Playwright launch — tránh bộ cờ mặc định của Playwright; tách rời để tắt app không giết Chrome giữa lúc ghi profile) với `--user-data-dir=<userData>/chrome-nick --remote-debugging-port=9222`.
- **Không dùng thư mục Chrome mặc định** của máy: Chrome 136+ bỏ qua remote debugging trên thư mục đó; copy riêng thư mục `Profile X` sang chỗ khác thì mất đăng nhập.
- Cổng 9222 đã có Chrome sống → dùng lại, không mở cái thứ hai (Chrome khoá thư mục dữ liệu).
- Anh Ber đăng nhập tay **một lần** trong cửa sổ đó (tự qua 2FA / checkpoint chính chủ).
- Endpoint CDP lưu vào `app_settings` (màn Cài đặt), nạp vào `Settings.browser_cdp_endpoint` lúc khởi động như OpenAI key / Telegram token.

Rủi ro còn lại (không phải "an toàn tuyệt đối"):
- Playwright qua CDP vẫn để lại dấu hiệu tự động hoá phát hiện được.
- Cổng debug trên máy → phần mềm độc hại trên chính máy đó điều khiển được phiên Facebook.
- Anh Ber lướt tay trong CHÍNH cửa sổ đó lúc tool chạy → tranh tab. Cửa sổ này chỉ để tool dùng; lướt cá nhân dùng Chrome thường.

### 3.2 Nick và trạng thái

- Một bản ghi clone, vai `all`. Màn desktop tạo sẵn khi chưa có (không bắt khách tự chọn vai).
- **Xác nhận đăng nhập thay cho nạp cookie**: nút "Kiểm tra kết nối" → `probe_session_reason` qua CDP:
  - `ok` → transition mới `LOGIN_VERIFIED` (thêm mới thay vì tái dùng `COOKIE_VALID` để log đúng nguồn); đích đến theo công tắc ủ ấm bên dưới.
  - `checkpoint` → `CHECKPOINT_DETECTED`.
  - chưa đăng nhập → giữ trạng thái, báo "chưa đăng nhập".
- Nạp cookie: giữ endpoint cho SaaS; **ẩn** khỏi màn desktop 1 nick. Attach CDP vốn đã bỏ qua ghi `cookies.json`.
- **Ủ ấm (warm-up)**: là lịch 7 ngày có sẵn từ Phase 3 (`services/warmup_service.py`) dành cho nick **mới tạo** — mỗi ngày 1 bài tập ngắn (lướt newsfeed, xem reels, like, comment thử, vào group, cuối cùng kiểm tra sức khoẻ) để nick trông như người thật trước khi đi làm việc. Trong 7 ngày đó nick ở `WARMING_UP`, scout chỉ lấy nick `ACTIVE` nên **không quét, không comment gì**. Với nick đã dùng thật thì lịch này vô nghĩa.
  - Chế độ 1 nick: **mặc định TẮT ủ ấm** — verify đăng nhập `ok` → transition mới `LOGIN_VERIFIED`: `ONBOARDING -> ACTIVE` (chỉ đi được khi chế độ 1 nick bật ủ ấm = tắt). Có công tắc "Nick mới tạo — bật ủ ấm 7 ngày" cho trường hợp đăng ký nick mới tinh; bật thì đi `ONBOARDING -> WARMING_UP` như cũ.
  - Chờ anh Ber xác nhận mặc định TẮT (ngưỡng anti-ban, CLAUDE.md §8).

### 3.3 Ngân sách hoạt động của 1 nick

Chốt với anh Ber 11/09/2026: **khung giờ do người dùng quyết định**, **trần quét tự tối ưu** — không có con số cứng do tool áp đặt.

**a) Khung giờ hoạt động — người dùng đặt**
- Màn Cài đặt: công tắc "Chỉ chạy trong khung giờ" + giờ bắt đầu / kết thúc (cho phép qua đêm, VD 20:00 – 02:00). Tắt = chạy cả ngày (đúng hành vi hiện tại).
- Ngoài khung: dispatcher không xếp job Facebook nào; job đang chạy thì cho xong. Health-check chỉ đọc DB vẫn chạy.

**b) Nhịp quét tự tối ưu — 2 vòng tự điều chỉnh, không có trần cố định**

Vòng 1 — theo từng nhóm ("nhóm nóng quét dày, nhóm nguội quét thưa"):
- Sàn = `scan_interval_minutes` khách đặt cho nhóm: không bao giờ quét nhanh hơn.
- Lượt quét có bài mới (`ingest_raw_posts` trả `fresh` ≥ 1) → chu kỳ nhóm về lại sàn.
- Lượt quét không có bài mới → chu kỳ giãn ×1.5, tối đa 8× sàn.
- Lượt quét lỗi → giãn như không có bài mới (vá luôn L3: không còn thử lại mỗi 60s).
- Lưu `current_scan_interval_minutes` + `next_scan_at` trên `campaign_groups` (migration `0008`); `is_due` đọc `next_scan_at` thay vì `last_scanned_at + scan_interval`.

Vòng 2 — theo sức khoẻ nick (hệ số giãn toàn cục, cùng kiểu `compute_delay` của comment):
- Tín hiệu xấu trong 24h: quét lỗi / không đọc được bài, comment `failed` / `shadowbanned`, `record_failure` của `AccountManager`.
- Có tín hiệu xấu → hệ số ×2 (tối đa ×8), nhân vào chu kỳ mọi nhóm. Chuỗi lượt ổn → hệ số ×0.8 dần về 1.
- Checkpoint vẫn đi state machine như cũ (dừng hẳn), vòng 2 chỉ xử lý vùng "bắt đầu có dấu hiệu".

Vì sao không cần trần lượt/giờ cố định: hàng đợi chạy tuần tự từng job (mỗi lượt quét mất thời gian mở trang + đọc), cộng sàn chu kỳ của khách, cộng nghỉ giữa job → tổng lượt quét tự bị chặn trên; 2 vòng trên chỉ làm thưa thêm khi nhóm nguội hoặc nick có dấu hiệu.

**c) Giữ nguyên**
- Nghỉ ngẫu nhiên giữa 2 job Facebook (người thật không chuyển việc tức thì).
- Comment 20/ngày + giãn cách chiến dịch; đăng bài 5/ngày — không đổi.

Hệ quả: với nhiều nhóm, 1 nick không giữ được "1–3 phút/nhóm" cho mọi nhóm cùng lúc; nhóm nóng được ưu tiên quét dày.

### 3.4 Hàng đợi: chống trùng + ưu tiên

- Mỗi job mang khoá (`scan:<group_id>`, `comment:<action_id>`, `publish:<id>`, `bump:<id>`, `warmup:<clone_id>`, `discover:<campaign_id>`). Khoá đang nằm trong hàng hoặc đang chạy → `enqueue` bỏ qua.
- Ưu tiên khi lấy job: comment/bump đến hạn > đăng bài > quét nhóm > cào nhóm > warm-up/health-check.
- Quét lỗi → dời mốc thử lại (dùng lại cơ chế đếm hỏng của `AccountManager`, thêm mốc `next_scan_at` hoặc cập nhật `last_scanned_at` kể cả khi lỗi — chọn khi làm, ưu tiên không cần migration).

### 3.5 Điểm hỏng duy nhất

- Nick rời `ACTIVE` (checkpoint / banned / cooldown) → mọi dispatcher dừng (đã tự nhiên vì không còn clone hợp lệ) + **đúng 1** thẻ Telegram "Toàn bộ tác vụ đã dừng vì nick <tên> <trạng thái>" lúc chuyển trạng thái, không gửi lại mỗi chu kỳ.
- Không tự thử lại. Anh Ber xử lý tay trong cửa sổ Chrome → bấm "Kiểm tra kết nối" → trở lại.
- Dashboard hiện dải trạng thái nick trên mọi trang.

## 4. Việc con (thứ tự làm)

1. `job_queue.py`: khoá chống trùng + ưu tiên; `scheduler.py` truyền khoá. (L2)
2. Nhịp quét tự tối ưu: migration `0008` (`current_scan_interval_minutes`, `next_scan_at` trên `campaign_groups`), vòng 1 theo nhóm + vòng 2 theo sức khoẻ nick, hàm thuần trong `services/anti_ban.py` để test offline. (L3, L4)
3. Khung giờ người dùng đặt: `app_settings` + guard trong `scheduler.py`. (L5)
4. `services/single_nick_service.py` (mới): tìm `chrome.exe`, khởi chạy tách rời / tái dùng cổng, kiểm kết nối; router desktop-only (theo mẫu `routers/settings.py`): `POST /api/nick/open-browser`, `POST /api/nick/verify`. (L1)
5. `AccountTransition.LOGIN_VERIFIED` + công tắc ủ ấm (mặc định tắt ở chế độ 1 nick). (L1)
6. Thông báo "toàn hệ thống dừng" một lần. (L7)
7. `warmup_task`: bỏ `headless=True`, theo cấu hình. (L6)
8. Frontend: màn "Nick" desktop (Mở Chrome / Kiểm tra kết nối / trạng thái / công tắc ủ ấm), dải trạng thái, ẩn nạp cookie ở desktop; khung giờ trong Cài đặt; hiện chu kỳ quét thực tế của từng nhóm ở màn chiến dịch.
9. `DELIVERY_STATUS.md`, `README.md`.

## 5. Tiêu chí nghiệm thu (viết trước khi code)

| Tiêu chí | Lệnh kiểm |
|---|---|
| Enqueue cùng khoá 2 lần khi job đầu chưa xong → job chạy đúng 1 lần; khoá nhả sau khi xong (kể cả job lỗi) | `.venv\Scripts\python.exe backend/tests/test_api.py` PASS |
| Có comment đến hạn và quét nhóm cùng trong hàng → comment chạy trước | như trên |
| Khung giờ bật, giờ hiện tại ngoài khung (kể cả khung qua đêm) → `_dispatch_scout/_shooter/_publisher/_bump` không xếp job nào; công tắc tắt → chạy như cũ | như trên, kiểm đột biến (gỡ guard khung giờ → phải đỏ) |
| Nhịp quét: có bài mới → chu kỳ về sàn; không bài mới / lỗi → ×1.5, không vượt 8× sàn, không bao giờ dưới sàn; tín hiệu xấu → hệ số ×2 (≤ ×8), lượt ổn → ×0.8 về 1 | như trên, kiểm đột biến (`max`↔`min` ở sàn, bỏ nhánh lỗi → phải đỏ) |
| Probe `ok` + ủ ấm tắt → `ONBOARDING -> ACTIVE`; ủ ấm bật → `WARMING_UP`; `checkpoint` → `CHECKPOINT`; chưa đăng nhập → giữ nguyên; nick rời ACTIVE → đúng 1 thông báo | như trên, kiểm đột biến |
| Cổng 9222 đã sống → `open-browser` không spawn tiến trình mới; SaaS → router 404 | như trên (mock subprocess + HTTP) |
| Frontend | `cd frontend; npx tsc --noEmit` 0 lỗi · `npx next build` 0 lỗi |
| Chạy thật (xin phép riêng từng bước) | burner: mở Chrome → đăng nhập tay → verify → quét 1 nhóm (chỉ đọc). Comment thật chỉ khi anh Ber đồng ý, dọn comment sau test |

## 6. Cần anh Ber chốt trước khi code

- Đã chốt 11/09/2026: khung giờ do người dùng đặt; nhịp quét tự tối ưu (mục 3.3).
- Còn chờ: xác nhận ủ ấm **mặc định tắt** ở chế độ 1 nick (mục 3.2).
