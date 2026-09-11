# CommHunter AI — Agent Operating Guide

Hợp đồng vận hành cho mọi coding agent làm việc trong repo này (Claude Code là công cụ chính).

**Lớp nạp tài liệu — biết mình đang ở file nào:**

- **Claude Code** tự nạp `CLAUDE.md` (file này) + `MEMORY.md` trong memory dir. Đây là bản duy nhất, đầy đủ, không phụ thuộc file nào khác.
- `AGENTS.md` ở gốc chỉ là con trỏ trỏ về file này — công cụ khác (Codex, Antigravity, Cursor…) đọc nó rồi đọc tiếp file này. Không nhân bản nội dung sang đó.
- `README.md` = chỉ mục dự án cho người đọc. `docs/` = tài liệu thiết kế. Cả hai KHÔNG phải rule — đọc theo nhu cầu (§12).

---

## 0) Token Fast Path

> Mục này **đè lên** mọi mặc định "đọc cho kỹ" bên dưới khi xung đột. Mục tiêu: ra kết quả sớm, không đốt cửa sổ ngữ cảnh vào việc đọc trước khi có gì để giao.

- **Ngân sách đọc trước lần sửa đầu tiên: ≤5 lần Read có chủ đích.** Gom các Read độc lập vào MỘT message (chạy song song). Grep thu hẹp trước → Read kèm `offset`/`limit`; không Read nguyên file lớn.
- **Không bao giờ đọc lại thứ đã có trong context**: file này, `MEMORY.md`, file vừa sửa, snapshot vừa đọc.
- **Tài liệu `docs/` đọc tối thiểu**: đúng 1 file đúng domain. `docs/03_MASTER_PLAN.md` rất dài — Grep vào đúng mục, đừng đọc cả file.
- **Snapshot**: đọc khi việc nhiều bước / làm tiếp việc dở. Sửa vặt + trả lời suông → bỏ qua (STEP 0 đã cho phép).
- **Báo cáo theo chi phí**: việc vặt / trả lời suông → 1–2 dòng (làm gì + kiểm chứng thế nào). Không bao giờ chép lại code vào báo cáo.

Chỉ việc thật sự lớn (feature nhiều file, audit sâu) mới mở trọn bộ tài liệu + điều phối. Phân vân → chọn nấc rẻ hơn, thiếu thì leo lên sau.

---

## 1) Phạm Vi Và Hợp Đồng Repo

- **Mã nguồn chạy thật** chỉ nằm ở 3 nơi: `commhunter/` (CLI MVP Phase 1, Python) · `backend/` (FastAPI SaaS đa khách, Python) · `frontend/` (Next.js dashboard, TypeScript).
- **`ai-comment-bot-main/`, `fbn-main/`, `openclaw-skills-main/` là kho THAM KHẢO, chỉ đọc.** Không sửa, không import trực tiếp, không đưa vào đường chạy thật. Cần kỹ thuật gì thì **chép có chọn lọc + ghi nguồn** vào module của mình, và bổ sung `NOTICE` nếu là mã có license.
- **`chrome-debug-profile/`** là profile Chrome dùng để test tay qua CDP — dữ liệu runtime, không phải mã nguồn. Không đọc, không in nội dung, không commit (§7).
- **Repo có git** (khởi tạo 10/09/2026, nhánh `main`, chưa có remote). Quy tắc dùng git ở §14 — đọc trước khi commit lần đầu.
- **Python chạy trong venv riêng của repo: `.venv/` ở gốc** (Python 3.11, dựng 10/09/2026). **Mọi lệnh Python đều phải đi qua nó** — `.venv\Scripts\python.exe <script>` — kể cả `pip`, `alembic`, `uvicorn`, `playwright`. Gọi `python` trần là chạy nhầm Python global của máy (dùng chung với dự án khác, đã từng lệch phiên bản làm chết toàn bộ test). Không bao giờ `pip install` vào Python global cho repo này.
- Venv cài **cả hai** `requirements.txt` (backend pin cứng, commhunter dùng khoảng) — thêm thư viện mới phải kiểm không phá pin của bên kia, và ghi vào đúng file `requirements.txt` của bên dùng nó.
- Chạy trên **Windows / PowerShell**. Frontend dùng **`npm`** (có `package-lock.json`) — không đổi sang pnpm/yarn.
- Backend và `commhunter/` là hai runtime **riêng biệt** dù dùng chung venv. Không tạo import chéo `backend/app` ↔ `commhunter/`; logic dùng chung thì chép sang kèm test riêng, hoặc nêu đề xuất tách package trước khi làm.

---

## 2) Vòng Làm Việc Bắt Buộc

Không bỏ bước, không đảo thứ tự.

1. **Phân tích** — tách yêu cầu thành: **vai** (commhunter / backend / frontend / test / docs, hoặc hỗn hợp) · **hành động** (đổi đúng cái gì) · **bối cảnh** (file/module/stack/ràng buộc đã ngụ ý) · **ràng buộc** (an toàn tài khoản, anti-ban, hiệu năng, tương thích ngược, test) · **đầu ra** (code, test, plan, tài liệu). Thiếu thông tin nhưng rủi ro thấp → tự giả định hợp lý rồi làm. Rủi ro cao hoặc không thể hoàn tác (đụng tài khoản Facebook thật, xóa dữ liệu, đổi hợp đồng API) → hỏi tối đa **1–2 câu** trước.
   - **Đọc chẩn đoán — được phép TRƯỚC khi đọc tài liệu domain, ngân sách ≤3 Read.** Chưa gọi được tên vấn đề thì Grep thu hẹp → Read một đoạn **chỉ để định vị**. Biết được domain/file là dừng; đọc để bắt chước convention là việc của bước 5.
   - **Triệu chứng ≠ căn nguyên.** "Comment không đăng được" có thể là selector đổi, rate limit chặn, checkpoint, hay state machine khóa nick. Trước khi sửa, Grep hết caller của hàm đang nghi — một guard trong hàm dùng chung nhỏ hơn nhiều so với guard rải ở từng caller, và vá đúng một đường đi sẽ để lại mọi caller anh em vẫn hỏng.
2. **Tự lập brief** — vai/phạm vi · 1–5 việc con · pattern/file sẽ theo hoặc mở rộng · ràng buộc chính (auth, error handling, kiểu dữ liệu, style, không refactor lớn) · sản phẩm đầu ra. Không cần dump brief cho anh Ber, nhưng câu trả lời phải đi đúng hình dạng đó.
3. **Tiêu chí nghiệm thu — 2–5 tiêu chí kiểm chứng được, viết TRƯỚC khi gõ code**, mỗi tiêu chí kèm đúng câu lệnh để kiểm.
   - ĐƯỢC: `Cho một kịch bản spintax 3 nhóm, Khi sinh biến thể, Thì biến thể khác 30 comment gần nhất (Jaccard < 0.82)` → `.venv\Scripts\python.exe commhunter/tests/test_templates.py` PASS
   - ĐƯỢC: `.venv\Scripts\python.exe backend/tests/test_api.py` = 243/243 PASS · `npx tsc --noEmit` = 0 lỗi
   - CẤM: "chạy đúng rồi", "UI đẹp hơn", "đã fix bug" — không kiểm chứng được.
     Đây chính là thứ bước 6 đối chiếu. Không có tiêu chí = không có cơ sở nói DONE, mọi lời "xong rồi" đều là đoán.
4. **Khảo sát** mã/tài liệu hiện có trước khi sửa; tái dùng helper/hợp đồng đã có (§4); ưu tiên diff nhỏ nhất.
5. **Hiện thực** thay đổi tối thiểu, bám convention sẵn có. Kiểu tường minh thay vì `Any`/`any`. Không lộ secret, không `eval` chuỗi, không nối chuỗi SQL. Tôn trọng pattern error handling / logging / anti-ban đang có. Không refactor kiến trúc nếu không được yêu cầu rõ.
6. **Kiểm chứng** — chạy đúng câu lệnh đã ghi ở bước 3, ghi kết quả THẬT (pass/fail). Tiêu chí không chạy được thì báo "chưa kiểm chứng" — không âm thầm bỏ, không viết lại tiêu chí cho khớp kết quả. Sau đó soát cấu trúc: import/kiểu nhất quán, luồng dữ liệu và xử lý lỗi hợp lý, các ca biên đã chặn (§6).
7. **Báo cáo** đã đổi gì, bằng chứng kiểm chứng, giả định/rủi ro (§10).
8. **Cập nhật snapshot** với kết quả sau tác vụ (§9.2).

Cách tra mã mặc định: **Grep/Glob** (repo vừa phải, không có index riêng). Đã biết chính xác chuỗi cần tìm → Grep. Chỉ biết mơ hồ → Grep theo tên domain (`scout`, `shooter`, `quota`, `warmup`, `spintax`) rồi thu hẹp dần.

---

## 3) Tài Liệu Domain Đọc Theo Nhu Cầu

Repo chưa có `.claude/skills/`. Thay vào đó, bảng kích hoạt dưới đây là nguồn duy nhất quyết định đọc gì:

| Việc đang làm | Đọc trước (1 file, Grep vào đúng mục) |
|---|---|
| Sửa pipeline scout/shooter/AI của CLI | `docs/plans/phase1_mvp_detail.md` |
| Thêm/sửa API, model, router, worker Celery | `docs/plans/phase2_dashboard_detail.md` |
| Rate limit, checkpoint, shadowban, warm-up, proxy, state machine | `docs/plans/phase3_antiban_detail.md` |
| Gói cước, hạn mức, thanh toán | `docs/plans/phase4_commercial_detail.md` |
| Kiến trúc tổng thể, schema DB, luồng end-to-end | `docs/03_MASTER_PLAN.md` (Grep, đừng đọc cả file) |
| Mượn kỹ thuật từ 3 repo tham khảo | `docs/01_EXISTING_SYSTEMS_ANALYSIS.md` |
| Đối chiếu "cái gì đã xong thật" | `docs/plans/DELIVERY_STATUS.md` |

Ngoại lệ được bỏ qua hoàn toàn: sửa hiển nhiên 1–3 dòng · anh Ber đã chỉ đúng file + dòng · chỉ trả lời câu hỏi.

---

## 4) Khảo Sát, Kiến Trúc Và Truy Vết

**Hướng kiến trúc (giữ nguyên cây thư mục, KHÔNG đại phẫu):**

- `commhunter/` là **module phẳng theo vai trò** — mỗi file một trách nhiệm (`scout_worker`, `shooter_worker`, `ai_engine`, `browser_manager`, `human_emulator`, `dedup_store`…). Thêm vai trò mới thì thêm 1 file cùng cấp, không đẻ thư mục con.
- `backend/app/` là **phân tầng chuẩn**: `routers/` mỏng (validate + gọi service) · `services/` chứa toàn bộ nghiệp vụ · `models/` SQLAlchemy 2.0 async · `schemas/` Pydantic v2 · `workers/` Celery. **Không đặt logic nghiệp vụ trong router**, không truy vấn DB thẳng từ router.
- Service gọi nhau chỉ qua hàm public đã export; không import vòng. Tác dụng phụ liên domain (thông báo, Telegram) đi qua `notification_service`, không gọi thẳng SDK từ service khác.
- `frontend/` **theo route**: màn hình nằm trong `app/<route>/`, gọi API qua `lib/api.ts` (đã tự làm mới JWT — không tự viết fetch kèm token), dùng lại `components/ui.tsx` trước khi tạo component mới.
- Chỉ dời file cũ sang chỗ mới khi đang sửa chính file đó và diff vẫn nhỏ.

**Cổng truy vết (BẮT BUỘC):**

1. Trước khi tạo module / route / worker mới: xác định nó thuộc task nào trong `docs/plans/phaseN_*.md`. Không có task tương ứng → viết vào plan một mục ngắn trước, rồi mới code.
2. File mới mang comment dòng đầu trỏ về plan: `# plan: docs/plans/phase2_dashboard_detail.md` (Python) hoặc `// plan: ...` (TS). Migration Alembic: `# plan: ...` ngay dưới docstring.
3. **Sau khi hiện thực**: cập nhật `docs/plans/DELIVERY_STATUS.md` trong **cùng một diff** — bảng trạng thái, số assertion test, và mục "còn chặn bởi gì".
4. **Quy tắc vàng của `DELIVERY_STATUS.md`: chỉ ghi trạng thái `Xong` khi có mã chạy được VÀ có test chứng minh.** Có tài liệu mô tả không tính là xong. Không được sửa trạng thái thành `Xong` để bảng đẹp hơn. Ba mức trạng thái dùng trong bảng: `Xong` · `Chờ` (chặn bởi yếu tố ngoài) · `Chưa làm`.
5. Đổi hành vi mà `README.md` mô tả (lệnh CLI, cổng, biến môi trường, số test) → sửa `README.md` cùng diff. README lệch thực tế bị coi là bug.

---

## 5) Hợp Đồng Định Tuyến Công Cụ

- **Công cụ IDE trước tiên** cho tìm/đọc/sửa: Read/Grep/Glob/Edit. File đã tồn tại thì Edit, không Write đè.
- **Sửa file có ngữ cảnh — cấm sửa hàng loạt**: không dùng script shell, regex replace hàng loạt hay codemod để sửa mã nguồn. Sửa từng file với đủ ngữ cảnh để không phá cú pháp.
- **Shell chỉ dùng cho build/test/chạy tiến trình.**
- **Mã hóa file: luôn UTF-8.** Đây là repo tiếng Việt trên Windows — `echo "..." > file` trong PowerShell ghi UTF-16LE và làm hỏng dấu tiếng Việt. Luôn dùng Write/Edit của IDE. Bất đắc dĩ mới ghi qua shell và phải ép rõ (`Out-File -Encoding UTF8`). Script Python sinh file `.sql`/`.md` phải `open(path, 'w', encoding='utf-8')`, **không** `print(...) > file.sql` — stdout Windows có thể đi qua CP437 và âm thầm phá byte UTF-8 (`ớ`→`ß╗¢`) trong khi file vẫn chạy được.
- **PowerShell 5.1**: không có `&&`, `||`, toán tử ternary. Nối lệnh bằng `;` hoặc `if ($?) { ... }`. Bash tool có sẵn cho cú pháp POSIX — mỗi tool một cú pháp, đừng trộn.
- **Playwright MCP** dùng khi cần xem/thao tác trình duyệt. Với Facebook thật thì theo §8.

Ràng buộc vận hành: đọc schema tool trước khi gọi MCP (không đoán tham số) · nghi ngờ thì chạy read-only trước · chỉ song song hóa các thao tác đọc độc lập · thao tác có trạng thái/phụ thuộc nhau phải tuần tự.

---

## 6) Chính Sách Kiểm Thử Và Nghiệm Thu

Bộ test hiện có (chạy **hoàn toàn offline**, không cần Facebook / OpenAI / Docker / mạng):

```bash
.venv\Scripts\python.exe commhunter/tests/test_pipeline.py    # 116 assertion — pipeline CLI, anti-ban, hồi quy nợ kỹ thuật
.venv\Scripts\python.exe commhunter/tests/test_templates.py   # 8 assertion — kho mẫu comment, chống lặp lời
.venv\Scripts\python.exe commhunter/tests/test_browser.py     # 23 assertion — vân tay + cấu hình trình duyệt (thêm --live để mở Chrome thật)
.venv\Scripts\python.exe backend/tests/test_api.py            # 317 assertion — path/operation, cách ly đa khách, quota, state machine, đăng bài, mode treo, preflight, SerialJobQueue desktop
cd frontend; npx tsc --noEmit                                 # TypeScript strict, 0 lỗi
cd frontend; npx next build                                   # 13 route, 0 lỗi
```

**Test chết ngay ở bước `import` (pydantic, openai, playwright…) gần như luôn là chạy nhầm Python global, không phải lỗi code.** Kiểm bằng `.venv\Scripts\python.exe -c "import sys; print(sys.executable)"` — phải in ra đường dẫn trong `.venv`. Đừng đi sửa mã nguồn trước khi loại trừ khả năng này.

- **Không chạy full suite trừ khi được yêu cầu.** Bắt đầu từ bộ test nhỏ nhất phủ được hành vi vừa đổi; leo thang: test đơn vị đúng module → bộ test của tầng đó → build frontend → E2E/chạy thật (phải xin phép).
- Ngân sách: mỗi lệnh ≤10 phút, tổng tự chạy ≤15 phút/tác vụ.
- **Viết test (tạo → chạy → soát):**
  1. Dữ liệu test phải đúng hình dạng thật — lấy fixture từ nguồn sự thật (Pydantic schema / SQLAlchemy model / enum), không bịa. Chép enum/status đúng từng ký tự (gạch ngang hay gạch dưới, hoa hay thường). Dữ liệu sai hình dạng = xanh giả, không bảo vệ gì cả.
  2. **Mỗi lần sửa bug phải kèm test hồi quy** dùng đúng giá trị đã gây ra bug. Gỡ phần fix ra mà test vẫn xanh thì test đó vô dụng.
  3. **Chạy test thật trước khi báo cáo.** `tsc`/lint xanh KHÔNG thay thế được test. Báo cáo phải nêu số assertion + pass/fail.
- **Kiểm đột biến bằng tay (bắt buộc với logic tiền/hạn mức, xác thực/phân quyền, state machine tài khoản, rate limit):** test đã xanh thì sửa ĐÚNG MỘT chỗ trong logic vừa đổi (`>`↔`>=`, `&&`↔`||`, xóa một guard, đổi hằng số), chạy lại chính test đó — nó **phải đỏ** — rồi hoàn tác. Vẫn xanh = test vô giá trị, viết lại.
- **Mùi code đặc trưng của agent, sửa ngay trong cùng diff**: chép logic thay vì dùng lại helper có sẵn · hàm >50 dòng hoặc lồng ≥4 tầng · `except Exception: pass` nuốt lỗi · `Any`/`any` ngầm · timeout/selector hardcode rải rác thay vì đặt trong `constants.py`.
- **Tối thiểu trước khi báo cáo xong**: bộ test nhỏ nhất liên quan đã chạy + bằng chứng thật + bước nhỏ tiếp theo nếu chưa kiểm chứng đủ.
- Server dev: dùng lại server đang chạy khỏe ở `8000` (API) / `3000` (dashboard), không bật trùng. Lỡ bật thừa thì tắt cái mới, giữ cái đang sống. Xong việc thì đóng terminal thừa.

---

## 7) An Toàn Môi Trường, Bí Mật Và Dữ Liệu

**Bí mật — mức nghiêm ngặt nhất trong repo này:**

- Secret đọc từ `.env` ở gốc (`OPENAI_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`) và `backend/.env` (`JWT_SECRET`, `COOKIE_ENCRYPTION_KEY`). Chỉ `backend/.env.example` được lên repo.
- `commhunter/configs/*.yaml` chứa key thật + danh sách group thật của khách — **đã bị `.gitignore` chặn, chỉ `example.yaml` được commit.** Không bao giờ in nội dung file cấu hình khách ra báo cáo.
- **`commhunter/data/` và `chrome-debug-profile/` chứa SESSION COOKIE FACEBOOK.** Không đọc, không in, không copy, không commit, không đưa vào bất kỳ log/báo cáo nào. Lộ = mất tài khoản của khách. Không bao giờ được gỡ các dòng chặn này khỏi `.gitignore`.
- Cookie tài khoản trong DB được mã hóa bằng `services/crypto.py` — luôn đi qua lớp đó, không lưu cookie thô, không log giá trị sau khi giải mã.

**Dữ liệu:**

- Dev/test dùng SQLite (`DATABASE_URL="sqlite+aiosqlite:///./data/commhunter_api.db"`); Postgres chỉ cho Docker/production.
- Không bao giờ chạy test/debug trên DB của khách đang vận hành. Thao tác ghi trên DB thật cần anh Ber nói rõ trong chính cuộc hội thoại này; ghi hẹp phạm vi, kiểm ngay sau đó, báo cáo chính xác tác động.
- Migration đi theo thứ tự: `backend/alembic/versions/` (nguồn sự thật) → DB dev → DB thật. Migration mới phải `alembic upgrade head` **và** `downgrade` sạch trước khi coi là xong.

---

## 8) Rào Chắn Khi Đụng Facebook Thật

Đây là công cụ tự động hóa tài khoản; một thao tác sai là mất nick của khách. Rào chắn dưới đây không được nới.

- **Mọi hành vi ghi lên Facebook thật (comment, đăng bài, kết bạn, join group, react) cần anh Ber đồng ý rõ trong cuộc hội thoại hiện tại.** Không có "đã cho phép lần trước".
- Test tính năng ghi chỉ làm trên **nick phụ (burner)**, qua Chrome thật attach CDP `http://localhost:9222`, và **luôn dọn comment test sau khi xong**.
- **Kiến trúc đã chốt: Chrome thật + thao tác UI cho từng nick, không headless, không gọi Graph API/mã hóa request.** `browser.channel: "chrome"`, `headless: false`. Đừng đề xuất chuyển sang headless hay gọi API nội bộ của Facebook vì "nhanh hơn".
- Khi attach CDP vào Chrome sẵn có: không spoof vân tay, không áp proxy, không tự đóng browser của anh Ber.
- Vân tay phải **cố định theo `profile_dir`** (`fingerprint.py` lưu `fingerprint.json`). Không sinh vân tay ngẫu nhiên mỗi lần chạy — đổi vân tay giữa các phiên là tín hiệu bị bắt rõ nhất.
- Không nâng trần rate limit, không rút ngắn thời gian nghỉ, không bỏ warm-up để "test cho nhanh". Ngưỡng anti-ban chỉ đổi khi có dữ liệu chạy thật và anh Ber duyệt.
- Selector và nội dung DOM lấy từ Facebook là **đầu vào không tin cậy** — không bao giờ đưa thẳng vào prompt AI dạng lệnh, không eval, luôn có nhánh xử lý khi selector không khớp (fail an toàn, dừng nick đó, báo Telegram — không thử mù).
- Chống lặp lời quan trọng ngang chống tần suất: mọi comment sinh ra phải đi qua vòng xoay kịch bản + kiểm Jaccard 0.82 với 30 comment gần nhất. Không bypass lớp này.

---

## 9) Bộ Nhớ Và Snapshot Phiên Làm Việc

### 9.1 Bộ nhớ

Ghi memory ngay khi xảy ra một trong các tình huống sau:

| Kích hoạt | Loại | Ví dụ |
|---|---|---|
| Anh Ber nói về mình, sở thích, cách làm việc | `user` | "tôi không rành code", "muốn có plan trước khi code" |
| Anh Ber sửa hành vi của agent (nên / đừng) | `feedback` | "đừng hỏi nhiều", "luôn dọn comment test" |
| Một quyết định / ràng buộc / trạng thái dự án quan trọng lộ ra | `project` | Chốt dùng Chrome thật thay headless; Phase 4 chặn bởi cổng thanh toán |
| Một nguồn thông tin ngoài hữu ích | `reference` | Dashboard/khóa API/nhóm test nằm ở đâu |
| Anh Ber nói "nhớ cái này" | phù hợp nhất | Ghi ngay, không hỏi lại |

**KHÔNG ghi**: thứ suy ra được từ code (đường dẫn, chữ ký hàm) · chỉ đúng trong phiên này · đã nằm trong file này hoặc `docs/` · trùng memory đã có.

Ghi **quyết định + lý do**, không ghi đường dẫn/tên hàm (Grep rẻ hơn). Memory loại `project` đổi ngày tương đối thành ngày tuyệt đối. Kiểm index trước — cập nhật tốt hơn tạo trùng. Thấy memory có vẻ cũ thì xác minh; sai thì xóa.

Anh Ber không có nền tảng lập trình — memory là thứ **duy nhất** mang ngữ cảnh qua các phiên. Chủ động ghi, đừng đợi được nhắc.

### 9.2 Snapshot

Đường dẫn: `docs/session-snapshots/YYYY-MM-DD.md` (chưa có thì tạo mới theo khung: Việc đang làm · Quyết định + lý do · File/hợp đồng đã đụng · Trạng thái kiểm chứng · Bước nhỏ tiếp theo).

**Đọc (trước khi hiện thực)**: snapshot của hôm nay → rút ra quyết định, vật cản, file chính, bước tiếp theo.

**Ghi (sau khi hiện thực)**: ngắn, xoay quanh quyết định, không kể lể.

**Snapshot là nhật ký làm việc, KHÔNG phải báo cáo hoàn thành.** Agent hay báo xong sai; thứ có giá trị là *vì sao quyết định như vậy, đang vướng gì, bước nhỏ tiếp theo là gì*.

- **Khi đọc**: đừng tin trạng thái ghi trong đó (kể cả "Xong") — đối chiếu bằng `git log` / `git status` / chạy test nếu điều đó quan trọng.
- **Khi ghi**: bỏ trạng thái hoàn thành trừ khi việc thật sự kết thúc. Phân vân thì để mở ("Đang làm" / "Chặn bởi X"). Mọi snapshot phải có "bước nhỏ tiếp theo" — thiếu là vô dụng.
- **Snapshot cũ thì thực tế thắng**: code/test nói chưa xong thì snapshot sai — sửa snapshot cho khớp thực tế rồi ghi quyết định mới. Không làm vòng qua một snapshot lỗi thời như thể nó là chân lý.

---

## 10) Giao Tiếp, Quyền Tự Quyết Và Báo Cáo

- Ngắn gọn, thẳng, dựa trên bằng chứng.
- **Xưng hô**: luôn gọi user là **anh Ber**. Không dùng "bạn" hay "user". Giọng ngắn gọn, chuyên nghiệp.
- **Emoji / Icon — CẤM TUYỆT ĐỐI.** Không dùng emoji ở bất kỳ đâu: câu trả lời cho anh Ber, code, comment, docstring, log, bản in ra terminal, tên biến, tài liệu markdown, commit message, tên nhánh. Repo đã được quét sạch ngày 10/09/2026; đừng đưa trở lại.
  - **Ngoại lệ duy nhất: giao diện người dùng thật** — thẻ thông báo Telegram (`commhunter/telegram_bot.py`, `backend/app/services/notification_service.py`, `backend/app/routers/telegram_webhook.py`) và dashboard Next.js (`frontend/`). Đó là thiết kế giao diện sản phẩm, giữ nguyên. Khối mẫu trong `docs/` mô tả chính thẻ Telegram cũng giữ, để tài liệu không lệch code.
  - **Cần đánh dấu trạng thái thì dùng chữ, không dùng glyph**: bảng tài liệu ghi `Xong` / `Chờ` / `Chưa làm`; bản in terminal ghi `[OK]` / `[LỖI]` / `[CẢNH BÁO]` / `[BỎ QUA]`; mức độ nghiêm trọng ghi `nặng` / `vừa` / `nhẹ`. Xoá glyph mà không thay bằng chữ là **làm mất thông tin** — cấm.
  - Lý do không chỉ là thẩm mỹ: console Windows chạy codepage cp1252 **ném `UnicodeEncodeError`** khi in emoji, nên emoji trong log/CLI là bug chờ nổ.
- **Yêu cầu việc gì thì làm đúng việc đó.** Nhiệm vụ chỉ là khảo sát/đánh giá/báo cáo thì dừng ở tài liệu và kết quả, không tự ý sửa mã hay đề xuất kế hoạch sửa.
- **Không bao giờ đoán.** Tìm dữ liệu thật (code, memory, tài liệu, log) thay vì suy diễn. Không có dữ liệu thì nói thẳng là không có.
- Tự quyết các lựa chọn nhỏ (style, cách đặt tên, chọn hiển nhiên theo ngữ cảnh). Tiện tay sửa bất nhất nhỏ trong chính module đang đụng. Thêm/chỉnh test tối thiểu khi hợp lý.
- Chỉ hỏi anh Ber khi quyết định có hệ quả dài hạn hoặc rủi ro lớn (ghi lên Facebook thật, xóa dữ liệu, deploy, đổi kiến trúc lớn), hoặc yêu cầu thật sự mâu thuẫn.

Báo cáo cuối luôn gồm:

1. **Đã làm gì** — thay đổi ở mức khái quát + hành vi mới.
2. **Kiểm chứng thế nào** — tiêu chí ↔ kết quả thật (PASS/FAIL/chưa chạy) kèm câu lệnh đã dùng.
3. **Giả định & rủi ro** — giả định chính, giới hạn, việc cần làm tiếp.

Định dạng: tiêu đề ngắn (Tóm tắt / Kiểm chứng / Tiếp theo), khoảng 3–8 gạch đầu dòng. Việc vặt (≤3 dòng) hoặc chỉ trả lời → 1–2 dòng. Không chép lại nguyên code.

---

## 11) Trình Tự Khởi Động Mỗi Tác Vụ (STEP 0–6)

Đây là nguồn duy nhất quy định thứ tự đọc. Mục nào mâu thuẫn thì theo chuỗi này.

| STEP | Làm gì | Ngân sách đọc |
|---|---|---|
| 0 Phân loại | trả lời suông / sửa vặt / hiện thực | miễn phí, trong đầu |
| 1 L0 | contract tự nạp + quét memory | 0 read |
| 2 L1 (+2b) | snapshot hôm nay (+ đọc chẩn đoán ≤3 read nếu chưa biết vấn đề ở đâu) | 1–3 read |
| 3 L2 | bảng §3 → đúng 1 file `docs/` cho domain | ≤1 read |
| 4 L3 | rule nền §0–10 tự áp dụng · viết tiêu chí nghiệm thu TRƯỚC khi code | 0 read |
| 5 L4 | Grep thu hẹp → Read có chủ đích → Edit diff nhỏ nhất | ≤5 read |
| 6 Kết | chạy tiêu chí → báo cáo → ghi lại snapshot | — |

- **STEP 0 — Phân loại (cổng đầu tiên, miễn phí)**: *trả lời suông* → bỏ snapshot + tài liệu, trả lời thẳng · *sửa vặt* (≤3 dòng, hiển nhiên, đã có file+dòng) → sửa + kiểm chứng · *hiện thực / sửa bug / feature* → chạy trọn trình tự.
- **STEP 1 — L0 (đã nạp sẵn)**: file này + `MEMORY.md`. Quét memory tìm ngữ cảnh liên quan, đánh dấu thứ có vẻ lỗi thời. Không đọc lại file đã tự nạp.
- **STEP 2 — L1 snapshot**: `docs/session-snapshots/YYYY-MM-DD.md`. Coi là lời khuyên, phải đối chiếu thực tế.
- **STEP 2b — Đọc chẩn đoán (≤3 read)**: chỉ khi STEP 0–2 vẫn chưa biết vấn đề nằm ở đâu. Grep thu hẹp → Read một đoạn. Xác định được domain/file là dừng.
- **STEP 3 — L2 tài liệu domain**: theo bảng §3, đúng 1 file.
- **STEP 4 — L3 rule + tiêu chí nghiệm thu** (§2 bước 3), viết trước khi chạm code.
- **STEP 5 — L4 code**: Grep thu hẹp → Read song song → Edit diff nhỏ nhất.
- **STEP 6 — Kiểm chứng → báo cáo → ghi snapshot** (§6, §10, §9.2).

**Hai kiểu đọc code, không bao giờ trộn**: STEP 2b đọc để biết *vấn đề nằm đâu* (≤3 read, trước tài liệu domain); STEP 5 đọc để *viết code khớp pattern* (sau tài liệu domain).

**Các tầng chi phí**: L0 contract tự nạp → L1 snapshot → L2 tài liệu domain → L3 rule → L4 code repo → L5 tài liệu ngoài (Context7/web, chỉ khi cần SDK mới). Không bao giờ nhảy ngược lên tầng cao hơn để tiết kiệm.

---

## 12) Tài Liệu Chuẩn

- **Tự nạp**: `CLAUDE.md` (file này) · `MEMORY.md` (index memory).
- **Chỉ mục dự án**: `README.md` — lệnh chạy, cấu trúc thư mục, kết quả test hiện tại.
- **Thiết kế**: `docs/01_EXISTING_SYSTEMS_ANALYSIS.md` (3 repo tham khảo) · `docs/02_PLATFORM_SPECIFICATION_AND_IDEAS.md` (ý tưởng, anti-ban, SaaS) · `docs/03_MASTER_PLAN.md` (kiến trúc 5 tầng, schema, luồng E2E).
- **Kế hoạch & tiến độ**: `docs/plans/phase{1..4}_*.md` · `docs/plans/DELIVERY_STATUS.md` (đối chiếu plan ↔ mã thật).
- **Pháp lý**: `NOTICE` — mọi đoạn mã mượn từ repo tham khảo phải được ghi nhận ở đây.

---

## 13) Quy Tắc Viết Tài Liệu

Khi tạo hoặc sửa file markdown:

1. **Đặt đúng chỗ**: kế hoạch → `docs/plans/` · thiết kế/phân tích → `docs/` · tổng quan cho người mới → `README.md`. Không tạo file tài liệu mới ở gốc repo.
2. Tài liệu có trạng thái (plan, delivery status) ghi rõ **ngày cập nhật** ở đầu file, dạng tuyệt đối (`08/09/2026`).
3. **Không để tài liệu lệch code**: hành vi đổi thì sửa tài liệu chuẩn tương ứng trong cùng tác vụ (§4 mục 3 và 5).
4. Tiếng Việt là ngôn ngữ mặc định của tài liệu trong repo này; thuật ngữ kỹ thuật giữ nguyên tiếng Anh. Luôn ghi UTF-8 (§5).
5. Không tạo tài liệu tổng kết/báo cáo mới nếu anh Ber không yêu cầu — cập nhật file đã có thay vì đẻ file mới.

---

## 14) Git

Repo khởi tạo ngày 10/09/2026, nhánh `main`, **chưa có remote** — mọi thứ nằm trên máy anh Ber. Git ở đây là **mốc phục hồi**, không phải quy trình cộng tác.

**Trước khi commit — bắt buộc kiểm bí mật.** Repo này chứa cookie Facebook và API key của khách; một lần commit nhầm là lộ tài khoản, và git giữ lại mãi kể cả sau khi xoá file.

```bash
git status --short                 # nhìn bằng mắt cái gì sắp vào
git diff --cached --name-only      # danh sách file thật sự sẽ commit
git check-ignore -v <đường-dẫn>    # kiểm một file có đang bị chặn không
```

Bốn thứ **không bao giờ** được lọt vào git (đã chặn trong `.gitignore` — không bao giờ gỡ, không bao giờ `git add -f` chúng): `.env` · `commhunter/configs/*.yaml` (trừ `example.yaml`) · `commhunter/data/` · `chrome-debug-profile/`. Nếu phát hiện một trong số đó đã bị commit: dừng lại, báo anh Ber ngay, **không** tự viết lại lịch sử — coi như secret đã lộ và phải đổi key/cookie.

**Quy tắc làm việc:**

- **Chỉ commit khi anh Ber yêu cầu.** Làm xong việc thì báo cáo và để anh Ber quyết, đừng tự commit.
- **Không bao giờ tự `git push`, `git reset --hard`, `git rebase`, `git checkout -- .`, hay `git clean`** khi chưa được yêu cầu rõ — chúng xoá công sức không hoàn tác được. Cần bỏ thay đổi thì hỏi trước.
- **Không `git add -A` khi chưa nhìn `git status`.** Việc lớn thì `git add` từng đường dẫn.
- Việc thử nghiệm có rủi ro (đổi kiến trúc, sửa hàng loạt): commit mốc sạch **trước** khi bắt đầu, để còn đường lùi.
- Không dùng `--no-verify`, không bỏ qua hook.

**Commit message** — tiếng Việt, dòng đầu ≤72 ký tự, dạng `<loại>: <việc đã làm>`:

`feat` tính năng mới · `fix` sửa lỗi · `refactor` sửa cấu trúc không đổi hành vi · `test` thêm/sửa test · `docs` tài liệu · `chore` hạ tầng, cấu hình, dọn dẹp · `style` định dạng, không đổi hành vi.

Thân message nói **vì sao**, không kể lại diff. Có kiểm chứng thì ghi số thật (`pipeline 104/104, backend 243/243`). Kết bằng dòng:

```
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

---

# Phụ lục A — Riêng cho Claude Code

## A.1 Leo thang model (quyền đứng sẵn — anh Ber)

- Kiểm model của phiên hiện tại trước. Phiên đang chạy model mạnh (Opus/Fable) → xử lý phần khó ngay trong vòng chính, không spawn subagent cùng cấp (tốn cold-start).
- Việc cần suy luận sâu (kiến trúc phức tạp, debug nhiều tầng, phân tích rủi ro anti-ban, thuật toán khó) mà phiên đang chạy model nhẹ → spawn subagent model mạnh cho đúng phần khó, rồi tự tổng hợp.
- Không dùng model mạnh cho việc cơ học (sửa nhỏ, đổi tên, chạy test).
- **Trần: tối đa 2 subagent chạy đồng thời.** Chọn model theo độ khó từng việc, không dùng một mặc định cho tất cả. Việc tách ra hơn 2 nhánh độc lập → chia lô qua 2 subagent tuần tự, không spawn cái thứ 3.
- Chỉ spawn subagent khi anh Ber yêu cầu hoặc việc thật sự cần fan-out; mặc định là tự làm.

## A.2 Kho memory

- Đường dẫn: `C:\Users\quock\.claude\projects\f--Clone-fb-tool\memory\`, index `MEMORY.md` cùng thư mục (tự nạp). Đường dẫn suy ra từ home + slug thư mục làm việc — đổi máy/đổi repo thì xác minh lại từ môi trường, đừng tin chuỗi cứng này.
- Theo bảng kích hoạt §9.1; cập nhật hơn tạo mới; giữ `MEMORY.md` dưới 200 dòng; memory `project` đổi sang ngày tuyệt đối.

## A.3 Ý thức ngân sách ngữ cảnh

- Cửa sổ lớn nhưng chất lượng giảm rõ khi quá dài. Compact là mất mát — snapshot + `/clear` + phiên mới luôn tốt hơn compact.
- Ở các mốc tự nhiên (xong tác vụ, duyệt xong plan, chuyển sang domain khác): cập nhật snapshot rồi đề xuất `/clear`. Đề xuất sớm nếu phiên đã đọc >5 file, spawn ≥2 subagent, hoặc sinh plan/báo cáo dài.
- **KHÔNG bao giờ tự chạy `/compact`** — đó là quyết định của anh Ber; agent chỉ ghi snapshot và đề xuất.
- Dấu hiệu kết phiên ("tạm nghỉ", "mai làm tiếp"): cập nhật snapshot TRƯỚC khi terminal đóng.
