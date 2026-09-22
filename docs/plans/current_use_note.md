# Ghi chú sử dụng hiện tại — CommHunter AI

> Ngày cập nhật: 22/09/2026

## Trạng thái

Bản hiện tại được giữ để anh Ber sử dụng local/desktop trên máy riêng. Đây không phải xác nhận production-ready hay xác nhận đã triển khai cho khách hàng khác.

## Bằng chứng hiện có

- Source runtime nằm đúng ở `backend/` và `commhunter/` tại gốc workspace.
- Backend security suites: `61 passed` với test dependencies trong `.venv`.
- Electron desktop đặt `RUN_MODE=desktop` và `AUTH_REQUIRED=false`; backend vẫn chỉ nhận request loopback/origin local.
- Frontend TypeScript check: PASS.
- CommHunter CLI help và parse Python: PASS.
- Hướng dẫn khởi chạy desktop: [desktop_user_guide.md](desktop_user_guide.md).

## Cách dùng an toàn

- Chỉ chạy local/desktop với cấu hình của anh Ber; không đưa secret vào Git.
- Browser automation mặc định tắt. Chỉ bật khi đã kiểm tra Chrome CDP, profile và nick phụ phù hợp.
- Mọi thao tác ghi lên Facebook thật vẫn cần được đồng ý rõ trong cuộc hội thoại hiện tại; test ghi chỉ dùng nick phụ và phải dọn nội dung test.
- Không đọc, sao chép hoặc commit `.env`, `commhunter/data/`, `chrome-debug-profile/` hay config khách.

## Giới hạn hiện tại

- Chưa coi đây là bản production hoặc bản bàn giao cho khách.
- Harness `backend/tests/test_api.py` là bộ lịch sử, không dùng làm security gate hiện tại vì tự đặt secret rỗng.
- Cấu hình môi trường local phải có giá trị boolean hợp lệ cho `DEBUG`; security suites đã chạy với `DEBUG=false` chỉ trong process test.
