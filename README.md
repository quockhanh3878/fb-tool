# Facebook Group Lead Hunter & Auto Engagement Platform (CommHunter AI)

Dự án phát triển nền tảng tự động hóa tìm kiếm khách hàng, giám sát hội nhóm Facebook, lọc bài viết tiềm năng và tự động tương tác/ứng tuyển theo kịch bản thông minh bằng AI.

---

## Mục lục Tài liệu dự án

Toàn bộ tài liệu chi tiết đã được biên soạn và phân loại trong thư mục [`docs/`](docs/):

1. **[01. Phân tích Cấu trúc 3 Hệ thống Mã nguồn Hiện có](docs/01_EXISTING_SYSTEMS_ANALYSIS.md)**
   * Đánh giá chi tiết `ai-comment-bot-main` (Selenium + Human-like typing + OpenAI).
   * Đánh giá chi tiết `fbn-main` (Playwright + SQLite State Store + Apprise Notification).
   * Đánh giá chi tiết `openclaw-skills-main/facebook-group-monitor` (Playwright Stealth + DOM Extractor + Feed Strip Stitcher).
   * Bảng so sánh và kế hoạch tái sử dụng linh kiện vào kiến trúc mới.

2. **[02. Đặc tả Ý tưởng & Kiến trúc Nền tảng SaaS (CommHunter AI)](docs/02_PLATFORM_SPECIFICATION_AND_IDEAS.md)**
   * Phân tích bài toán thực tế của khách hàng (thay thế CTV, săn đơn viết comm 24/7).
   * Đặc tả các module tự cấu hình: Quản lý group, Bộ lọc từ khóa & AI, Xưởng kịch bản cmt, Hẹn giờ Bump bài.
   * Kinh nghiệm thực chiến từ cộng đồng MMO: Mô hình Scout-Shooter, chiến thuật né bẫy Link Spam, phòng tránh gậy Admin.
   * Hai chế độ vận hành: Semi-Auto (duyệt qua Telegram) & Full-Auto.
   * Thiết kế Tech Stack, Bảng giá gói cước dịch vụ và Lộ trình phát triển sản phẩm.

3. **[03. MASTER PLAN — Kế hoạch tổng thể phát triển nền tảng](docs/03_MASTER_PLAN.md)**
   * Kiến trúc hệ thống 5 tầng (Client → API → Worker → Data → Infra) với sơ đồ Mermaid.
   * Ma trận tái sử dụng mã nguồn chi tiết: Mapping cụ thể từng file/function từ 3 repo vào module mới.
   * Database Schema PostgreSQL đầy đủ với ER Diagram (9 bảng).
   * Chi tiết 6 module kỹ thuật: Scout Worker, Shooter Worker, AI Engine, Notification Hub, Account Manager, Anti-Ban Engine — mỗi module có flowchart và pseudocode.
   * Luồng hoạt động End-to-End với sequence diagram.
   * Cơ chế chống ban 5 lớp: Rate Limiting, Checkpoint Detection, Shadowban Detection, Profile Landing Page, Admin Blacklist.
   * Thiết kế UI Dashboard (8 màn hình) và Telegram Bot (Inline Keyboard Semi-Auto).
   * Mô hình kinh doanh: 3 gói cước (199k-799k/tháng), phân tích chi phí/lợi nhuận.
   * Lộ trình 4 Phase: MVP Script (2 tuần) → Web Dashboard (4 tuần) → Anti-Ban Engine (4 tuần) → Commercialization.
   * Ma trận rủi ro và KPIs đo lường thành công cho từng phase.

---

## Cấu trúc Thư mục Dự án

```
fb-tool/
├── README.md                                 # Tài liệu tổng quan dự án
├── docs/                                     # Kho tài liệu thiết kế & phân tích
│   ├── 01_EXISTING_SYSTEMS_ANALYSIS.md       # Phân tích kỹ thuật 3 repo có sẵn
│   ├── 02_PLATFORM_SPECIFICATION_AND_IDEAS.md # Ý tưởng nền tảng, Anti-ban & SaaS
│   ├── 03_MASTER_PLAN.md                     # Kế hoạch tổng thể phát triển
│   └── plans/                                # Kế hoạch triển khai chi tiết từng Phase
│       ├── README.md                         # Danh mục & Tổng quan các plans
│       ├── phase1_mvp_detail.md              # Phase 1: MVP Script (Tuần 1-2)
│       ├── phase2_dashboard_detail.md        # Phase 2: Web Dashboard (Tuần 3-6)
│       ├── phase3_antiban_detail.md          # Phase 3: Anti-Ban Engine (Tuần 7-10)
│       ├── phase4_commercial_detail.md       # Phase 4: Thương mại hóa (Tuần 11+)
│       └── DELIVERY_STATUS.md                # Đối chiếu plan ↔ mã nguồn thực tế
│
├── commhunter/                               # MÃ NGUỒN SẢN PHẨM (Phase 1 MVP)
│   ├── commhunter.py                         # Entry point CLI: run / login / status
│   ├── scout_worker.py                       # Quét bài từ group
│   ├── shooter_worker.py                     # Đăng comment
│   ├── ai_engine.py                          # Lọc bài + sinh comment bằng AI
│   ├── telegram_bot.py                       # Thông báo + Inline Keyboard (Semi-Auto)
│   ├── browser_manager.py                    # Chrome thật (channel) + stealth + attach CDP
│   ├── fingerprint.py                        # Vân tay ổn định theo từng nick clone
│   ├── human_emulator.py                     # Mô phỏng gõ phím / rê chuột người thật
│   ├── dedup_store.py                        # SQLite: dedup, trạng thái, thống kê
│   ├── config_loader.py / models.py / constants.py
│   ├── requirements.txt
│   ├── configs/example.yaml                  # Config mẫu (bí mật đọc từ .env)
│   ├── tests/test_pipeline.py                # Smoke test offline (104 assertion)
│   └── data/                                 # Runtime — ĐÃ bị .gitignore chặn
│
├── backend/                                  # API SaaS ĐA KHÁCH HÀNG (Phase 2-4)
│   ├── app/
│   │   ├── main.py                           # FastAPI app + CORS + /health
│   │   ├── config.py / database.py / security.py / dependencies.py
│   │   ├── models/                           # 11 bảng SQLAlchemy 2.0 (async)
│   │   ├── schemas/                          # Pydantic v2 request/response
│   │   ├── routers/                          # auth, campaigns, clones, posts,
│   │   │                                     #   stats, health, billing, telegram
│   │   ├── services/                         # pipeline, AI, anti-ban, warm-up,
│   │   │                                     #   account state machine, proxy, quota
│   │   └── workers/                          # Celery: scout, shooter, bump,
│   │                                         #   warm-up, health-check
│   ├── alembic/                              # Migration (0001 = 11 bảng)
│   ├── tests/test_api.py                     # 132 assertion offline (SQLite)
│   ├── requirements.txt / Dockerfile / docker-compose.yaml
│
├── frontend/                                 # DASHBOARD Next.js 16 + Tailwind 4
│   ├── app/                                  # 12 route: login, register, dashboard,
│   │                                         #   campaigns, posts, clones, health,
│   │                                         #   stats, billing, settings
│   ├── lib/api.ts                            # Client JWT + tự làm mới token
│   ├── components/ui.tsx                     # Bộ thành phần dùng chung
│   └── Dockerfile
│
├── ai-comment-bot-main/                      # Mã nguồn tham khảo: Hành vi gõ phím & rê chuột người thật
├── fbn-main/                                 # Mã nguồn tham khảo: Bộ khung Playwright & quản lý State SQLite
└── openclaw-skills-main/                     # Mã nguồn tham khảo: Kỹ thuật cào bài nhóm Facebook Stealth
```

---

## Chạy thử nhanh

```bash
cd commhunter
pip install -r requirements.txt
playwright install chromium

cp configs/example.yaml configs/khach.yaml     # sửa cho đúng khách hàng
# Đặt OPENAI_API_KEY / TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID vào file .env ở thư mục gốc

python commhunter.py status --config configs/khach.yaml            # kiểm tra trước khi chạy
python commhunter.py login  --config configs/khach.yaml --profile scout
python commhunter.py login  --config configs/khach.yaml --profile shooter
python commhunter.py run    --config configs/khach.yaml

python tests/test_pipeline.py                  # smoke test, không cần mạng
python tests/test_browser.py                   # test vân tay + cấu hình trình duyệt
python tests/test_browser.py --live            # + mở Chrome thật kiểm chứng
```

### Trình duyệt: Chrome thật + vân tay theo nick + chế độ attach

- **`browser.channel: "chrome"`** (mặc định) — chạy Google Chrome đã cài trên
  máy thay vì Chromium bundled. Khó bị Facebook phát hiện hơn hẳn. Tự rơi về
  Chromium nếu máy không có Chrome.
- **`browser.headless: false`** (mặc định) — hiện browser. Nuôi nick bằng
  browser thật + thao tác UI như người an toàn hơn nhiều headless + gọi mã.
- **Vân tay theo nick** — `fingerprint.py` sinh canvas / WebGL / hardwareConcurrency…
  cố định và khớp nhau cho từng `profile_dir`, lưu ở `<profile_dir>/fingerprint.json`.
- **Attach CDP** — đặt `accounts.<role>.cdp_endpoint: "http://localhost:9222"`
  (hoặc `browser.attach_cdp`) để cắm vào một Chrome đang chạy sẵn đã đăng nhập,
  phục vụ test tay. Mở Chrome kèm cờ `--remote-debugging-port=9222`. Khi attach:
  không spoof vân tay, không áp proxy, không tự đóng browser của bạn.

> **Sprint 0 Hardening đã hoàn thành.** 4 lỗi mức nặng (warmup click bừa, verify dương tính giả, rate limit đếm sai, không có circuit-breaker) đã được xử lý triệt để. Bộ test pipeline offline đạt **104/104 PASS**. Hệ thống an toàn và sẵn sàng bước vào Sprint 3 kiểm thử trên Facebook thật.

---

## Chạy nền tảng SaaS (Backend + Dashboard)

### Cách 1 — Docker (đầy đủ 5 service: db, redis, api, worker, beat)

```bash
cp backend/.env.example backend/.env           # sửa JWT_SECRET & COOKIE_ENCRYPTION_KEY
docker compose -f backend/docker-compose.yaml up -d --build
curl http://localhost:8000/health              # {"status":"ok"}
```

Thêm dashboard (service thứ 6, chạy ở cổng 3000):

```bash
docker compose -f backend/docker-compose.yaml --profile dashboard up -d --build
```

### Cách 2 — Chạy tay khi phát triển (SQLite, không cần Docker)

```bash
cd backend
pip install -r requirements.txt
export DATABASE_URL="sqlite+aiosqlite:///./data/commhunter_api.db"
alembic upgrade head
uvicorn app.main:app --reload                  # http://localhost:8000/docs
python tests/test_api.py                       # 132/132 PASS, offline

cd ../frontend
npm install && npm run dev                     # http://localhost:3000
```

### Soạn nội dung không bị lặp

Facebook chặn **lặp lời** trước khi chặn tần suất, nên phần soạn kịch bản được làm nặng tay:

- **Trình soạn spintax** (`/campaigns/[id]` → tab Kịch bản): bôi đen chữ rồi bấm `{ }` để biến
  thành nhóm xoay, `|` để thêm lựa chọn. Vừa gõ vừa thấy số nhóm, số biến thể và bản xem trước.
- **Kiểm lỗi tức thì:** báo một lượt **tất cả** vấn đề — thiếu ngoặc, nhóm chỉ có một lựa chọn,
  hai lựa chọn trùng chữ, biến thể quá ngắn/quá dài, có link, hoặc tổng biến thể quá ít.
- **"Số ngày chạy chưa phải lặp":** quy đổi tổng biến thể theo trần comment/ngày của chiến dịch.
  Dưới 1 ngày là báo đỏ — dấu hiệu kho câu quá mỏng.
- **Xoay vòng kịch bản:** hệ thống luôn chọn kịch bản **ít dùng nhất** trước, rồi trong kịch bản
  đó chọn biến thể **khác 30 comment gần nhất** (đo bằng Jaccard trên tập từ, ngưỡng 0.82 — đảo
  trật tự câu vẫn bị tính là trùng).
- Lúc duyệt lead tay, nút *Lấy câu từ kịch bản* sinh sẵn một biến thể đã né hàng đợi, và cảnh
  báo hiện ngay nếu câu đang gõ giống câu vừa gửi.

Chi tiết thiết kế: [DELIVERY_STATUS §4b](docs/plans/DELIVERY_STATUS.md).

### Kiểm thử

| Bộ test | Phạm vi | Kết quả |
|---|---|---|
| `commhunter/tests/test_pipeline.py` | Phase 1: pipeline CLI, anti-ban, hồi quy nợ kỹ thuật | **104/104 PASS** |
| `backend/tests/test_api.py` | Phase 2-4: 51 path / 65 operation, cách ly đa khách, quota, máy trạng thái, worker, xoay vòng & chống trùng | **243/243 PASS** |
| `commhunter/tests/test_templates.py` | Kho mẫu comment, chống lặp lời | **8/8 PASS** |
| `commhunter/tests/test_browser.py` | Vân tay + cấu hình trình duyệt | **23/23 PASS** |
| `npx next build` (frontend) | 13 route, TypeScript strict | **0 lỗi** |

Cả hai bộ test chạy **hoàn toàn offline** — không cần Facebook, OpenAI, Docker hay mạng.

---

## Các bước tiếp theo (Next Steps)
Xem chi tiết tại [03. Master Plan — Mục 9: Lộ trình phát triển](docs/03_MASTER_PLAN.md#9-lộ-trình-phát-triển-4-phase).

1. **Phase 1 (Tuần 1-2):** MVP + Sprint 0 Hardening hoàn tất (104/104 PASS) → **Còn lại: Sprint 3 — kiểm thử trên Facebook thật.** Việc này bắt buộc phải có tài khoản clone thật, cookie thật và thời gian theo dõi nhiều ngày nên không thể làm offline.
2. **Phase 2 (Tuần 3-6):** Backend FastAPI đa khách (65 operation, 11 bảng, JWT, Celery) + Dashboard Next.js 13 màn hình + Docker Compose 5 service + Alembic migration.
3. **Phase 3 (Tuần 7-10):** Máy trạng thái 7 trạng thái, ủ ấm 7 ngày, phát hiện checkpoint 3 lớp, phát hiện shadowban, giãn nhịp thích ứng, pool proxy, clone dự phòng tự thay → **Còn lại: hiệu chỉnh ngưỡng bằng dữ liệu chạy thật.**
4. **Phase 4 (Tuần 11+):** 3 gói cước + hạn mức cưỡng chế + vòng đời thanh toán → **Còn lại: đấu nối cổng thanh toán thật (VNPay/Momo) — cần tài khoản merchant.**
