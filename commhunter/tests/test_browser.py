# -*- coding: utf-8 -*-
"""
Test cho lớp trình duyệt mới: fingerprint theo nick + channel=chrome + attach CDP.

Chạy:
    python tests/test_browser.py            # phần thuần, luôn chạy
    python tests/test_browser.py --live     # thêm phần mở Chrome thật kiểm chứng

Phần --live cần Google Chrome đã cài; nó mở 1 persistent context tạm, kiểm
tra init script vân tay có ăn không, rồi xoá sạch profile tạm.
"""
import asyncio
import json
import shutil
import sys
import tempfile
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fingerprint import (  # noqa: E402
    build_stealth_init_js,
    describe_fingerprint,
    generate_fingerprint,
    load_or_create_fingerprint,
)
from config_loader import load_config  # noqa: E402
from models import BrowserConfig  # noqa: E402

ok = fail = 0


def check(label, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  PASS  {label}")
    else:
        fail += 1
        print(f"  FAIL  {label} {extra}")


print("\n=== 1. Fingerprint xác định theo seed ===")
fp_a1 = generate_fingerprint("F:/profiles/scout")
fp_a2 = generate_fingerprint("F:/profiles/scout")
fp_b = generate_fingerprint("F:/profiles/shooter")
check("cùng seed → cùng vân tay", fp_a1 == fp_a2)
check("seed khác → vân tay khác", fp_a1 != fp_b)
check("UA là Windows Chrome", "Windows NT 10.0" in fp_a1["user_agent"])
check("platform khớp UA", fp_a1["platform"] == "Win32")
check(
    "hardwareConcurrency hợp lệ",
    fp_a1["hardware_concurrency"] in (4, 6, 8, 12, 16),
)
check("viewport nhỏ hơn hoặc bằng screen", fp_a1["viewport"]["width"] <= fp_a1["screen"]["width"])
check("có 3 số nhiễu canvas", len(fp_a1["canvas_noise"]) == 3)

print("\n=== 2. Init script chứa đúng giá trị vân tay ===")
js = build_stealth_init_js(fp_a1)
check("là chuỗi JS không rỗng", isinstance(js, str) and len(js) > 200)
check("nhúng hardwareConcurrency", str(fp_a1["hardware_concurrency"]) in js)
check("nhúng webgl renderer", fp_a1["webgl_renderer"] in js)
check("patch getParameter 37445/37446", "37445" in js and "37446" in js)
check("override navigator.webdriver", "webdriver" in js)
check("có nhiễu canvas getImageData", "getImageData" in js)

print("\n=== 3. Persist fingerprint.json ===")
tmp = Path(tempfile.mkdtemp(prefix="fp_test_"))
try:
    fp1 = load_or_create_fingerprint(str(tmp))
    check("tạo file fingerprint.json", (tmp / "fingerprint.json").exists())
    fp2 = load_or_create_fingerprint(str(tmp))
    check("đọc lại ra đúng vân tay cũ", fp1 == fp2)
    saved = json.loads((tmp / "fingerprint.json").read_text(encoding="utf-8"))
    check("file có user_agent", bool(saved.get("user_agent")))
    check("describe_fingerprint trả chuỗi gọn", "core" in describe_fingerprint(fp1))
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("\n=== 4. Cấu hình browser + cdp_endpoint ===")
cfg_text = """
service: {name: t, specialties: t, strengths: t, landing_page_note: t}
groups:
  - {url: "https://www.facebook.com/groups/1", name: g1}
browser:
  channel: chrome
  headless: false
accounts:
  scout:   {cookie_file: c, profile_dir: data/browser_profiles/scout, cdp_endpoint: "http://localhost:9222"}
  shooter: {cookie_file: c, profile_dir: data/browser_profiles/shooter}
openai: {api_key: "sk-test-fake", model: gpt-4o-mini}
comment: {mode: full_auto}
"""
tmp_cfg = Path(tempfile.mktemp(suffix=".yaml"))
tmp_cfg.write_text(cfg_text, encoding="utf-8")
try:
    cfg = load_config(str(tmp_cfg))
    check("browser.channel = chrome", cfg.browser.channel == "chrome")
    check("browser.headless = False", cfg.browser.headless is False)
    check("scout.cdp_endpoint parse đúng", cfg.accounts["scout"].cdp_endpoint == "http://localhost:9222")
    check("shooter.cdp_endpoint = None", cfg.accounts["shooter"].cdp_endpoint is None)
    check("BrowserConfig mặc định channel=chrome", BrowserConfig().channel == "chrome")
finally:
    tmp_cfg.unlink(missing_ok=True)

print("\n=== 5. find_config_problems chấp nhận attach dùng chung ===")
import commhunter as ch  # noqa: E402

cfg2 = load_config(str(ROOT / "configs" / "example.yaml"))
cfg2.accounts["scout"].cdp_endpoint = "http://localhost:9222"
cfg2.accounts["shooter"].cdp_endpoint = "http://localhost:9222"
cfg2.accounts["scout"].profile_dir = ""
cfg2.accounts["shooter"].profile_dir = ""
probs = ch.find_config_problems(cfg2)
check("không báo lỗi profile_dir trống khi có cdp", not any("profile_dir" in p for p in probs), probs)


async def _live():
    global ok, fail
    print("\n=== LIVE. Mở Chrome thật kiểm chứng init script ===")
    from browser_manager import BrowserManager
    from models import AppConfig

    tmpdir = Path(tempfile.mkdtemp(prefix="live_profile_"))
    mgr = BrowserManager(AppConfig())  # channel=chrome, headless=False mặc định
    try:
        ctx = await mgr.create_stealth_context(
            profile_dir=str(tmpdir), headless=True
        )
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await page.goto("about:blank")
        fp = load_or_create_fingerprint(str(tmpdir))

        hc = await page.evaluate("navigator.hardwareConcurrency")
        check("LIVE navigator.hardwareConcurrency khớp vân tay", hc == fp["hardware_concurrency"], f"{hc} vs {fp['hardware_concurrency']}")

        plat = await page.evaluate("navigator.platform")
        check("LIVE navigator.platform = Win32", plat == "Win32", plat)

        wd = await page.evaluate("navigator.webdriver")
        check("LIVE navigator.webdriver falsy", not wd, wd)

        gpu = await page.evaluate(
            """() => {
                const c = document.createElement('canvas');
                const gl = c.getContext('webgl') || c.getContext('experimental-webgl');
                if (!gl) return null;
                return gl.getParameter(37446);
            }"""
        )
        check("LIVE WebGL renderer bị spoof theo vân tay", gpu == fp["webgl_renderer"], f"{gpu}")

        langs = await page.evaluate("navigator.languages.join(',')")
        check("LIVE navigator.languages có vi-VN", "vi-VN" in langs, langs)
    finally:
        await mgr.close_all()
        shutil.rmtree(tmpdir, ignore_errors=True)


if "--live" in sys.argv:
    asyncio.run(_live())

print("\n" + "=" * 50)
print(f"KET QUA: {ok} PASS / {fail} FAIL")
print("=" * 50)
sys.exit(1 if fail else 0)
