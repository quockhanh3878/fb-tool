# Đóng gói CommHunter AI thành app desktop chạy trên máy khách

> Cập nhật: 11/09/2026. Trạng thái: Giai đoạn 1-3/6 — Xong (có mã chạy được + kiểm chứng thủ công). Giai đoạn 4-5 — Chưa làm.

## Context

Hiện tại hệ thống là SaaS trung tâm: FastAPI + Postgres + Celery/Redis + Next.js đứng sau docker-compose, nhiều khách share 1 server, multi-tenant filter theo `user_id`. Mục tiêu: đảo mô hình — **mỗi khách cài 1 app desktop, tự chạy toàn bộ hệ thống trên máy họ** (không qua server trung tâm), khách không biết gì về code/DB — chỉ double-click icon là chạy đủ, có bước cài đặt rõ ràng. Đã chốt: SQLite local + đóng gói Electron/Tauri.

Điểm khó nhất: **Celery + Redis** — Windows không có bản Redis chính thức, bắt khách cài Docker/WSL phá nguyên tắc "double-click chạy". Điều kiện thuận lợi đã khảo sát để thay thế mà không viết lại nghiệp vụ:
- Mọi Celery task theo đúng 1 khuôn: hàm thuần + hàm async nội bộ hoàn toàn không đụng Celery context. Chỉ 3 task `bind=True` dùng `self.retry()` là phần Celery-specific thật sự.
- `backend/app/main.py`: `create_app()` không tự gọi `uvicorn.run` → embed được trong Electron sidecar.
- `commhunter/browser_manager.py`: mặc định `_launch_persistent()` dùng `channel="chrome"` (Chrome thật đã cài) — không cần khách tự mở CDP tay.

## Kiến trúc mới

```
Electron App (khách double-click icon)
 Electron main process
  1. Kiểm tra first-run (thư mục userData tồn tại chưa)
  2. Spawn "backend sidecar" = python (embedded, bundled) chạy
     backend/app/desktop_runner.py (Giai đoạn 2, chưa làm)
       - alembic upgrade head (idempotent)
       - seed user mặc định nếu DB rỗng
       - start uvicorn (FastAPI app) trên 127.0.0.1:8877
       - RUN_MODE=desktop -> app/main.py tự start_scheduler() (ĐÃ XONG)
  3. Poll GET /health tới khi 200 OK
  4. Spawn "frontend sidecar" = node server.js (Next standalone) trên 127.0.0.1:3100
  5. Mở BrowserWindow load http://127.0.0.1:3100
  6. Playwright bên trong backend sidecar tự mở CHROME THẬT (persistent context)
  7. before-quit: kill sạch 2 tiến trình con

 DB: SQLite trong thư mục dữ liệu người dùng
```

## A. Thay Celery+Redis — APScheduler in-process + SerialJobQueue [ĐÃ XONG]

- `backend/app/config.py`: field `run_mode` (`"saas"` mặc định giữ nguyên hành vi cũ, `"desktop"` bật scheduler in-process).
- `backend/app/workers/job_queue.py` (mới): `SerialJobQueue` — 1 hàng đợi asyncio tuần tự, thay `worker_prefetch_multiplier=1`/`task_acks_late`. 1 job lỗi không giết hàng đợi (log + tiếp tục), không tự retry — job vốn được gọi lại ở chu kỳ dispatch kế tiếp.
- `backend/app/workers/scheduler.py` (mới): `AsyncIOScheduler` đăng ký đúng 7 job, chu kỳ COPY 1:1 từ `celery_app.conf.beat_schedule` (scout 60s, shooter 30s, bump 300s, warmup crontab 9h, health check 1800s, wake cooldown 600s, publisher 60s). Mỗi job dispatcher gọi thẳng hàm async nội bộ hiện có trong `*_task.py` (`_due_groups`, `_scan_one`, `_due_actions`, `_execute`, `_due_bumps`, `_bump_one`, `_clones_needing_warmup`, `_run_step`, `_check_all`, `_wake`, `_due_publishes`, `_execute_one`) rồi enqueue qua `job_queue` — KHÔNG sửa các hàm Celery task hiện có (`celery_app.py` + wrapper `@celery_app.task` trong 7 file `*_task.py` giữ nguyên 100%, chế độ SaaS không đổi hành vi).
- `backend/app/main.py`: `lifespan()` gọi `start_scheduler()`/`stop_scheduler()` khi `settings.run_mode == "desktop"`.
- `backend/requirements.txt`: thêm `apscheduler==3.11.3`.
- Test: `backend/tests/test_api.py` mục 14g (3 assertion) — `SerialJobQueue` chạy đúng thứ tự, không bao giờ 2 job chạy song song, 1 job lỗi không giết hàng đợi. Verify thủ công: `RUN_MODE=desktop` khởi động app → 7 job đăng ký đúng tên, `/health` 200, job_queue worker sống; `RUN_MODE` mặc định (không set) → hành vi SaaS cũ không đổi.
- Kiểm chứng: `backend/tests/test_api.py` **317/317 PASS** (314 + 3 mới).

## B. Desktop config — seed user + auto-login + màn Cài đặt [ĐÃ XONG]

- `backend/app/models/app_setting.py` (mới) — bảng key-value `app_settings` (migration `0006_app_settings.py`, nối sau `0005_ai_comments_optional.py`).
- `backend/app/services/app_settings_service.py` (mới) — `get_value`/`set_value`; `ensure_cookie_key` sinh 1 lần + lưu bền (vá xong rủi ro #2: trước đây tự sinh tạm RAM khi rỗng); `apply_to_runtime_settings` nạp OpenAI key/Telegram token/cookie key từ DB vào `Settings` singleton — CHỈ dùng khi `RUN_MODE=desktop` (1 máy/1 khách, an toàn ghi đè singleton toàn tiến trình; SaaS đa khách KHÔNG được dùng module này).
- `backend/app/services/desktop_service.py` (mới) — `ensure_desktop_user`: seed đúng 1 user cố định (`khach@local.commhunter`) + subscription gói Studio hạn 100 năm (không chặn quota), idempotent.
- `backend/app/routers/auth.py` — `POST /api/auth/desktop-session`: auto-login, cấp token ngay không cần mật khẩu. 404 ở chế độ SaaS.
- `backend/app/routers/settings.py` (mới) — `GET/PUT /api/settings`: màn "Cài đặt" cho OpenAI key/Telegram token, không trả lại giá trị thật (chỉ báo đã cấu hình hay chưa). 404 ở chế độ SaaS. PUT ghi DB + áp dụng ngay vào `Settings` singleton (không cần restart).
- `backend/app/main.py` — `lifespan()` khi `RUN_MODE=desktop`: mở 1 DB session gọi `apply_to_runtime_settings` TRƯỚC khi bật scheduler/nhận request đầu tiên (đặc biệt trước lần gọi `services/crypto.py` đầu tiên).
- Test: `backend/tests/test_api.py` mục 14h (11 assertion) — 404 ở SaaS, auto-login idempotent (gọi lại vẫn ra đúng 1 user), GET/PUT settings, PUT áp dụng ngay không cần restart, cookie key sinh 1 lần không đổi. Kiểm đột biến 2 điểm (bỏ early-return `ensure_cookie_key`, đảo điều kiện gate `run_mode`) đều bắt đỏ đúng chỗ, đã hoàn tác.
- Kiểm chứng: `alembic upgrade head` → `alembic check` không drift → `downgrade base` → `upgrade head` lại sạch. `backend/tests/test_api.py` **328/328 PASS** (317 + 11 mới).

## C. Electron shell tối thiểu [ĐÃ XONG]

- `desktop/main.js` (mới) — spawn 2 sidecar bằng `.venv`/`node` HỆ THỐNG (chưa bundle, Giai đoạn 4 mới đóng gói riêng): backend qua `.venv/Scripts/python.exe -m uvicorn` (`RUN_MODE=desktop`, `DATABASE_URL` SQLite trong `app.getPath("userData")`, `JWT_SECRET` sinh 1 lần + lưu bền), frontend qua `npm run dev -p 3100` (`shell: true` bắt buộc trên Windows vì `npm.cmd` không tự chạy được qua `spawn` không shell — lỗi `spawn EINVAL`). Health-poll `GET /health` mỗi 500ms, timeout 30s, splash window trong lúc chờ, lỗi rõ ràng (dialog + log ra `userData/logs/*.log`) nếu timeout. Mở `BrowserWindow` load `http://127.0.0.1:3100` sau khi cả 2 sidecar khoẻ.
- `killProcessTree` (`taskkill /pid <pid> /T /F`) không đủ tin cậy dọn cây tiến trình khi sidecar spawn qua `shell:true` (npm.cmd → cmd.exe → node) — tiến trình trung gian thoát trước khi con kịp giữ liên kết parent PID hợp lệ nên `/T` bỏ sót cháu. Thêm `killByPort(port)` dọn theo cổng đang LISTEN (`netstat -ano | findstr :<port> | findstr LISTENING` → `taskkill /pid <pid> /T /F`) làm lớp dọn dự phòng, gọi cùng `killProcessTree` trong `before-quit`.
- Kiểm chứng thủ công (không phải unit test — đúng như plan gốc mô tả Giai đoạn 3-4): `cd desktop && npm start` (phải bỏ biến môi trường `ELECTRON_RUN_AS_NODE` nếu có trong shell, nếu không `require("electron")` trả về path string thay vì API — lỗi `Cannot read properties of undefined (reading 'whenReady')`). Health-poll backend (8877) + frontend (3100) đều 200 OK, `BrowserWindow` mở đúng dashboard thật (title "CommHunter AI — Nền tảng Săn Lead..."). Đóng app **graceful** (đóng window thật/`taskkill /pid <id>` không `/F`, kích hoạt `window-all-closed` → `app.quit()` → `before-quit` thật sự — **không phải** `Stop-Process -Force`, lệnh này bỏ qua toàn bộ lifecycle event của Electron và không phản ánh đúng hành vi khách đóng app bằng nút X) → xác nhận bằng `Get-CimInstance`/`netstat`: cả tiến trình `python.exe` (uvicorn) và `node.exe` (next dev, kể cả tiến trình con `start-server.js`) đều bị dọn sạch, cổng 8877/3100 hết LISTEN.

## D-E. Chưa làm (Giai đoạn 4-6)

- Giai đoạn 4 — Đóng gói thật (bundle `.venv`, Next standalone, electron-builder NSIS). `commhunter/browser_manager.py` `channel="chrome"` chưa verify trên máy sạch có cần `playwright install` không.
- Giai đoạn 5 — Tài liệu hoá first-run cho khách.
- Frontend chưa có màn "Cài đặt" gọi `/api/settings`, chưa có logic auto-login gọi `/api/auth/desktop-session` (API đã sẵn sàng, chỉ thiếu UI).

### Rủi ro / giả định chưa chốt (cần anh Ber xác nhận trước khi làm Giai đoạn 4 trở đi)
1. Bỏ `self.retry()` tức thời (giờ chỉ thử lại ở chu kỳ dispatch kế tiếp 30-60s) — SLA chấp nhận được không?
2. ~~Cookie encryption key phải sinh 1 lần + lưu bền cho desktop~~ — ĐÃ VÁ (Giai đoạn 2, `ensure_cookie_key`).
3. `playwright install` (driver nội bộ) — cần verify trên máy Windows sạch chưa từng cài.
4. 1 hàng đợi tuần tự TOÀN CỤC (không khoá riêng theo clone) — nhiều clone chạy lần lượt, chậm hơn Celery pool.
5. Giữ code path Postgres/`asyncpg` không xoá — cần `requirements-desktop.txt` riêng nếu muốn giảm dung lượng installer.
6. Cổng nội bộ cố định 8877/3100 — chấp nhận hard-code hay cần dò cổng trống?
7. Không code-signing → SmartScreen cảnh báo "Unknown publisher".
8. User desktop seed (`khach@local.commhunter`) dùng gói Studio hạn 100 năm để không chặn quota — mô hình billing hiện tại (Starter/Pro/Studio trả phí) không còn ý nghĩa khi bán app desktop 1 lần; cần anh Ber chốt mô hình kinh doanh cho bản desktop (bán đứt file cài đặt? vẫn thu phí định kỳ qua license key riêng?) trước khi đụng tới `services/plans.py`/`routers/billing.py`.
