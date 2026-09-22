# Hướng Dẫn Vận Hành & Khởi Chạy Lần Đầu CommHunter AI (Desktop First-Run Guide)

> Tài liệu hướng dẫn cài đặt và sử dụng dành cho khách hàng sử dụng bản cài đặt Desktop CommHunter AI trên hệ điều hành Windows.
> Phiên bản: 0.1.0 — Cập nhật: 2026-09-12.

---

## 1. Yêu Cầu Hệ Thống

- **Hệ điều hành**: Windows 10 (64-bit) hoặc Windows 11.
- **Dung lượng ổ cứng trống**: Tối thiểu 1.5 GB.
- **Trình duyệt**: Google Chrome bản mới nhất đã được cài đặt trên máy.
- **Kết nối mạng**: Kết nối Internet ổn định.

---

## 2. Các Bước Cài Đặt Bản Desktop

### Bước 1: Chạy bộ cài đặt
1. Tải về file cài đặt `CommHunterAI-Setup-0.1.0.exe`.
2. Nhấp đúp vào file để khởi động trình cài đặt NSIS.

### Bước 2: Xử lý cảnh báo Windows SmartScreen (nếu xuất hiện)
Vì ứng dụng chưa mua chứng chỉ chữ ký số thương mại (Code-Signing Certificate), Windows có thể hiển thị màn hình màu xanh với tiêu đề:
`Windows protected your PC / Microsoft Defender SmartScreen prevented an unrecognized app from starting.`
- Bấm vào dòng liên kết gạch chân: **More info** (Thêm thông tin).
- Bấm vào nút: **Run anyway** (Vẫn chạy).

### Bước 3: Hoàn tất cài đặt
- Chọn thư mục cài đặt mong muốn (mặc định tại `C:\Program Files\CommHunter AI` hoặc thư mục người dùng).
- Tích chọn **Create Desktop Shortcut** để tạo biểu tượng ngoài màn hình Desktop.
- Bấm **Install** -> Chờ quá trình giải nén hoàn tất -> Bấm **Finish**.

---

## 3. Khởi Động Chrome Chế Độ Gỡ Lỗi (CDP Port 9222)

Để CommHunter AI có thể tương tác với Facebook an toàn nhất (sử dụng vân tay trình duyệt thật và địa chỉ IP của chính máy tính), ứng dụng kết nối với Google Chrome qua cổng điều khiển 9222.

### Cách mở Chrome Debug:
1. Mở cửa sổ dòng lệnh **PowerShell** hoặc **Command Prompt** (bấm phím Windows, gõ `powershell` rồi ấn Enter).
2. Dán dòng lệnh sau và ấn Enter:
   ```powershell
   & "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="$env:LOCALAPPDATA\CommHunterChrome"
   ```
   *(Lưu ý: Dòng lệnh trên sẽ mở một cửa sổ Chrome riêng biệt chuyên dùng cho tool, tách biệt hoàn toàn với dữ liệu duyệt web cá nhân hàng ngày của bạn).*
3. Trên cửa sổ Chrome vừa mở ra, truy cập vào `https://www.facebook.com` và đăng nhập tài khoản Facebook của bạn. Vượt qua mã 2FA nếu có.
4. Giữ cửa sổ Chrome này mở (có thể thu nhỏ xuống thanh taskbar).

---

## 4. Khởi Chạy Ứng Dụng CommHunter AI & Cấu Hình Ban Đầu

1. Nhấp đúp vào biểu tượng **CommHunter AI** ngoài màn hình Desktop.
2. Màn hình khởi động xuất hiện trong khoảng 2-3 giây để khởi tạo cơ sở dữ liệu SQLite và nạp giao diện.
3. Ứng dụng sẽ tự động đăng nhập thẳng vào màn hình **Dashboard** (Bảng điều khiển) mà không đòi hỏi tài khoản hay mật khẩu.

### Cấu hình Khóa API (Mục Cài Đặt):
1. Vào menu **Cài đặt** (Settings) ở góc trái màn hình.
2. **OpenAI API Key**: Nhập mã khóa API của bạn (dạng `sk-...`) để kích hoạt tính năng AI phân tích bài viết và viết bình luận tự động.
3. **Telegram Bot Token**: Nhập mã token bot Telegram của bạn (lấy từ `@BotFather`) nếu muốn nhận thông báo tức thời về điện thoại mỗi khi có khách hàng tiềm năng.
4. Bấm **Lưu cài đặt**.

---

## 5. Sử Dụng Tính Năng Đăng Bài Tự Động & Đẩy Bài (Auto-Bump)

Hệ thống đã nạp sẵn kịch bản dịch vụ Writing Commission và mẫu bình luận mặc định của Nyatymita.

### Cách tạo lịch đăng bài nhóm:
1. Vào menu **Đăng bài** (Publishing Studio) trên thanh điều hướng.
2. Bấm nút **Soạn bài đăng mới**.
3. **Nội dung bài viết**: Hệ thống đã điền sẵn bài mẫu. Bạn có thể chỉnh sửa hoặc bấm **Nạp mẫu bài đăng mặc định**.
4. **Tần suất lặp lại**: Hệ thống đã chọn sẵn **2 tuần / lần (14 ngày)**.
5. **Tự động bình luận đẩy bài (Auto-bump)**: Ô chọn đã được bật sẵn mặc định, hệ thống sẽ tự động lưu link bài sau khi đăng và cmt đẩy bài **4 lần / ngày** vào các khung giờ **10h, 14h, 18h, 21h**.
6. **Chọn nhóm mục tiêu**:
   - Nếu đã có chiến dịch, bấm **+ Thêm toàn bộ nhóm** để nạp nhanh tất cả các nhóm đã tham gia.
   - Hoặc dán link nhóm trực tiếp vào ô bên dưới.
7. Bấm **Xác nhận & Lên lịch đăng**.

---

## 6. Những Lưu Ý Quan Trọng Để Giữ Nick An Toàn

1. **Không lướt web cá nhân trên cửa sổ Chrome Debug**: Cửa sổ Chrome mở bằng cổng 9222 chỉ để tool chạy tự động. Bạn nên lướt Facebook cá nhân trên trình duyệt Chrome thông thường.
2. **Không vượt quá hạn mức ngày**: Mặc định hệ thống giới hạn tối đa 5 bài đăng/ngày và 20 bình luận/ngày cho một tài khoản clone. Không nên can thiệp tăng quá cao để tránh bị Facebook hạn chế tính năng.
3. **Giãn cách giữa các lần bình luận**: Hệ thống tự động đặt khoảng nghỉ tối thiểu từ 3 đến 5 phút giữa các bình luận để mô phỏng hành vi gõ phím của người thật.
4. **Khi gặp sự cố Checkpoint**: Nếu Facebook yêu cầu xác minh tài khoản, hãy mở trực tiếp cửa sổ Chrome debug để thực hiện các bước xác minh chính chủ bằng tay.

---

## 7. Xử Lý Sự Cố Nhanh

- **Nếu ứng dụng báo "Backend/Dashboard không phản hồi sau 30 giây"**: Đóng app, mở Task Manager kiểm tra xem có tiến trình Python hoặc Node nào bị treo hay không, kết thúc tiến trình rồi mở lại app.
- **Nếu đăng bài báo "Không kết nối được Chrome 9222"**: Kiểm tra xem cửa sổ Chrome debug ở Bước 3 đã được mở hay chưa.
- **Xem chi tiết các trường hợp lỗi khác**: Tham khảo tài liệu chuyên sâu tại file `docs/plans/error_scenarios_and_troubleshooting.md`.
