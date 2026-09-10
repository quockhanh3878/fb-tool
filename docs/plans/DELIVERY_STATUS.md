# 📊 TÌNH TRẠNG BÀN GIAO — Đối chiếu Plan ↔ Mã nguồn thực tế

> Cập nhật: 08/09/2026. Tài liệu này đối chiếu **từng task trong 4 plan** với mã nguồn
> đã thực sự tồn tại trong repo, và nói rõ **cái gì chưa làm được và vì sao**.
>
> Nguyên tắc: chỉ đánh ✅ khi có mã nguồn chạy được **và** có test chứng minh.
> Việc chỉ có tài liệu mô tả không được tính là hoàn thành.

---

## 1. Bảng điểm tổng

| Phase | Task theo plan | ✅ Đã có mã + test | ⏳ Chặn bởi yếu tố ngoài | Ghi chú |
|---|---|---|---|---|
| **Phase 1 — MVP Script** | 11 | 10 | 1 (Sprint 3: chạy thật) | 104/104 assertion PASS |
| **Phase 2 — Dashboard** | 17 | 16 | 1 (deploy VPS + SSL) | 165/165 assertion PASS |
| **Phase 3 — Anti-Ban** | 6 | 6 | — (ngưỡng cần hiệu chỉnh thật) | Logic thuần, test offline |
| **Phase 4 — Thương mại** | 7 | 3 | 4 (cổng thanh toán, marketing) | Xem §5 |

### Bằng chứng kiểm thử

```
commhunter/tests/test_pipeline.py   →  104 PASS / 0 FAIL
backend/tests/test_api.py           →  165 PASS / 0 FAIL
frontend: npx tsc --noEmit          →    0 lỗi
frontend: npx next build            →    0 lỗi TypeScript, 13 route
API surface (openapi.json)          →   51 path / 65 operation
docker compose config --services    →    db, redis, api, worker, beat  (đủ 5)
alembic upgrade head / downgrade    →    11 bảng + 0002 (xoay vòng), lên xuống đều sạch
```

---

## 2. Phase 1 — MVP Script

| Task | Trạng thái | Nơi hiện thực |
|---|---|---|
| Config YAML + Data Models | ✅ | `commhunter/config_loader.py`, `models.py` |
| Browser Manager (Playwright Stealth) | ✅ | `commhunter/browser_manager.py` |
| Scout Worker | ✅ | `commhunter/scout_worker.py` |
| Dedup Store (SQLite) | ✅ | `commhunter/dedup_store.py` |
| AI Engine (lọc + sinh comment) | ✅ | `commhunter/ai_engine.py` |
| Human Emulator | ✅ | `commhunter/human_emulator.py` |
| Shooter Worker | ✅ | `commhunter/shooter_worker.py` |
| Telegram Bot bán tự động | ✅ | `commhunter/telegram_bot.py` |
| CLI Entry Point | ✅ | `commhunter/commhunter.py` |
| Integration Test offline | ✅ | `commhunter/tests/test_pipeline.py` |
| **Sprint 3 — Kiểm thử Facebook thật** | ⏳ **Chặn** | Cần tài khoản clone thật, cookie thật, và theo dõi nhiều ngày. Không thể mô phỏng offline. |

**Nợ kỹ thuật đã trả trong đợt này:** `AIEngine.__init__` trước đây chỉ nhận chuỗi `api_key`,
nhưng test lại truyền cả `AppConfig`. SDK `openai` không kiểm kiểu nên lỗi bị giấu tới lúc gọi API
thật. Hợp đồng nay nhận **cả hai** dạng và báo `TypeError` rõ ràng với dạng thứ ba.

---

## 3. Phase 2 — Backend & Dashboard

### Sprint 3 — Nền tảng Backend

| Task | Trạng thái | Nơi hiện thực |
|---|---|---|
| Docker Compose stack | ✅ | `backend/docker-compose.yaml` — đúng 5 service, có healthcheck cho db/redis/api |
| Migration PostgreSQL | ✅ | `backend/alembic/versions/0001_khoi_tao_11_bang.py` — 11 bảng |
| Auth API (JWT) | ✅ | `backend/app/routers/auth.py` + `security.py` — access 15 phút, refresh 7 ngày |
| Campaign CRUD API | ✅ | `backend/app/routers/campaigns.py` |
| Clone Management API | ✅ | `backend/app/routers/clones.py` — cookie mã hóa Fernet |

Tiêu chí nghiệm thu của plan đều đạt: `docker compose config` liệt kê đủ 5 service,
`alembic upgrade head` tạo đủ bảng, `GET /health` trả `{"status":"ok"}`.

### Sprint 4 — Dashboard

| Màn hình theo plan | Trạng thái | Route |
|---|---|---|
| Next.js Setup | ✅ | Next 16 + React 19 + Tailwind 4, TypeScript strict |
| Dashboard Overview | ✅ | `/dashboard` |
| Campaign Manager | ✅ | `/campaigns` |
| Group Manager | ✅ | `/campaigns/[id]` → tab Group |
| Script Studio | ✅ | `/campaigns/[id]` → tab Kịch bản — soạn thảo spintax có kiểm lỗi tức thì, xem trước, duyệt biến thể (xem §4b) |
| Clone Manager | ✅ | `/clones` (nạp cookie, ủ ấm, chuyển trạng thái tay) |
| Post Feed | ✅ | `/posts` (duyệt lead + hàng đợi comment) |
| Bump Scheduler | ✅ | `/campaigns/[id]` → tab Bump |
| Stats & Reports | ✅ | `/stats` |
| *(bổ sung)* Health Monitor | ✅ | `/health` |
| *(bổ sung)* Gói cước | ✅ | `/billing` |
| *(bổ sung)* Cài đặt | ✅ | `/settings` |

### Sprint 5 — Tích hợp & Deploy

| Task | Trạng thái | Ghi chú |
|---|---|---|
| Telegram Webhook | ✅ | `backend/app/routers/telegram_webhook.py` — liên kết `/start <mã>`, nút duyệt/bỏ qua, kiểm tra secret token |
| E2E Testing | ✅ | `backend/tests/test_api.py` — 16 nhóm, bao gồm cách ly đa khách và luồng ingest → duyệt → hàng đợi |
| **Production Deploy (VPS + SSL)** | ⏳ **Chặn** | Cần máy chủ, tên miền và chứng chỉ thật. Dockerfile + compose đã sẵn sàng để `up` trên VPS bất kỳ. |

---

## 4. Phase 3 — Anti-Ban Engine

| Task | Trạng thái | Nơi hiện thực |
|---|---|---|
| Account State Machine (7 trạng thái) | ✅ | `backend/app/services/account_manager.py` — 13 cặp chuyển hợp lệ; chuyển sai ném `InvalidTransitionError` |
| Warm-up Pipeline 7 ngày | ✅ | `backend/app/services/warmup_service.py` + `workers/warmup_task.py` |
| Checkpoint Detection 3 lớp | ✅ | `backend/app/services/anti_ban.py` — URL, tiêu đề (Việt + Anh), DOM |
| Shadowban Detection | ✅ | `anti_ban.ShadowbanDetector` — đối chiếu comment có thật sự hiện trên trang |
| Proxy Manager | ✅ | `backend/app/services/proxy_manager.py` + `/api/health/proxies/*` |
| Adaptive Rate Limiter | ✅ | `anti_ban.compute_delay` — tỉ lệ thành công ≥0.95 giãn ×0.8, <0.50 kịch trần; luôn kẹp trong [180, 1800] giây |
| Health Monitor Dashboard | ✅ | `/health` + `backend/app/routers/health.py` |

**Tự phục hồi đã hiện thực:** `workers/health_check_task.py` phát hiện clone mất cookie → chuyển
`CHECKPOINT` → tìm clone dự phòng thay thế; clone hết hạn nghỉ tự đánh thức; proxy chết tự xoay
(hết proxy thì giữ IP cũ, thà chậm còn hơn dừng hẳn).

> ⚠️ **Còn lại:** các ngưỡng (3 lỗi → cooldown, 5 lỗi → cảnh báo, trần 20 comment/ngày) đang là
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
| Billing Service (hạn mức, hết hạn) | ✅ | `services/plans.py` là nguồn sự thật duy nhất về quota; `services/quota.py` cưỡng chế ở tầng router |
| 3 gói cước 199k / 399k / 799k | ✅ | Có test: khách Starter thêm group thứ 6 bị chặn 403, nâng Pro thì thêm được |
| Vòng đời thanh toán | ✅ | `/api/billing/subscribe` sinh mã đối soát → `/api/billing/confirm` kích hoạt, gia hạn **cộng dồn** vào hạn cũ |
| **Cổng thanh toán VNPay/Momo** | ⏳ **Chặn** | Cần tài khoản merchant + khóa bí mật. Điểm cắm là `create_payment_intent` trong `routers/billing.py`. |
| **Onboarding Wizard 5 bước** | ⏳ Chưa làm | Không chặn; là việc UI thuần, xếp sau vì các màn hình cốt lõi có giá trị hơn. |
| **Landing Page / Referral** | ⏳ Chưa làm | Việc marketing, nằm ngoài phạm vi mã sản phẩm. |
| **Admin Dashboard** | ⏳ Chưa làm | Đã có sẵn `get_admin_user` và cờ `is_admin` để cắm vào. |

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
