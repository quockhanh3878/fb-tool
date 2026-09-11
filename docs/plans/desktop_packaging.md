# Đóng gói CommHunter AI thành app desktop chạy trên máy khách

> Cập nhật: 11/09/2026. Trạng thái: Giai đoạn 1-4/6 — Xong (có mã chạy được + kiểm chứng thủ công, kể cả cài đặt thật từ file `.exe`). Mục G (Telegram long-polling cho desktop) — Xong, chưa chạy với bot thật. Giai đoạn 5 (tài liệu first-run) — Chưa làm.

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

## D. Auto-login + màn Cài đặt (vá lỗ hổng UI trước khi đóng gói) [ĐÃ XONG]

Trước Giai đoạn 4, mở app đóng gói vẫn hiện landing page SaaS (phải tự đăng ký/đăng nhập) và không có UI nhập OpenAI key/Telegram token dù API đã sẵn (`/api/auth/desktop-session`, `/api/settings`) — vá cả hai trước khi đóng gói thật để bản cài đặt dùng được ngay:

- `frontend/lib/api.ts`: thêm `api.desktopSession()`, `api.appSettings()`, `api.updateAppSettings()`.
- `frontend/lib/auth.tsx`: `AuthProvider.refreshUser` — khi chưa có access token, thử gọi `desktop-session` trước khi coi là chưa đăng nhập; SaaS trả 404 thì rơi về hành vi cũ (màn đăng nhập), không đổi gì. Thêm `isDesktop` vào `AuthState`.
- `frontend/app/page.tsx`: khi `isDesktop && user` thật, `router.replace("/dashboard")` — bỏ qua landing SaaS.
- `frontend/app/(app)/settings/page.tsx`: thêm thẻ "Cấu hình OpenAI & Telegram Bot" gọi `GET/PUT /api/settings`; tự ẩn khi backend trả 404 (chế độ SaaS) vì `appSettings` vẫn `null`.
- Kiểm chứng: `npx tsc --noEmit` 0 lỗi, `npx next build` 14 route 0 lỗi. Chạy thật `npm start` (dev sidecar): `POST /api/auth/desktop-session` trả token, `GET/PUT /api/settings` hoạt động đúng qua UI.
- **Vá 11/09/2026 — bản trên vẫn đòi đăng nhập trong thực tế** (lần kiểm trước chỉ gọi API bằng HTTP, không qua trình duyệt nên không lộ):
  - CORS: cửa sổ Electron mở `127.0.0.1:3100`, API ở `127.0.0.1:8877` → cross-origin; `cors_origins` mặc định chỉ có cổng `3000` nên trình duyệt chặn mọi request. `desktop/main.js` `startBackend` truyền `CORS_ORIGINS` (JSON) cho cổng `FRONTEND_PORT`. Không đổi mặc định SaaS.
  - `frontend/lib/auth.tsx`: luôn gọi `desktop-session` khi mount (không chỉ khi chưa có token) — để `isDesktop` đúng ở mọi lần mở app và token cũ hỏng bị thay luôn. SaaS: 404 → giữ token đang có.
  - `frontend/lib/api.ts` `tryRefresh`: refresh hỏng → thử `desktop-session` trước khi đá ra `/login`.
  - `frontend/app/login/page.tsx`: ở desktop có user thì `router.replace("/dashboard")`.
  - Bẫy khi tự chạy `.exe` từ terminal của VS Code/Claude Code: terminal kế thừa `ELECTRON_RUN_AS_NODE=1` → app thoát ngay mã 0, không mở cửa sổ. Phải `Remove-Item Env:ELECTRON_RUN_AS_NODE` trước. Khách mở từ shortcut không bị.

## E. Đóng gói thật — bundle Python Embeddable + Next standalone + electron-builder NSIS [ĐÃ XONG]

- **Phát hiện quan trọng khi khảo sát**: bundle nguyên `.venv` (như kiến trúc gốc mô tả) **không chạy được trên máy khách** — `venv` trên Windows không copy `python311.dll` vào `Scripts/`, `python.exe` của venv phụ thuộc bản Python gốc cài ở đường dẫn cố định trên máy dev (`pyvenv.cfg` → `home = C:\Users\...\Python311`). Máy khách không có đúng đường dẫn đó thì `python.exe` không chạy được — đã tự kiểm chứng bằng `strings`/`ls`, xác nhận `.venv/Scripts/` không có `python311.dll` còn bản cài gốc thì có.
- **Hướng sửa**: dựng runtime Python **Embeddable** chính thức (`python-3.11.9-embed-amd64.zip` từ python.org, tự chứa `python311.dll`, portable thật) tại `desktop/build-runtime/python` — bật `Lib\site-packages` trong `python311._pth`, cài `pip` qua `get-pip.py`, `pip install -r backend/requirements.txt -r commhunter/requirements.txt` (2 file không xung đột pin, đã kiểm). Verify: `python.exe -m uvicorn app.main:app` chạy được từ thư mục bất kỳ, `POST /api/auth/desktop-session` + `GET/PUT /api/settings` trả đúng trên DB SQLite hoàn toàn mới (bảng tự tạo qua `init_models()` khi thấy `sqlite` trong `DATABASE_URL` — không cần alembic cho desktop). Không cần bundle Chromium: `browser_manager.py` mặc định `channel="chrome"` dùng Chrome thật đã cài trên máy khách; driver node.exe của Playwright đã nằm sẵn trong `site-packages/playwright/driver`.
- `desktop/main.js`: thêm nhánh `IS_PACKAGED` (`app.isPackaged`) — backend dùng `resources/python/python.exe` thay `.venv`; frontend dùng `resources/frontend/server.js` (Next standalone) chạy bằng chính `process.execPath` của Electron với `ELECTRON_RUN_AS_NODE=1` (Electron đã nhúng sẵn Node đầy đủ, không cần đóng gói Node riêng). Chế độ dev (`npm start`, chưa đóng gói) giữ nguyên hành vi cũ (`.venv` + `npm run dev`).
- `frontend/next.config.ts` đã có sẵn `output: "standalone"` (dùng chung với Docker). Build packaging phải cố định `NEXT_PUBLIC_API_URL=http://127.0.0.1:8877` lúc `next build` — biến `NEXT_PUBLIC_*` được inline vào JS client lúc build, đặt lại lúc chạy không có tác dụng.
- **Bẫy của electron-builder (mất nửa buổi mới ra)**: `extraResources` copy thư mục thì bộ liệt kê file **luôn bỏ qua mọi thư mục tên `node_modules`** ở tầng duyệt cây, trước khi filter kịp chạy — filter tường minh không cứu được vì thư mục chưa từng lọt vào danh sách để lọc. Next standalone lại cần `node_modules` thật (`server.js` gọi `require("next")` trực tiếp). Fix: hook `afterPack` (`desktop/scripts/after-pack.js`) copy tay `frontend/.next/standalone/node_modules` bằng `fs.cpSync` sau khi electron-builder đóng gói xong.
- `desktop/package.json`: thêm `electron-builder` (devDependency), field `build` (appId, `extraResources` cho `python/`, `backend/` (chỉ `app/`+`alembic/`+`alembic.ini`), `commhunter/` (chỉ `*.py` phẳng + `configs/example.yaml`, loại `data/`/`tests/`/cookie thật), `frontend/` (standalone + static + public)), `win.target: nsis`, script `npm run dist`.
- `.gitignore`: thêm `desktop/build-runtime/` + `desktop/release/` (blob nhị phân dựng lại được bằng script, không commit).
- **Chạy thật kiểm chứng (không phải chỉ build xong)**: `npm run dist` ra `release/CommHunterAI-Setup-0.1.0.exe` (~128MB, unpacked ~497MB) → cài **silent** (`/S /D=...`) vào thư mục test riêng, tách khỏi thư mục `.venv`/repo hiện có → xoá sạch `userData` cũ (mô phỏng máy sạch chưa từng chạy) → chạy `.exe` đã cài: backend health 200 sau ~1s (Python Embeddable, không đụng `.venv`), frontend health 200 sau ~1s (Next standalone, không cần `npm`), `POST /api/auth/desktop-session` + `GET/PUT /api/settings` qua HTTP thật đều đúng, cửa sổ chính mở đúng tiêu đề. Đóng graceful → `before-quit` dọn sạch cả 2 sidecar, cổng 8877/3100 hết LISTEN.

## G. Telegram long-polling cho desktop [ĐÃ XONG]

- **Lỗ hổng (phát hiện khi đối chiếu yêu cầu khách 11/09/2026)**: backend chỉ nhận Update Telegram qua webhook (`POST /api/webhook/telegram`). Webhook cần URL public — máy khách chạy local không có, nên ở chế độ desktop nút bấm bán tự động (ứng tuyển / xem trước / bỏ qua) và lệnh `/start <mã>` liên kết chat **không bao giờ tới backend**. Tin báo gửi đi vẫn tới.
- `backend/app/routers/telegram_webhook.py`: tách `handle_update(db, update, notifier)` dùng chung; endpoint webhook chỉ còn kiểm secret + gọi hàm này (hành vi SaaS không đổi).
- `backend/app/services/notification_service.py`: thêm `get_updates(offset, timeout)`; `_call` nhận `timeout` (client HTTP phải chờ lâu hơn thời gian Telegram giữ kết nối).
- `backend/app/workers/telegram_poller.py` (mới): `poll_once` + `TelegramPoller` — long-polling 25s, đọc lại token mỗi vòng (khách nhập token ở màn Cài đặt khi app đang chạy), đổi token thì reset offset, chưa có token thì ngủ 10s, lỗi / 409 (bot đang gắn webhook) thì lùi 30s và log hướng dẫn gỡ webhook. Offset nhích qua update TRƯỚC khi xử lý để update làm handler lỗi không bị gửi lại mãi. Không tự gọi `deleteWebhook` — đó là thao tác đổi cấu hình bot, để anh Ber quyết.
- `backend/app/main.py`: `RUN_MODE=desktop` bật poller sau `start_scheduler()`, tắt trước `stop_scheduler()`.
- Kiểm chứng: `backend/tests/test_api.py` mục 14j (6 assertion — `/start` qua getUpdates gắn chat_id, offset, 409 giữ offset, update lỗi không chặn update sau, start/stop sạch khi chưa có token), đã kiểm đột biến (`update_id + 1` → `update_id` bắt đỏ 2 assertion). Boot app `RUN_MODE=desktop` trên DB tạm: `/health` 200, poller chạy, tắt sạch. **Chưa chạy với bot Telegram thật.**

## F. Chưa làm (Giai đoạn 6)

- Giai đoạn 5 (tài liệu first-run) đã gộp lên trạng thái "Xong 1-4", đổi số — mục còn lại là **tài liệu hoá hướng dẫn cài đặt cho khách** (ảnh chụp, các bước, xử lý cảnh báo SmartScreen).
- Icon ứng dụng riêng (đang dùng icon mặc định của Electron).
- Chưa test trên một máy Windows **thực sự khác** (chỉ mô phỏng máy sạch bằng cách xoá `userData` + cài vào thư mục cách ly trên cùng máy dev — loại được lỗi phụ thuộc `.venv`/`npm`, nhưng chưa loại được khác biệt phần cứng/Windows edition/chính sách nhóm của máy khách thật).
- `playwright install-deps`/Visual C++ Redistributable trên máy khách chưa cài gì — chưa verify (máy dev đã có sẵn các runtime này nên không phát hiện được nếu thiếu).

### Rủi ro / giả định chưa chốt (cần anh Ber xác nhận trước khi làm Giai đoạn 4 trở đi)
1. Bỏ `self.retry()` tức thời (giờ chỉ thử lại ở chu kỳ dispatch kế tiếp 30-60s) — SLA chấp nhận được không?
2. ~~Cookie encryption key phải sinh 1 lần + lưu bền cho desktop~~ — ĐÃ VÁ (Giai đoạn 2, `ensure_cookie_key`).
3. `playwright install` (driver nội bộ) — cần verify trên máy Windows sạch chưa từng cài.
4. 1 hàng đợi tuần tự TOÀN CỤC (không khoá riêng theo clone) — nhiều clone chạy lần lượt, chậm hơn Celery pool.
5. Giữ code path Postgres/`asyncpg` không xoá — cần `requirements-desktop.txt` riêng nếu muốn giảm dung lượng installer.
6. Cổng nội bộ cố định 8877/3100 — chấp nhận hard-code hay cần dò cổng trống?
7. Không code-signing → SmartScreen cảnh báo "Unknown publisher".
8. User desktop seed (`khach@local.commhunter`) dùng gói Studio hạn 100 năm để không chặn quota — mô hình billing hiện tại (Starter/Pro/Studio trả phí) không còn ý nghĩa khi bán app desktop 1 lần; cần anh Ber chốt mô hình kinh doanh cho bản desktop (bán đứt file cài đặt? vẫn thu phí định kỳ qua license key riêng?) trước khi đụng tới `services/plans.py`/`routers/billing.py`.
9. Desktop tạo bảng bằng `init_models()` (`create_all`), không chạy alembic — `create_all` **không thêm cột mới vào bảng đã có**. Bản cài mới thì đủ cột; một DB desktop đã có dữ liệu nâng cấp lên bản có migration thêm cột (`0005`, `0007`) sẽ lỗi "no such column". Hiện chưa có DB desktop nào đang dùng (đã kiểm `%APPDATA%` 11/09/2026); cần chạy `alembic upgrade head` lúc khởi động trước khi giao bản cập nhật cho máy đã có dữ liệu.
