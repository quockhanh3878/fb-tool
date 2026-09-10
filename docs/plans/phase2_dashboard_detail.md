# 📋 PHASE 2 — WEB DASHBOARD & BACKEND: Chi tiết Triển khai (Tuần 3-6)

> **Mục tiêu:** Chuyển đổi MVP Script thành nền tảng Web Self-Service, cho phép khách hàng tự đăng ký tài khoản, tự cấu hình chiến dịch, quản lý clone và theo dõi kết quả trên giao diện web mà không cần hỗ trợ kỹ thuật.
> **Tiền đề:** Phase 1 MVP Script đã chạy ổn định cho khách Nyatymita.
> **Tham chiếu:** [Master Plan §3, §7, §9](file:///f:/Clone/fb-tool/docs/03_MASTER_PLAN.md) | [Phase 1 Detail](file:///f:/Clone/fb-tool/docs/plans/phase1_mvp_detail.md)

---

## Cấu trúc thư mục Phase 2

```
fb-tool/
├── commhunter/                         # MVP Code (từ Phase 1)
├── backend/                            # FastAPI Backend mới
│   ├── app/
│   │   ├── main.py                     # FastAPI entry point
│   │   ├── config.py                   # Settings (env-based)
│   │   ├── database.py                 # SQLAlchemy + PostgreSQL
│   │   ├── dependencies.py             # Dependency injection
│   │   ├── models/                     # SQLAlchemy ORM Models
│   │   │   ├── user.py
│   │   │   ├── campaign.py
│   │   │   ├── group.py
│   │   │   ├── clone_account.py
│   │   │   ├── comment_script.py
│   │   │   ├── discovered_post.py
│   │   │   ├── comment_action.py
│   │   │   ├── bump_schedule.py
│   │   │   └── subscription.py
│   │   ├── schemas/                    # Pydantic Request/Response Schemas
│   │   │   ├── auth.py
│   │   │   ├── campaign.py
│   │   │   ├── group.py
│   │   │   └── ...
│   │   ├── routers/                    # API Endpoints
│   │   │   ├── auth.py                 # POST /auth/register, /auth/login
│   │   │   ├── campaigns.py            # CRUD /campaigns
│   │   │   ├── groups.py               # CRUD /campaigns/{id}/groups
│   │   │   ├── scripts.py              # CRUD /campaigns/{id}/scripts
│   │   │   ├── clones.py               # CRUD /clones
│   │   │   ├── posts.py                # GET /posts (feed bài phát hiện)
│   │   │   ├── stats.py                # GET /stats/dashboard
│   │   │   └── telegram_webhook.py     # POST /webhook/telegram
│   │   ├── services/                   # Business Logic Layer
│   │   │   ├── campaign_service.py
│   │   │   ├── scout_service.py
│   │   │   ├── shooter_service.py
│   │   │   └── notification_service.py
│   │   └── workers/                    # Celery Tasks
│   │       ├── celery_app.py
│   │       ├── scout_task.py           # Kế thừa scout_worker.py từ Phase 1
│   │       ├── shooter_task.py         # Kế thừa shooter_worker.py từ Phase 1
│   │       ├── bump_task.py
│   │       └── warmup_task.py
│   ├── alembic/                        # Database migrations
│   ├── docker-compose.yaml             # PostgreSQL + Redis + API + Worker
│   ├── Dockerfile
│   ├── requirements.txt
│   └── .env.example
├── frontend/                           # Next.js Dashboard
│   ├── app/
│   │   ├── layout.tsx
│   │   ├── page.tsx                    # Landing / Login
│   │   ├── dashboard/
│   │   │   ├── page.tsx                # Dashboard Overview
│   │   │   ├── campaigns/
│   │   │   │   ├── page.tsx            # Danh sách chiến dịch
│   │   │   │   ├── [id]/
│   │   │   │   │   ├── page.tsx        # Chi tiết chiến dịch
│   │   │   │   │   ├── groups/page.tsx # Quản lý group
│   │   │   │   │   └── scripts/page.tsx# Xưởng kịch bản
│   │   │   ├── clones/page.tsx         # Quản lý clone
│   │   │   ├── posts/page.tsx          # Feed bài viết
│   │   │   ├── bump/page.tsx           # Lịch bump
│   │   │   └── stats/page.tsx          # Báo cáo thống kê
│   ├── components/
│   │   ├── ui/                         # Shadcn UI components
│   │   ├── campaign-card.tsx
│   │   ├── post-feed.tsx
│   │   ├── clone-status-badge.tsx
│   │   └── stats-chart.tsx
│   ├── lib/
│   │   ├── api.ts                      # API client (fetch wrapper)
│   │   └── auth.ts                     # JWT token management
│   ├── package.json
│   └── tailwind.config.ts
└── docs/
```

---

## Sprint 3 (Tuần 3): Backend Foundation

### Task 2.1: Setup dự án Backend + Database (Ngày 1-2)

**Subtask 2.1.1: Khởi tạo FastAPI project**
- Cài đặt FastAPI + Uvicorn + SQLAlchemy + Alembic + Celery + Redis
- Cấu hình `Settings` class đọc từ `.env`
- Setup CORS middleware cho frontend

**Subtask 2.1.2: Docker Compose stack**
```yaml
# docker-compose.yaml
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: commhunter
      POSTGRES_USER: commhunter
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - pgdata:/var/lib/postgresql/data
    ports: ["5432:5432"]

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]

  api:
    build: .
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
    environment:
      DATABASE_URL: postgresql+asyncpg://commhunter:${DB_PASSWORD}@db:5432/commhunter
      REDIS_URL: redis://redis:6379/0
    ports: ["8000:8000"]
    depends_on: [db, redis]

  worker:
    build: .
    command: celery -A app.workers.celery_app worker --loglevel=info
    environment:
      DATABASE_URL: postgresql+asyncpg://commhunter:${DB_PASSWORD}@db:5432/commhunter
      REDIS_URL: redis://redis:6379/0
    depends_on: [db, redis]

  beat:
    build: .
    command: celery -A app.workers.celery_app beat --loglevel=info
    depends_on: [worker]

volumes:
  pgdata:
```

**Subtask 2.1.3: PostgreSQL Schema Migration**
- Chuyển đổi schema SQLite từ Phase 1 sang PostgreSQL ORM models
- Sử dụng 9 bảng theo [Master Plan §3](file:///f:/Clone/fb-tool/docs/03_MASTER_PLAN.md)
- Tạo Alembic initial migration

**Acceptance Criteria:**
- [ ] `docker compose up` khởi động đầy đủ 5 services
- [ ] Alembic migrate thành công, tạo đủ 9 bảng
- [ ] API endpoint `/health` trả về `{"status": "ok"}`

---

### Task 2.2: REST API — Auth & User Management (Ngày 2-3)

**Endpoints:**

| Method | Path | Mô tả |
|--------|------|-------|
| POST | `/api/auth/register` | Đăng ký tài khoản mới (email + password) |
| POST | `/api/auth/login` | Đăng nhập, trả về JWT access + refresh token |
| POST | `/api/auth/refresh` | Refresh JWT token |
| GET | `/api/auth/me` | Lấy thông tin user hiện tại |
| PUT | `/api/auth/me` | Cập nhật profile (telegram_chat_id, display_name) |
| POST | `/api/auth/connect-telegram` | Liên kết Telegram Bot với tài khoản |

**Security:**
- JWT Access Token (15 phút) + Refresh Token (7 ngày)
- Password hash: bcrypt
- Rate limit: 5 request/phút cho login/register

**Acceptance Criteria:**
- [ ] Register + Login flow hoạt động
- [ ] JWT middleware bảo vệ tất cả endpoint private
- [ ] Refresh token flow hoạt động

---

### Task 2.3: REST API — Campaign CRUD (Ngày 3-4)

**Endpoints:**

| Method | Path | Mô tả |
|--------|------|-------|
| GET | `/api/campaigns` | Danh sách chiến dịch của user |
| POST | `/api/campaigns` | Tạo chiến dịch mới |
| GET | `/api/campaigns/{id}` | Chi tiết chiến dịch |
| PUT | `/api/campaigns/{id}` | Cập nhật chiến dịch |
| DELETE | `/api/campaigns/{id}` | Xóa chiến dịch |
| POST | `/api/campaigns/{id}/activate` | Bật chiến dịch |
| POST | `/api/campaigns/{id}/pause` | Tạm dừng chiến dịch |

**Nested Resources:**

| Method | Path | Mô tả |
|--------|------|-------|
| GET | `/api/campaigns/{id}/groups` | Danh sách group của chiến dịch |
| POST | `/api/campaigns/{id}/groups` | Thêm group |
| PUT | `/api/campaigns/{id}/groups/{gid}` | Cập nhật group (tần suất quét...) |
| DELETE | `/api/campaigns/{id}/groups/{gid}` | Xóa group |
| GET | `/api/campaigns/{id}/scripts` | Danh sách kịch bản comment |
| POST | `/api/campaigns/{id}/scripts` | Tạo kịch bản mới |
| PUT | `/api/campaigns/{id}/scripts/{sid}` | Cập nhật kịch bản |
| DELETE | `/api/campaigns/{id}/scripts/{sid}` | Xóa kịch bản |

**Business Logic quan trọng:**
- Kiểm tra `subscription.max_groups` trước khi cho thêm group
- Validate URL group hợp lệ (kế thừa [fbn/extractor.py](file:///f:/Clone/fb-tool/fbn-main/fbn/extractor.py) `parse_group_ref`)
- Khi activate chiến dịch → tạo Celery periodic task cho Scout Worker

**Acceptance Criteria:**
- [ ] CRUD hoạt động đầy đủ cho Campaign, Group, Script
- [ ] Validation: Không vượt quota group theo gói cước
- [ ] Activate/Pause toggle Celery Beat schedule

---

### Task 2.4: REST API — Clone Management (Ngày 4-5)

**Endpoints:**

| Method | Path | Mô tả |
|--------|------|-------|
| GET | `/api/clones` | Danh sách clone của user |
| POST | `/api/clones` | Thêm clone mới |
| PUT | `/api/clones/{id}` | Cập nhật thông tin clone |
| DELETE | `/api/clones/{id}` | Xóa clone |
| POST | `/api/clones/{id}/upload-cookie` | Upload file cookie JSON |
| GET | `/api/clones/{id}/health` | Kiểm tra sức khỏe clone |
| POST | `/api/clones/{id}/check-session` | Kiểm tra session còn sống |

**Upload Cookie Flow:**
1. User upload file cookie (JSON hoặc Netscape format)
2. Backend gọi `load_facebook_cookies()` (kế thừa [fbn/auth.py](file:///f:/Clone/fb-tool/fbn-main/fbn/auth.py)) để validate
3. Lưu cookie vào DB (encrypted) + tạo browser profile directory
4. Chạy background task kiểm tra session

**Acceptance Criteria:**
- [ ] Upload cookie thành công cho cả JSON và Netscape format
- [ ] Check session phát hiện chính xác trạng thái (active/expired/checkpoint)
- [ ] Không vượt quota clone theo gói cước

---

### Task 2.5: Celery Workers — Migrate từ Phase 1 (Ngày 5-7)

**Subtask 2.5.1: `scout_task.py`**
- Kế thừa `scout_worker.py` từ Phase 1
- Đọc cấu hình từ PostgreSQL thay vì YAML
- Lưu kết quả vào bảng `discovered_posts`
- Bắn notification qua `notification_service`

**Subtask 2.5.2: `shooter_task.py`**
- Kế thừa `shooter_worker.py` từ Phase 1
- Đọc job từ bảng `comment_actions` (status = queued)
- Cập nhật status sau khi hoàn thành

**Subtask 2.5.3: `bump_task.py`**
- Đọc `bump_schedules` có `is_active = True` và đến giờ
- Gọi shooter để thả comment bump

**Subtask 2.5.4: Celery Beat schedule**
```python
# celery_app.py
from celery.schedules import crontab

app.conf.beat_schedule = {
    'scout-scan-all': {
        'task': 'app.workers.scout_task.scan_all_active_campaigns',
        'schedule': 60.0,  # Mỗi 60 giây kiểm tra campaign nào cần quét
    },
    'shooter-process-queue': {
        'task': 'app.workers.shooter_task.process_comment_queue',
        'schedule': 30.0,  # Mỗi 30 giây kiểm tra comment queue
    },
    'bump-check-schedule': {
        'task': 'app.workers.bump_task.check_bump_schedules',
        'schedule': 300.0,  # Mỗi 5 phút kiểm tra bài cần bump
    },
}
```

**Acceptance Criteria:**
- [ ] Scout task chạy đúng tần suất cho từng campaign
- [ ] Shooter task xử lý comment queue tuần tự, đúng rate limit
- [ ] Bump task hoạt động theo lịch cấu hình
- [ ] Tất cả task multi-tenant: Không xung đột giữa các user

---

## Sprint 4 (Tuần 4): Frontend Dashboard

### Task 2.6: Setup Next.js + Shadcn UI (Ngày 1)
- `npx -y create-next-app@latest ./frontend`
- Cài đặt Shadcn UI, Tailwind CSS
- Cấu hình API client (`lib/api.ts`) với JWT interceptor
- Layout: Sidebar navigation + Top bar

### Task 2.7: Trang Dashboard Overview (Ngày 1-2)
- Card tổng quan: Bài quét hôm nay / Bài phù hợp / Comment đã gửi / Tỷ lệ thành công
- Biểu đồ xu hướng 7 ngày (line chart)
- Danh sách 5 bài phù hợp gần nhất (quick view)
- Trạng thái tài khoản clone (badge: active/warning/error)

### Task 2.8: Trang Quản lý Chiến dịch (Ngày 2-3)
- Danh sách chiến dịch dạng card grid
- Form tạo/sửa chiến dịch:
  - Tên chiến dịch
  - Chế độ: Semi-Auto / Full-Auto (radio)
  - Textarea cho AI Filter prompt
  - Tag input cho whitelist/blacklist keywords
  - Slider cho max_comments_per_day, delay range
- Toggle Activate / Pause

### Task 2.9: Trang Quản lý Group (Ngày 3-4)
- Bảng danh sách group: URL, Tên, Trạng thái, Tần suất quét, Lần quét cuối
- Form thêm group: Input URL + Select tần suất
- Status badge: Active (xanh) / Pending (vàng) / Blocked (đỏ)

### Task 2.10: Trang Xưởng Kịch bản (Ngày 4-5)
- Danh sách kịch bản hiện có
- Form soạn kịch bản:
  - Tên
  - Loại: Spintax / AI Contextual
  - Textarea nội dung template (với syntax highlight cho spintax)
  - Textarea AI system prompt (cho loại AI)
  - Upload ảnh portfolio đính kèm
- Nút "Preview": Sinh thử 3 mẫu comment từ kịch bản

### Task 2.11: Trang Quản lý Clone (Ngày 5-6)
- Bảng clone: Tên, Vai trò (Scout/Shooter), Trạng thái, CMT hôm nay / Max
- Form thêm clone:
  - Upload cookie file (JSON/Netscape)
  - Chọn vai trò
  - Input proxy address (optional)
- Nút "Kiểm tra session" → Call API check-session
- Health indicator: Thanh progress bar ngày (số cmt / max)

### Task 2.12: Trang Feed Bài viết (Ngày 6-7)
- Bảng/card list bài viết đã phát hiện
- Filter: Theo trạng thái (new/notified/commented/skipped) + Theo group + Theo ngày
- Chi tiết bài: Nội dung, AI score, AI reason, comment đã gửi (nếu có)
- Nút "Ứng tuyển ngay" (trigger manual comment)

### Task 2.13: Trang Lịch Bump (Ngày 7)
- Danh sách bài cần bump
- Form thêm: URL bài + Khung giờ (multi-select checkbox) + Danh sách tin nhắn bump
- Toggle Active / Pause cho từng bài

### Task 2.14: Trang Báo cáo Thống kê (Ngày 7)
- Biểu đồ cột: Số bài phát hiện theo ngày (30 ngày)
- Biểu đồ tròn: Phân bố trạng thái bài (commented/skipped/expired)
- Bảng: Top 5 group hiệu quả nhất (tỷ lệ bài phù hợp)
- Số liệu: Tổng comment / Tỷ lệ thành công / Thời gian phản hồi trung bình

---

## Sprint 5 (Tuần 5-6): Tích hợp & Deploy

### Task 2.15: Tích hợp Telegram Webhook với Backend (Ngày 1-2)
- Migrate `telegram_bot.py` từ Phase 1 sang FastAPI webhook endpoint
- Callback query xử lý trong `routers/telegram_webhook.py`
- Liên kết Telegram chat_id với user account

### Task 2.16: End-to-End Testing (Ngày 3-4)
| # | Test Case | Expected |
|---|---|---|
| E2E-01 | Đăng ký tài khoản + Tạo chiến dịch + Thêm group | Tất cả CRUD thành công |
| E2E-02 | Upload cookie + Check session | Session active |
| E2E-03 | Activate chiến dịch → Scout bắt đầu quét | Bài mới xuất hiện trong Feed |
| E2E-04 | Semi-auto: Telegram nhận thông báo → Bấm ứng tuyển | Comment được gửi thành công |
| E2E-05 | Dashboard thống kê cập nhật | Số liệu đúng real-time |
| E2E-06 | 2 user cùng lúc không xung đột | Multi-tenant isolation OK |

### Task 2.17: Deploy Production (Ngày 5-7)
- Thuê VPS (4 vCPU, 16GB RAM) hoặc AWS EC2
- Setup domain: `app.commhunter.vn`
- SSL certificate (Let's Encrypt)
- Nginx reverse proxy
- Docker Compose production build
- Monitoring: Basic health check + Uptime robot
- Backup PostgreSQL hàng ngày

**Acceptance Criteria Phase 2:**
- [ ] Khách mới tự đăng ký, tự cấu hình, tự chạy chiến dịch mà không cần hỗ trợ
- [ ] Hệ thống chạy ổn định 7 ngày liên tục không crash
- [ ] Response time API < 200ms cho 95% requests
- [ ] Dashboard load < 2 giây
