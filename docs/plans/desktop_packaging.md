# Đóng gói CommHunter AI thành app desktop chạy trên máy khách

> Cập nhật: 11/09/2026. Trạng thái: Giai đoạn 1/6 — Xong (có mã chạy được + test). Giai đoạn 2-5 — Chưa làm.

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

## B-E. Chưa làm (Giai đoạn 2-6)

Xem lịch sử quyết định gốc trong session-snapshot 2026-09-11 (mục "Kiến trúc mới" đầy đủ + rủi ro chưa chốt) để tiếp tục:
- Giai đoạn 2 — Desktop config: SQLite mặc định + seed user mặc định + auto-login (`/auth/desktop-session`) + `app_settings` (bảng key-value cho OpenAI key/Telegram token nhập qua UI, migration mới **phải là `0006`** vì `0005_ai_comments_optional.py` đã tồn tại) + cookie encryption key sinh 1 lần lưu bền (bug cần vá — hiện tự sinh tạm RAM khi rỗng).
- Giai đoạn 3 — Electron shell tối thiểu (`desktop/main.js`, chưa bundle).
- Giai đoạn 4 — Đóng gói thật (bundle `.venv`, Next standalone, electron-builder NSIS).
- Giai đoạn 5 — Tài liệu hoá first-run cho khách.

### Rủi ro / giả định chưa chốt (cần anh Ber xác nhận trước khi làm Giai đoạn 2 trở đi)
1. Bỏ `self.retry()` tức thời (giờ chỉ thử lại ở chu kỳ dispatch kế tiếp 30-60s) — SLA chấp nhận được không?
2. Cookie encryption key phải sinh 1 lần + lưu bền cho desktop (khác RAM tạm hiện tại).
3. `playwright install` (driver nội bộ) — cần verify trên máy Windows sạch chưa từng cài.
4. 1 hàng đợi tuần tự TOÀN CỤC (không khoá riêng theo clone) — nhiều clone chạy lần lượt, chậm hơn Celery pool.
5. Giữ code path Postgres/`asyncpg` không xoá — cần `requirements-desktop.txt` riêng nếu muốn giảm dung lượng installer.
6. Cổng nội bộ cố định 8877/3100 — chấp nhận hard-code hay cần dò cổng trống?
7. Không code-signing → SmartScreen cảnh báo "Unknown publisher".
