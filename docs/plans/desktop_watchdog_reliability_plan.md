# Kế hoạch watchdog và tự phục hồi desktop CommHunter AI

> Cập nhật: 23/09/2026. Trạng thái: Chưa làm.

## Mục tiêu

Giúp bản desktop tiếp tục vận hành an toàn khi không có người trực: phát hiện
backend/frontend sidecar chết hoặc mất phản hồi, khôi phục có kiểm soát và không
lặp lại hành động Facebook có kết quả chưa chắc chắn.

Kế hoạch này bổ sung cho `desktop_packaging.md`; không thay đổi mô hình xác thực
desktop, không mở quyền SaaS và không tự thực hiện thao tác ghi lên Facebook.

## Ranh giới

- Phạm vi chính: Electron desktop, backend `RUN_MODE=desktop`, `SerialJobQueue`
  và các tác vụ có lease.
- SaaS Docker chỉ được bổ sung kiểm tra liveness/readiness và hướng dẫn supervisor.
  `docker compose` không tự restart container chỉ vì healthcheck là `unhealthy`;
  không coi `restart: unless-stopped` là watchdog cho tiến trình còn treo.
- Khi một comment/post bị ngắt hoặc timeout, trạng thái phải là
  `unknown_outcome` để người dùng duyệt trước khi retry, không tự gửi lại.

## Thiết kế đề xuất

### 1. Supervisor cho hai sidecar trong Electron

Tách logic giám sát thuần ra khỏi `desktop/main.js` để test bằng Node. Supervisor
quản lý `backend` và `frontend` với các trạng thái `starting`, `healthy`,
`restarting`, `failed`, `stopping`.

- Child process thoát ngoài lúc người dùng tắt app: ghi lý do, dọn PID/cổng cũ,
  rồi restart. Backend restart phải restart frontend theo thứ tự backend trước,
  frontend sau vì dashboard phụ thuộc API.
- Sau boot, probe định kỳ backend `/ready` và frontend. Timeout request ngắn;
  chỉ restart sau 3 probe liên tiếp không đạt để tránh restart vì một nhịp chậm.
- Backoff có giới hạn: 5 lần trong cửa sổ 30 phút, chờ tăng dần 2/5/15/30/60 giây.
  Vượt ngưỡng thì dừng auto-restart, hiện dialog kèm đường dẫn log; không tạo vòng
  lặp vô hạn hoặc nhiều child cùng cổng.
- Cờ `stopping` được bật trước `before-quit`; mọi callback `exit`/probe sau đó
  chỉ cleanup, tuyệt đối không respawn.

### 2. Liveness của scheduler và hàng đợi desktop

`/ready` ở desktop cần phản ánh cả DB/schema lẫn scheduler/job queue còn tiến
hành: timestamp job gần nhất bắt đầu/kết thúc, job đang chạy, độ dài queue và lỗi
timeout gần nhất. Electron chỉ dựa vào readiness này, không dùng `/health` vốn
chỉ chứng minh HTTP process còn trả lời.

- Thêm timeout có cấu hình cho từng job trong `SerialJobQueue`, mặc định lấy từ
  giới hạn browser operation hiện có; test được phép override xuống 1 giây.
- Timeout phải hủy coroutine, giải phóng key `_pending`, ghi log có `key` nhưng
  không ghi dữ liệu khách, để job tiếp theo vẫn chạy.
- Các đường comment/publish đang giữ lease phải chuyển sang `unknown_outcome`
  trước khi release. Browser runtime cần cleanup trong `finally` khi coroutine bị
  hủy để không để Chrome/page treo ngầm.
- `maintenance_task.recover_stale_jobs` vẫn là lớp phục hồi durable khi backend
  bị kill; không dùng nó để tự requeue Facebook side effect chưa xác nhận.

### 3. Hành vi SaaS/deploy

- Giữ `GET /live` cho process liveness và nâng `GET /ready` thành readiness có
  dependency/scheduler phù hợp mode chạy.
- Tài liệu deploy phải yêu cầu supervisor có khả năng restart theo liveness
  (systemd, Kubernetes hoặc dịch vụ tương đương). Nếu vẫn dùng Docker Compose,
  tiến trình phải tự thoát non-zero khi watchdog xác nhận tình trạng không phục
  hồi được để policy `restart: unless-stopped` có tác dụng.

## Lộ trình thực hiện

| Bước | Hạng mục | File dự kiến | Trạng thái |
|---|---|---|---|
| 1 | Viết contract supervisor, cấu hình interval/timeout/backoff và Node unit test thuần | `desktop/supervisor.js`, `desktop/tests/*`, `desktop/package.json` | Xong |
| 2 | Nối supervisor vào `main.js`: exit handler, periodic probe, restart theo thứ tự, cleanup và UI failure | `desktop/main.js` | Xong |
| 3 | Bổ sung job timeout, metric/heartbeat queue và desktop readiness | `backend/app/workers/job_queue.py`, `scheduler.py`, `main.py`, `config.py` | Xong |
| 4 | Bảo toàn lease và `unknown_outcome` khi cancellation/kill; bổ sung hồi quy | worker/service liên quan, `maintenance_task.py` | Xong |
| 5 | Cập nhật Docker/deploy runbook, DELIVERY_STATUS và hướng dẫn xử lý lỗi | `backend/docker-compose.yaml`, `docs/plans/*` | Xong |
| 6 | Kiểm thử unit, integration và bản `.exe` đóng gói trong môi trường offline | backend/desktop tests, `desktop` package | Chờ |

## Tiêu chí nghiệm thu

1. Unit test supervisor: backend hoặc frontend thoát bất thường được restart đúng
   thứ tự; graceful quit không restart; quá 5 lỗi/30 phút chuyển `failed` và không
   spawn thêm tiến trình.
2. Với probe lỗi 3 lần liên tiếp, Electron dọn process/cổng cũ và phục hồi cả
   dashboard trong tối đa 60 giây; có test dùng fake clock/spawn, không cần Chrome
   hoặc Facebook.
3. Test queue với job treo (timeout test = 1 giây): job sau vẫn chạy, `_pending`
   được giải phóng, readiness phản ánh lỗi và action có side effect không tự retry.
4. Backend current gate, frontend typecheck/build và desktop Node tests đều xanh:

```powershell
$env:DEBUG='false'; $env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
Push-Location backend; ..\.venv\Scripts\python.exe -m pytest tests -q; Pop-Location
Push-Location frontend; npx tsc --noEmit; npx next build; Pop-Location
Push-Location desktop; node --test tests; Pop-Location
```

5. Kiểm chứng bản đóng gói, không ghi Facebook: khởi động `.exe`, chủ động kết
   thúc backend rồi frontend, xác nhận mỗi lần phục hồi đúng một instance, cổng
   8877/3100 không bị trùng và đóng app không còn sidecar.
6. Soak test offline tối thiểu 24 giờ với scheduler/test jobs giả; báo cáo số lần
   restart, timeout và backlog. Chỉ sau đó mới xin anh Ber một phiên quan sát
   Facebook burner riêng, không tự động chạy hành vi ghi.

## Rủi ro và quyết định cần giữ

- Không dùng restart để che lỗi Facebook/checkpoint: state machine và preflight
  vẫn là hàng rào chính cho tài khoản.
- Cancel coroutine không bảo đảm dừng một subprocess/browser nếu runtime không
  cleanup; phải có regression test cleanup trước khi bật restart tự động.
- Ngưỡng backoff là giá trị khởi đầu có chủ đích, cần telemetry từ soak test trước
  khi tăng/giảm.
- Không coi các kiểm thử legacy `backend/tests/test_api.py` là release gate;
  cần cập nhật hoặc tách nó để không gây tín hiệu sai cho CI.

## Kết quả triển khai 23/09/2026

- Bước 1: Xong phần contract supervisor và 5 Node unit test offline.
- Bước 2: Xong nối Electron với `/ready`, probe lặp lại, restart có thứ tự, backoff giới hạn và cleanup khi thoát.
- Bước 3: Xong timeout theo từng job, heartbeat/readiness queue và readiness desktop có trạng thái scheduler.
- Bước 4: Xong chuyển comment/publish đã claim sang `unknown_outcome` khi coroutine bị hủy, kèm regression test.
- Bước 5: Xong cập nhật ghi chú Docker; Compose vẫn cần external supervisor vì healthcheck không tự hồi phục tiến trình bị treo.
- Bước 6: Chờ kiểm chứng `.exe` cách ly và soak test offline 24 giờ; chưa coi đây là release sign-off.
