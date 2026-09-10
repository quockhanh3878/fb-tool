# 📋 PHASE 3 — ANTI-BAN ENGINE & ACCOUNT MANAGER: Chi tiết Triển khai (Tuần 7-10)

> **Mục tiêu:** Hardening hệ thống để chạy bền bỉ 24/7, tự động phát hiện và xử lý mọi sự cố tài khoản clone (checkpoint, shadowban, rate limit), tự ủ ấm clone mới, tự xoay vòng proxy và tự phục hồi khi gặp lỗi — không cần can thiệp thủ công.
> **Tiền đề:** Phase 2 Web Dashboard đã hoạt động ổn định với nhiều khách hàng.
> **Tham chiếu:** [Master Plan §4.5, §6](file:///f:/Clone/fb-tool/docs/03_MASTER_PLAN.md)

---

## Cấu trúc module mới Phase 3

```
backend/app/
├── services/
│   ├── account_manager.py              # State machine + Lifecycle management
│   ├── warmup_service.py               # Pipeline ủ ấm 7 ngày
│   ├── anti_ban_engine.py              # Rate limiter + Detection + Response
│   ├── proxy_manager.py                # Quản lý pool proxy + rotation
│   └── health_monitor.py               # Dashboard sức khỏe tổng hợp
├── workers/
│   ├── warmup_task.py                  # Celery task ủ ấm hàng ngày
│   ├── health_check_task.py            # Celery task kiểm tra sức khỏe định kỳ
│   └── proxy_rotation_task.py          # Celery task xoay proxy
└── routers/
    └── health.py                       # API endpoints cho Health Dashboard
```

---

## Sprint 6 (Tuần 7-8): Account State Machine & Warm-up

### Task 3.1: Account State Machine (Ngày 1-3 — 16 giờ)

**File:** `services/account_manager.py`

**State Machine cho mỗi Clone Account:**

```
                                    ┌──────────┐
                        Nạp cookie  │Onboarding│
                        ──────────> │          │
                                    └────┬─────┘
                                         │ Cookie hợp lệ
                                         ▼
                                    ┌──────────┐
                                    │WarmingUp │ (7 ngày tự động lướt, like, join group)
                                    │          │
                                    └────┬─────┘
                                         │ Hoàn thành warm-up
                                         ▼
                    ┌────────────── ┌──────────┐ ──────────────┐
                    │               │  Active  │               │
                    │    ┌─────────>│          │<─────────┐    │
                    │    │          └──┬───┬───┘          │    │
                    │    │             │   │               │    │
                    │   Sau 4-8h      │   │     Sau 48h   │    │
                    │    │             │   │    + verify   │    │
                    │    │             │   │               │    │
                    │ ┌──┴───┐        │   │         ┌─────┴──┐ │
                    │ │Cool- │<───────┘   └────────>│Check-  │ │
                    │ │down  │ Đạt quota            │point   │ │
                    │ └──────┘ hoặc rate            └───┬────┘ │
                    │          limited                   │      │
                    │                          Không xác │      │
                    │                          minh được │      │
                    │                                    ▼      │
                    │                              ┌─────────┐  │
                    │                              │ Banned  │  │
                    │                              └─────────┘  │
                    │                                           │
                    │ Clone dự phòng sẵn sàng                   │
                    └───────────┐                               │
                                ▼                               │
                           ┌──────────┐                         │
                           │Rotating  │ (Xoay vòng giữa nhiều  │
                           │          │  clone cùng vai trò)    │
                           └──────────┘─────────────────────────┘
```

**Triển khai State Machine:**

```python
class AccountState(Enum):
    ONBOARDING = "onboarding"
    WARMING_UP = "warming_up"
    ACTIVE = "active"
    COOLDOWN = "cooldown"
    CHECKPOINT = "checkpoint"
    BANNED = "banned"
    ROTATING = "rotating"

class AccountTransition(Enum):
    COOKIE_VALID = "cookie_valid"
    WARMUP_COMPLETE = "warmup_complete"
    QUOTA_REACHED = "quota_reached"
    RATE_LIMITED = "rate_limited"
    COOLDOWN_EXPIRED = "cooldown_expired"
    CHECKPOINT_DETECTED = "checkpoint_detected"
    VERIFICATION_SUCCESS = "verification_success"
    VERIFICATION_FAILED = "verification_failed"
    ROTATE = "rotate"

# Bảng chuyển trạng thái (from_state, transition) -> to_state
STATE_TRANSITIONS = {
    (AccountState.ONBOARDING, AccountTransition.COOKIE_VALID): AccountState.WARMING_UP,
    (AccountState.WARMING_UP, AccountTransition.WARMUP_COMPLETE): AccountState.ACTIVE,
    (AccountState.ACTIVE, AccountTransition.QUOTA_REACHED): AccountState.COOLDOWN,
    (AccountState.ACTIVE, AccountTransition.RATE_LIMITED): AccountState.COOLDOWN,
    (AccountState.ACTIVE, AccountTransition.CHECKPOINT_DETECTED): AccountState.CHECKPOINT,
    (AccountState.ACTIVE, AccountTransition.ROTATE): AccountState.ROTATING,
    (AccountState.COOLDOWN, AccountTransition.COOLDOWN_EXPIRED): AccountState.ACTIVE,
    (AccountState.CHECKPOINT, AccountTransition.VERIFICATION_SUCCESS): AccountState.COOLDOWN,  # Nghỉ 48h
    (AccountState.CHECKPOINT, AccountTransition.VERIFICATION_FAILED): AccountState.BANNED,
    (AccountState.ROTATING, AccountTransition.ROTATE): AccountState.ACTIVE,
}

class AccountManager:
    async def transition(self, clone_id: str, event: AccountTransition):
        """Chuyển trạng thái an toàn với logging và notification."""
        clone = await self.get_clone(clone_id)
        current_state = AccountState(clone.status)
        key = (current_state, event)

        if key not in STATE_TRANSITIONS:
            raise InvalidTransitionError(f"Cannot {event.value} from {current_state.value}")

        new_state = STATE_TRANSITIONS[key]
        await self.update_state(clone_id, new_state)
        await self.log_health_event(clone_id, event, current_state, new_state)

        # Side effects
        if new_state == AccountState.COOLDOWN:
            cooldown_hours = random.uniform(4, 8)
            await self.schedule_cooldown_wakeup(clone_id, hours=cooldown_hours)
        elif new_state == AccountState.CHECKPOINT:
            await self.pause_all_tasks_for_clone(clone_id)
            await self.notify_user(clone_id, "⚠️ Clone bị checkpoint! Cần xác minh.")
        elif new_state == AccountState.BANNED:
            await self.deactivate_clone(clone_id)
            await self.try_switch_to_backup(clone_id)
            await self.notify_user(clone_id, "🚫 Clone bị ban. Đã chuyển sang clone dự phòng.")

    async def try_switch_to_backup(self, failed_clone_id: str):
        """Tự động chuyển sang clone dự phòng cùng vai trò."""
        failed_clone = await self.get_clone(failed_clone_id)
        backup = await self.find_available_clone(
            user_id=failed_clone.user_id,
            role=failed_clone.role,
            exclude_id=failed_clone_id
        )
        if backup:
            await self.assign_campaigns_to_clone(backup.id, failed_clone.campaigns)
            await self.notify_user(failed_clone.user_id,
                f"✅ Đã chuyển sang clone '{backup.display_name}' tự động.")
        else:
            await self.notify_user(failed_clone.user_id,
                "⚠️ Không còn clone dự phòng! Vui lòng thêm clone mới.")
```

**Bảng bổ sung Database:**
```sql
ALTER TABLE clone_accounts ADD COLUMN warmup_day INTEGER DEFAULT 0;  -- Ngày warm-up hiện tại (0-7)
ALTER TABLE clone_accounts ADD COLUMN warmup_started_at TIMESTAMP;
ALTER TABLE clone_accounts ADD COLUMN cooldown_until TIMESTAMP;
ALTER TABLE clone_accounts ADD COLUMN last_checkpoint_at TIMESTAMP;
ALTER TABLE clone_accounts ADD COLUMN consecutive_failures INTEGER DEFAULT 0;
ALTER TABLE clone_accounts ADD COLUMN is_backup BOOLEAN DEFAULT FALSE;
```

**Acceptance Criteria:**
- [ ] Tất cả state transitions hợp lệ theo bảng
- [ ] Invalid transitions raise exception
- [ ] Side effects (notify, pause, switch) trigger chính xác
- [ ] Health log ghi lại mọi chuyển trạng thái

---

### Task 3.2: Warm-up Pipeline 7 ngày (Ngày 3-5 — 12 giờ)

**File:** `services/warmup_service.py` + `workers/warmup_task.py`

**Lịch trình ủ ấm tự động:**

| Ngày | Hành vi | Thời lượng | Chi tiết kỹ thuật |
|------|---------|------------|-------------------|
| **1** | Lướt Newsfeed | 5 phút | `page.evaluate("window.scrollBy(0, 800)")` x10 lần, delay 3-5s giữa mỗi scroll |
| **2** | Lướt Newsfeed + Xem 2 Reels | 8 phút | Navigate đến `/reel/`, watch 15-30s mỗi reel |
| **3** | Like 3 bài ngẫu nhiên | 3 phút | Tìm nút Like `[aria-label*="Like"]`, click + delay 30-60s |
| **4** | Like 5 bài + Xem Reels | 8 phút | Kết hợp ngày 2+3 |
| **5** | Comment 1 bài (AI ngắn) | 5 phút | Comment trên bài của bạn bè: "Hay quá", "Thanks for sharing" |
| **6** | Comment 2 bài + Join 2-3 group | 10 phút | Join group bằng cách click "Join Group" button |
| **7** | Health check tổng thể | 3 phút | Kiểm tra session, profile visible, không bị restrict |

**Triển khai Celery task:**
```python
# workers/warmup_task.py

@celery_app.task(bind=True, max_retries=3)
def warmup_daily_step(self, clone_id: str):
    """Chạy 1 bước warm-up cho clone. Gọi mỗi ngày bởi Celery Beat."""
    clone = get_clone(clone_id)
    if clone.status != "warming_up":
        return

    day = clone.warmup_day + 1
    warmup_service = WarmupService()

    try:
        if day == 1:
            warmup_service.browse_newsfeed(clone, duration_minutes=5)
        elif day == 2:
            warmup_service.browse_newsfeed(clone, duration_minutes=3)
            warmup_service.watch_reels(clone, count=2)
        elif day == 3:
            warmup_service.like_random_posts(clone, count=3)
        elif day == 4:
            warmup_service.like_random_posts(clone, count=5)
            warmup_service.watch_reels(clone, count=2)
        elif day == 5:
            warmup_service.comment_friend_post(clone, count=1)
        elif day == 6:
            warmup_service.comment_friend_post(clone, count=2)
            warmup_service.join_groups(clone, group_urls=clone.campaign_groups[:3])
        elif day >= 7:
            health = warmup_service.full_health_check(clone)
            if health.is_healthy:
                account_manager.transition(clone_id, AccountTransition.WARMUP_COMPLETE)
                return
            else:
                # Kéo dài warm-up thêm 1-2 ngày
                clone.warmup_day = 5  # Quay lại ngày 5
                return

        update_clone(clone_id, warmup_day=day)
    except CheckpointError:
        account_manager.transition(clone_id, AccountTransition.CHECKPOINT_DETECTED)
```

**Acceptance Criteria:**
- [ ] Clone mới trải qua 7 ngày warm-up tự động
- [ ] Mỗi ngày thực hiện đúng hành vi theo bảng
- [ ] Sau ngày 7, clone chuyển sang Active nếu healthy
- [ ] Nếu gặp checkpoint trong warm-up, tự xử lý

---

### Task 3.3: Checkpoint Detection & Auto-Pause (Ngày 5-6 — 8 giờ)

**File:** `services/anti_ban_engine.py`

**3 lớp phát hiện checkpoint:**

```python
class CheckpointDetector:
    async def detect(self, page) -> CheckpointResult | None:
        """Phát hiện checkpoint theo 3 lớp."""
        # Lớp 1: URL-based detection
        url = page.url
        if any(kw in url for kw in ["checkpoint", "login", "recover", "challenge"]):
            return CheckpointResult(type="url_redirect", url=url)

        # Lớp 2: Title-based detection
        title = (await page.title()).lower()
        checkpoint_titles = [
            "security check", "xác minh", "confirm your identity",
            "log in", "đăng nhập", "account restricted",
            "tài khoản bị hạn chế"
        ]
        if any(kw in title for kw in checkpoint_titles):
            return CheckpointResult(type="title_match", title=title)

        # Lớp 3: DOM-based detection (popup/modal)
        checkpoint_selectors = [
            '[data-testid="checkpoint"]',
            'form[action*="checkpoint"]',
            '[aria-label*="security check"]',
            'div:has-text("Your account has been locked")',
            'div:has-text("Tài khoản của bạn đã bị khóa")',
        ]
        for selector in checkpoint_selectors:
            element = await page.query_selector(selector)
            if element:
                return CheckpointResult(type="dom_element", selector=selector)

        return None
```

**Auto-Response khi phát hiện:**
1. Dừng ngay lập tức mọi task đang chạy cho clone này
2. Chuyển state → `CHECKPOINT`
3. Bắn cảnh báo Telegram cho user
4. Nếu có clone backup → Chuyển campaign sang clone backup trong < 1 phút
5. Log sự kiện vào `account_health_logs`

---

### Task 3.4: Shadowban Detection (Ngày 6-7 — 8 giờ)

**Cơ chế:** Sau khi Shooter comment thành công, mở 1 tab ẩn danh (hoặc dùng Scout account) navigate đến cùng bài viết, kiểm tra comment vừa đăng có hiển thị không.

```python
class ShadowbanDetector:
    async def check_comment_visibility(
        self,
        post_url: str,
        comment_text_fragment: str,
        verification_context  # Browser context khác (Scout hoặc Incognito)
    ) -> bool:
        """Kiểm tra comment có hiển thị cho người khác không."""
        page = await verification_context.new_page()
        try:
            await page.goto(post_url, wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)

            # Cuộn xuống vùng comment
            await page.evaluate("window.scrollBy(0, 2000)")
            await page.wait_for_timeout(2000)

            # Tìm comment chứa fragment
            page_text = await page.inner_text("body")
            # So khớp 50 ký tự đầu tiên (tránh false positive)
            return comment_text_fragment[:50] in page_text
        finally:
            await page.close()
```

**Xử lý khi phát hiện Shadowban:**
1. Đánh dấu `comment_actions.status = "shadowbanned"`
2. Tăng `clone.consecutive_failures += 1`
3. Nếu `consecutive_failures >= 3`: Chuyển clone sang Cooldown 24h
4. Nếu `consecutive_failures >= 5`: Đánh dấu clone nghi ngờ, cảnh báo user
5. Bắn thông báo: "⚠️ Comment trên bài [link] bị ẩn (shadowban). Clone đang tạm nghỉ."

**Acceptance Criteria:**
- [ ] Phát hiện chính xác shadowban (test với comment thật)
- [ ] Không false positive khi comment hiển thị bình thường
- [ ] Auto-cooldown khi shadowban liên tiếp

---

## Sprint 7 (Tuần 9-10): Proxy Manager & Health Dashboard

### Task 3.5: Proxy Manager (Ngày 1-3 — 12 giờ)

**File:** `services/proxy_manager.py`

**Chức năng:**
1. **Gán cố định proxy cho mỗi clone:** Mỗi clone luôn dùng cùng 1 IP
2. **Pool Management:** Quản lý danh sách proxy available/assigned/blacklisted
3. **Auto-rotate:** Khi proxy bị đánh dấu (clone bị checkpoint khi dùng proxy đó), tự gán proxy mới
4. **Health Check:** Kiểm tra proxy còn sống không (mỗi 30 phút)

```python
class ProxyManager:
    async def assign_proxy(self, clone_id: str) -> str:
        """Gán proxy chưa dùng cho clone."""
        available = await self.get_available_proxies()
        if not available:
            raise NoProxyAvailable("Hết proxy! Cần thêm proxy vào pool.")
        proxy = available[0]
        await self.mark_assigned(proxy.id, clone_id)
        return proxy.address  # "socks5://user:pass@ip:port"

    async def rotate_proxy(self, clone_id: str, reason: str):
        """Xoay proxy: Blacklist proxy cũ, gán proxy mới."""
        old_proxy = await self.get_proxy_for_clone(clone_id)
        if old_proxy:
            await self.blacklist_proxy(old_proxy.id, reason=reason)
        new_proxy = await self.assign_proxy(clone_id)
        await self.update_clone_proxy(clone_id, new_proxy)
        return new_proxy

    async def check_proxy_health(self, proxy_address: str) -> bool:
        """Kiểm tra proxy hoạt động bằng cách request đến Facebook."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://www.facebook.com",
                    proxy=proxy_address,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    return resp.status == 200
        except Exception:
            return False
```

**Bảng Database bổ sung:**
```sql
CREATE TABLE proxies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    address TEXT NOT NULL,           -- "socks5://user:pass@ip:port"
    type TEXT DEFAULT 'residential', -- residential / mobile_4g / datacenter
    country TEXT DEFAULT 'VN',
    status TEXT DEFAULT 'available', -- available / assigned / blacklisted / dead
    assigned_to_clone_id UUID REFERENCES clone_accounts(id),
    assigned_at TIMESTAMP,
    blacklisted_at TIMESTAMP,
    blacklist_reason TEXT,
    last_health_check TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);
```

---

### Task 3.6: Adaptive Rate Limiter (Ngày 3-4 — 8 giờ)

**File:** Bổ sung vào `services/anti_ban_engine.py`

**Cơ chế Adaptive:** Thay vì dùng rate limit cố định, hệ thống tự điều chỉnh dựa trên phản hồi:

```python
class AdaptiveRateLimiter:
    def __init__(self):
        self.base_delay = 600  # 10 phút
        self.min_delay = 180   # 3 phút (không bao giờ thấp hơn)
        self.max_delay = 1800  # 30 phút (không bao giờ cao hơn)

    async def get_next_delay(self, clone_id: str) -> int:
        """Tính delay trước comment tiếp theo dựa trên lịch sử."""
        recent_actions = await self.get_recent_actions(clone_id, hours=24)
        recent_failures = [a for a in recent_actions if a.status in ("failed", "shadowbanned")]
        recent_success = [a for a in recent_actions if a.status == "success"]

        # Tỉ lệ thành công
        total = len(recent_actions) or 1
        success_rate = len(recent_success) / total

        if success_rate >= 0.95:
            # Mọi thứ tốt → Giảm delay dần (nhưng không dưới min)
            delay = max(self.min_delay, self.base_delay * 0.8)
        elif success_rate >= 0.80:
            # Bình thường → Giữ nguyên
            delay = self.base_delay
        elif success_rate >= 0.50:
            # Có dấu hiệu xấu → Tăng delay
            delay = min(self.max_delay, self.base_delay * 1.5)
        else:
            # Tình trạng nghiêm trọng → Delay tối đa
            delay = self.max_delay

        # Thêm random jitter +-20%
        jitter = delay * random.uniform(-0.2, 0.2)
        return int(delay + jitter)
```

---

### Task 3.7: Health Monitor Dashboard (Ngày 5-7 — 12 giờ)

**API Endpoints mới:**

| Method | Path | Mô tả |
|--------|------|-------|
| GET | `/api/health/overview` | Tổng quan sức khỏe tất cả clone |
| GET | `/api/health/clone/{id}/timeline` | Timeline sự kiện của 1 clone |
| GET | `/api/health/proxies` | Trạng thái pool proxy |
| GET | `/api/health/alerts` | Danh sách cảnh báo chưa xử lý |

**Frontend — Trang Health Monitor:**

| Phần | Nội dung |
|------|----------|
| **Clone Health Grid** | Grid card cho mỗi clone: Tên, Trạng thái (badge màu), Số cmt hôm nay, Streak (ngày hoạt động liên tục), Progress bar warmup |
| **Alert Feed** | Timeline các sự kiện: checkpoint detected, shadowban, proxy rotated, cooldown started/ended |
| **Proxy Pool** | Bảng: IP, Trạng thái, Gán cho clone nào, Health check lần cuối |
| **Success Rate Chart** | Biểu đồ đường: Tỷ lệ comment thành công theo ngày (30 ngày) |

**Acceptance Criteria Phase 3:**
- [ ] Clone mới tự warm-up 7 ngày thành công (tỷ lệ > 90%)
- [ ] Checkpoint detection phát hiện đúng 100% (không miss)
- [ ] Shadowban detection hoạt động chính xác
- [ ] Auto-switch sang clone backup trong < 1 phút khi clone chính bị sự cố
- [ ] Proxy rotation hoạt động khi cần
- [ ] Rate limiter tự điều chỉnh: Giảm delay khi an toàn, tăng khi có dấu hiệu xấu
- [ ] Health Dashboard hiển thị real-time trạng thái toàn hệ thống
