# Kịch Bản Các Trường Hợp Lỗi & Cẩm Nang Xử Lý Sự Cố (Error Scenarios & Troubleshooting Guide)

> Tài liệu kỹ thuật phục vụ vận hành, giám sát và xử lý sự cố cho CommHunter AI (chế độ Desktop và SaaS).
> Phiên bản: 1.0.0 — Cập nhật: 2026-09-12.
> Quy tắc bất biến: An toàn tài khoản là ưu tiên số một. Mọi sự cố không rõ ràng phải chọn nhánh an toàn (Fail-Safe), dừng thao tác ghi, không đoán bừa.

---

## 1. Nguyên Tắc An Toàn Cốt Lõi (Fail-Safe Principles)

1. **Không giả lập permalink**: Khi bài đăng lên nhóm chưa lấy được link bài thật (do chờ duyệt hoặc Facebook chưa cập nhật feed), hệ thống tuyệt đối không sinh link ngẫu nhiên. Trạng thái được giữ là `published_no_url`.
2. **Ngắt toàn bộ khi gặp Checkpoint**: Phát hiện dấu hiệu checkpoint lập tức dừng mọi tác vụ quét bài, bình luận, đẩy bài và đăng bài. Cách ly nick tối thiểu 48 giờ.
3. **Tuân thủ hạn mức ngày (Daily Quota)**: Quota đăng bài và quota bình luận là chốt chặn cứng. Khi chạm hạn mức, các nhóm còn lại tự động chuyển sang `skipped_quota`, không cố vượt trần.
4. **Cô lập dữ liệu cục bộ**: Phiên bản desktop sử dụng SQLite độc lập tại máy khách, không gửi dữ liệu tài khoản hay cookie về bất kỳ máy chủ trung tâm nào.

---

## 2. Nhóm 1: Lỗi Nghiệp Vụ Đăng Bài Nhóm & Auto-Bump Bình Luận

### Kịch bản 1.1: Bài viết rơi vào hàng đợi chờ duyệt (Pending Admin Approval)
- **Mã sự cố**: `PUB-ERR-01`
- **Mức độ**: [Vừa]
- **Triệu chứng**: Sau khi nhấn đăng bài vào nhóm, Facebook hiển thị thông báo "Bài viết của bạn đã được gửi đến quản trị viên". Trình duyệt không điều hướng đến permalink bài viết (`post_url = None`).
- **Cơ chế tự xử lý của hệ thống**:
  - `publisher_service` gán trạng thái nhóm mục tiêu là `published_no_url`.
  - Tính 1 lượt vào bộ đếm `daily_post_count` của nick (vì hành vi ghi đã gửi lên Facebook).
  - Tạm thời chưa khởi tạo bản ghi `BumpSchedule` cho bài viết này để tránh việc bình luận vào một URL không tồn tại.
- **Quy trình xử lý thủ công (SOP)**:
  1. Khi quản trị viên nhóm duyệt bài, truy cập vào nhóm lấy đường link bài viết thật (dạng `https://www.facebook.com/groups/<group_id>/posts/<post_id>/`).
  2. Vào Dashboard -> chọn Chiến dịch -> mở tab **Lịch bump tự động**.
  3. Dán link bài viết vào ô mục tiêu, chọn khung giờ mặc định (10h, 14h, 18h, 21h) và nhấn **Tạo lịch bump**.

---

### Kịch bản 1.2: Bài viết đã đăng bị gỡ hoặc nhóm Facebook bị khoá
- **Mã sự cố**: `PUB-ERR-02`
- **Mức độ**: [Nhẹ]
- **Triệu chứng**: Đến khung giờ bump (10h, 14h, 18h, 21h), tiến trình bump truy cập link bài viết thì nhận thông báo "Nội dung này hiện không khả dụng" hoặc nhóm đã bị quản trị viên lưu trữ.
- **Cơ chế tự xử lý của hệ thống**:
  - Worker `bump_task` không tìm thấy hộp soạn bình luận.
  - Bắt ngoại lệ `ElementNotFoundError`, ghi nhận trạng thái lượt bump là `skipped: invalid_message` hoặc `failed`.
  - Không cố gắng lặp lại liên tục; chờ đến khung giờ kế tiếp để tránh phát sinh request bất thường.
- **Quy trình xử lý thủ công (SOP)**:
  - Vào Dashboard -> tab **Lịch bump tự động**, tìm dòng chứa URL bài viết bị lỗi và bấm **Xoá** hoặc **Tạm dừng**.

---

### Kịch bản 1.3: Chạm hạn mức đăng bài trong ngày (`daily_post_limit`)
- **Mã sự cố**: `PUB-ERR-03`
- **Mức độ**: [Nhẹ]
- **Triệu chứng**: Chiến dịch có 8 nhóm cần đăng, nhưng nick clone chỉ còn quota đăng 5 bài trong ngày.
- **Cơ chế tự xử lý của hệ thống**:
  - Đăng thành công 5 nhóm đầu tiên.
  - 3 nhóm còn lại được gắn trạng thái `skipped_quota` với lý do "Đã đạt hạn mức đăng bài trong ngày của nick".
  - Trạng thái chung của bài đăng chuyển thành `partially_published` (Đăng một phần).
  - Chu kỳ lặp lại 14 ngày kế tiếp vẫn được tạo mới ở trạng thái `SCHEDULED` để tiếp tục ở kỳ sau.
- **Quy trình xử lý thủ công (SOP)**:
  - Không cần can thiệp. Hệ thống tự bảo vệ nick khỏi bị Facebook đánh giá là spam hàng loạt.

---

### Kịch bản 1.4: Mẫu nội dung Spintax quá đơn điệu bị nghi ngờ spam
- **Mã sự cố**: `PUB-ERR-04`
- **Mức độ**: [Vừa]
- **Triệu chứng**: Đăng liên tiếp vào 3 nhóm thì Facebook xuất hiện popup "Bạn đang chia sẻ quá nhanh, vui lòng thử lại sau".
- **Cơ chế tự xử lý của hệ thống**:
  - Bộ kiểm tra Spintax linting cảnh báo trước nếu tổng số biến thể khả thi < 10.
  - Khi gặp popup chặn, tiến trình dừng ngay việc đăng vào các nhóm còn lại, ghi log lỗi `rate_limited` và đưa nick vào trạng thái nghỉ.
- **Quy trình xử lý thủ công (SOP)**:
  1. Mở phần soạn bài trong **Publishing Studio**.
  2. Bổ sung các cụm từ đồng nghĩa dạng `{Chào mọi người|Hello cả nhà|Chào các bạn}` để số biến thể khả thi đạt tối thiểu 50.

---

## 3. Nhóm 2: Lỗi Tài Khoản Facebook & Cơ Chế Chống Ban (Anti-Ban Engine)

### Kịch bản 2.1: Tài khoản dính Checkpoint (Xác minh danh tính)
- **Mã sự cố**: `ACC-ERR-01`
- **Mức độ**: [Nghiêm trọng]
- **Triệu chứng**: Trình duyệt bị chuyển hướng đến các đường dẫn chứa `/checkpoint/` hoặc trang xuất hiện tiêu đề "Hãy giúp chúng tôi xác minh danh tính của bạn".
- **Cơ chế tự xử lý của hệ thống**:
  - `account_manager` kích hoạt sự kiện `CHECKPOINT_DETECTED`.
  - Nick chuyển ngay sang trạng thái `checkpoint`.
  - Thu hồi toàn bộ quyền quét (scout), bình luận (shooter) và đăng bài (poster) của nick.
  - Thiết lập thời gian cách ly bắt buộc tối thiểu 48 giờ (`cooldown_until = now + 48h`).
- **Quy trình xử lý thủ công (SOP)**:
  1. Bật cửa sổ Chrome debug có profile của nick.
  2. Tự tay vượt qua các bước xác minh chính chủ (nhận mã OTP, chọn ảnh bạn bè, đổi mật khẩu).
  3. Sau khi vào lại Facebook bình thường, vào Dashboard bấm **Kiểm tra kết nối** để chuyển trạng thái nick về `active`.

---

### Kịch bản 2.2: Bị chặn tính năng bình luận tạm thời (Action Blocked)
- **Mã sự cố**: `ACC-ERR-02`
- **Mức độ**: [Nghiêm trọng]
- **Triệu chứng**: Thao tác gửi comment bị Facebook từ chối kèm thông báo "Tính năng này tạm thời bị chặn đối với tài khoản của bạn".
- **Cơ chế tự xử lý của hệ thống**:
  - Bộ kiểm chứng 3 chiều (Verify Phrase) phát hiện nội dung comment vẫn còn kẹt trong ô nhập liệu.
  - Đánh dấu lượt comment là `FAILED`, tăng bộ đếm lỗi liên tiếp (`consecutive_failures`).
  - Khi đạt 3 lỗi liên tiếp, tự động chuyển nick sang trạng thái `cooldown` nghỉ từ 4 đến 8 giờ.
- **Quy trình xử lý thủ công (SOP)**:
  - Vào phần cấu hình chiến dịch, tăng độ giãn cách tối thiểu giữa 2 comment (`delay_min_seconds` >= 300 giây = 5 phút).
  - Giảm `max_comments_per_day` xuống dưới 15 comment/ngày.

---

### Kịch bản 2.3: Bình luận bị ẩn ngầm (Shadowban)
- **Mã sự cố**: `ACC-ERR-03`
- **Mức độ**: [Vừa]
- **Triệu chứng**: Tool báo đã bình luận thành công, tài khoản clone vẫn nhìn thấy bình luận dưới bài viết, nhưng người ngoài hoặc tab ẩn danh không nhìn thấy.
- **Cơ chế tự xử lý của hệ thống**:
  - Hàm `verify_comment_visible` kiểm tra sự tồn tại của cụm từ ngẫu nhiên (Verify Phrase) từ góc nhìn công khai.
  - Khi không tìm thấy, hệ thống ghi nhận trạng thái `SHADOWBANNED`.
  - Tự động đẩy thời gian giãn cách giữa các comment lên mức trần tối đa (1800 giây = 30 phút).
- **Quy trình xử lý thủ công (SOP)**:
  1. Kiểm tra lại nội dung bình luận mẫu: loại bỏ các link ngoài (`http/https`), số điện thoại, hoặc từ ngữ bị Facebook liệt vào danh sách đen.
  2. Điều hướng khách hàng về website thông qua việc tìm kiếm thương hiệu thay vì để link trần.

---

### Kịch bản 2.4: Phiên đăng nhập hết hạn (Session Expired / Cookie chết)
- **Mã sự cố**: `ACC-ERR-04`
- **Mức độ**: [Vừa]
- **Triệu chứng**: Truy cập Facebook bị văng về trang chủ hoặc xuất hiện form đăng nhập `facebook.com/login`.
- **Cơ chế tự xử lý của hệ thống**:
  - Cổng kiểm tra trước khi chạy (Preflight Gate) phát hiện `login_expired`.
  - Chặn đứng tác vụ xuất bản và quét bài, không cố tình bấm nút để tránh kích hoạt checkpoint.
- **Quy trình xử lý thủ công (SOP)**:
  - Mở cửa sổ Chrome debug và đăng nhập lại tài khoản Facebook.

---

## 4. Nhóm 3: Lỗi Tầng Trình Duyệt & Kết Nối Chrome CDP 9222

### Kịch bản 3.1: Chrome CDP chưa được bật hoặc cổng 9222 bị chiếm
- **Mã sự cố**: `BRW-ERR-01`
- **Mức độ**: [Nghiêm trọng]
- **Triệu chứng**: Nhật ký hệ thống báo lỗi `BrowserRuntimeUnavailable: Không kết nối được Chrome qua cổng 9222`.
- **Cơ chế tự xử lý của hệ thống**:
  - Không sinh dữ liệu giả lập (nguyên tắc CLAUDE.md §8).
  - Tác vụ dừng lại ở trạng thái `FAILED`, ghi rõ lý do "Không chạy được trình duyệt để thao tác".
  - Bảo lưu toàn bộ dữ liệu bài viết chưa đăng.
- **Quy trình xử lý thủ công (SOP)**:
  1. Mở PowerShell và khởi động lại Chrome với lệnh:
     `chrome.exe --remote-debugging-port=9222 --user-data-dir="<đường_dẫn_profile>"`
  2. Sau khi Chrome mở lên, quay lại Dashboard bấm nút **Đăng ngay** hoặc chờ scheduler quét lại.

---

### Kịch bản 3.2: Xung đột thao tác khi người dùng dùng chung cửa sổ Chrome của tool
- **Mã sự cố**: `BRW-ERR-02`
- **Mức độ**: [Vừa]
- **Triệu chứng**: Tool đang gõ nội dung bài viết thì người dùng bấm chuột chuyển tab hoặc lướt trang cá nhân, làm ô nhập mất focus (`composer_lost_focus`).
- **Cơ chế tự xử lý của hệ thống**:
  - Trước khi gõ văn bản, tool kiểm tra lại trạng thái hiển thị của ô nhập.
  - Nếu mất tiêu điểm, tool thử lấy lại focus tối đa 3 lần. Nếu không được, huỷ lượt đăng một cách an toàn thay vì gõ nhầm văn bản vào vị trí khác.
- **Quy trình xử lý thủ công (SOP)**:
  - Để cửa sổ Chrome debug chạy ngầm hoặc thu nhỏ.
  - Việc lướt web cá nhân nên thực hiện trên một profile Chrome thông thường khác.

---

### Kịch bản 3.3: Giao diện Facebook thay đổi cấu trúc mã nguồn (DOM Selector)
- **Mã sự cố**: `BRW-ERR-03`
- **Mức độ**: [Vừa]
- **Triệu chứng**: Tool không tìm thấy nút "Bạn đang nghĩ gì thế?" hoặc nút "Đăng".
- **Cơ chế tự xử lý của hệ thống**:
  - Sử dụng danh sách bộ chọn đa tầng (Fallback Selector Pool) theo `aria-label`, `role="textbox"` và ngôn ngữ kép (Việt / Anh).
  - Nếu toàn bộ thất bại, ghi nhận lỗi rõ ràng và lưu ảnh chụp màn hình chẩn đoán tại `userData/logs/debug_screenshots/`.
- **Quy trình xử lý thủ công (SOP)**:
  - Thu thập file ảnh chụp màn hình trong thư mục log để tiến hành cập nhật bộ selector mới.

---

## 5. Nhóm 4: Lỗi Hạ Tầng Ứng Dụng Desktop (Electron, SQLite, Windows)

### Kịch bản 4.1: Xung đột cổng mạng nội bộ (Cổng 8877 hoặc 3100 bị chiếm)
- **Mã sự cố**: `DSK-ERR-01`
- **Mức độ**: [Vừa]
- **Triệu chứng**: Khởi động app xuất hiện thông báo lỗi: "Backend/Dashboard không phản hồi sau 30 giây".
- **Cơ chế tự xử lý của hệ thống**:
  - Tiến trình Electron có hàm `killByPort` tự động dò tìm và dọn dẹp các tiến trình con mồ côi (zombie process) còn kẹt lại từ các phiên trước khi đóng ứng dụng.
- **Quy trình xử lý thủ công (SOP)**:
  1. Đóng app CommHunter AI.
  2. Mở PowerShell chạy lệnh kiểm tra:
     `netstat -ano | findstr :8877`
     `netstat -ano | findstr :3100`
  3. Nếu có tiến trình lạ đang chiếm giữ, tắt tiến trình đó bằng `taskkill /pid <PID> /F` rồi mở lại app.

---

### Kịch bản 4.2: Máy tính rơi vào chế độ Ngủ (Sleep / Hibernate)
- **Mã sự cố**: `DSK-ERR-02`
- **Mức độ**: [Nhẹ]
- **Triệu chứng**: Laptop gập màn hình hoặc máy ngủ qua đêm, các khung giờ bump 10h, 14h không được thực hiện đúng giờ.
- **Cơ chế tự xử lý của hệ thống**:
  - Khi máy tính thức giấc, scheduler tiếp tục chạy và hàm `is_bump_due` sẽ kiểm tra lại toàn bộ các khung giờ trong ngày chưa được thực thi để kích hoạt bù.
- **Quy trình xử lý thủ công (SOP)**:
  - Nếu cần hệ thống chạy liên tục 24/7, vào cài đặt Windows (Power & Sleep Settings) thiết lập máy không tự động Sleep khi đang cắm sạc.

---

### Kịch bản 4.3: Ứng dụng bị đóng đột ngột (Tắt Task Manager / Mất điện)
- **Mã sự cố**: `DSK-ERR-03`
- **Mức độ**: [Nhẹ]
- **Triệu chứng**: Ứng dụng bị ngắt nguồn khi đang dở một thao tác ghi cơ sở dữ liệu.
- **Cơ chế tự xử lý của hệ thống**:
  - SQLite hoạt động ở chế độ WAL (Write-Ahead Logging), giao dịch chưa hoàn tất sẽ tự động rollback an toàn khi khởi động lại, không gây hỏng tệp `commhunter_api.db`.
- **Quy trình xử lý thủ công (SOP)**:
  - Khởi động lại app bình thường.

---

### Kịch bản 4.4: Cảnh báo bảo mật Windows SmartScreen khi cài đặt
- **Mã sự cố**: `DSK-ERR-04`
- **Mức độ**: [Nhẹ]
- **Triệu chứng**: Chạy file `CommHunterAI-Setup-0.1.0.exe` xuất hiện màn hình xanh "Windows protected your PC (Unknown Publisher)".
- **Cơ chế tự xử lý của hệ thống**:
  - Đây là cơ chế mặc định của Windows đối với phần mềm chưa mua chứng chỉ chữ ký số Code-Signing thương mại.
- **Quy trình xử lý thủ công (SOP)**:
  - Nhấp vào dòng chữ **More info** -> Chọn nút **Run anyway** để tiến hành cài đặt.

---

## 6. Nhóm 5: Lỗi Dịch Vụ Ngoại Vi & Kết Nối Mạng

### Kịch bản 5.1: Mất kết nối mạng Internet đột ngột
- **Mã sự cố**: `EXT-ERR-01`
- **Mức độ**: [Vừa]
- **Triệu chứng**: Đang tải bài viết thì mạng bị ngắt, trình duyệt trả về mã `ERR_INTERNET_DISCONNECTED`.
- **Cơ chế tự xử lý của hệ thống**:
  - `SerialJobQueue` giải phóng hàng đợi, không để tiến trình bị treo vô hạn.
  - Lùi thời gian quét nhóm theo hàm mũ (Exponential backoff), không bắn lặp lại request dồn dập.
- **Quy trình xử lý thủ công (SOP)**:
  - Kiểm tra lại đường truyền mạng Wi-Fi/LAN của máy tính.

---

### Kịch bản 5.2: OpenAI API hết hạn ngạch hoặc sai API Key (Lỗi 401 / 429)
- **Mã sự cố**: `EXT-ERR-02`
- **Mức độ**: [Nhẹ]
- **Triệu chứng**: Tiến trình lọc bài AI hoặc sinh bình luận tự động báo lỗi quota.
- **Cơ chế tự xử lý của hệ thống**:
  - Hệ thống kích hoạt cơ chế dự phòng (Fallback): Tự động chuyển sang sử dụng kịch bản Spintax cố định đã cài đặt sẵn trong chiến dịch mà không làm dừng tiến trình.
- **Quy trình xử lý thủ công (SOP)**:
  - Vào mục Cài đặt trên Dashboard, cập nhật lại OpenAI API Key còn hạn mức.

---

### Kịch bản 5.3: Bot Telegram xung đột Webhook cũ (Lỗi 409 Conflict)
- **Mã sự cố**: `EXT-ERR-03`
- **Mức độ**: [Nhẹ]
- **Triệu chứng**: Chế độ Desktop chạy long-polling nhận mã lỗi 409 do bot trước đó đang gắn webhook public.
- **Cơ chế tự xử lý của hệ thống**:
  - `TelegramPoller` bắt lỗi 409, ghi log hướng dẫn và tự động lùi 30 giây thử lại, không gây crash ứng dụng.
- **Quy trình xử lý thủ công (SOP)**:
  - Mở trình duyệt truy cập: `https://api.telegram.org/bot<BOT_TOKEN>/deleteWebhook` để xoá webhook cũ.

---

## 7. Bảng Ma Trận Tra Cứu Nhanh & Mức Độ Ưu Tiên Xử Lý

| Mã lỗi | Tên sự cố | Mức độ | Tự động xử lý | Cần người can thiệp |
|---|---|---|---|---|
| `PUB-ERR-01` | Nhóm duyệt bài trước khi đăng | [Vừa] | Đánh dấu `published_no_url`, giữ quota | Nạp link tay sau khi admin duyệt |
| `PUB-ERR-02` | Bài đăng bị xoá hoặc nhóm đóng | [Nhẹ] | Bỏ qua lượt bump, dời khung giờ sau | Xoá/tạm dừng lịch bump trong dashboard |
| `PUB-ERR-03` | Chạm hạn mức đăng bài ngày | [Nhẹ] | Chuyển nhóm còn lại sang `skipped_quota` | Không cần (hệ thống tự bảo vệ) |
| `PUB-ERR-04` | Spintax nghèo nàn bị cảnh báo | [Vừa] | Dừng chuỗi đăng, cho nick nghỉ | Bổ sung thêm biến thể Spintax |
| `ACC-ERR-01` | Tài khoản dính Checkpoint | [Nghiêm trọng] | Ngắt mọi job, cách ly tối thiểu 48h | Tự mở Chrome debug xác minh danh tính |
| `ACC-ERR-02` | Bị chặn bình luận (Action Blocked) | [Nghiêm trọng] | Đưa nick vào `cooldown` 4 - 8 giờ | Tăng giãn cách cmt, giảm trần/ngày |
| `ACC-ERR-03` | Bình luận bị ẩn ngầm (Shadowban) | [Vừa] | Tăng giãn cách lên mức kịch trần (30p) | Đổi câu cmt, bỏ link trần nhạy cảm |
| `ACC-ERR-04` | Hết hạn phiên đăng nhập | [Vừa] | Preflight chặn trước, không gửi request | Đăng nhập lại trên Chrome debug |
| `BRW-ERR-01` | Chrome CDP 9222 chưa bật/bị đóng | [Nghiêm trọng] | Dừng an toàn ở `FAILED`, không mock | Khởi động lại Chrome với port 9222 |
| `BRW-ERR-02` | Xung đột focus chuột với người dùng | [Vừa] | Thử lấy lại focus 3 lần, huỷ an toàn | Dùng Chrome khác để lướt web cá nhân |
| `BRW-ERR-03` | Facebook đổi giao diện (DOM) | [Vừa] | Dùng đa bộ chọn, chụp ảnh màn hình debug | Cập nhật lại selector trong code |
| `DSK-ERR-01` | Cổng 8877 hoặc 3100 bị chiếm | [Vừa] | Dọn dẹp tiến trình zombie qua `killByPort` | Kiểm tra phần mềm chiếm cổng |
| `DSK-ERR-02` | Máy tính đi vào chế độ Sleep | [Nhẹ] | Scheduler thức giấc tự kích hoạt bù | Tắt Sleep máy tính nếu muốn chạy 24/7 |
| `DSK-ERR-03` | Tắt app đột ngột / mất điện | [Nhẹ] | SQLite WAL tự rollback giao dịch dở | Mở lại app bình thường |
| `DSK-ERR-04` | Windows SmartScreen cảnh báo | [Nhẹ] | Không ảnh hưởng mã nguồn | Bấm "More info" -> "Run anyway" |
| `EXT-ERR-01` | Mất kết nối Internet | [Vừa] | Giải phóng queue, lùi nhịp quét lũy tiến | Kiểm tra lại mạng máy tính |
| `EXT-ERR-02` | OpenAI API hết hạn mức / sai key | [Nhẹ] | Tự fallback về mẫu Spintax tĩnh | Nạp lại API Key trong Cài đặt |
| `EXT-ERR-03` | Bot Telegram xung đột Webhook | [Nhẹ] | Poller tự lùi 30s thử lại | Mở link xoá webhook của bot |
