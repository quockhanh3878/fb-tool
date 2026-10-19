# KẾ HOẠCH HOÀN THIỆN — Community Marketing & Lead Monitor (chạy trên laptop)

> Cập nhật: 23/09/2026 (anh Ber đã chốt Q1–Q4, xem §6) · Trạng thái: **Đang triển khai** (M1a, M1b offline, M2, M4 và M5 mô phỏng đã có mã/test; M3/M6 đã có phần mã và gate offline; M7/live còn chờ) · Khách mục tiêu: Nyatymita (vẽ comm)
>
> Nguồn yêu cầu: bản chuyển JD cộng tác viên thành 8 job tự động (`PR_POST`, `PR_BUMP`, `LEAD_SCAN`, `LEAD_MATCH`, `LEAD_REPLY`, `PAGE_MONITOR`, `HANDOFF`, `HEALTH_CHECK`) do anh Ber gửi ngày 23/09/2026.
> Đọc kèm: `DELIVERY_STATUS.md` (cái gì đã xong thật), `phase3_antiban_detail.md` (ngưỡng anti-ban), `desktop_packaging.md` (runtime desktop).

---

## 1. Mục tiêu

Người vận hành **không phải ngồi canh Facebook**. App desktop tự chạy các tác vụ lặp lại, chỉ đẩy thông báo khi có việc cần người: lead mới, khách phản hồi, hoặc lỗi. Discord là "hộp thư cảnh báo" trên điện thoại; Telegram giữ nguyên cho nút duyệt bán tự động. Lead có **2 mode tách biệt**, chọn theo chiến dịch: **Tự comment** — lead đúng điều kiện thì app tự ứng comm bằng kịch bản có sẵn rồi báo kết quả; **Thông báo** — app chỉ báo về bot khi phát hiện người đang cần tìm dịch vụ, người vận hành tự xử lý. Đơn hàng vẫn xử lý trên Nyatymita — app **không** đụng tới đơn.

Kiến trúc chốt: 3 worker độc lập dùng chung một cổng thông báo, không làm một agent khổng lồ.

```text
PR Worker ............ PR_POST, PR_BUMP
Lead Hunter .......... LEAD_SCAN -> LEAD_MATCH -> LEAD_REPLY
Interaction Watcher .. PAGE_MONITOR
        |
        v
Notification Gateway (HANDOFF / ERROR) --> Discord webhook  (+ Telegram như hiện tại)
        ^
HEALTH_CHECK (giám sát cả 3 worker + session nick)
```

---

## 2. Đối chiếu 8 job với mã đã có

Phần lớn đã có mã chạy được. Việc chính là **nối cho khép kín + thêm Discord + thêm Interaction Watcher**, không viết lại.

| Job | Đã có (mã + test) | Còn thiếu | Mức việc |
|---|---|---|---|
| `PR_POST` | `publisher_service.execute_publish`, lặp mặc định 14 ngày, kho ảnh ≤10 ảnh, lịch sử permalink (`post_publish_history`), jitter giờ đăng | Chặn đăng trùng cùng nội dung vào cùng nhóm trong cửa sổ lặp; báo HANDOFF/ERROR qua gateway | nhỏ |
| `PR_BUMP` | `bump_task` khung 10/17/19/21, jitter, quota, giãn cách chung hàng đợi comment | Kiểm bài còn sống trước khi bump (bị xoá/khoá/tắt comment thì dừng bump + báo); tự lấy URL bài PR mới nhất từ lịch sử publish thay vì nhập tay | vừa |
| `LEAD_SCAN` | `scout_task._scan_one` quét nhóm + quét comment theo `lead_keywords`, dedup `content_hash` / `fb_comment_id` | Ghi nhật ký lượt chạy (`job_runs`) | nhỏ |
| `LEAD_MATCH` | AI chấm `relevance_score`, ngưỡng `min_relevance_score`, blacklist/whitelist | Vùng **không chắc chắn** (`need_review`): ở mode Tự comment, điểm lưng chừng thì không comment, chuyển thông báo cho người | vừa |
| `LEAD_REPLY` | `full_auto` tự xếp hàng comment, xoay kịch bản + Jaccard 0.82, giãn cách comment; `semi_auto` gửi thông báo Telegram | Đặt tên rõ 2 mode (Tự comment / Thông báo); mode Tự comment báo **kết quả** sau khi comment xong (kịch bản đã dùng + link comment) | nhỏ |
| `PAGE_MONITOR` | Không có. Hiện chỉ quét comment trên bài Scout vừa thấy trong nhóm | **Worker mới**: theo dõi comment mới trên bài PR của chính mình + trả lời vào comment ứng tuyển của mình | lớn |
| `HANDOFF` | Telegram qua `notification_outbox` (có retry, dedup), liên kết người nhận bằng `/start <mã>` | Discord (webhook kênh + bot nhắn riêng), danh sách người tiếp nhận (điền ID tay hoặc tự đăng ký với bot), mẫu thẻ chuẩn | lớn |
| `HEALTH_CHECK` | `health_check_task`, `preflight_service`, watchdog desktop, state machine nick | Phát hiện job **không chạy** (quá hạn), ngắt mạch khi lỗi liên tiếp theo từng job, báo ERROR qua Discord | vừa |

**Ngoài phạm vi đợt này:** tin nhắn Messenger / hộp thư Page — anh Ber tạm hoãn (§6, Q2).

---

## 3. Các mốc triển khai

Mỗi mốc là một diff tự đứng được, test offline trước, không cần Facebook. Chỉ mốc M7 đụng Facebook thật và phải được anh Ber duyệt trong chính phiên đó.

### M0 — Đo nền (0.5 ngày)

- Q1–Q4 đã chốt (§6).
- Chạy bộ test hiện có, ghi số thật làm mốc so sánh.
- Nghiệm thu: bộ test backend + `commhunter/tests/test_pipeline.py` xanh trước khi sửa gì.

### M1a — Notification Gateway + Discord webhook kênh (2 ngày)

- Thêm cột `channel` (`telegram` | `discord_webhook` | `discord_dm`) vào `notification_outbox` (migration `0014`, `server_default='telegram'` để dữ liệu cũ không vỡ). `chat_id` dùng làm đích chung (chat id Telegram / định danh webhook / Discord user ID).
- Bảng `notification_recipients` (cùng migration): `channel`, `recipient_id`, `display_name`, `event_types` (JSON: lead / khách phản hồi / lỗi), `source` (`manual` | `bot_registered`), `verified_at`, `is_active`. Đây là nguồn duy nhất trả lời "gửi cho ai".
- Service mới `discord_service.py`: gửi qua **Discord webhook URL**. Webhook lưu trong `app_settings`, **mã hoá** qua `services/crypto.py` như secret khác, không log URL.
- Worker outbox hiện có gửi theo `channel`; giữ retry/backoff/dedup cũ. HTTP 429 của Discord tôn trọng `retry_after`.
- Hàm dùng chung `notify_handoff(event_type, summary, source, occurred_at, link)` và `notify_error(...)` trong `notification_service` — tự tra `notification_recipients` theo `event_type` rồi xếp outbox cho từng kênh. Mọi worker gọi qua đây, không gọi thẳng HTTP.
- **Điền ID tay (Q4, cách 1):** người vận hành dán Discord user ID trên dashboard → bản ghi `source=manual`. Trên thẻ webhook kênh, người đó được mention `<@user_id>` để điện thoại rung.
- Thẻ Discord (embed) gồm đúng 6 trường yêu cầu: Loại sự kiện · Tóm tắt · Nguồn · Thời gian · Người tiếp nhận · Link trực tiếp. Tóm tắt lấy từ DOM Facebook là đầu vào không tin cậy: cắt độ dài, vô hiệu `@everyone`/`@here` (`allowed_mentions` chỉ cho phép đúng người tiếp nhận).
- Nghiệm thu:
  - Cho một sự kiện lead, Khi gateway dựng payload, Thì embed có đủ 6 trường và `allowed_mentions.users` chỉ chứa người tiếp nhận đăng ký loại `lead` → `backend/tests/test_notification_gateway.py` PASS.
  - Nội dung chứa `@everyone` không ping cả server (kiểm payload) → cùng file.
  - Webhook trả 429 → outbox hoãn theo `retry_after`, không đánh dấu `sent` → cùng file; kiểm đột biến bỏ nhánh 429 phải đỏ.
  - `alembic upgrade head` và `downgrade -1` sạch.

### M1b — Discord bot nhắn riêng + tự đăng ký (2 ngày)

> Trạng thái hiện tại: luồng DM `/dangky <mã>` và `/huy` đã triển khai/test offline. Desktop-only `POST /api/settings/discord-link-code` sinh mã một lần. Bot đọc `DISCORD_BOT_TOKEN` từ môi trường, không lưu token trong repo; Gateway live chờ tiến trình desktop nhận được biến môi trường.

- **Cấu hình bot (Q4, cách 2):** người vận hành dán Discord bot token (mã hoá qua `crypto.py`) trên dashboard. Người nhận tự đăng ký với bot, không cần ai tra ID hộ.
- Luồng đăng ký, theo khuôn `/start <mã>` của Telegram đã có: dashboard sinh mã đăng ký ngắn hạn (dùng 1 lần, hết hạn) → người nhận nhắn bot `/dangky <mã>` (slash command hoặc tin nhắn riêng) → backend ghi `notification_recipients` với `source=bot_registered`, `channel=discord_dm` → bot trả lời xác nhận. Có `/huy` để tự huỷ nhận tin.
- Máy local không có URL public, nên bot nhận lệnh qua **kết nối Gateway đi ra** (giống lý do Telegram dùng long-polling ở desktop). Chạy như worker desktop cạnh `telegram_poller.py`, bật/tắt theo `RUN_MODE=desktop` + có token.
- Thư viện: đọc tài liệu Discord hiện hành trước khi code (intent tối thiểu cho tin nhắn riêng + slash command, điều kiện bot được nhắn riêng người dùng). Nếu thêm thư viện (vd `discord.py`) phải kiểm không phá pin trong `backend/requirements.txt`.
- Gửi tin riêng thất bại (người nhận chặn tin nhắn, không còn chung server) → rơi về webhook kênh + ghi lỗi, không mất thông báo.
- Nghiệm thu:
  - Mã đăng ký đúng → tạo đúng 1 người nhận; mã sai / hết hạn / dùng lần 2 → từ chối → `backend/tests/test_discord_bot.py` PASS; đột biến bỏ kiểm hết hạn phải đỏ.
  - Gửi DM lỗi 403 → outbox xếp thêm bản webhook kênh → cùng file.
  - Không có token → worker bot không khởi động, app vẫn chạy bình thường → cùng file.

### M2 — Job registry + HEALTH_CHECK (2 ngày)

> Trạng thái hiện tại: lõi durable `job_runs`, circuit breaker và kiểm tra job quá hạn đã triển khai/test offline. Scheduler đã có nhịp gọi HEALTH_CHECK; phần soak/live worker còn để M7.

- Bảng `job_runs` (job_name, started_at, finished_at, status, counts JSON, error). 8 tên job là hằng số trong một enum `JobName`; các dispatch trong `workers/scheduler.py` bọc qua một helper ghi `job_runs` (một chỗ, không rải ở từng task).
- `HEALTH_CHECK` mở rộng `health_check_task`:
  - Job quá hạn (không có lượt thành công trong `2 × chu kỳ`) → ERROR "job không chạy".
  - **Ngắt mạch theo job**: N lỗi liên tiếp (N người dùng đặt, mặc định 3) → tạm dừng job đó, ERROR, chờ người vận hành bấm chạy lại trên dashboard. Không tự thử mù.
  - Mất session / checkpoint / CAPTCHA đã có ở state machine nick → chỉ cần đẩy thêm qua `notify_error`.
- Nghiệm thu:
  - Cho job `PR_BUMP` lỗi 3 lần liên tiếp, Thì job chuyển `paused` và có đúng 1 ERROR trong outbox (dedup) → `backend/tests/test_job_health.py` PASS; đột biến `>=`→`>` phải đỏ.
  - Cho `LEAD_SCAN` không chạy 2 chu kỳ, Thì phát ERROR "job không chạy" → cùng file.

### M3 — PR Worker khép kín (2 ngày)

- `PR_POST`: chặn đăng trùng — cùng `content_hash` + cùng nhóm trong cửa sổ lặp thì bỏ qua, ghi lý do. App **không** sửa nội dung PR (không cho AI viết lại bài PR; chỉ spintax người dùng soạn).
- `PR_BUMP`:
  - Bump tự trỏ tới permalink PR mới nhất trong `post_publish_history` của chiến dịch (lựa chọn nhập tay vẫn giữ).
  - Trước khi bump: kiểm bài còn sống (tái dùng `POST_GONE_MARKERS` + dấu hiệu tắt bình luận). Chết/khoá → đánh dấu bump `inactive`, ERROR kèm link, **không** comment.
- Nghiệm thu:
  - Cho bài đã xoá (DOM giả chứa marker), Khi đến giờ bump, Thì không có comment nào được xếp hàng và bump chuyển `inactive` → `backend/tests/test_pr_worker.py` PASS; gỡ guard phải đỏ.
  - Cho 2 lượt publish cùng nội dung cùng nhóm trong 14 ngày, Thì lượt 2 bị bỏ qua với lý do `duplicate_pr` → cùng file.

### M4 — Lead Hunter 2 mode + vùng không chắc chắn (1.5 ngày)

Anh Ber chốt (Q3): đây là **2 mode khác nhau**, chọn theo chiến dịch, dùng lại `CampaignMode` đã có — không thêm cột mới:

| Mode (tên trên dashboard) | Giá trị | Hành vi |
|---|---|---|
| **Tự comment** | `full_auto` | Lead đúng điều kiện → app tự xếp hàng comment bằng kịch bản đang bật (qua đủ quota, giãn cách, xoay kịch bản, Jaccard 0.82). Comment xong → thông báo **kết quả**: "Đã ứng theo kịch bản X" + link bài + link comment |
| **Thông báo** | `semi_auto` | Phát hiện người đang cần tìm dịch vụ → gửi thông báo về bot (Telegram + Discord) kèm link bài; app không tự comment, người vận hành tự xử lý |

- "Đúng điều kiện" ở mode Tự comment = điểm AI ≥ `min_relevance_score` **và** có kịch bản đang bật **và** nick/quota cho phép.
- **Vùng không chắc chắn** (theo yêu cầu gốc: "không chắc thì không tự quyết"): thêm ngưỡng `review_floor` người dùng đặt trên chiến dịch. Điểm trong `[review_floor, min_relevance_score)` → `PostStatus.NEED_REVIEW = "need_review"`, **không** comment, gửi thông báo "cần người xem". Không có kịch bản đang bật → cũng chuyển `need_review`, không tự sinh câu mới. Dưới `review_floor` → bỏ như hiện tại.
- Migration `0015` cho `campaigns.review_floor` (có `server_default`); `need_review` chỉ cần migration nếu cột trạng thái bị ràng buộc enum — kiểm khi hiện thực.
- Nghiệm thu:
  - Cho chiến dịch `full_auto`, ngưỡng 0.7, lead điểm 0.9 có kịch bản, Thì có đúng 1 `comment_actions` được xếp hàng → `backend/tests/test_lead_modes.py` PASS.
  - Cùng chiến dịch, lead điểm 0.6 với `review_floor` 0.5, Thì không có `comment_actions` mới, post ở `need_review`, có 1 thông báo "cần người xem" → cùng file; đột biến biên `<`↔`<=` phải đỏ.
  - Cho chiến dịch `semi_auto`, lead điểm 0.95, Thì không có `comment_actions` mới và có 1 thông báo phát hiện → cùng file.
  - Comment tự động thành công → outbox có thông báo kết quả chứa tên kịch bản + link comment → cùng file.
  - `alembic upgrade head` / `downgrade -1` sạch.

### M5 — Interaction Watcher: `PAGE_MONITOR` (3–4 ngày)

> Trạng thái hiện tại: phần lọc/lưu/HANDOFF đã triển khai và kiểm chứng offline. Bài test dùng link tổng hợp trong repo, lookback 1 ngày, không ghi lên Facebook; selector/live wiring vẫn để bước sau.

- Worker mới `workers/interaction_task.py` (+ service `interaction_service.py`), chu kỳ người dùng đặt (mặc định 15 phút, có jitter).
- Nguồn theo dõi, chỉ **đọc**:
  1. Bài PR của mình còn trong cửa sổ theo dõi (từ `post_publish_history`, mặc định 14 ngày).
  2. Bài có comment ứng tuyển của mình (`comment_actions.comment_url`) → bắt **trả lời** vào comment đó ("khách phản hồi" / "người đăng bài phản hồi").
- Tái dùng extractor `scrape_post_comments_raw`; loại comment của chính mình (`own_fb_id`); dedup theo `fb_comment_id` (bảng `interactions` mới hoặc mở rộng `comment_leads` — chọn khi đọc code ở bước hiện thực, ưu tiên tái dùng).
- Mỗi tương tác mới → HANDOFF **ngay**, kèm link comment.
- Tôn trọng anti-ban: dùng chung lease trình duyệt + hàng đợi tuần tự desktop, không mở song song với scout/shooter; giới hạn số bài mở mỗi lượt.
- Selector không khớp → trả rỗng + ERROR một lần (dedup), không tạo tương tác giả.
- Nghiệm thu:
  - Cho DOM giả có 2 comment người khác + 1 comment của mình, Thì tạo đúng 2 tương tác và 2 HANDOFF; chạy lại lần 2 tạo 0 → `backend/tests/test_interaction_watcher.py` PASS.
  - Cho trả lời vào comment ứng tuyển của mình, Thì loại sự kiện là "khách phản hồi" → cùng file.
  - Extractor gặp DOM lạ → 0 tương tác, 1 ERROR → cùng file.

### M6 — Dashboard (2 ngày)

- `/settings`: thẻ Discord — dán webhook kênh, dán bot token, nút "Tạo mã đăng ký", danh sách người tiếp nhận (thêm ID tay / thấy người tự đăng ký, chọn loại sự kiện từng người, tắt/xoá), nút "Gửi thử". Trên trang chiến dịch, mode hiển thị bằng lời thường: "Tự comment khi đúng điều kiện" / "Chỉ thông báo khi phát hiện khách", kèm ô `review_floor` giải thích thành "dưới mức này thì bỏ, từ mức này tới ngưỡng comment thì hỏi người".
- Route mới `/jobs`: 8 job, lần chạy gần nhất, trạng thái, lỗi gần nhất, nút tạm dừng/chạy lại (gỡ ngắt mạch).
- `/leads` + `/posts`: bộ lọc `need_review` + "đã tự ứng"; hiển thị tương tác từ Interaction Watcher.
- Mọi gọi API qua `lib/api.ts`, dùng lại `components/ui.tsx`.
- Nghiệm thu: `cd frontend; npx tsc --noEmit` = 0 lỗi · `npx next build` 0 lỗi (số route tăng thêm 1) · kiểm tay nút "Gửi thử" tới webhook test của anh Ber.

### M7 — Chạy thật + đóng gói (2 ngày + soak)

- **Cần anh Ber duyệt rõ trong phiên**: E2E trên nick phụ + nhóm burner `1042987808508567` qua CDP 9222 — đăng PR → bump → comment test từ nick khác → Interaction Watcher bắt được → thẻ Discord tới điện thoại. Dọn sạch bài/comment test.
- Build lại `.exe`, chạy trong thư mục cách ly, soak 24 giờ **không đụng Facebook** (job chạy với runtime giả) để kiểm HEALTH_CHECK + watchdog.
- Cập nhật `DELIVERY_STATUS.md`, `README.md`, `desktop_user_guide.md` (cách tạo Discord webhook).

**Tổng ước tính:** ~16 ngày làm việc, chưa tính thời gian chờ duyệt E2E và soak.

---

## 4. Luật cứng (map từ mục NEVER của yêu cầu)

Mỗi luật có test canh, không chỉ nằm trên giấy:

| Luật | Cách cưỡng chế |
|---|---|
| Không tự đổi giá / nội dung PR | Publisher chỉ dùng nội dung người dùng soạn; không có đường AI viết lại bài PR (test M3) |
| Không tự tạo kịch bản ứng tuyển mới | Mode Tự comment chỉ dùng kịch bản đang bật; không có kịch bản → `need_review`, không sinh câu mới (test M4) |
| Không cam kết với khách / không xử lý đơn | App chỉ ứng comm lần đầu trên bài tìm dịch vụ; không trả lời inbox, không trả lời tiếp khi khách phản hồi — mọi phản hồi của khách đi HANDOFF (M5) |
| Không chắc thì không làm | Vùng `need_review` (M4), selector lạ → dừng + ERROR (M5), ngắt mạch theo job (M2) |
| Không spam | Giữ nguyên quota, giãn cách, Jaccard 0.82, warm-up. Không nâng trần để test |

---

## 5. Rủi ro

- **Selector Facebook đổi** — rủi ro lớn nhất cho `PAGE_MONITOR` và kiểm bài sống của `PR_BUMP`. Giảm thiểu: fail an toàn + ERROR + test DOM giả; bảo trì selector theo đợt.
- **Tăng số lần mở trình duyệt** — Interaction Watcher thêm lượt đọc mỗi chu kỳ. Giảm thiểu: chu kỳ dài, giới hạn bài/lượt, dùng chung lease, không chạy song song.
- **Discord webhook / bot token lộ** = người ngoài gửi được tin vào kênh hoặc điều khiển bot. Giảm thiểu: mã hoá lưu trữ, không log, có nút đổi.
- **Người lạ tự đăng ký với bot** để nhận thông tin lead. Giảm thiểu: chỉ đăng ký được bằng mã do dashboard sinh, dùng 1 lần, có hạn; người vận hành thấy và xoá được mọi người nhận.
- **Kết nối Gateway Discord rớt** trên laptop. Giảm thiểu: tự nối lại có backoff; gửi tin đi vẫn qua REST/webhook nên thông báo không phụ thuộc kết nối nhận lệnh; HEALTH_CHECK báo nếu rớt lâu.
- **Ngưỡng `review_floor` / chu kỳ quét** chưa có dữ liệu thật — để người dùng đặt, mặc định dè dặt, hiệu chỉnh sau M7.

---

## 6. Quyết định đã chốt (anh Ber, 23/09/2026)

- **Q1 — Kênh thông báo:** giữ cả hai. Discord nhận cảnh báo; Telegram giữ nút Duyệt/Bỏ qua.
- **Q2 — Messenger / hộp thư Page:** tạm hoãn. Đợt này chỉ theo dõi comment.
- **Q3 — `LEAD_REPLY`:** 2 mode khác nhau theo chiến dịch (M4). **Tự comment**: lead đúng điều kiện thì app tự ứng comm bằng kịch bản có sẵn, rồi báo kết quả. **Thông báo**: app chỉ gửi về bot khi phát hiện người đang cần tìm dịch vụ. Lead lưng chừng ở mode Tự comment → không comment, báo người xem.
- **Q4 — Người tiếp nhận:** hỗ trợ cả hai cách — điền Discord user ID tay (M1a), hoặc cấu hình bot để người nhận tự đăng ký và nhận tin nhắn riêng (M1b). Mỗi người nhận chọn loại sự kiện muốn nhận.
