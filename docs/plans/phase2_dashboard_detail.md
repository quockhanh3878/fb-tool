# PHASE 2 — WEB DASHBOARD & BACKEND: Chi tiết Triển khai (Tuần 3-6)

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
| POST | `/api/campaigns/{id}/groups/discover` | Cào hồ sơ clone Scout, nạp các nhóm đã tham gia (status `paused`, chờ duyệt) |
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

**Subtask 2.5.5: `discover_joined_groups` (cào nhóm đã tham gia)**
- Task Celery riêng, kích hoạt theo yêu cầu từ `POST /api/campaigns/{id}/groups/discover` (không nằm trong Beat).
- `scout_worker.scrape_joined_groups()` mở trang "Nhóm của bạn" bằng tài khoản Scout, cuộn, bóc `{key, name, url}` — chỉ đọc, có fail-safe khi selector không khớp (trả rỗng).
- **Soi DOM thật 10/09/2026** (`/groups/joins/`, CDP 9222): `EXTRACT_GROUPS_JS` bóc đúng ~93 nhóm; đã sửa để cắt đuôi "Lần hoạt động gần nhất…" / "Bạn và N người bạn…" khỏi tên nhóm (trước đó `textContent` nối cả metadata làm tên dài >120 ký tự và bị xoá trắng).
- `services/group_discovery_service.merge_discovered_groups()` chuẩn hoá qua `parse_group_ref`, loại trùng theo `group_key`, thêm tới khi đầy `subscription.max_groups`, phần dư tính vào `skipped_quota`.
- Nhóm mới về ở trạng thái `paused` — người dùng tự bật nhóm muốn theo dõi. Bắn tóm tắt qua `notification_service` nếu user đã liên kết Telegram.

**Subtask 2.5.6: Đăng bài Seeding thật (Task 2.14 — bổ sung 10/09/2026)**
- Trước đây `publisher_service.execute_publish` **giả lập**: sinh `simulated_url` bằng timestamp + số ngẫu nhiên rồi ghi `status = published`. Dashboard hiển thị "Đã đăng" kèm link không tồn tại — báo cáo sai sự thật. Đã bỏ hoàn toàn.
- `commhunter/shooter_worker.publish_post(group_url, content)` bám nguyên trình tự phòng thủ của `post_comment`: warmup → goto → `detect_checkpoint_page` → tìm composer (`COMPOSER_TRIGGER/TEXTBOX/SUBMIT_SELECTORS`) → `human_mouse_jiggle` → `human_type` → submit → verify bằng `POST_SUCCESS_PHRASES` → mở lại feed nhóm, bóc permalink bằng `EXTRACT_LATEST_POST_JS`.
- Trả `PublishResult(status, post_url, error)`: `published` (có link) · `published_no_url` (đăng xong, không bóc được link — không coi là thành công trọn vẹn) · `failed` (selector không khớp / checkpoint → dừng nick, **không thử mù, không bịa link**).
- `workers/browser_runtime.publish_post_real` là cầu nối theo khuôn `post_comment_real`.
- **Attach CDP cho backend (bổ sung 10/09/2026)**: `RuntimeAccount.cdp_endpoint` + `RuntimeConfig.browser.attach_cdp`; `build_runtime_config` đọc `settings.browser_cdp_endpoint` (`BROWSER_CDP_ENDPOINT`). Có giá trị → ScoutWorker/ShooterWorker attach vào Chrome đang mở (`getattr(cfg, "cdp_endpoint", None)` đã có sẵn ở Phase 1), clone **không cần** `cookie_data_encrypted`; đồng thời bỏ proxy và không ghi cookie giải mã ra đĩa (`_maybe_write_cookies`). Rỗng → giữ nguyên: mỗi clone một profile persistent + vân tay. Chỉ dùng dev/test trên máy anh Ber. Test: mục 7b `test_api.py`.
- `execute_publish`: mỗi group một bản render spintax riêng; `BrowserRuntimeUnavailable` → `status = failed` (không rơi về giả lập); `daily_post_count` tăng theo **số nhóm đã đăng**; trạng thái tổng: toàn bộ link OK → `published`, một phần → `partially_published`, không nhóm nào → `failed`.
- **Soi DOM composer thật 10/09/2026** (nick phụ, CDP 9222, group "Hội BMW"): nút mở là `div[role="button"]` text "Bạn viết gì đi…"; dialog heading "Tạo bài viết", ô nhập `[role="textbox"][contenteditable]` KHÔNG còn aria-label mô tả; nút Đăng `aria-label="Đăng"` có `aria-disabled="true"` tới khi có nội dung → `COMPOSER_SUBMIT_SELECTORS` thêm biến thể `:not([aria-disabled="true"])` đứng trước. `publish_post` mở composer + gõ + bấm Đăng chạy trọn. Group bật kiểm duyệt → bài vào hàng chờ, trả `PUBLISHED_NO_URL` đúng thiết kế; **chưa verify `EXTRACT_LATEST_POST_JS` E2E** (cần group không kiểm duyệt). Bài test đã dọn khỏi hàng chờ.
- **Migration `0004_track_a_dang_bai.py` (bổ sung 10/09/2026)**: tạo bảng `post_publishes` + thêm `clone_accounts.daily_post_count` / `daily_post_limit` (NOT NULL, `server_default` `0` / `5` — bảng đã có dữ liệu khách). Xoá nợ `alembic check` báo drift. `upgrade head` + `downgrade base` sạch.
- **E2E đường backend — Track A Item 3 (bổ sung 11/09/2026, anh Ber duyệt)**: chạy thật `publisher_task._due_publishes` → `execute_publish` → `browser_runtime.publish_post_real` trên burner `1042987808508567` (CDP 9222, clone không cookie). Kết quả: `PublishStatus.PUBLISHED` + `publish_results[0].post_url` là permalink thật + `daily_post_count` +1 + `note_ok` giữ nick active; `browser_runtime.delete_own_post_real` (mới) dọn sạch. Lộ + sửa 2 bug: (1) `_post_submitted_ok` báo `submit_not_confirmed` giả khi hộp thoại soạn bài đóng chậm → POLL tối đa `POST_SUBMIT_CONFIRM_TIMEOUT_MS` = 14s; bỏ "đã đăng" trần khỏi `POST_SUCCESS_PHRASES`. (2) trang permalink FB chèn bài "được đề xuất" cùng nút "Hành động đối với bài viết này..." → `delete_own_post` bấm nhầm → `_open_own_post_menu` lọc theo tên tài khoản đang đăng nhập (`_current_account_name` từ payload bootstrap); `_click_menu_text`/`_confirm_delete_dialog` chuyển sang JS click.
- **Rollback / cleanup (bổ sung 11/09/2026)**: `ShooterWorker.delete_own_post(page, post_url, author_name=None)` — xoá bài chính mình đã đăng (mở permalink → nút menu `aria-label*="Hành động đối với bài viết này của <tên>"` → mục "Xóa bài viết" / "Chuyển vào thùng rác" → nút xác nhận khớp tuyệt đối → verify `POST_GONE_MARKERS`; fail an toàn). `execute_publish`: khi `BrowserRuntimeUnavailable` xảy ra **sau khi** đã đăng xong ≥1 nhóm → KHÔNG còn gán `publish_results = []` (trước đây làm mất permalink đã ghi thật, không còn đường dọn); giữ kết quả, trạng thái `partially_published`, `error_message` liệt kê link đã đăng để anh Ber rà soát tay. **KHÔNG tự xoá** bài đã lên — đó là nội dung khách muốn giữ, và xoá là một thao tác GHI có rủi ro riêng cần người quyết. Test: `test_pipeline.py` (delete_own_post, 3 assertion) + `test_api.py` mục 14d (5 assertion), đều đã kiểm đột biến.

**Bổ sung: lịch sử publish/comment và trạng thái lead (22/09/2026)**
- Migration `0013_publish_comment_lead_history.py` tạo `post_publish_history`; bổ sung `fb_comment_id` và `comment_url` cho `comment_actions`, cùng `comment_url` cho `comment_leads`. Mỗi group publish được lưu durable theo `post_url`, trạng thái, thời điểm và lỗi; JSON snapshot cũ vẫn được giữ để tương thích.
- API vận hành: `GET /api/publishing/history` và `GET /api/comment-history` trả lịch sử theo campaign/clone/status; dữ liệu lead từ `/api/leads` có `post_url`, `comment_url`, `is_read` và thao tác đọc/lưu trữ/xoá.
- Dashboard `/leads` cho phép lọc theo campaign/trạng thái, mở link bài gốc hoặc link comment, đánh dấu đã đọc và lưu trữ. Đây là lớp theo dõi lead đã phát hiện, không phải bộ quét Facebook tự động.
- `ShooterWorker.post_comment` bóc permalink comment khi Facebook trả được `comment_id`; browser bridge trả cả `comment_url` và `fb_comment_id`, có fallback tương thích với worker cũ.
- Kiểm chứng: targeted backend history 65 pass chứng minh lưu/truy vấn history, frontend typecheck/build pass, migration `0013` upgrade sạch; E2E clone CDP trên group test `1042987808508567` tạo post/comment thật, extractor lấy comment ID/link qua browser bridge và dọn sạch sau test. Extractor DOM và đường Beat đã được nối; selector vẫn fail-safe và cần bảo trì khi Facebook đổi DOM.

**Bổ sung: upload ảnh Facebook thật (22/09/2026)**
- `ShooterWorker._attach_media` tìm `input[type="file"]` thuộc composer, dùng `set_input_files` và chờ thumbnail `blob:` hoặc file list được Facebook nhận đủ; lỗi đọc/tải ảnh trả `media_upload_not_verified` và không submit bài.
- **E2E clone CDP 9222** trên group `1042987808508567`: dùng JPG hợp lệ trong máy test, composer dựng thumbnail blob, bài đăng thật trả `PUBLISHED` + permalink `1053179080822773`; sau đó comment thật trả `fb_comment_id = 1053180110822670` và permalink có `comment_id`; cleanup `delete_own_post_real` trả `True`.
- Ảnh mẫu placeholder không hợp lệ đã bị Facebook từ chối đúng thiết kế; kiểm thử thành công dùng JPG hệ thống hợp lệ. Không đưa ảnh test hoặc session vào repo.

**Subtask 2.5.7: Hộp thư "Nhắc tới" (Track B — bổ sung 10/09/2026)**
- Mục tiêu: trong lúc Scout quét nhóm, bắt luôn các bài **nhắc tên thương hiệu / dịch vụ của khách** (khác với bài lead cần ứng tuyển) và gom vào một hộp thư riêng để anh Ber theo dõi và phản hồi tay.
- `campaigns.mention_keywords` (JSON list) — danh sách từ khoá thương hiệu. Rỗng thì tính năng tắt hẳn cho chiến dịch đó (không tốn gì thêm).
- Bảng `mentions`: `campaign_id` (CASCADE), `campaign_group_id` / `discovered_post_id` (SET NULL), `content_hash` (dedup theo `UniqueConstraint(campaign_id, content_hash)` — cùng công thức `compute_content_hash` với `discovered_posts`), `matched_keywords`, `author_name`, `content_text`, `post_url`, `status` (`new` / `read` / `archived`), `discovered_at`, `seen_at`.
- `services/mention_service.detect_mentions(db, campaign, group, posts)` — hàm thuần DB, so khớp `mention_keywords` với text bài đã ingest bằng `ai_service.normalize_vi` (bỏ dấu, hạ chữ thường — bắt được cả tiếng Việt gõ thiếu dấu), bỏ bài trùng `content_hash`. Không phụ thuộc Playwright → test offline. Không commit.
- Móc vào cả hai đường ingest: `workers/scout_task._scan_one` (Beat) và `POST /api/campaigns/{id}/ingest` (Scout worker nộp tay) — chạy sau `process_campaign_posts`, trước `commit`. Có `mention` mới + user đã liên kết Telegram → bắn tóm tắt một dòng qua `notification_service`.
- **Bắn Telegram dùng chung một helper (bổ sung 10/09/2026)**: `mention_service.notify_mentions(user, campaign_name, mentions, notifier=None)` — guard `mentions` rỗng / `user is None` / `telegram_chat_id` rỗng ở một chỗ, gọi `mention_summary` + `NotificationService.send_text`. Cả hai đường ingest gọi helper này (trước đây chỉ đường Beat bắn, `POST /ingest` bỏ sót). Test: mục 4e `test_api.py` (helper + hồi quy spy trên `routers/posts.notify_mentions`).
- Router `/api/mentions`: `GET ""` (lọc `campaign_id` / `status`, phân trang) · `GET /unread-count` (badge sidebar, đếm `status = new`) · `POST /{id}/read` · `POST /{id}/archive` · `DELETE /{id}`. Cách ly đa khách qua `Campaign.user_id`.
- Dashboard: route `/mentions` (danh sách, lọc theo chiến dịch/trạng thái, nút Đã đọc / Lưu trữ / Xoá, mở bài gốc) + mục sidebar "Nhắc tới" kèm badge số chưa đọc (poll `unread-count`). Ô nhập `mention_keywords` (TagInput) trong tab Cấu hình chiến dịch.
- Migration `0003_hop_thu_nhac_toi.py` — thêm cột + tạo bảng, mọi cột NOT NULL có `server_default`.

**Subtask 2.5.8: Mode treo — tự bảo vệ khi chạy không người trực (Track C — bổ sung 11/09/2026)**
- Bối cảnh: đường comment (shooter) đã có `AccountManager.record_failure` tự cho nick nghỉ khi hỏng liên tiếp / dính checkpoint. Đường **quét (scout)** và **đăng bài (publisher)** thì chưa — Beat cứ 60s lại chọn đúng nick đó chạy lại, nick checkpoint bị "đâm" liên tục. Track C bịt hai lỗ này, dùng lại đúng state machine sẵn có (không thêm trạng thái mới).
- `AccountManager.note_ok(clone)` — một lượt việc KHÔNG-phải-comment (quét / đăng bài) trót lọt: chỉ reset `consecutive_failures` + dập nhịp `last_activity_at`, KHÔNG đụng `daily_comment_count` như `record_success`.
- `browser_runtime.ScoutCheckpoint` + hàm thuần `wrap_scout_error(exc)` — `scout_worker.CheckpointError` (kéo theo Playwright, không import được ở tầng module) được bắt theo tên lớp rồi bọc lại. `scan_group_raw` raise `ScoutCheckpoint` khi gặp.
- `scout_task._scan_one`: `ScoutCheckpoint` → `_flag_scout_checkpoint` (`AccountManager.transition(CHECKPOINT_DETECTED)`, nuốt `InvalidTransitionError` nếu đã ở CHECKPOINT/BANNED) → trả `{"error": "scout_checkpoint"}`, không quét lại. Lỗi thường → `_note_scout_failure` (`record_failure`, đủ ngưỡng thì tự cooldown). Lượt OK → `note_ok`.
- `publisher_service.execute_publish`: sau khi ghi kết quả, soi `results` — có `error == "checkpoint"` → `transition(CHECKPOINT_DETECTED)`; không nhóm nào đăng được (không checkpoint) → `record_failure`; có nhóm đăng được → `note_ok`.
- Thông báo dùng chung `notification_service.build_clone_notifier(db)` — trả `async (user_id, message)` tra `User.telegram_chat_id` rồi bắn. `health_check_task._notifier` cũng rút gọn về helper này.
- Test: `test_api.py` mục 14d-bis (poster checkpoint / hỏng toàn bộ, 2 assertion) + 14e (scout checkpoint, hỏng 3 lượt → cooldown, lượt OK reset, `wrap_scout_error`, 6 assertion). Đã kiểm đột biến 4 điểm (guard `saw_checkpoint`, `note_ok` reset, `wrap_scout_error` khớp tên lớp, ngưỡng `record_failure`).

**Subtask 2.5.9: Preflight sức khoẻ nick trước lượt chạy thật (Track D — bổ sung 11/09/2026)**
- Bối cảnh: khi chạy dài không người trực, cần xác nhận nick còn đăng nhập + không dính checkpoint TRƯỚC khi Scout quét hay Poster đăng, thay vì phát hiện giữa chừng (đã đăng nửa vời) hoặc để Beat 60s cứ chọn lại nick hỏng.
- `browser_manager.probe_session_reason(profile_dir, cdp_endpoint)` — mở `facebook.com`, phân biệt `ok` / `checkpoint` (URL hoặc `detect_checkpoint_page` trên DOM) / `login_expired` (URL `login` hoặc `button[name="login"]`) / `error`. `check_session` cũ (trả `bool`) nay chỉ là `probe_session_reason(...) == "ok"` — không nhân đôi logic.
- `workers/browser_runtime.preflight_check_real(clone, cookies)` — cầu nối, trả `{"ok": bool, "reason": str}`. Attach CDP nếu có; `BrowserRuntimeUnavailable` → `{"ok": False, "reason": "runtime_unavailable: ..."}`.
- `services/preflight_service.run_preflight(db, clone, *, cookies=None, prober=None)` — `ok` → `AccountManager.note_ok`; `checkpoint` → `transition(CHECKPOINT_DETECTED)` (nuốt `InvalidTransitionError`); còn lại → `record_failure` (đủ ngưỡng tự cooldown). KHÔNG commit — caller commit. `prober` tách ra để test offline tiêm giả.
- Gate qua `settings.preflight_before_run` (`PREFLIGHT_BEFORE_RUN`, **mặc định TẮT** — bật thêm một lần mở browser ~30-60s cho mỗi lượt): bật thì `scout_task._scan_one` và `publisher_service.execute_publish` chạy preflight ngay sau khi chọn clone; không đạt → huỷ lượt (`{"error": "preflight_failed", "reason": ...}` / `PostPublish.status = failed`), nick đã bị state machine dừng.
- Celery `workers/preflight_task.preflight_clone(clone_id)` / `preflight_user_clones(user_id)` — kích hoạt theo yêu cầu (không vào Beat), quét nick active của một khách.
- Test: `test_api.py` mục 14f (8 assertion — 3 nhánh state machine theo `reason`, gate publish + gate scout đều KHÔNG gọi runtime khi preflight hỏng). Đã kiểm đột biến (`reason == "checkpoint"` → `!=` → 2 assertion đỏ). **Chạy thật 11/09/2026** (CDP 9222, burner): `preflight_check_real` → `{"ok": True, "reason": "ok"}`.

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
