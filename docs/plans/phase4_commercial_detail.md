# PHASE 4 — THƯƠNG MẠI HÓA & MỞ RỘNG: Chi tiết Triển khai (Tuần 11+)

> **Mục tiêu:** Đóng gói sản phẩm SaaS hoàn chỉnh, tích hợp thanh toán tự động, xây dựng Landing Page marketing, hệ thống onboarding cho khách mới, và mở rộng ra các thị trường ngách khác ngoài writing commission.
> **Tiền đề:** Phase 3 Anti-Ban Engine hoạt động ổn định, hệ thống tự vận hành 24/7.
> **Tham chiếu:** [Master Plan §8, §9](file:///f:/Clone/fb-tool/docs/03_MASTER_PLAN.md)

---

## Cấu trúc module mới Phase 4

```
fb-tool/
├── backend/app/
│   ├── routers/
│   │   ├── billing.py                  # Quản lý gói cước & thanh toán
│   │   ├── admin.py                    # Admin dashboard API
│   │   └── referral.py                 # Hệ thống referral
│   ├── services/
│   │   ├── billing_service.py          # Logic gói cước, quota, gia hạn
│   │   ├── payment_gateway.py          # Tích hợp VNPay / Momo / Stripe
│   │   ├── onboarding_service.py       # Wizard setup cho khách mới
│   │   └── referral_service.py         # Quản lý mã giới thiệu
│   └── models/
│       ├── payment.py                  # Lịch sử thanh toán
│       └── referral.py                 # Bảng referral code
├── frontend/app/
│   ├── (public)/                       # Landing page (không cần auth)
│   │   ├── page.tsx                    # Trang chủ marketing
│   │   ├── pricing/page.tsx            # Bảng giá
│   │   └── features/page.tsx           # Tính năng chi tiết
│   ├── onboarding/                     # Wizard setup cho user mới
│   │   ├── step1/page.tsx              # Chọn gói cước
│   │   ├── step2/page.tsx              # Tạo chiến dịch đầu tiên
│   │   ├── step3/page.tsx              # Upload clone cookie
│   │   ├── step4/page.tsx              # Thêm group
│   │   └── step5/page.tsx              # Soạn kịch bản + Kết nối Telegram
│   └── admin/                          # Admin-only pages
│       ├── users/page.tsx              # Quản lý tất cả users
│       ├── billing/page.tsx            # Quản lý thanh toán
│       └── system/page.tsx             # System health overview
└── landing/                            # Landing page riêng (nếu tách domain)
```

---

## Sprint 8 (Tuần 11-12): Thanh toán & Gói cước

### Task 4.1: Billing Service & Subscription Logic (Ngày 1-3)

**Database bổ sung:**
```sql
CREATE TABLE payments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    subscription_id UUID REFERENCES subscriptions(id),
    amount INTEGER NOT NULL,             -- Số tiền (VND)
    currency TEXT DEFAULT 'VND',
    payment_method TEXT,                 -- vnpay / momo / stripe / manual
    transaction_id TEXT,                 -- Mã giao dịch từ gateway
    status TEXT DEFAULT 'pending',       -- pending / success / failed / refunded
    metadata JSONB,                      -- Dữ liệu gateway trả về
    created_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP
);

CREATE TABLE referral_codes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),  -- Người sở hữu mã
    code TEXT UNIQUE NOT NULL,           -- VD: "NYATYMITA20"
    discount_percent INTEGER DEFAULT 10, -- Giảm giá %
    max_uses INTEGER DEFAULT 100,
    current_uses INTEGER DEFAULT 0,
    commission_percent INTEGER DEFAULT 15, -- Hoa hồng cho người giới thiệu
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE referral_usage (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    referral_code_id UUID NOT NULL REFERENCES referral_codes(id),
    referred_user_id UUID NOT NULL REFERENCES users(id),
    payment_id UUID REFERENCES payments(id),
    commission_amount INTEGER,           -- Hoa hồng thực nhận (VND)
    created_at TIMESTAMP DEFAULT NOW()
);
```

**Luồng thanh toán:**
```
1. User chọn gói cước (Starter/Pro/Studio)
2. Hệ thống tạo payment record (status=pending)
3. Redirect đến cổng thanh toán (VNPay/Momo)
4. User thanh toán
5. Gateway callback → API endpoint /webhook/payment
6. Xác nhận giao dịch → Cập nhật subscription
7. Kích hoạt quota theo gói mới
8. Gửi email/Telegram xác nhận
```

**Subscription Lifecycle:**
```python
class BillingService:
    async def check_quota(self, user_id: str, resource: str) -> bool:
        """Kiểm tra user còn quota không."""
        sub = await self.get_active_subscription(user_id)
        if not sub:
            raise NoSubscription("Cần đăng ký gói cước để sử dụng.")

        quotas = {
            "starter": {"groups": 5, "clones": 1, "ai_comments": False, "bump": False},
            "pro": {"groups": 20, "clones": 3, "ai_comments": True, "bump": True},
            "studio": {"groups": 999, "clones": 10, "ai_comments": True, "bump": True},
        }
        plan_quota = quotas[sub.plan]

        if resource == "groups":
            current = await self.count_user_groups(user_id)
            return current < plan_quota["groups"]
        elif resource == "clones":
            current = await self.count_user_clones(user_id)
            return current < plan_quota["clones"]
        elif resource == "ai_comments":
            return plan_quota["ai_comments"]
        elif resource == "bump":
            return plan_quota["bump"]
        return False

    async def handle_expiry(self):
        """Chạy hàng ngày: Xử lý subscription hết hạn."""
        expired = await self.get_expired_subscriptions()
        for sub in expired:
            # Tạm dừng tất cả campaign
            await self.pause_all_campaigns(sub.user_id)
            # Gửi thông báo nhắc gia hạn
            await self.notify_expiry(sub.user_id, grace_days=3)
            # Sau 3 ngày grace period: Deactivate hoàn toàn
```

**Acceptance Criteria:**
- [ ] Thanh toán qua VNPay/Momo thành công
- [ ] Subscription kích hoạt đúng quota
- [ ] Tự động nhắc gia hạn khi sắp hết hạn
- [ ] Grace period 3 ngày trước khi tạm dừng dịch vụ

---

### Task 4.2: Tích hợp Cổng thanh toán (Ngày 3-5)

**Ưu tiên 1: VNPay** (phổ biến nhất tại VN)

```python
# services/payment_gateway.py

class VNPayGateway:
    def __init__(self, tmn_code, secret_key, payment_url):
        self.tmn_code = tmn_code
        self.secret_key = secret_key
        self.payment_url = payment_url

    def create_payment_url(self, order_id: str, amount: int, description: str) -> str:
        """Tạo URL thanh toán VNPay."""
        params = {
            "vnp_Version": "2.1.0",
            "vnp_Command": "pay",
            "vnp_TmnCode": self.tmn_code,
            "vnp_Amount": amount * 100,  # VNPay nhận đơn vị x100
            "vnp_OrderInfo": description,
            "vnp_TxnRef": order_id,
            "vnp_ReturnUrl": f"{FRONTEND_URL}/payment/callback",
            "vnp_IpAddr": "127.0.0.1",
            "vnp_CreateDate": datetime.now().strftime("%Y%m%d%H%M%S"),
            "vnp_CurrCode": "VND",
            "vnp_Locale": "vn",
            "vnp_OrderType": "other",
        }
        # Sign params với HMAC-SHA512
        params["vnp_SecureHash"] = self._sign(params)
        return f"{self.payment_url}?{urlencode(params)}"

    def verify_callback(self, params: dict) -> bool:
        """Xác thực callback từ VNPay."""
        secure_hash = params.pop("vnp_SecureHash", "")
        expected_hash = self._sign(params)
        return hmac.compare_digest(secure_hash, expected_hash)
```

**Ưu tiên 2: Momo** (e-wallet phổ biến)
- Tích hợp Momo QR Payment API

**Ưu tiên 3: Chuyển khoản thủ công** (fallback)
- User chuyển khoản → Gửi ảnh chụp → Admin confirm thủ công

---

### Task 4.3: Onboarding Wizard cho User mới (Ngày 5-7)

**5 bước setup từ A-Z:**

| Step | Tên | Nội dung | Validation |
|------|-----|----------|------------|
| 1 | **Chọn gói cước** | Card 3 gói: Starter/Pro/Studio. Highlight gói Pro. Hỗ trợ mã giảm giá. | Phải chọn 1 gói |
| 2 | **Tạo chiến dịch đầu tiên** | Form: Tên chiến dịch + Mô tả ngắn dịch vụ của bạn + Chọn Semi/Full-Auto | Tên không trống |
| 3 | **Thêm tài khoản Clone** | Hướng dẫn cách lấy cookie (video/ảnh). Form upload cookie file. Auto-check session. | Cookie hợp lệ, session active |
| 4 | **Thêm Group mục tiêu** | Input URL group. Suggest các group phổ biến theo ngành. Auto-validate URL. | Ít nhất 1 group |
| 5 | **Soạn kịch bản & Kết nối Telegram** | Template mẫu pre-filled. Nút "Sinh thử comment AI". QR code kết nối Telegram Bot. | Kết nối Telegram thành công |

**UX đặc biệt:**
- Progress bar 5 bước ở đầu trang
- Mỗi bước có video tutorial ngắn (30s) ở sidebar
- Nút "Bỏ qua, tôi tự setup sau" cho user nâng cao
- Sau step 5: Confetti animation + "Chiến dịch đã sẵn sàng!" → Redirect vào Dashboard

---

## Sprint 9 (Tuần 13-14): Marketing & Mở rộng

### Task 4.4: Landing Page Marketing (Ngày 1-3)

**Cấu trúc Landing Page:**

| Section | Nội dung |
|---------|----------|
| **Hero** | Headline: "Tự động săn khách hàng trên Facebook Groups 24/7" + Sub: "Thay thế CTV lười biếng bằng AI thông minh" + CTA: "Dùng thử miễn phí" |
| **Pain Points** | 3 cards: "CTV không kỷ luật", "Bỏ lỡ khách vì bận", "Sợ bị ban nick" |
| **How It Works** | 4 bước: Thêm group → AI quét bài → Duyệt 1 chạm trên Telegram → Chốt đơn |
| **Features** | Grid 6 tính năng: AI Comment, Semi-Auto, Anti-Ban, Multi-Clone, Telegram Bot, Analytics |
| **Social Proof** | Testimonial từ khách Nyatymita + Thống kê: "500+ đơn đã chốt qua CommHunter" |
| **Pricing** | Bảng 3 gói cước + FAQ |
| **CTA Bottom** | "Bắt đầu miễn phí ngay hôm nay — Không cần thẻ tín dụng" |

**SEO:**
- Title: "CommHunter AI — Tự động tìm khách & ứng tuyển commission trên Facebook Groups"
- Meta Description: "Nền tảng AI giúp creator, shop dịch vụ tự động quét group Facebook, lọc bài phù hợp và ứng tuyển 24/7. Thay thế CTV. An toàn. Hiệu quả."
- Structured Data: SoftwareApplication schema

---

### Task 4.5: Hệ thống Referral / Affiliate (Ngày 3-5)

**Cơ chế:**
- Mỗi user có 1 mã giới thiệu duy nhất (VD: `NYATY20`)
- User mới dùng mã → Giảm 10-20% tháng đầu
- User giới thiệu → Nhận 15% hoa hồng trên thanh toán của người được giới thiệu (recurring 3 tháng)
- Dashboard Referral: Thống kê số người đã giới thiệu, tổng hoa hồng, rút tiền

**API Endpoints:**

| Method | Path | Mô tả |
|--------|------|-------|
| GET | `/api/referral/my-code` | Lấy mã giới thiệu của user |
| POST | `/api/referral/apply` | Áp dụng mã giảm giá khi thanh toán |
| GET | `/api/referral/stats` | Thống kê referral (số người, hoa hồng) |
| POST | `/api/referral/withdraw` | Yêu cầu rút hoa hồng |

---

### Task 4.6: Admin Dashboard (Ngày 5-7)

**Chức năng Admin:**

| Trang | Chức năng |
|-------|----------|
| **User Management** | Danh sách tất cả users, search, filter theo gói. Nút: Upgrade/Downgrade gói, Ban user |
| **Billing Overview** | Tổng doanh thu tháng này, MRR, Biểu đồ doanh thu theo tháng, Danh sách giao dịch |
| **System Health** | Tổng hợp: Số campaign active, Số clone active, Tỷ lệ uptime, Queue size, Error rate |
| **Clone Pool** | Quản lý dàn clone cho gói Studio (platform cấp). Trạng thái, assign cho user |
| **Proxy Pool** | Quản lý proxy: Thêm/xóa, Health status, Usage stats |
| **Support Tickets** | Inbox từ Telegram/Email, Assign cho team |

---

### Task 4.7: Mở rộng Template ngành (Ngày 7+)

**Ngoài Writing Commission, hệ thống hoàn toàn áp dụng được cho:**

| Ngành | Keyword mẫu | Kịch bản mẫu |
|-------|-------------|---------------|
| **Vẽ Commission** | "tìm hoạ sĩ", "cần vẽ", "nhận vẽ comm" | "Bên mình chuyên chibi/realistic/anime style, bạn ghé xem gallery ở đầu tường nhà nhé" |
| **Dịch thuật** | "cần dịch", "tìm biên dịch", "dịch fic" | "Mình chuyên dịch EN-VI/CN-VI, chất lượng và deadline luôn đúng hẹn" |
| **Content Marketing** | "cần viết bài", "tìm copywriter" | "Mình chuyên viết content theo brief, có portfolio và case study thực tế" |
| **Gia sư Online** | "tìm gia sư", "cần dạy kèm" | "Mình có kinh nghiệm dạy [môn], phương pháp hiệu quả" |
| **Design Freelance** | "cần thiết kế", "tìm designer" | "Bên mình nhận logo/banner/branding, xem mẫu ở trang cá nhân" |

**Triển khai:**
- Tạo bộ Template cho mỗi ngành (pre-filled keywords, AI prompts, kịch bản mẫu)
- Trong Onboarding Wizard Step 2: User chọn ngành → Auto-fill cấu hình
- Marketplace Template: User chia sẻ template hiệu quả cho cộng đồng

---

## Acceptance Criteria Phase 4

- [ ] Thanh toán online (VNPay/Momo) hoạt động end-to-end
- [ ] Subscription tự động kích hoạt/hết hạn/nhắc gia hạn
- [ ] Onboarding Wizard: User mới setup từ 0 đến chạy được trong 10 phút
- [ ] Landing Page: Lighthouse Performance > 90, SEO score > 90
- [ ] Referral system: Mã giảm giá + Hoa hồng tính đúng
- [ ] Admin Dashboard: Quản lý toàn bộ hệ thống từ 1 nơi
- [ ] 50+ khách trả phí ổn định trong 2 tháng đầu
- [ ] MRR > 15.000.000d / tháng
- [ ] Churn rate < 10% / tháng
