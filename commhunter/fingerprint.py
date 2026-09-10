"""
Fingerprint — Sinh vân tay trình duyệt ỔN ĐỊNH theo từng nick clone.

Vấn đề: BrowserManager cũ chỉ random User-Agent mỗi lần khởi động. UA đổi
xoành xoạch trong khi canvas / WebGL / hardwareConcurrency vẫn y hệt nhau
giữa mọi nick → còn dễ lộ hơn để nguyên. Facebook so khớp các tín hiệu này
với nhau và với lịch sử của tài khoản.

Giải pháp: mỗi profile_dir có MỘT vân tay cố định, sinh xác định từ seed
(đường dẫn profile), lưu ra `<profile_dir>/fingerprint.json` và tái dùng mãi.
Các hàm ở đây THUẦN (không đụng Playwright) nên test offline được.
"""
import hashlib
import json
import random
from pathlib import Path
from typing import Optional

from constants import (
    LOCALE,
    TIMEZONE,
    FP_DEVICE_MEMORY_POOL,
    FP_HARDWARE_CONCURRENCY_POOL,
    FP_LANGUAGES,
    FP_SCREEN_SIZES,
    FP_WEBGL_PAIRS,
    FP_WINDOWS_UA_POOL,
)

FINGERPRINT_FILENAME = "fingerprint.json"
# Tăng khi đổi cấu trúc vân tay để buộc sinh lại — nhưng cân nhắc: đổi vân tay
# của một nick đang chạy cũng là một tín hiệu bất thường với Facebook.
FINGERPRINT_VERSION = 1


def _seeded_rng(seed: str) -> random.Random:
    """RNG xác định từ chuỗi seed (đường dẫn profile)."""
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return random.Random(int(digest[:16], 16))


def generate_fingerprint(seed: str) -> dict:
    """Sinh vân tay xác định từ seed. Cùng seed → cùng vân tay, mãi mãi.

    Chỉ dùng cho persistent context (nick clone). Chế độ attach vào Chrome
    thật KHÔNG spoof gì cả.
    """
    rng = _seeded_rng(seed)

    ua = rng.choice(FP_WINDOWS_UA_POOL)
    webgl_vendor, webgl_renderer = rng.choice(FP_WEBGL_PAIRS)
    screen_w, screen_h = rng.choice(FP_SCREEN_SIZES)

    # Viewport nhỏ hơn screen một chút (thanh tab + taskbar), số chẵn.
    inner_w = screen_w - rng.choice([0, 0, 16])
    inner_h = screen_h - rng.choice([79, 87, 105, 121])

    return {
        "version": FINGERPRINT_VERSION,
        "seed": seed,
        "user_agent": ua,
        "platform": "Win32",
        "hardware_concurrency": rng.choice(FP_HARDWARE_CONCURRENCY_POOL),
        "device_memory": rng.choice(FP_DEVICE_MEMORY_POOL),
        "languages": list(FP_LANGUAGES),
        "locale": LOCALE,
        "timezone": TIMEZONE,
        "viewport": {"width": inner_w, "height": inner_h},
        "screen": {"width": screen_w, "height": screen_h},
        "webgl_vendor": webgl_vendor,
        "webgl_renderer": webgl_renderer,
        # Nhiễu canvas: 3 số nguyên nhỏ, cố định theo nick.
        "canvas_noise": [rng.randint(-4, 4) for _ in range(3)],
    }


def read_fingerprint(profile_dir: str) -> Optional[dict]:
    """Đọc vân tay đã lưu, KHÔNG tạo mới. None nếu chưa có / hỏng.

    Dùng cho lệnh `status` (chỉ đọc) để không rải fingerprint.json vào các
    profile chưa đăng nhập.
    """
    path = Path(profile_dir) / FINGERPRINT_FILENAME
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if data.get("version") == FINGERPRINT_VERSION and data.get("user_agent"):
        return data
    return None


def load_or_create_fingerprint(profile_dir: str) -> dict:
    """Đọc vân tay đã lưu; nếu chưa có / sai version thì sinh mới và ghi lại."""
    path = Path(profile_dir) / FINGERPRINT_FILENAME
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("version") == FINGERPRINT_VERSION and data.get("user_agent"):
                return data
        except (json.JSONDecodeError, OSError):
            pass

    fp = generate_fingerprint(str(Path(profile_dir).resolve()))
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(fp, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass
    return fp


def build_stealth_init_js(fp: dict) -> str:
    """Dựng đoạn JS chèn vào `context.add_init_script` — chạy TRƯỚC mọi script
    của trang, trên mọi frame, kể cả các page mở sau này.

    Nhất quán hoá: navigator.*, screen.*, WebGL getParameter, nhiễu canvas.
    playwright-stealth lo phần navigator.webdriver / chrome.runtime; ở đây
    chỉ bù những gì stealth không chạm và neo chúng theo từng nick.
    """
    payload = {
        "platform": fp["platform"],
        "hardwareConcurrency": fp["hardware_concurrency"],
        "deviceMemory": fp["device_memory"],
        "languages": fp["languages"],
        "screenW": fp["screen"]["width"],
        "screenH": fp["screen"]["height"],
        "webglVendor": fp["webgl_vendor"],
        "webglRenderer": fp["webgl_renderer"],
        "canvasNoise": fp["canvas_noise"],
    }
    cfg_json = json.dumps(payload)

    return (
        "(() => {\n"
        f"  const FP = {cfg_json};\n"
        "  const def = (obj, prop, value) => {\n"
        "    try { Object.defineProperty(obj, prop, { get: () => value, configurable: true }); }\n"
        "    catch (e) {}\n"
        "  };\n"
        "\n"
        "  // --- navigator ---\n"
        "  def(navigator, 'platform', FP.platform);\n"
        "  def(navigator, 'hardwareConcurrency', FP.hardwareConcurrency);\n"
        "  def(navigator, 'deviceMemory', FP.deviceMemory);\n"
        "  def(navigator, 'languages', Object.freeze(FP.languages.slice()));\n"
        "  try { def(navigator, 'webdriver', false); } catch (e) {}\n"
        "\n"
        "  // --- screen (neo theo nick, tránh lệch giữa các phiên) ---\n"
        "  def(screen, 'width', FP.screenW);\n"
        "  def(screen, 'height', FP.screenH);\n"
        "  def(screen, 'availWidth', FP.screenW);\n"
        "  def(screen, 'availHeight', FP.screenH - 40);\n"
        "  def(screen, 'colorDepth', 24);\n"
        "  def(screen, 'pixelDepth', 24);\n"
        "\n"
        "  // --- WebGL: vendor / renderer không che dấu ---\n"
        "  const patchGL = (proto) => {\n"
        "    if (!proto) return;\n"
        "    const orig = proto.getParameter;\n"
        "    proto.getParameter = function (p) {\n"
        "      if (p === 37445) return FP.webglVendor;\n"
        "      if (p === 37446) return FP.webglRenderer;\n"
        "      return orig.call(this, p);\n"
        "    };\n"
        "  };\n"
        "  try { patchGL(window.WebGLRenderingContext && WebGLRenderingContext.prototype); } catch (e) {}\n"
        "  try { patchGL(window.WebGL2RenderingContext && WebGL2RenderingContext.prototype); } catch (e) {}\n"
        "\n"
        "  // --- Nhiễu canvas: xê dịch vài pixel cố định theo nick ---\n"
        "  const n = FP.canvasNoise;\n"
        "  const jitter = (data) => {\n"
        "    for (let i = 0; i < data.length; i += 4) {\n"
        "      data[i]     = Math.min(255, Math.max(0, data[i]     + n[0]));\n"
        "      data[i + 1] = Math.min(255, Math.max(0, data[i + 1] + n[1]));\n"
        "      data[i + 2] = Math.min(255, Math.max(0, data[i + 2] + n[2]));\n"
        "    }\n"
        "    return data;\n"
        "  };\n"
        "  try {\n"
        "    const origGetImageData = CanvasRenderingContext2D.prototype.getImageData;\n"
        "    CanvasRenderingContext2D.prototype.getImageData = function (...args) {\n"
        "      const res = origGetImageData.apply(this, args);\n"
        "      jitter(res.data);\n"
        "      return res;\n"
        "    };\n"
        "  } catch (e) {}\n"
        "  try {\n"
        "    const origToDataURL = HTMLCanvasElement.prototype.toDataURL;\n"
        "    HTMLCanvasElement.prototype.toDataURL = function (...args) {\n"
        "      try {\n"
        "        const ctx = this.getContext('2d');\n"
        "        if (ctx && this.width && this.height) {\n"
        "          const img = ctx.getImageData(0, 0, this.width, this.height);\n"
        "          ctx.putImageData(img, 0, 0);\n"
        "        }\n"
        "      } catch (e) {}\n"
        "      return origToDataURL.apply(this, args);\n"
        "    };\n"
        "  } catch (e) {}\n"
        "})();"
    )


def describe_fingerprint(fp: Optional[dict]) -> str:
    """Một dòng tóm tắt cho lệnh `status`."""
    if not fp:
        return "chưa có"
    gpu = fp.get("webgl_renderer", "?")
    # Rút gọn chuỗi ANGLE(...) dài dòng
    if "," in gpu:
        gpu = gpu.split(",")[1].strip() if len(gpu.split(",")) > 1 else gpu
    return (
        f"{fp.get('hardware_concurrency', '?')} core / "
        f"{fp.get('device_memory', '?')}GB / {gpu} / "
        f"{fp.get('viewport', {}).get('width', '?')}x{fp.get('viewport', {}).get('height', '?')}"
    )
