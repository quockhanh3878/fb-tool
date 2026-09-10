"""
Hằng số và ngưỡng an toàn cho toàn hệ thống CommHunter.
"""
import unicodedata


def normalize_vi(text: str) -> str:
    """Chuẩn hoá text tiếng Việt để so khớp: bỏ dấu + hạ chữ thường.

    'đ'/'Đ' được xử lý riêng vì NFD không tách được ký tự này.
    """
    text = (text or "").lower().replace("đ", "d").replace("Đ", "d")
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")


# ── Browser Stealth ────────────────────────────────────────────────────────
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

USER_AGENTS_POOL = [
    USER_AGENT,
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Safari/605.1.15",
]

BROWSER_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-features=IsolateOrigins,site-per-process",
    "--start-maximized",
]

VIEWPORT = {"width": 1280, "height": 900}
LOCALE = "vi-VN"
TIMEZONE = "Asia/Ho_Chi_Minh"

# ── Browser Runtime ────────────────────────────────────────────────────────
# "chrome" = dùng Google Chrome thật đã cài trên máy (khó bị phát hiện hơn
# Chromium bundled của Playwright). Rơi về "chromium" nếu máy không có Chrome.
BROWSER_CHANNEL = "chrome"
BROWSER_CHANNEL_FALLBACK = "chromium"
# Mặc định HIỆN browser. Nuôi nick bằng browser thật + thao tác UI như người
# an toàn hơn nhiều so với headless + gọi mã trực tiếp.
BROWSER_HEADLESS_DEFAULT = False

# ── Fingerprint Pools (dùng cho fingerprint.generate_fingerprint) ───────────
# Máy khách phần lớn chạy Windows nên khoá về Windows để UA ↔ platform ↔ GPU
# luôn khớp nhau. Mỗi nick bốc xác định 1 bộ và giữ nguyên mãi.
FP_WINDOWS_UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
]
FP_HARDWARE_CONCURRENCY_POOL = [4, 6, 8, 8, 12, 16]
FP_DEVICE_MEMORY_POOL = [4, 8, 8, 16]
FP_LANGUAGES = ["vi-VN", "vi", "en-US", "en"]
FP_SCREEN_SIZES = [
    (1366, 768),
    (1536, 864),
    (1920, 1080),
    (1600, 900),
    (1440, 900),
]
# (UNMASKED_VENDOR_WEBGL, UNMASKED_RENDERER_WEBGL) — chuỗi ANGLE thật của Chrome/Windows.
FP_WEBGL_PAIRS = [
    (
        "Google Inc. (Intel)",
        "ANGLE (Intel, Intel(R) UHD Graphics 620 Direct3D11 vs_5_0 ps_5_0, D3D11)",
    ),
    (
        "Google Inc. (Intel)",
        "ANGLE (Intel, Intel(R) Iris(R) Xe Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)",
    ),
    (
        "Google Inc. (NVIDIA)",
        "ANGLE (NVIDIA, NVIDIA GeForce GTX 1650 Direct3D11 vs_5_0 ps_5_0, D3D11)",
    ),
    (
        "Google Inc. (NVIDIA)",
        "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)",
    ),
    (
        "Google Inc. (AMD)",
        "ANGLE (AMD, AMD Radeon(TM) Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)",
    ),
]

# ── Anti-Ban Thresholds ────────────────────────────────────────────────────
MAX_COMMENTS_PER_DAY = 20
MAX_GROUPS_PER_CYCLE = 10
SCAN_DELAY_MIN_SEC = 30        # Giãn cách giữa các group
SCAN_DELAY_MAX_SEC = 90
PAGE_LOAD_WAIT_MIN_MS = 2000
PAGE_LOAD_WAIT_MAX_MS = 4000
SCROLL_WAIT_MIN_MS = 1500
SCROLL_WAIT_MAX_MS = 2500
SCROLL_PASSES = 4              # Số lần cuộn feed khi quét group
WARMUP_DURATION_MIN_SEC = 30   # Lướt newsfeed trước khi comment
WARMUP_DURATION_MAX_SEC = 60

# ── Warmup Safety ──────────────────────────────────────────────────────────
WARMUP_HREF_BLOCKLIST = [
    "/logout", "logout.php", "/leave", "remove.php", "/report",
    "/delete", "/settings", "/privacy", "/checkpoint", "l.facebook.com", "/ads/",
    "/marketplace", "/messages", "/notifications", "/friends/requests", "/create",
]
WARMUP_LABEL_BLOCKLIST = [
    "rời", "leave", "báo cáo", "report", "đăng xuất", "log out",
    "xóa", "delete", "chặn", "block", "ẩn", "hide", "gỡ", "remove", "thích", "like",
    "chia sẻ", "share", "bình luận", "comment", "theo dõi", "follow", "tham gia", "join", "mời", "invite",
]
WARMUP_SCROLL_DOWN_BIAS = 0.8
WARMUP_HOVER_PROBABILITY = 0.35

# ── Circuit Breaker ────────────────────────────────────────────────────────
CIRCUIT_BREAKER_FAILURES = 3


# ── Comment Typing ─────────────────────────────────────────────────────────
TYPING_DELAY_MIN_MS = 80
TYPING_DELAY_MAX_MS = 350
TYPO_PROBABILITY = 0.05
FAKE_WORD_PROBABILITY = 0.05
CURSOR_JIGGLE_PROBABILITY = 0.03

# ── Selectors ──────────────────────────────────────────────────────────────
COMMENT_BOX_SELECTORS = [
    '[aria-label*="Write a comment"][contenteditable="true"]',
    '[aria-label*="Viết bình luận"][contenteditable="true"]',
    '[aria-label*="Comment as"][contenteditable="true"]',
    '[aria-label*="Bình luận với tư cách"][contenteditable="true"]',
    'div[role="textbox"][contenteditable="true"]',
]

FEED_SELECTOR = '[role="feed"] > *'

# Nút "..." trên chính bình luận của mình (mở menu Chỉnh sửa / Xóa).
# aria-label xác nhận qua DOM group thật 2026-09.
OWN_COMMENT_MENU_LABELS = [
    "Chỉnh sửa hoặc xóa bình luận này",
    "Edit or delete this comment",
]
COMMENT_DELETE_MENU_TEXTS = ["Xóa", "Xoá", "Delete"]
COMMENT_DELETE_CONFIRM_HEADINGS = ["Xóa bình luận", "Delete comment"]

# ── Checkpoint / Login Detection ───────────────────────────────────────────
CHECKPOINT_URL_PATTERNS = [
    "checkpoint",
    "login",
    "/recover",
    "security",
    "two_step_verification",
]

# ── AI Defaults ────────────────────────────────────────────────────────────
AI_MODEL_DEFAULT = "gpt-4o-mini"
AI_FILTER_TEMPERATURE = 0.3
AI_COMMENT_TEMPERATURE = 0.8
AI_FILTER_MAX_TOKENS = 500
AI_COMMENT_MAX_TOKENS = 300
AI_RETRY_COUNT = 3
AI_RETRY_DELAY_SEC = 2

# ── Database ───────────────────────────────────────────────────────────────
DEFAULT_DB_PATH = "data/commhunter.db"

# ── Logging ────────────────────────────────────────────────────────────────
LOG_FORMAT = "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} — {message}"
LOG_ROTATION = "10 MB"
LOG_RETENTION = "7 days"

# ── JavaScript ─────────────────────────────────────────────────────────────
# JS để extract data từ 1 post element.
# Cập nhật 2026-09 sau khi soi DOM group thật:
#   • Permalink của post CHỈ nằm ở link timestamp, kèm ?comment_id & __cft__/__tn__
#     — bản cũ loại thẳng mọi link có 'comment_id' nên KHÔNG BAO GIỜ lấy được URL.
#     Nay: match /groups/<gid>/posts|permalink/<pid> rồi dựng lại permalink sạch.
#   • FB render "xem thêm" làm text bị nhân đôi trong CÙNG một div[dir=auto]
#     → thêm bước gỡ chuỗi lặp X+X.
EXTRACT_POST_JS = r"""(el) => {
    const fullText = el.textContent || '';
    if (fullText.length < 60) return null;

    // --- Author ---
    let author = '';
    for (const a of el.querySelectorAll('a[href*="/user/"], a[href*="/profile.php"]')) {
        const name = (a.getAttribute('aria-label') || a.textContent || '').trim();
        if (name && name.length > 1 && name.length < 60 && !/^\d/.test(name)) {
            author = name;
            break;
        }
    }

    // --- Post URL: quét mọi link, chuẩn hoá về permalink sạch ---
    let postUrl = '';
    let postId = '';
    const cleanLink = (href) => {
        if (!href) return '';
        let m = href.match(/\/groups\/(\d+)\/(?:posts|permalink)\/(\d+)/);
        if (m) { postId = m[2]; return 'https://www.facebook.com/groups/' + m[1] + '/posts/' + m[2] + '/'; }
        m = href.match(/[?&](?:story_fbid|fbid)=(\d+)/);
        if (m && /[?&]id=(\d+)/.test(href)) {
            postId = m[1];
            const idm = href.match(/[?&]id=(\d+)/);
            return 'https://www.facebook.com/' + idm[1] + '/posts/' + m[1] + '/';
        }
        m = href.match(/facebook\.com\/[^\/]+\/(?:posts|permalink)\/(\d+)/);
        if (m && !href.includes('/photo')) {
            postId = m[1];
            try { const u = new URL(href, location.origin); return u.origin + u.pathname; } catch (e) {}
        }
        return '';
    };
    for (const a of el.querySelectorAll('a[href]')) {
        const c = cleanLink(a.getAttribute('href') || a.href || '');
        if (c) { postUrl = c; break; }
    }

    // --- Post text ---
    const dedupeDouble = (s) => {
        const n = s.length;
        if (n < 40) return s;
        const h = Math.floor(n / 2);
        const a = s.slice(0, h).trim();
        const b = s.slice(h).trim().replace(/[.…\s]+$/, '');
        const a2 = a.replace(/[.…\s]+$/, '');
        if (a2.length > 15 && (a2 === b || a2.startsWith(b) || b.startsWith(a2))) {
            return a;
        }
        return s;
    };
    const seen = [];
    for (const d of el.querySelectorAll('div[dir="auto"]')) {
        let t = (d.textContent || '').trim();
        if (!t || t.length < 15 || t === author) continue;
        t = dedupeDouble(t);
        if (seen.some(s => s === t || s.startsWith(t) || t.startsWith(s))) {
            for (let i = 0; i < seen.length; i++) {
                if (t.length > seen[i].length && (t.startsWith(seen[i]) || seen[i].startsWith(t))) {
                    seen[i] = t;
                }
            }
            continue;
        }
        seen.push(t);
    }
    seen.sort((a, b) => b.length - a.length);
    const text = (seen[0] || '').substring(0, 2000);

    // --- Comment Count ---
    let commentCount = 0;
    for (const ce of el.querySelectorAll('[aria-label*="bình luận"], [aria-label*="comment"]')) {
        const mm = (ce.getAttribute('aria-label') || '').match(/([\d.,]+)/);
        if (mm) {
            const v = parseInt(mm[1].replace(/[.,]/g, ''), 10);
            if (!isNaN(v)) commentCount = Math.max(commentCount, v);
        }
    }

    // --- Images ---
    const imageCount = el.querySelectorAll('img[src*="scontent"]').length;

    if (!author && text.length < 20) return null;

    return {
        author: author || 'Unknown',
        text: text,
        url: postUrl,
        postId: postId,
        images: imageCount,
        commentCount: commentCount,
    };
}"""
