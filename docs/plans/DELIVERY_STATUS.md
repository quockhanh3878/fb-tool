# TÌNH TRẠNG BÀN GIAO — Đối chiếu Plan ↔ Mã nguồn thực tế

> Cập nhật: 11/09/2026 (Track A Item 3: E2E đường backend `publisher_task → execute_publish → publish_post_real` chạy thật trên burner group `1042987808508567` — `PublishStatus.PUBLISHED` + permalink thật + `delete_own_post_real` dọn sạch; sửa 2 bug `_post_submitted_ok` báo FAILED giả và `_open_own_post_menu` bấm nhầm bài "được đề xuất". Track D: `preflight_service.run_preflight` kiểm nick còn đăng nhập + không checkpoint trước lượt quét/đăng, gate qua `settings.preflight_before_run`; +14 assertion (pipeline 116, backend 314). Track C "mode treo": scout + publisher tự dừng nick khi checkpoint / hỏng liên tiếp qua `AccountManager`, dùng chung `build_clone_notifier`; +8 assertion mục 14d-bis/14e). 10/09/2026: migration `0004` cho Track A; `notify_mentions` bắn Telegram ở CẢ HAI đường ingest. Tài liệu này đối chiếu **từng task trong 4 plan** với mã nguồn
> đã thực sự tồn tại trong repo, và nói rõ **cái gì chưa làm được và vì sao**.
>
> Nguyên tắc: chỉ ghi **Xong** khi có mã nguồn chạy được **và** có test chứng minh.
> Ba mức trạng thái: **Xong** · **Chờ** (chặn bởi yếu tố ngoài) · **Chưa làm**.
> Việc chỉ có tài liệu mô tả không được tính là hoàn thành.

---

## 1. Bảng điểm tổng

| Phase | Task theo plan | Đã có mã + test | Chặn bởi yếu tố ngoài | Ghi chú |
|---|---|---|---|---|
| **Phase 1 — MVP Script** | 11 | 10 | 1 (Sprint 3: chạy thật) | 116/116 assertion PASS |
| **Phase 2 — Dashboard** | 19 | 18 | 1 (deploy VPS + SSL) | 328/328 assertion PASS; đăng bài E2E đường backend đã chạy thật trên burner |
| **Phase 3 — Anti-Ban** | 6 | 6 | — (ngưỡng cần hiệu chỉnh thật) | Logic thuần, test offline |
| **Phase 4 — Thương mại** | 7 | 5 | 2 (cổng thanh toán, admin dashboard) | Xem §5 |

### Bằng chứng kiểm thử

```
commhunter/tests/test_pipeline.py   →  116 PASS / 0 FAIL
backend/tests/test_api.py           →  328 PASS / 0 FAIL (14g: SerialJobQueue, 14h: seed user + app_settings che do desktop)
frontend: npx tsc --noEmit          →    0 lỗi
frontend: npx next build            →    0 lỗi TypeScript, 15 route
API surface (openapi.json)          →   68 path / 86 operation
docker compose config --services    →    db, redis, api, worker, beat  (đủ 5)
alembic upgrade head / downgrade    →    11 bảng + 0002 (xoay vòng) + 0003 (Nhắc tới) + 0004 (Track A: post_publishes + daily_post_*) + 0005 (tuỳ chọn AI comment) + 0006 (app_settings che do desktop), lên xuống sạch, `alembic check` không drift
```

---

## 2. Phase 1 — MVP Script

| Task | Trạng thái | Nơi hiện thực |
|---|---|---|
| Config YAML + Data Models | Xong | `commhunter/config_loader.py`, `models.py` |
| Browser Manager (Playwright Stealth) | Xong | `commhunter/browser_manager.py` |
| Scout Worker | Xong | `commhunter/scout_worker.py` |
| Dedup Store (SQLite) | Xong | `commhunter/dedup_store.py` |
| AI Engine (lọc + sinh comment) | Xong | `commhunter/ai_engine.py` |
| Human Emulator | Xong | `commhunter/human_emulator.py` |
| Shooter Worker | Xong | `commhunter/shooter_worker.py` |
| Telegram Bot bán tự động | Xong | `commhunter/telegram_bot.py` |
| CLI Entry Point | Xong | `commhunter/commhunter.py` |
| Integration Test offline | Xong | `commhunter/tests/test_pipeline.py` |
| **Sprint 3 — Kiểm thử Facebook thật** | **Chặn** | Cần tài khoản clone thật, cookie thật, và theo dõi nhiều ngày. Không thể mô phỏng offline. |

**Nợ kỹ thuật đã trả trong đợt này:** `AIEngine.__init__` trước đây chỉ nhận chuỗi `api_key`,
nhưng test lại truyền cả `AppConfig`. SDK `openai` không kiểm kiểu nên lỗi bị giấu tới lúc gọi API
thật. Hợp đồng nay nhận **cả hai** dạng và báo `TypeError` rõ ràng với dạng thứ ba.

---

## 3. Phase 2 — Backend & Dashboard

### Sprint 3 — Nền tảng Backend

| Task | Trạng thái | Nơi hiện thực |
|---|---|---|
| Docker Compose stack | Xong | `backend/docker-compose.yaml` — đúng 5 service, có healthcheck cho db/redis/api |
| Migration PostgreSQL | Xong | `backend/alembic/versions/0001_khoi_tao_11_bang.py` — 11 bảng |
| Auth API (JWT) | Xong | `backend/app/routers/auth.py` + `security.py` — access 15 phút, refresh 7 ngày |
| Campaign CRUD API | Xong | `backend/app/routers/campaigns.py` |
| Cào nhóm đã tham gia (`POST /groups/discover`) | Xong | `scout_worker.scrape_joined_groups` + `services/group_discovery_service.py` + `workers/scout_task.discover_joined_groups`; test: 4b (endpoint) + 4c (gộp, dedup, quota, status paused). **Soi DOM thật 10/09/2026** (`/groups/joins/`, CDP 9222): `EXTRACT_GROUPS_JS` bóc 93 nhóm; sửa để cắt đuôi metadata "Lần hoạt động gần nhất…" khỏi tên nhóm (trước đó tên dài >120 ký tự bị xoá trắng, mất ~20 nhóm). |
| Clone Management API | Xong | `backend/app/routers/clones.py` — cookie mã hóa Fernet |
| Cầu nối trình duyệt backend ↔ Phase 1 (`workers/browser_runtime.py`) | Xong | `build_runtime_config` bơm cấu hình DB vào ScoutWorker/ShooterWorker Phase 1. Đặt `BROWSER_CDP_ENDPOINT` → attach vào Chrome đang mở, clone không cần cookie trong DB (dev/test); rỗng → mỗi clone chạy profile persistent + vân tay riêng (production). Không attach thì bỏ proxy/không ghi cookie giải mã ra đĩa. Test: mục 7b (10 assertion — propagate endpoint, trim, bỏ proxy, guard ghi cookie). |
| Đăng bài Seeding thật (Task 2.14) | Xong | Mã: `commhunter/shooter_worker.publish_post` + `workers/browser_runtime.publish_post_real` + `services/publisher_service.execute_publish` (đã bỏ hẳn `simulated_url`). Test 14b (browser không sẵn sàng → `failed`, không bịa link) + 14c (đăng một phần → `partially_published`, `daily_post_count` theo số nhóm). Migration `0004` đã khớp `post_publishes` + `clone_accounts.daily_post_count/daily_post_limit` với model (xoá nợ `alembic check` drift). **Chạy thật 10/09/2026** (nick phụ, CDP 9222, group "Hội BMW"): `publish_post` mở composer + gõ + bấm Đăng OK — `COMPOSER_TRIGGER/TEXTBOX/SUBMIT_SELECTORS` đã hiệu chỉnh theo DOM thật (nút Đăng có `aria-disabled` tới khi có nội dung → thêm `:not([aria-disabled])`). Group bật kiểm duyệt bài → bài vào hàng chờ, `publish_post` trả `PUBLISHED_NO_URL` **đúng thiết kế** (không bịa link). Bài test đã xoá khỏi hàng chờ. **Group không kiểm duyệt (nick phụ là admin) 10/09/2026** (`1042987808508567`): xác nhận `publish_post` GHI THẬT được — bài lên feed nhóm ngay. Lộ 2 bug ở khâu xác nhận (đã sửa cùng diff): (1) `_post_submitted_ok` đếm mọi `[role="dialog"]` → luôn `FAILED` giả vì FB giữ sẵn dialog thông báo → sửa: chỉ soi ô soạn bài còn mở không. (2) FB đời mới giấu permalink khỏi mọi `href` trong feed (href mốc thời gian chỉ là `?__cft__…#?xxx`, chữ mốc thời gian bị xáo span) → `EXTRACT_LATEST_POST_JS` không bao giờ khớp → thêm `_permalink_by_clicking_timestamp` (đánh dấu thẻ `<a>` mốc thời gian của bài chứa lát text, click, đọc URL đích `/groups/<gid>/posts/<id>/`) + `_clean_permalink` rút URL sạch. Verify E2E một lượt: `publish_post` → `PUBLISHED` + `post_url = /groups/1042987808508567/posts/1043001558507192/`, mở ra đúng bài, xoá sạch. Test hồi quy: `commhunter/tests/test_pipeline.py` mục publish, 114/114 PASS, đã kiểm đột biến. **Rollback / cleanup (11/09/2026):** `ShooterWorker.delete_own_post(page, post_url)` — mở permalink → nút menu `aria-label*="Hành động đối với bài viết này"` (JS click tránh overlay) → mục "Xóa bài viết" / "Chuyển vào thùng rác" → nút xác nhận khớp tuyệt đối (`Xóa`/`Chuyển`, KHÔNG bắt "Xác nhận") → verify mở lại permalink thấy `POST_GONE_MARKERS`; fail an toàn khi không khớp. Test offline `test_pipeline.py` (3 assertion: happy path + không thấy menu + url rỗng), đã kiểm đột biến (`in`→`not in` nút xác nhận → đỏ). `publisher_service.execute_publish`: trình duyệt chết giữa chừng sau khi đã đăng ≥1 nhóm → GIỮ `publish_results` (trước đây xoá trắng, mất permalink đã ghi thật), trạng thái `partially_published`, `error_message` liệt kê link đã đăng để rà soát tay — KHÔNG tự xoá (bài đã lên là nội dung khách muốn giữ; xoá là thao tác ghi có rủi ro riêng). Test `test_api.py` mục 14d (5 assertion), đã kiểm đột biến. **Track A Item 3 — E2E đường backend 11/09/2026** (anh Ber duyệt, burner `1042987808508567`, CDP 9222): dựng `PostPublish` status `SCHEDULED` → `publisher_task._due_publishes` nhặt đúng → `execute_publish` → `browser_runtime.publish_post_real` → `PublishStatus.PUBLISHED`, `publish_results[0].post_url = /groups/1042987808508567/posts/1043164428490905/` (permalink thật), `daily_post_count` +1, `note_ok` giữ nick active → `delete_own_post_real` (mới, cầu nối theo khuôn `publish_post_real`) dọn sạch, verify feed + pending trống. Chạy trọn một lượt không lỗi. Lộ + sửa 2 bug cùng diff: (1) `_post_submitted_ok` báo `submit_not_confirmed` giả khi hộp thoại đóng chậm → POLL tối đa `POST_SUBMIT_CONFIRM_TIMEOUT_MS` (14s) thay vì soi 1 lần; bỏ cụm "đã đăng" trần khỏi `POST_SUCCESS_PHRASES` (dễ dương tính giả). (2) trang permalink FB chèn bài "được đề xuất" cùng nút "Hành động đối với bài viết này..." → `delete_own_post` bấm nhầm bài người khác → `_open_own_post_menu` lọc theo tên tài khoản đang đăng nhập (`_current_account_name` bóc từ payload bootstrap, `CURRENT_ACCOUNT_NAME_RE`), chỉ rơi về nút khớp chung khi không xác định được tên; `_click_menu_text`/`_confirm_delete_dialog` chuyển sang JS click (overlay chắn). Test hồi quy: `test_pipeline.py` 116/116 (+2 `_open_own_post_menu`), đã kiểm đột biến. |
| Mode treo — tự bảo vệ khi chạy không người trực (Track C, Subtask 2.5.8) | Xong | Đường quét (scout) + đăng bài (publisher) nay cũng đi qua `AccountManager` như đường comment: `note_ok` (reset đếm hỏng sau lượt trót lọt, không đụng `daily_comment_count`), `browser_runtime.ScoutCheckpoint` + hàm thuần `wrap_scout_error` (bọc `CheckpointError` Phase 1), `scout_task._scan_one` bắt checkpoint → `transition(CHECKPOINT_DETECTED)` không quét lại / lỗi thường → `record_failure` (đủ 3 lượt tự cooldown), `publisher_service.execute_publish` soi `results` checkpoint/hỏng-toàn-bộ/OK. Thông báo dùng chung `notification_service.build_clone_notifier` (health_check cũng rút về helper này). Test `test_api.py` mục 14d-bis (2) + 14e (6), đã kiểm đột biến 4 điểm. Không thêm trạng thái / cột DB mới. |
| Preflight sức khoẻ nick (Track D, Subtask 2.5.9) | Xong | `browser_runtime.preflight_check_real(clone)` → `BrowserManager.probe_session_reason` (mở facebook.com, phân biệt `ok` / `checkpoint` / `login_expired` / `error`; `check_session` cũ nay uỷ quyền cho hàm này). `services/preflight_service.run_preflight(db, clone, *, cookies, prober)` — `ok` → `note_ok`, `checkpoint` → `transition(CHECKPOINT_DETECTED)`, còn lại → `record_failure` (đủ ngưỡng tự cooldown); không commit, caller commit. Gate qua `settings.preflight_before_run` (mặc định TẮT — thêm 1 lần mở browser/lượt): bật thì `scout_task._scan_one` + `publisher_service.execute_publish` chạy preflight sau khi chọn clone, không đạt → huỷ lượt (`preflight_failed`), nick đã bị state machine dừng. Celery `preflight_task.preflight_clone` / `preflight_user_clones` (kích hoạt theo yêu cầu, không vào Beat). Test `test_api.py` mục 14f (8 assertion — 3 nhánh state machine + gate publish/scout không gọi runtime), đã kiểm đột biến (`reason == "checkpoint"` → `!=` bắt đỏ). **Chạy thật 11/09/2026** (CDP 9222, burner): `preflight_check_real` → `{"ok": True, "reason": "ok"}`. |
| Hộp thư "Nhắc tới" (Track B, Subtask 2.5.7) | Xong | `campaigns.mention_keywords` + bảng `mentions` (migration `0003`) · `services/mention_service.detect_mentions` (khớp từ khoá bỏ dấu, dedup `content_hash`) móc vào `workers/scout_task._scan_one` và `POST /api/campaigns/{id}/ingest` · router `/api/mentions` (list/unread-count/read/archive/delete, cách ly đa khách) · dashboard `/mentions` + badge sidebar + ô `mention_keywords` trong tab Cấu hình. `mention_service.notify_mentions` bắn Telegram summary ở **cả hai** đường ingest (Beat `scout_task._scan_one` + API `POST /api/campaigns/{id}/ingest`) — trước đây chỉ đường Beat bắn. Test: mục 4d (18 assertion — khớp/dedup/phân trang/đổi trạng thái/cách ly đa khách/keyword rỗng thì tắt) + mục 4e (4 assertion — notify_mentions hai đường ingest, guard chat_id/rỗng). `alembic upgrade head` + `downgrade` sạch. **Chạy thật 10/09/2026** (chỉ đọc, CDP 9222): (a) scan nhóm test thật → `detect_mentions` bắt đúng lượt nhắc (khớp không dấu + hạ chữ thường), dedup lần 2 = 0, `GET /api/mentions` + `POST /{id}/read` + `unread-count` đúng. (b) chạy trọn `scout_task._scan_one` qua đường Beat với clone **không có cookie** (nhờ `BROWSER_CDP_ENDPOINT`) → 3 bài ingest, 2 lượt nhắc ghi DB, `result` không lỗi. Chưa kiểm badge dashboard + Telegram summary với backend/frontend chạy sống. |

Tiêu chí nghiệm thu của plan đều đạt: `docker compose config` liệt kê đủ 5 service,
`alembic upgrade head` tạo đủ bảng, `GET /health` trả `{"status":"ok"}`.

### Sprint 4 — Dashboard

| Màn hình theo plan | Trạng thái | Route |
|---|---|---|
| Next.js Setup | Xong | Next 16 + React 19 + Tailwind 4, TypeScript strict |
| Dashboard Overview | Xong | `/dashboard` |
| Campaign Manager | Xong | `/campaigns` |
| Group Manager | Xong | `/campaigns/[id]` → tab Group |
| Script Studio | Xong | `/campaigns/[id]` → tab Kịch bản — soạn thảo spintax có kiểm lỗi tức thì, xem trước, duyệt biến thể (xem §4b) |
| Clone Manager | Xong | `/clones` (nạp cookie, ủ ấm, chuyển trạng thái tay) |
| Post Feed | Xong | `/posts` (duyệt lead + hàng đợi comment) |
| *(bổ sung)* Hộp thư Nhắc tới | Xong | `/mentions` (danh sách lượt nhắc thương hiệu, lọc + đổi trạng thái, badge sidebar) |
| Bump Scheduler | Xong | `/campaigns/[id]` → tab Bump |
| Stats & Reports | Xong | `/stats` |
| *(bổ sung)* Health Monitor | Xong | `/health` |
| *(bổ sung)* Gói cước | Xong | `/billing` |
| *(bổ sung)* Cài đặt | Xong | `/settings` |

### Sprint 5 — Tích hợp & Deploy

| Task | Trạng thái | Ghi chú |
|---|---|---|
| Telegram Webhook | Xong | `backend/app/routers/telegram_webhook.py` — liên kết `/start <mã>`, nút duyệt/bỏ qua, kiểm tra secret token |
| E2E Testing | Xong | `backend/tests/test_api.py` — 16 nhóm, bao gồm cách ly đa khách và luồng ingest → duyệt → hàng đợi |
| **Production Deploy (VPS + SSL)** | **Chặn** | Cần máy chủ, tên miền và chứng chỉ thật. Dockerfile + compose đã sẵn sàng để `up` trên VPS bất kỳ. |

---

## 4. Phase 3 — Anti-Ban Engine

| Task | Trạng thái | Nơi hiện thực |
|---|---|---|
| Account State Machine (7 trạng thái) | Xong | `backend/app/services/account_manager.py` — 13 cặp chuyển hợp lệ; chuyển sai ném `InvalidTransitionError` |
| Warm-up Pipeline 7 ngày | Xong | `backend/app/services/warmup_service.py` + `workers/warmup_task.py` |
| Checkpoint Detection 3 lớp | Xong | `backend/app/services/anti_ban.py` — URL, tiêu đề (Việt + Anh), DOM |
| Shadowban Detection | Xong | `anti_ban.ShadowbanDetector` — đối chiếu comment có thật sự hiện trên trang |
| Proxy Manager | Xong | `backend/app/services/proxy_manager.py` + `/api/health/proxies/*` |
| Adaptive Rate Limiter | Xong | `anti_ban.compute_delay` — tỉ lệ thành công ≥0.95 giãn ×0.8, <0.50 kịch trần; luôn kẹp trong [180, 1800] giây |
| Health Monitor Dashboard | Xong | `/health` + `backend/app/routers/health.py` |

**Tự phục hồi đã hiện thực:** `workers/health_check_task.py` phát hiện clone mất cookie → chuyển
`CHECKPOINT` → tìm clone dự phòng thay thế; clone hết hạn nghỉ tự đánh thức; proxy chết tự xoay
(hết proxy thì giữ IP cũ, thà chậm còn hơn dừng hẳn).

> **Còn lại:** các ngưỡng (3 lỗi → cooldown, 5 lỗi → cảnh báo, trần 20 comment/ngày) đang là
> con số đặt theo kinh nghiệm cộng đồng. Chỉ dữ liệu chạy thật mới hiệu chỉnh được.

---

## 4b. Comment xoay vòng & chống trùng lặp

Bộ lọc spam của Facebook bắt **lặp lời** trước khi bắt tần suất. Vấn đề được tách làm hai,
xử lý ở hai tầng khác nhau — trộn lẫn hai cái này là nguồn gốc của phần lớn lỗi lặp:

| Loại trùng | Xảy ra lúc nào | Nơi xử lý |
|---|---|---|
| Trùng **trong mẫu** (mẫu quá nghèo biến thể) | Lúc người dùng soạn kịch bản | `script_engine.lint_template` + `SpintaxEditor` |
| Trùng **lúc gửi** (câu vừa dùng lại rơi trúng) | Lúc pipeline dựng comment | `script_engine.render_unique` + `pipeline.recent_comment_texts` |

**Xoay vòng kịch bản.** `pipeline.pick_script` chọn kịch bản **ít dùng nhất trước**
(`usage_count ASC, last_used_at ASC NULLS FIRST, is_default DESC`), chỉ xét kịch bản đang bật.
Mỗi lần dùng thì `mark_script_used` tăng đếm — nhờ vậy 3 kịch bản sẽ được chia đều 1/3 lượt
thay vì kịch bản mặc định gánh hết. Migration `0002_xoay_vong_kich_ban_comment.py` thêm
`is_active` / `usage_count` / `last_used_at`, **có `server_default`** để hàng dữ liệu cũ không
vỡ khi nâng cấp.

**Chống lặp lúc gửi.** `render_unique` bốc tối đa 40 biến thể, so với **30 comment gần nhất**
của chiến dịch (kể cả comment mới `QUEUED` — nếu chỉ tính comment đã gửi thì duyệt hai lead
liên tiếp vẫn ra cùng một câu). Độ giống đo bằng **Jaccard trên tập từ**, ngưỡng `0.82`; cố ý
không dùng `difflib` vì đảo trật tự câu vẫn phải bị coi là trùng. Hết lượt thử mà vẫn đụng thì
trả về biến thể **ít giống nhất**, không ném lỗi — thà nói hơi giống còn hơn bỏ trống lead.

**Giao diện.** Thẻ *Sức khỏe nội dung* quy đổi số biến thể thành **"số ngày chạy chưa phải lặp"**
theo trần comment/ngày của chiến dịch — con số này mới là thứ người dùng quyết định được, chứ
"1.024 biến thể" thì không nói lên điều gì. `SpintaxEditor` gọi `/scripts/lint` (debounce 400ms)
và hiển thị **mọi** lỗi cùng lúc thay vì dừng ở lỗi đầu tiên. Ở ô soạn comment lúc duyệt lead,
nút *Lấy câu từ kịch bản* sinh sẵn một biến thể đã né hàng đợi, và cảnh báo hiện ngay nếu câu
đang gõ giống câu vừa gửi.

> **Ranh giới client/server:** `frontend/lib/spintax.ts` chỉ **đếm và xem trước**. Toàn bộ luật
> nghiệm thu nằm ở endpoint `/lint` phía server, để không nuôi hai bộ luật rồi lệch nhau.

---

## 5. Phase 4 — Thương mại hóa

| Task | Trạng thái | Ghi chú |
|---|---|---|
| Billing Service (hạn mức, hết hạn) | Xong | `services/plans.py` là nguồn sự thật duy nhất về quota; `services/quota.py` cưỡng chế ở tầng router |
| 3 gói cước 199k / 399k / 799k | Xong | Có test: khách Starter thêm group thứ 6 bị chặn 403, nâng Pro thì thêm được |
| Vòng đời thanh toán | Xong | `/api/billing/subscribe` sinh mã đối soát → `/api/billing/confirm` kích hoạt, gia hạn **cộng dồn** vào hạn cũ |
| **Cổng thanh toán VNPay/Momo** | **Chặn** | Cần tài khoản merchant + khóa bí mật. Điểm cắm là `create_payment_intent` trong `routers/billing.py`. |
| **Onboarding Wizard 5 bước** | Xong | `frontend/app/(app)/onboarding/page.tsx` — luồng 5 bước chọn gói, tạo campaign, nạp clone, thêm nhóm, kịch bản & telegram |
| **Landing Page / Referral** | Xong | `frontend/app/page.tsx` — Landing page SaaS: Hero, Tính năng, Bảng giá, Quy trình, FAQ (Referral chưa làm) |
| **Admin Dashboard** | Chưa làm | Đã có sẵn `get_admin_user` và cờ `is_admin` để cắm vào. |

---

## 5b. Đóng gói desktop (mới, kế hoạch riêng ngoài 4 phase gốc)

Xem `docs/plans/desktop_packaging.md`. Mục tiêu: mỗi khách chạy toàn bộ hệ thống trên máy riêng (SQLite local, không qua server trung tâm), đóng gói Electron.

| Giai đoạn | Trạng thái | Ghi chú |
|---|---|---|
| 1 — Thay Celery+Redis bằng APScheduler + SerialJobQueue | Xong | `backend/app/workers/{job_queue,scheduler}.py` mới; `RUN_MODE=desktop` bật trong `main.py`, chế độ SaaS cũ không đổi hành vi. Test mục 14g (3 assertion) |
| 2 — Desktop config (seed user, app_settings, cookie key bền) | Xong | `desktop_service.ensure_desktop_user`, `app_settings_service.py`, router `settings.py`, `POST /api/auth/desktop-session`; migration `0006_app_settings.py`. Test mục 14h (11 assertion) |
| 3 — Electron shell tối thiểu | Xong | `desktop/main.js` mới (spawn 2 sidecar bằng `.venv`/`node` hệ thống, chưa bundle); health-poll → mở window → `before-quit` dọn sạch (taskkill tree + dọn theo cổng dự phòng). Kiểm chứng thủ công: `npm start` trong `desktop/`, đóng graceful, xác nhận process/port sạch qua `Get-CimInstance`/`netstat` |
| 4 — Đóng gói thật (bundle `.venv`, NSIS) | Chưa làm | — |
| 5 — Tài liệu first-run cho khách | Chưa làm | — |

---

## 6. Những gì KHÔNG thể hoàn thành ở môi trường này

Nói thẳng để không ai hiểu nhầm mức độ sẵn sàng:

1. **Kiểm thử trên Facebook thật (Phase 1 Sprint 3).** Cần tài khoản clone thật, cookie đăng nhập
   thật và nhiều ngày quan sát. Mọi con số anti-ban hiện tại là giả định chưa được thực tế xác nhận.
2. **Triển khai production (Phase 2 Sprint 5).** Cần VPS, tên miền, chứng chỉ SSL.
3. **Cổng thanh toán thật (Phase 4).** Cần tài khoản merchant VNPay/Momo.
4. **Gọi OpenAI thật.** `AIService` có đủ 3 lần thử lại và **fallback trả chuỗi rỗng** khi lỗi —
   cố tình không bịa comment. Nhưng chất lượng comment do AI viết thì phải có khóa API mới đánh giá được.

Mọi thứ còn lại đều đã có mã nguồn chạy được và test chứng minh.
