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
GROUPS_SCROLL_PASSES = 10      # Trang "Nhóm của bạn" dài hơn feed nên cuộn nhiều hơn
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
    # Group kiểu hỏi-đáp/thảo luận: ô nhập là "Viết câu trả lời..."
    # (xác nhận DOM group thật 2026-09-10).
    '[aria-label*="Viết câu trả lời"][contenteditable="true"]',
    '[aria-label*="Write an answer"][contenteditable="true"]',
    '[aria-label*="Comment as"][contenteditable="true"]',
    '[aria-label*="Bình luận với tư cách"][contenteditable="true"]',
    'div[role="textbox"][contenteditable="true"]',
]

FEED_SELECTOR = '[role="feed"] > *'

# ── Post Composer (đăng bài / seeding vào group) ───────────────────────────
# Đã soi DOM group thật 2026-09-10 (group "Hội BMW"): nút mở là
# div[role="button"] text "Bạn viết gì đi..."; dialog heading "Tạo bài viết",
# ô nhập là [role="textbox"][contenteditable] KHÔNG còn aria-label mô tả; nút
# Đăng có aria-label="Đăng" và aria-disabled="true" tới khi có nội dung.
# Nhánh gọi vẫn phải fail an toàn (dừng nick, không thử mù) khi không khớp.
COMPOSER_TRIGGER_SELECTORS = [
    'div[role="button"]:has-text("Bạn viết gì đi")',
    'div[role="button"]:has-text("Write something")',
    '[role="button"]:has-text("Bạn viết gì đi")',
    '[role="button"]:has-text("Bạn đang nghĩ gì")',
    '[role="button"]:has-text("Viết gì đó")',
]
COMPOSER_TEXTBOX_SELECTORS = [
    '[role="dialog"] [role="textbox"][contenteditable="true"]',
    '[role="dialog"] div[role="textbox"]',
    '[aria-label*="Tạo bài viết"][contenteditable="true"]',
    '[aria-label*="Create a public post"][contenteditable="true"]',
]
# aria-disabled="true" khi ô nhập còn trống — chỉ bấm nút đã bật.
COMPOSER_SUBMIT_SELECTORS = [
    '[role="dialog"] [aria-label="Đăng"]:not([aria-disabled="true"])',
    '[role="dialog"] [aria-label="Post"]:not([aria-disabled="true"])',
    '[role="dialog"] div[role="button"]:has-text("Đăng"):not([aria-disabled="true"])',
    '[role="dialog"] div[role="button"]:has-text("Post"):not([aria-disabled="true"])',
    '[role="dialog"] [aria-label="Đăng"]',
    '[role="dialog"] [aria-label="Post"]',
]
# Cụm từ báo bài đã lên (toast / trạng thái sau khi submit). KHÔNG dùng "đã đăng"
# trần — cụm này nằm rải rác khắp UI (nhãn mốc thời gian…) dễ gây dương tính giả.
POST_SUCCESS_PHRASES = [
    "bài viết của bạn đã được đăng", "your post is now published",
    "post published", "đã chia sẻ bài viết của bạn",
    "đang chờ phê duyệt", "pending approval",
    "sẽ hiển thị sau khi được phê duyệt", "will be visible once approved",
]
# Chờ tối đa bao lâu để hộp thoại soạn bài đóng sau khi bấm Đăng (poll 2s/lần).
POST_SUBMIT_CONFIRM_TIMEOUT_MS = 14000
# Số lần cuộn feed nhóm khi đi tìm lại permalink của bài vừa đăng.
COMPOSER_VERIFY_SCROLL_PASSES = 3

# FB đời mới (soi DOM thật 2026-09-10, group không kiểm duyệt) KHÔNG còn nhả
# permalink sạch vào href của mốc thời gian — href chỉ là "?__cft__[0]=...#?xxx"
# và chữ mốc thời gian bị xáo span chống scrape. Đường chắc ăn: đánh dấu đúng
# thẻ <a> mốc thời gian của bài chứa lát text rồi CLICK, FB tự điều hướng sang
# URL chuẩn /groups/<gid>/posts/<id>/. JS này nhận [textFragment], gắn thuộc
# tính data-cth-permalink lên thẻ cần click, trả về true/false.
MARK_TIMESTAMP_ANCHOR_JS = r"""([textFragment]) => {
    const clean = (s) => (s || '').replace(/\s+/g, ' ').trim().toLowerCase();
    const needle = clean(textFragment);
    if (!needle || needle.length < 12) return false;
    document.querySelectorAll('[data-cth-permalink]').forEach(
        (el) => el.removeAttribute('data-cth-permalink')
    );
    const kids = [...document.querySelectorAll('[role="feed"] > *')];
    const story = kids.find((k) => clean(k.textContent || '').includes(needle));
    if (!story) return false;
    const links = [...story.querySelectorAll('a[href]')];
    // Ưu tiên href đã có sẵn path permalink (một số phiên bản/locale còn nhả).
    for (const a of links) {
        if (/\/(posts|permalink)\//.test(a.getAttribute('href') || '')) {
            a.setAttribute('data-cth-permalink', '1');
            return true;
        }
    }
    // Không có -> thẻ mốc thời gian: href bắt đầu bằng '?' và có '#?' hoặc
    // tham số __tn__=,O, (KHÔNG phải link '/user/' của tác giả).
    for (const a of links) {
        const h = a.getAttribute('href') || '';
        if (h.includes('/user/')) continue;
        if (h.startsWith('?') && (h.includes('#?') || h.includes('__tn__=%2CO'))) {
            a.setAttribute('data-cth-permalink', '1');
            return true;
        }
    }
    return false;
}"""
MARK_TIMESTAMP_ANCHOR_SELECTOR = 'a[data-cth-permalink]'
# Rút permalink chuẩn từ URL bài (bỏ query tracking + hash).
PERMALINK_URL_RE = (
    r"https://(?:www|m|web|mbasic)\.facebook\.com/"
    r"(?:groups/\d+/(?:posts|permalink)|[^/?#]+/(?:posts|permalink)|permalink)"
    r"/[^/?#]+"
)

# ── Group Discovery ────────────────────────────────────────────────────────
# Trang liệt kê các nhóm tài khoản đã tham gia. Danh sách "group key" là trang
# chức năng cần loại (joins, feed, discover…) nằm ngay trong EXTRACT_GROUPS_JS.
JOINED_GROUPS_URL = "https://www.facebook.com/groups/joins/"

# Nút "..." trên chính bình luận của mình (mở menu Chỉnh sửa / Xóa).
# aria-label xác nhận qua DOM group thật 2026-09.
OWN_COMMENT_MENU_LABELS = [
    "Chỉnh sửa hoặc xóa bình luận này",
    "Edit or delete this comment",
]
COMMENT_DELETE_MENU_TEXTS = ["Xóa", "Xoá", "Delete"]
COMMENT_DELETE_CONFIRM_HEADINGS = ["Xóa bình luận", "Delete comment"]

# Xoá bài viết CHÍNH mình đã đăng (đường rollback / cleanup của publish_post).
# DOM group thật 2026-09-10: nút mở menu là [aria-haspopup="menu"] có aria-label
# "Hành động đối với bài viết này của <tên nick>" -> menu item "Xóa bài viết" /
# "Chuyển vào thùng rác" -> hộp thoại xác nhận -> nút "Xóa" / "Chuyển".
OWN_POST_MENU_SELECTORS = [
    '[aria-haspopup="menu"][aria-label*="Hành động đối với bài viết này"]',
    '[aria-haspopup="menu"][aria-label*="Actions for this post"]',
]
# Trang permalink của FB đời mới nhồi thêm bài "được đề xuất" / quảng cáo có
# cùng nút "Hành động đối với bài viết này..." -> query_selector đầu tiên hay
# trúng bài NGƯỜI KHÁC. Lọc theo tên tài khoản đang đăng nhập ("... của <tên>")
# mới chắc chắn xoá đúng bài mình. Các mẫu aria-label kèm tên:
OWN_POST_MENU_ARIA_NAMED = [
    'Hành động đối với bài viết này của {name}',
    'Actions for this post by {name}',
]
# Bóc tên tài khoản đang đăng nhập từ payload bootstrap của trang.
CURRENT_ACCOUNT_NAME_RE = r'"NAME":"([^"]{1,80})","SHORT_NAME"'
OWN_POST_DELETE_MENU_TEXTS = [
    "Xóa bài viết", "Xoá bài viết", "Chuyển vào thùng rác",
    "Move to trash", "Delete post",
]
# Chữ nhận diện hộp thoại xác nhận (so khớp không phân biệt hoa thường).
OWN_POST_DELETE_CONFIRM_HINTS = ["xóa", "xoá", "thùng rác", "trash", "delete", "move to"]
# Nhãn nút xác nhận — KHỚP TUYỆT ĐỐI để không bắt nhầm tiêu đề
# "Xóa bài viết vĩnh viễn?" hay nút "Xác nhận" của luồng khác.
OWN_POST_DELETE_CONFIRM_BUTTON_TEXTS = ["Xóa", "Xoá", "Chuyển", "Delete", "Move"]
# Dấu hiệu bài đã biến mất khi mở lại permalink (verify sau khi xoá).
POST_GONE_MARKERS = [
    "không tìm thấy", "nội dung không khả dụng", "bài viết không khả dụng",
    "content isn't available", "this content isn't available",
    "bạn hiện không xem được nội dung này",
]

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

# JS bóc danh sách nhóm từ trang "Nhóm của bạn". Chỉ ĐỌC href, không click.
# DOM Facebook là đầu vào không tin cậy: trả mảng rỗng khi không khớp gì để
# nhánh gọi fail an toàn, không bao giờ ném lỗi.
EXTRACT_GROUPS_JS = r"""() => {
    const RESERVED = new Set([
        'joins','feed','discover','create','category','search','browse',
        'pending','requests','activity','notifications',
        'your-groups-and-communities'
    ]);
    const found = {};
    for (const a of document.querySelectorAll('a[href*="/groups/"]')) {
        const href = a.getAttribute('href') || '';
        const m = href.match(/^(?:https?:\/\/[^/]+)?\/groups\/([^/?#]+)\/?(?:[?#].*)?$/);
        if (!m) continue;
        const key = m[1];
        if (!key || RESERVED.has(key)) continue;
        let name = (a.textContent || '').replace(/\s+/g, ' ').trim();
        // textContent nối luôn cả metadata "Lần hoạt động gần nhất: ..." /
        // "Bạn và N người bạn khác..." — cắt bỏ để lấy đúng tên nhóm
        // (xác nhận DOM trang /groups/joins/ thật 2026-09-10).
        name = name.split(/Lần hoạt động|Last active|Bạn và |You and |·/)[0].trim();
        if (name.length > 120) name = name.slice(0, 120).trim();
        if (!(key in found) || (!found[key] && name)) found[key] = name;
    }
    return Object.keys(found).map(k => ({
        key: k,
        name: found[k] || k,
        url: 'https://www.facebook.com/groups/' + k + '/',
    }));
}"""

# JS tìm lại permalink của bài VỪA ĐĂNG trong feed nhóm, khớp theo một lát text.
# Nhận [textFragment]: chuỗi ~40-80 ký tự lấy từ nội dung bài. Trả về permalink
# sạch hoặc '' nếu không tìm thấy (nhánh gọi coi đó là published_no_url).
EXTRACT_LATEST_POST_JS = r"""([textFragment]) => {
    const clean = (s) => (s || '').replace(/\s+/g, ' ').trim().toLowerCase();
    const needle = clean(textFragment);
    if (!needle || needle.length < 12) return '';

    const cleanLink = (href) => {
        if (!href) return '';
        let m = href.match(/\/groups\/(\d+)\/(?:posts|permalink)\/(\d+)/);
        if (m) return 'https://www.facebook.com/groups/' + m[1] + '/posts/' + m[2] + '/';
        m = href.match(/facebook\.com\/[^\/]+\/(?:posts|permalink)\/(\d+)/);
        if (m && !href.includes('/photo')) {
            try { const u = new URL(href, location.origin); return u.origin + u.pathname; } catch (e) {}
        }
        return '';
    };

    const nodes = document.querySelectorAll('[role="feed"] > *');
    for (const el of nodes) {
        const body = clean(el.textContent || '');
        if (!body.includes(needle)) continue;
        for (const a of el.querySelectorAll('a[href]')) {
            const c = cleanLink(a.getAttribute('href') || a.href || '');
            if (c) return c;
        }
    }
    return '';
}"""

# JS bóc comment đã render trên trang permalink. Chỉ nhận comment có link chứa
# ``comment_id``; nếu Facebook đổi DOM và không tìm được tín hiệu này thì trả
# mảng rỗng, không tự đoán tác giả/nội dung để tránh tạo lead giả.
EXTRACT_COMMENTS_JS = r"""([postUrl, limit]) => {
    const clean = (s) => (s || '').replace(/\s+/g, ' ').trim();
    const ignored = new Set([
        'Thích', 'Bày tỏ cảm xúc', 'Trả lời', 'Chia sẻ', 'Like', 'Reply', 'Share',
        'Viết bình luận...', 'Write a comment...'
    ]);
    const result = [];
    const seen = new Set();
    const links = [...document.querySelectorAll('a[href*="comment_id="]')];
    for (const link of links) {
        if (result.length >= limit) break;
        const href = link.href || link.getAttribute('href') || '';
        let parsed;
        try { parsed = new URL(href, location.origin); } catch (e) { continue; }
        const commentId = parsed.searchParams.get('comment_id') || '';
        if (!commentId || seen.has(commentId)) continue;
        let box = link;
        let text = '';
        let author = '';
        let authorId = '';
        let commentedAt = '';
        for (let depth = 0; depth < 10 && box; depth += 1, box = box.parentElement) {
            const candidates = [...box.querySelectorAll('[dir="auto"]')]
                .filter((node) => !node.closest('a[href*="/user/"], a[href*="profile.php"]'))
                .map((node) => clean(node.textContent))
                .filter((value) => value.length >= 2 && value.length <= 10000 && !ignored.has(value))
                .filter((value) => !/^\d+\s*(gi[oờ]|ph[uú]t|ng[aà]y|h|m|d|w)$/i.test(value));
            if (candidates.length) text = candidates.sort((a, b) => a.length - b.length)[0];
            const authorLink = [...box.querySelectorAll('a[href*="/user/"], a[href*="profile.php"]')]
                .find((a) => clean(a.textContent).length > 1);
            if (authorLink) {
                author = clean(authorLink.textContent);
                const authorHref = authorLink.getAttribute('href') || '';
                const idMatch = authorHref.match(/[?&]id=(\d+)/) || authorHref.match(/\/user\/(\d+)/);
                authorId = idMatch ? idMatch[1] : '';
            }
            const time = box.querySelector('time[datetime], abbr[title]');
            if (time) commentedAt = time.getAttribute('datetime') || time.getAttribute('title') || '';
            if (text && author) break;
        }
        // Không nhận timestamp/tên rời rạc khi DOM chưa expose author.
        if (!text || (!author && text.length < 8)) continue;
        seen.add(commentId);
        result.push({
            id: commentId, text, author, authorId, url: postUrl || '',
            commentUrl: (postUrl || '').split('#')[0].split('?')[0] + '?comment_id=' + encodeURIComponent(commentId),
            commentedAt,
        });
    }
    return result;
}"""
