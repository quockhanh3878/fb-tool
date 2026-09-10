# -*- coding: utf-8 -*-
"""
Bộ test API + service của backend — chạy OFFLINE hoàn toàn.

Không cần Docker, PostgreSQL, Redis, OpenAI hay Facebook: dùng SQLite tạm
và httpx ASGITransport gọi thẳng vào app.

Chạy:
    python tests/test_api.py
"""
import asyncio
import os
import random
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

DB_FILE = Path(tempfile.mkdtemp()) / "test_api.db"
os.environ.update(
    DATABASE_URL=f"sqlite+aiosqlite:///{DB_FILE.as_posix()}",
    JWT_SECRET="test-secret-key-only-for-offline-test",
    COOKIE_ENCRYPTION_KEY="",
    TELEGRAM_BOT_TOKEN="",
    OPENAI_API_KEY="",
    AUTH_RATE_LIMIT_PER_MINUTE="100",
)

import httpx  # noqa: E402
from httpx import ASGITransport  # noqa: E402

from app.database import init_models  # noqa: E402
from app.main import app  # noqa: E402

ok = fail = 0


def check(label: str, condition: bool, extra: str = "") -> None:
    global ok, fail
    if condition:
        ok += 1
        print(f"  PASS  {label}")
    else:
        fail += 1
        print(f"  FAIL  {label} {extra}")


def section(title: str) -> None:
    print(f"\n=== {title} ===")


async def main() -> None:
    await init_models()
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await run_api_tests(client)


async def run_api_tests(client: httpx.AsyncClient) -> None:
    # ── 1. Health & Auth ────────────────────────────────────────────────
    section("1. Health & Auth")
    resp = await client.get("/health")
    check("GET /health tra ve ok", resp.status_code == 200 and resp.json()["status"] == "ok")

    resp = await client.post(
        "/api/auth/register",
        json={"email": "khach1@test.vn", "password": "matkhau123", "display_name": "Khach 1"},
    )
    check("Dang ky tai khoan moi", resp.status_code == 201, resp.text[:200])
    tokens = resp.json()
    access = tokens["access_token"]
    auth = {"Authorization": f"Bearer {access}"}

    resp = await client.post(
        "/api/auth/register", json={"email": "khach1@test.vn", "password": "matkhau123"}
    )
    check("Dang ky trung email bi tu choi 409", resp.status_code == 409)

    resp = await client.post(
        "/api/auth/register", json={"email": "yeu@test.vn", "password": "123"}
    )
    check("Mat khau qua ngan bi tu choi 422", resp.status_code == 422)

    resp = await client.post(
        "/api/auth/login", json={"email": "khach1@test.vn", "password": "sai-mat-khau"}
    )
    check("Dang nhap sai mat khau -> 401", resp.status_code == 401)

    resp = await client.post(
        "/api/auth/login", json={"email": "khach1@test.vn", "password": "matkhau123"}
    )
    check("Dang nhap dung -> 200 + token", resp.status_code == 200 and "access_token" in resp.json())

    resp = await client.get("/api/auth/me")
    check("Endpoint private khong token -> 401", resp.status_code == 401)

    resp = await client.get("/api/auth/me", headers={"Authorization": "Bearer rac"})
    check("Token rac -> 401", resp.status_code == 401)

    resp = await client.get("/api/auth/me", headers=auth)
    me = resp.json()
    check("GET /me tra ve dung email", resp.status_code == 200 and me["email"] == "khach1@test.vn")
    check("Tai khoan moi duoc cap goi starter", me["subscription"]["plan"] == "starter")

    resp = await client.post(
        "/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    check("Refresh token cap access token moi", resp.status_code == 200)

    resp = await client.post("/api/auth/refresh", json={"refresh_token": access})
    check("Dung access token de refresh -> 401 (sai loai token)", resp.status_code == 401)

    # ── 2. Campaign CRUD ────────────────────────────────────────────────
    section("2. Campaign CRUD")
    resp = await client.post(
        "/api/campaigns",
        headers=auth,
        json={
            "name": "San comm viet truyen",
            "mode": "semi_auto",
            "service_name": "Nyatymita Writing",
            "service_specialties": "Ngon tinh, co trang",
            "ai_filter_prompt": "Chi lay bai tim nguoi viet truyen co ngan sach",
            "whitelist_keywords": ["tim comm", "can viet"],
            "blacklist_keywords": ["da tim duoc"],
            "max_comments_per_day": 20,
        },
    )
    check("Tao chien dich", resp.status_code == 201, resp.text[:200])
    campaign = resp.json()
    cid = campaign["id"]

    resp = await client.post(
        "/api/campaigns",
        headers=auth,
        json={"name": "Delay nguoc", "delay_min_seconds": 900, "delay_max_seconds": 300},
    )
    check("delay_max < delay_min bi chan 422", resp.status_code == 422)

    resp = await client.get("/api/campaigns", headers=auth)
    check("Liet ke chien dich", resp.status_code == 200 and len(resp.json()) == 1)

    resp = await client.put(
        f"/api/campaigns/{cid}", headers=auth, json={"min_relevance_score": 0.8}
    )
    check("Cap nhat chien dich", resp.status_code == 200 and resp.json()["min_relevance_score"] == 0.8)

    resp = await client.post(f"/api/campaigns/{cid}/activate", headers=auth)
    check("Bat chien dich khi chua co group -> 422", resp.status_code == 422)

    # ── 3. Group + kiem tra URL ─────────────────────────────────────────
    section("3. Group & validate URL")
    resp = await client.post(
        f"/api/campaigns/{cid}/groups",
        headers=auth,
        json={"group_url": "https://www.facebook.com/groups/hoiyeutieuthuyet/", "group_name": "Hoi Yeu Tieu Thuyet"},
    )
    check("Them group hop le", resp.status_code == 201, resp.text[:200])
    group = resp.json()
    gid = group["id"]
    check("Group_key duoc chuan hoa", group["group_key"] == "hoiyeutieuthuyet")

    resp = await client.post(
        f"/api/campaigns/{cid}/groups",
        headers=auth,
        json={"group_url": "https://m.facebook.com/groups/hoiyeutieuthuyet/posts/999/"},
    )
    check("Them group trung (khac URL, cung key) -> 409", resp.status_code == 409)

    resp = await client.post(
        f"/api/campaigns/{cid}/groups", headers=auth, json={"group_url": "https://google.com/abc"}
    )
    check("URL khong phai Facebook -> 422", resp.status_code == 422)

    resp = await client.post(f"/api/campaigns/{cid}/activate", headers=auth)
    check("Bat chien dich khi da co group", resp.status_code == 200 and resp.json()["is_active"])

    # ── 4. Han muc goi cuoc ─────────────────────────────────────────────
    section("4. Han muc goi cuoc (Starter = 5 group)")
    for index in range(4):
        await client.post(
            f"/api/campaigns/{cid}/groups",
            headers=auth,
            json={"group_url": f"https://www.facebook.com/groups/nhomtest{index}/"},
        )
    resp = await client.post(
        f"/api/campaigns/{cid}/groups",
        headers=auth,
        json={"group_url": "https://www.facebook.com/groups/vuotquota/"},
    )
    check("Group thu 6 vuot quota Starter -> 403", resp.status_code == 403, resp.text[:200])

    resp = await client.get("/api/billing/usage", headers=auth)
    usage = resp.json()
    check("Usage bao dung 5/5 group", usage["groups_used"] == 5 and usage["groups_limit"] == 5)

    resp = await client.post(
        "/api/billing/confirm", headers=auth, json={"plan": "pro", "months": 1}
    )
    check("Nang cap len Pro", resp.status_code == 200 and resp.json()["plan"] == "pro")

    resp = await client.post(
        f"/api/campaigns/{cid}/groups",
        headers=auth,
        json={"group_url": "https://www.facebook.com/groups/saukhinangcap/"},
    )
    check("Sau khi nang Pro, them group thanh cong", resp.status_code == 201)

    # ── 5. Script Studio ────────────────────────────────────────────────
    section("5. Script Studio (spintax)")
    resp = await client.post(
        f"/api/campaigns/{cid}/scripts",
        headers=auth,
        json={
            "name": "Kich ban chao hang",
            "type": "spintax",
            "template_content": "{Chao ban|Hi ban}, minh {nhan viet|lam} the loai nay nhe, ban inbox minh de xem mau va bao gia cu the nha",
            "is_default": True,
        },
    )
    check("Tao kich ban spintax", resp.status_code == 201, resp.text[:200])
    sid = resp.json()["id"]

    resp = await client.post(
        f"/api/campaigns/{cid}/scripts/{sid}/preview?count=3", headers=auth
    )
    preview = resp.json()
    check("Preview sinh bien the", resp.status_code == 200 and len(preview["variants"]) >= 1)
    check("Dem duoc tong so bien the (2x2=4)", preview["total_variants"] == 4)


    # ── 5b. Script Studio: soi mau, liet ke bien the, xoay vong ─────────
    section("5b. Soi mau spintax & xoay vong kich ban")

    resp = await client.post(
        f"/api/campaigns/{cid}/scripts/lint",
        headers=auth,
        json={"template_content": "{Chao ban|Hi ban}, minh {nhan viet|lam} the loai nay nhe, ban inbox minh de xem mau va bao gia cu the nha"},
    )
    report = resp.json()
    check("Soi mau chua luu -> 200", resp.status_code == 200, resp.text[:200])
    check("Mau tot -> ok=True", report["ok"] is True, str(report["issues"]))
    check("Dem dung 2 nhom xoay", report["group_count"] == 2)
    check("Dem dung 4 bien the", report["total_variants"] == 4)
    check("Bao so ngay chay khong lap (4 bien the / 20 mot ngay)", report["days_without_repeat"] == 0.2)

    resp = await client.post(
        f"/api/campaigns/{cid}/scripts/lint",
        headers=auth,
        json={"template_content": "{Chao ban|Chao ban} minh nhan viet truyen ngon tinh co trang nhe ban oi"},
    )
    report = resp.json()
    messages = " ".join(i["message"] for i in report["issues"])
    check("Phat hien lua chon trung trong cung nhom", "lặp lại" in messages, messages[:120])

    resp = await client.post(
        f"/api/campaigns/{cid}/scripts/lint",
        headers=auth,
        json={"template_content": "{Chao ban|Hi ban thieu ngoac dong"},
    )
    report = resp.json()
    check("Phat hien ngoac lech -> ok=False", report["ok"] is False)
    check("Bao dung loi ngoac lech", "Ngoặc lệch" in report["issues"][0]["message"])

    resp = await client.post(
        f"/api/campaigns/{cid}/scripts/lint",
        headers=auth,
        json={"template_content": "Ghe xem portfolio cua minh tai nyatymita.com nhe ban oi, gia rat tot"},
    )
    report = resp.json()
    messages = " ".join(i["message"] for i in report["issues"])
    check("Soi mau bat duoc link", report["ok"] is False and "link" in messages)
    check("Soi mau canh bao khong co nhom xoay", "chưa có nhóm xoay" in messages)

    resp = await client.post(
        f"/api/campaigns/{cid}/scripts/lint",
        headers=auth,
        json={"template_content": "{a|b} ngan"},
    )
    report = resp.json()
    check(
        "Soi mau bat duoc bien the qua ngan",
        report["ok"] is False and any("quá " in i["message"] or "quá " in i["message"] for i in report["issues"]),
        str(report["issues"]),
    )

    resp = await client.post(f"/api/campaigns/{cid}/scripts/{sid}/expand", headers=auth)
    expand = resp.json()
    check("Liet ke toan bo bien the", resp.status_code == 200 and len(expand["variants"]) == 4)
    check("Cac bien the khong trung nhau", len(set(expand["variants"])) == 4)
    check("Mau nho -> khong bi cat bot", expand["truncated"] is False)

    # Kich ban thu hai de kiem tra vong xoay
    resp = await client.post(
        f"/api/campaigns/{cid}/scripts",
        headers=auth,
        json={
            "name": "Kich ban 2",
            "type": "spintax",
            "template_content": "{Minh cung nhan|Ben minh nhan} viet the loai nay ban nhe, ban nhan tin rieng cho minh de trao doi ky hon",
        },
    )
    sid2 = resp.json()["id"]
    check("Tao kich ban thu hai", resp.status_code == 201)
    check("Kich ban moi mac dinh dang bat", resp.json()["is_active"] is True)
    check("Kich ban moi chua duoc dung lan nao", resp.json()["usage_count"] == 0)

    resp = await client.put(
        f"/api/campaigns/{cid}/scripts/{sid2}", headers=auth, json={"is_active": False}
    )
    check("Tat tam mot kich ban ma khong xoa", resp.json()["is_active"] is False)
    resp = await client.put(
        f"/api/campaigns/{cid}/scripts/{sid2}", headers=auth, json={"is_active": True}
    )
    check("Bat lai kich ban", resp.json()["is_active"] is True)

    # ── 6. Clone + cookie ───────────────────────────────────────────────
    section("6. Clone & cookie")
    resp = await client.post(
        "/api/clones",
        headers=auth,
        json={"display_name": "Clone Shooter 1", "role": "shooter", "daily_comment_limit": 20},
    )
    check("Tao clone", resp.status_code == 201, resp.text[:200])
    clone = resp.json()
    clone_id = clone["id"]
    check("Clone moi o trang thai onboarding", clone["status"] == "onboarding")

    bad_cookie = b'[{"name":"abc","value":"1","domain":".facebook.com"}]'
    resp = await client.post(
        f"/api/clones/{clone_id}/upload-cookie",
        headers=auth,
        files={"file": ("cookies.json", bad_cookie, "application/json")},
    )
    check("Cookie thieu c_user/xs bi tu choi 422", resp.status_code == 422)

    good_cookie = (
        b'[{"name":"c_user","value":"100012345","domain":".facebook.com","path":"/"},'
        b'{"name":"xs","value":"abc:xyz","domain":".facebook.com","path":"/"},'
        b'{"name":"ads_id","value":"zzz","domain":".doubleclick.net","path":"/"}]'
    )
    resp = await client.post(
        f"/api/clones/{clone_id}/upload-cookie",
        headers=auth,
        files={"file": ("cookies.json", good_cookie, "application/json")},
    )
    body = resp.json()
    check("Upload cookie hop le", resp.status_code == 200, resp.text[:200])
    check("Chi giu cookie mien facebook (2/3)", body["cookie_count"] == 2)
    check("Rut duoc fb_user_id", body["fb_user_id"] == "100012345")
    check("Cookie hop le -> clone chuyen sang warming_up", body["status"] == "warming_up")

    resp = await client.get(f"/api/clones/{clone_id}/health", headers=auth)
    check("Health clone co tien trinh warmup 7 ngay", resp.json()["warmup"]["total_days"] == 7)

    resp = await client.post(
        f"/api/clones/{clone_id}/transition",
        headers=auth,
        json={"event": "warmup_complete", "details": "test"},
    )
    check("Chuyen warmup_complete -> active", resp.status_code == 200 and resp.json()["status"] == "active")

    resp = await client.post(
        f"/api/clones/{clone_id}/transition",
        headers=auth,
        json={"event": "warmup_complete"},
    )
    check("Chuyen trang thai bat hop le -> 409", resp.status_code == 409)


    # ── 6b. Kiem tra tai khoan & chan doan ──────────────────────────────
    section("6b. Kiem tra tai khoan & chan doan")
    from app.database import get_session_factory
    from app.models.clone_account import CloneAccount as _CloneRow
    from app.services.crypto import encrypt_cookies as _encrypt

    resp = await client.get(f"/api/clones/{clone_id}/diagnose", headers=auth)
    diag = resp.json()
    check("Chan doan clone tra ve phieu day du", resp.status_code == 200, resp.text[:200])
    check(
        "Clone cookie tot -> khong co loi nghiem trong",
        not [i for i in diag["issues"] if i["severity"] == "critical"],
    )
    check("Clone active + cookie tot -> san sang nhan viec", diag["ready"] is True)
    check(
        "Chua gan proxy -> canh bao no_proxy",
        any(i["code"] == "no_proxy" for i in diag["issues"]),
    )
    check(
        "Chi co 1 clone -> canh bao khong co du phong",
        any(i["code"] == "no_backup" for i in diag["issues"]),
    )
    check("Diem suc khoe bi tru dung 20", diag["score"] == 80, str(diag["score"]))

    resp = await client.post(f"/api/clones/{clone_id}/check-session", headers=auth)
    body = resp.json()
    check("check-session tra ve chan doan", resp.status_code == 200 and "issues" in body)
    check("Cookie hop le -> clone van o active", body["status"] == "active")
    check("check-session xac nhan cookie dung duoc", body["cookie_ok"] is True)

    resp = await client.post("/api/clones/check-all", headers=auth)
    body = resp.json()
    check("Kiem tra tat ca clone", resp.status_code == 200, resp.text[:200])
    check("Bao cao du so clone", len(body["reports"]) == 1)
    check("Khong clone nao bi ha trang thai", body["transitioned"] == [])
    check("Tong quan dem duoc clone san sang", body["summary"]["ready_count"] == 1)
    check("Nang luc con lai = tran - da dung", body["summary"]["capacity_left"] == 20)

    # Cookie hong trong luc clone dang chay la tinh huong nguy hiem nhat:
    # scheduler van giao viec cho mot phien da chet. Phai ha trang thai NGAY.
    async with get_session_factory()() as probe:
        row = await probe.get(_CloneRow, clone_id)
        cookie_backup = row.cookie_data_encrypted
        row.cookie_data_encrypted = _encrypt(
            [
                {
                    "name": "c_user",
                    "value": "100012345",
                    "domain": ".facebook.com",
                    "path": "/",
                    "expires": -1,
                }
            ]
        )
        await probe.commit()

    resp = await client.post("/api/clones/check-all", headers=auth)
    body = resp.json()
    check(
        "Cookie thieu xs -> clone bi ha trang thai ngay",
        body["transitioned"] == ["Clone Shooter 1"],
        str(body["transitioned"]),
    )
    check("Clone hong -> khong con san sang", body["summary"]["ready_count"] == 0)
    check(
        "Chan doan goi dung ma loi cookie_broken",
        any(i["code"] == "cookie_broken" for i in body["reports"][0]["issues"]),
    )
    check("Loi nghiem trong keo diem xuong muc bad", body["summary"]["grade"] == "bad")

    async with get_session_factory()() as probe:
        row = await probe.get(_CloneRow, clone_id)
        row.cookie_data_encrypted = cookie_backup
        row.status = "active"
        await probe.commit()

    # ── 7. Pipeline: nop bai tu Scout ───────────────────────────────────
    section("7. Pipeline ingest (loc tu khoa -> AI -> thong bao)")
    posts_payload = {
        "group_id": gid,
        "posts": [
            {
                "author": "Nguyen Van A",
                "text": "Minh dang tim comm viet truyen ngon tinh, budget 500k, ai nhan inbox minh nhe. Can gap trong tuan nay.",
                "url": "https://www.facebook.com/groups/hoiyeutieuthuyet/posts/111/",
                "commentCount": 2,
            },
            {
                "author": "Tran Thi B",
                "text": "Bai nay minh da tim duoc nguoi roi nhe, cam on moi nguoi da quan tam den bai viet cua minh.",
                "url": "https://www.facebook.com/groups/hoiyeutieuthuyet/posts/222/",
                "commentCount": 1,
            },
            {
                "author": "Le Van C",
                "text": "Hom nay troi dep qua di moi nguoi oi, ai di choi khong cho minh theo voi nhe hehe.",
                "url": "https://www.facebook.com/groups/hoiyeutieuthuyet/posts/333/",
                "commentCount": 0,
            },
            {
                "author": "Pham Thi D",
                "text": "Can viet truyen dai tap, ngan sach thoa thuan, uu tien ban co kinh nghiem viet ngon tinh co trang.",
                "url": "https://www.facebook.com/groups/hoiyeutieuthuyet/posts/444/",
                "commentCount": 50,
            },
        ],
    }
    resp = await client.post(f"/api/campaigns/{cid}/ingest", headers=auth, json=posts_payload)
    stats = resp.json()
    check("Ingest 4 bai thanh cong", resp.status_code == 201, resp.text[:300])
    check("Luu 4 bai moi", stats["ingested"] == 4)
    check("1 bai phu hop duoc thong bao", stats["notified"] == 1, str(stats))
    check("3 bai bi loai (blacklist/khong tu khoa/qua dong)", stats["skipped"] == 3, str(stats))

    resp = await client.post(f"/api/campaigns/{cid}/ingest", headers=auth, json=posts_payload)
    check("Ingest lai cung du lieu -> 0 bai moi (dedup)", resp.json()["ingested"] == 0)

    resp = await client.get(f"/api/posts?campaign_id={cid}", headers=auth)
    feed = resp.json()
    check("Feed tra ve dung 4 bai", feed["total"] == 4)
    notified = [p for p in feed["items"] if p["status"] == "notified"]
    check("Bai duoc thong bao la bai cua Nguyen Van A", len(notified) == 1 and notified[0]["author_name"] == "Nguyen Van A")

    # ── 8. Ung tuyen & hang doi ─────────────────────────────────────────
    section("8. Ung tuyen thu cong & hang doi comment")
    post_id = notified[0]["id"]
    resp = await client.post(
        f"/api/posts/{post_id}/apply",
        headers=auth,
        json={"comment_text": "Chao ban, minh chuyen viet ngon tinh co trang da nhieu nam, ban xem thu vai mau minh ghim tren tuong nha minh nhe"},
    )
    check("Ung tuyen bang comment tu soan", resp.status_code == 200, resp.text[:200])
    action_id = resp.json()["id"]
    check("Luot comment o trang thai queued", resp.json()["status"] == "queued")

    resp = await client.post(
        f"/api/posts/{post_id}/apply",
        headers=auth,
        json={"comment_text": "Xem portfolio cua minh tai nyatymita.com nhe ban oi, gia ca hop ly lam"},
    )
    check("Comment chua link bi chan 422", resp.status_code == 422, resp.text[:150])

    resp = await client.get("/api/queue", headers=auth)
    check("Hang doi co 1 luot cho", resp.status_code == 200 and len(resp.json()) == 1)

    resp = await client.post(f"/api/queue/{action_id}/cancel", headers=auth)
    check("Huy luot trong hang doi", resp.status_code == 200 and resp.json()["status"] == "failed")

    resp = await client.post(f"/api/queue/{action_id}/cancel", headers=auth)
    check("Huy lai luot da huy -> 409", resp.status_code == 409)

    # ── 9. Thong ke ─────────────────────────────────────────────────────
    section("9. Thong ke dashboard")
    resp = await client.get("/api/stats/dashboard?days=7", headers=auth)
    dash = resp.json()
    check("Dashboard tra ve 200", resp.status_code == 200)
    check("Dem dung 4 bai hom nay", dash["posts_today"] == 4, str(dash))
    check("Dem dung 1 bai phu hop", dash["matched_today"] == 1)
    check("Xu huong co du 7 diem", len(dash["trend"]) == 7)
    check("Dem dung so group", dash["total_groups"] == 6)

    resp = await client.get("/api/stats/groups", headers=auth)
    check("Bao cao hieu qua group", resp.status_code == 200 and len(resp.json()) >= 1)

    resp = await client.get("/api/stats/status-breakdown", headers=auth)
    breakdown = resp.json()
    check("Phan bo trang thai bai viet", breakdown["skipped"] == 3 and breakdown["notified"] == 1)

    # ── 10. Cach ly nhieu khach (multi-tenant) ──────────────────────────
    section("10. Cach ly du lieu giua cac khach hang")
    resp = await client.post(
        "/api/auth/register", json={"email": "khach2@test.vn", "password": "matkhau456"}
    )
    auth2 = {"Authorization": f"Bearer {resp.json()['access_token']}"}

    resp = await client.get("/api/campaigns", headers=auth2)
    check("Khach 2 khong thay chien dich cua khach 1", resp.json() == [])

    resp = await client.get(f"/api/campaigns/{cid}", headers=auth2)
    check("Truy cap chien dich nguoi khac -> 404", resp.status_code == 404)

    resp = await client.get(f"/api/posts/{post_id}", headers=auth2)
    check("Truy cap bai viet nguoi khac -> 404", resp.status_code == 404)

    resp = await client.get(f"/api/clones/{clone_id}", headers=auth2)
    check("Truy cap clone nguoi khac -> 404", resp.status_code == 404)

    resp = await client.get("/api/stats/dashboard", headers=auth2)
    check("Thong ke khach 2 bang 0", resp.json()["posts_today"] == 0)

    # ── 11. Health monitor & proxy ──────────────────────────────────────
    section("11. Health monitor & proxy pool")
    resp = await client.get("/api/health/overview", headers=auth)
    check("Health overview liet ke clone", resp.status_code == 200 and len(resp.json()) == 1)

    resp = await client.get(f"/api/health/clone/{clone_id}/timeline", headers=auth)
    check("Timeline co su kien chuyen trang thai", resp.status_code == 200 and len(resp.json()) >= 2)

    resp = await client.post(
        "/api/health/proxies",
        headers=auth,
        json={"address": "socks5://user:pass@1.2.3.4:1080", "type": "residential"},
    )
    check("Them proxy vao pool", resp.status_code == 201, resp.text[:150])

    resp = await client.post(f"/api/health/proxies/assign/{clone_id}", headers=auth)
    check("Gan proxy cho clone", resp.status_code == 200 and resp.json()["status"] == "assigned")

    resp = await client.post(f"/api/health/proxies/rotate/{clone_id}?reason=test", headers=auth)
    check("Xoay proxy khi het pool -> 409", resp.status_code == 409, resp.text[:150])

    resp = await client.get("/api/health/proxies/overview", headers=auth)
    check("Tong quan pool proxy", resp.status_code == 200 and resp.json()["total"] == 1)


    # ── 11b. Tong quan suc khoe cap tai khoan ───────────────────────────
    section("11b. Tong quan suc khoe & canh bao")
    resp = await client.get("/api/health/summary", headers=auth)
    body = resp.json()
    check("Tong quan suc khoe", resp.status_code == 200, resp.text[:200])
    check("Dem dung so clone", body["clone_count"] == 1)
    check("Da gan proxy -> het canh bao no_proxy",
          all(i["code"] != "no_proxy" for i in body["top_issues"]))
    check("Van con canh bao thieu clone du phong",
          any(i["code"] == "no_backup" for i in body["top_issues"]))
    check("Co dem canh bao chua xu ly", isinstance(body["unacknowledged_alerts"], int))

    resp = await client.get("/api/health/diagnostics", headers=auth)
    check("Chan doan hang loat", resp.status_code == 200 and len(resp.json()) == 1)

    resp = await client.post("/api/health/alerts/ack-all", headers=auth)
    acked = resp.json()["acknowledged"]
    check("Danh dau da xu ly toan bo canh bao", resp.status_code == 200 and acked >= 1, str(acked))
    resp = await client.get("/api/health/alerts", headers=auth)
    check("Sau ack-all thi khong con canh bao treo", resp.json() == [])

    # ── 12. Bump (tinh nang goi Pro) ────────────────────────────────────
    section("12. Lich bump bai")
    resp = await client.post(
        f"/api/campaigns/{cid}/bumps",
        headers=auth,
        json={
            "target_post_url": "https://www.facebook.com/groups/hoiyeutieuthuyet/posts/111/",
            "cron_schedule": [8, 12, 20],
            "bump_messages": ["Up bai nhe moi nguoi", "{Up|Len} bai a"],
        },
    )
    check("Tao lich bump (goi Pro)", resp.status_code == 201, resp.text[:200])

    resp = await client.post(
        f"/api/campaigns/{cid}/bumps",
        headers=auth,
        json={"target_post_url": "https://facebook.com/x", "cron_schedule": [99], "bump_messages": ["a"]},
    )
    check("Khung gio 99 bi tu choi 422", resp.status_code == 422)

    resp = await client.get(f"/api/campaigns/{cid}/bumps", headers=auth)
    check("Liet ke lich bump", resp.status_code == 200 and len(resp.json()) == 1)

    # Khach 2 dang o goi Starter -> khong duoc dung bump
    resp = await client.post("/api/campaigns", headers=auth2, json={"name": "CD khach 2"})
    cid2 = resp.json()["id"]
    resp = await client.post(
        f"/api/campaigns/{cid2}/bumps",
        headers=auth2,
        json={"target_post_url": "https://facebook.com/x", "cron_schedule": [8], "bump_messages": ["a"]},
    )
    check("Goi Starter khong duoc dung Bump -> 403", resp.status_code == 403, resp.text[:150])

    # ── 13. Telegram webhook ────────────────────────────────────────────
    section("13. Telegram webhook")
    resp = await client.post("/api/auth/connect-telegram", headers=auth)
    link_code = resp.json()["link_code"]
    check("Sinh ma lien ket Telegram", resp.status_code == 200 and len(link_code) == 8)

    resp = await client.post(
        "/api/webhook/telegram",
        json={"message": {"chat": {"id": 555666777}, "text": f"/start {link_code}"}},
    )
    check("Webhook /start lien ket chat_id", resp.status_code == 200 and resp.json()["handled"] == "start")

    resp = await client.get("/api/auth/me", headers=auth)
    check("chat_id da duoc gan vao tai khoan", resp.json()["telegram_chat_id"] == "555666777")

    resp = await client.post(
        "/api/webhook/telegram",
        json={"message": {"chat": {"id": 999}, "text": "/start SAIMA00"}},
    )
    check("Ma lien ket sai khong gan nham", resp.status_code == 200)

    # Nut "Bo qua" tu chat da lien ket
    resp = await client.get(f"/api/posts?campaign_id={cid}&status=notified", headers=auth)
    target = resp.json()["items"][0]["id"] if resp.json()["items"] else post_id
    resp = await client.post(
        "/api/webhook/telegram",
        json={
            "callback_query": {
                "data": f"skip:{target}",
                "message": {"chat": {"id": 555666777}},
            }
        },
    )
    check("Callback skip duoc xu ly", resp.status_code == 200 and resp.json()["handled"] == "callback_query")

    resp = await client.get(f"/api/posts/{target}", headers=auth)
    check("Bai chuyen sang skipped sau khi bam Bo qua", resp.json()["status"] == "skipped")

    # Chat la khong duoc dieu khien bai cua nguoi khac
    resp = await client.post(
        "/api/webhook/telegram",
        json={"callback_query": {"data": f"skip:{target}", "message": {"chat": {"id": 111000}}}},
    )
    check("Chat chua lien ket khong thao tac duoc", resp.status_code == 200)

    # ── 14. Xoa tai nguyen ──────────────────────────────────────────────
    section("14. Xoa tai nguyen")
    resp = await client.delete(f"/api/campaigns/{cid}/groups/{gid}", headers=auth)
    check("Xoa group -> 204", resp.status_code == 204)

    resp = await client.delete(f"/api/clones/{clone_id}", headers=auth)
    check("Xoa clone -> 204", resp.status_code == 204)

    resp = await client.get("/api/clones", headers=auth)
    check("Danh sach clone rong sau khi xoa", resp.json() == [])

    resp = await client.delete(f"/api/campaigns/{cid}", headers=auth)
    check("Xoa chien dich -> 204", resp.status_code == 204)

    resp = await client.get(f"/api/posts?campaign_id={cid}", headers=auth)
    check("Xoa chien dich keo theo bai viet (cascade)", resp.json()["total"] == 0)

    # ── 14b. Multi-Role Clones & Post Publishing API ────────────────────
    section("14b. Multi-Role Clones & Post Publishing API")
    await client.post("/api/billing/confirm", headers=auth, json={"plan": "studio", "months": 1})

    resp = await client.post(
        "/api/clones",
        headers=auth,
        json={"display_name": "Clone Quet 1", "role": "scout", "notes": "Chuyen quet lead"},
    )
    check("Tao clone scout", resp.status_code == 201 and resp.json()["role"] == "scout")
    scout_id = resp.json()["id"]

    resp = await client.post(
        "/api/clones",
        headers=auth,
        json={"display_name": "Clone Ban 2", "role": "shooter", "notes": "Chuyen cmt"},
    )
    check("Tao clone shooter", resp.status_code == 201 and resp.json()["role"] == "shooter")
    shooter_id = resp.json()["id"]

    resp = await client.post(
        "/api/clones",
        headers=auth,
        json={"display_name": "Clone Dang 3", "role": "poster", "daily_post_limit": 10},
    )
    check("Tao clone poster", resp.status_code == 201 and resp.json()["role"] == "poster")
    poster_id = resp.json()["id"]

    resp = await client.post(
        "/api/clones",
        headers=auth,
        json={"display_name": "Clone All 4", "role": "all"},
    )
    check("Tao clone all (da nhiem)", resp.status_code == 201 and resp.json()["role"] == "all")
    all_id = resp.json()["id"]

    # Thu tao bai dang voi clone co vai tro 'scout' -> Phai bi tu choi 422
    resp = await client.post(
        "/api/publishing",
        headers=auth,
        json={
            "title": "Bai test sai role",
            "content_template": "Noi dung bai dang mau",
            "target_groups": [{"group_id": "g1", "group_name": "Nhom 1"}],
            "clone_account_id": scout_id,
        },
    )
    check("Clone scout khong duoc phep tao bai dang -> 422", resp.status_code == 422)

    # Tao bai dang hop le voi clone 'poster'
    resp = await client.post(
        "/api/publishing",
        headers=auth,
        json={
            "title": "Bai tuyen dung moi",
            "content_template": "{Chao moi nguoi|Hello ca nha}! Minh dang tim dong doi.",
            "target_groups": [
                {"group_id": "g100", "group_name": "Freelancer VN", "group_url": "https://facebook.com/groups/freelance"}
            ],
            "clone_account_id": poster_id,
        },
    )
    check("Tao bai dang hop le voi poster -> 201", resp.status_code == 201)
    pub_id = resp.json()["id"]
    check("Trang thai bai dang ban dau la scheduled", resp.json()["status"] == "scheduled")

    # Lay danh sach bai dang
    resp = await client.get("/api/publishing", headers=auth)
    check("Liet ke bai dang -> co 1 item", resp.status_code == 200 and resp.json()["total"] >= 1)

    # De clone poster san sang dang bai, upload cookie va chuyen sang active
    good_cookie = (
        b'[{"name":"c_user","value":"100099999","domain":".facebook.com","path":"/"},'
        b'{"name":"xs","value":"abc:xyz","domain":".facebook.com","path":"/"}]'
    )
    await client.post(
        f"/api/clones/{poster_id}/upload-cookie",
        headers=auth,
        files={"file": ("cookies.json", good_cookie, "application/json")},
    )
    resp = await client.post(
        f"/api/clones/{poster_id}/transition",
        headers=auth,
        json={"event": "warmup_complete"},
    )
    check("Kich hoat clone poster thanh active", resp.status_code == 200 and resp.json()["status"] == "active")

    # Thuc thi dang ngay
    resp = await client.post(f"/api/publishing/{pub_id}/publish-now", headers=auth)
    check("Dang bai ngay lap tuc -> 200", resp.status_code == 200)
    check("Trang thai chuyen sang published", resp.json()["status"] == "published")
    check("Co ket qua dang bai vao group", len(resp.json().get("publish_results", [])) == 1)

    # Xoa bai dang
    resp = await client.delete(f"/api/publishing/{pub_id}", headers=auth)
    check("Xoa bai dang -> 204", resp.status_code == 204)

    # Don dep clone test
    for cid_item in (scout_id, shooter_id, poster_id, all_id):
        await client.delete(f"/api/clones/{cid_item}", headers=auth)


def run_unit_tests() -> None:
    """Test thuần logic — không cần HTTP."""
    section("15. Logic thuan: spintax, state machine, rate limiter")

    from app.services.script_engine import (
        ScriptError,
        contains_link,
        count_variants,
        render_spintax,
        validate_comment,
    )

    rng = random.Random(42)
    check("Spintax lay 1 trong cac lua chon", render_spintax("{a|b|c}", rng) in ("a", "b", "c"))
    check("Spintax long nhau", render_spintax("{x{1|1}|y{2|2}}", rng) in ("x1", "y2"))
    check("Dem bien the 2x3=6", count_variants("{a|b} {1|2|3}") == 6)
    check("Phat hien link http", contains_link("xem tai https://abc.com") is True)
    check("Phat hien domain tran", contains_link("ghe nyatymita.com nhe") is True)
    check("Cau khong link -> False", contains_link("minh nhan viet truyen nhe") is False)

    try:
        validate_comment("ngan")
        check("Comment qua ngan bi chan", False)
    except ScriptError:
        check("Comment qua ngan bi chan", True)

    from app.services.account_manager import (
        InvalidTransitionError,
        STATE_TRANSITIONS,
        cooldown_duration,
        next_state,
    )
    from app.models.enums import AccountState, AccountTransition

    check("Bang chuyen trang thai co du 13 cap", len(STATE_TRANSITIONS) == 13, str(len(STATE_TRANSITIONS)))
    check(
        "onboarding + cookie_valid -> warming_up",
        next_state(AccountState.ONBOARDING, AccountTransition.COOKIE_VALID) is AccountState.WARMING_UP,
    )
    check(
        "active + quota_reached -> cooldown",
        next_state(AccountState.ACTIVE, AccountTransition.QUOTA_REACHED) is AccountState.COOLDOWN,
    )
    check(
        "checkpoint + verification_failed -> banned",
        next_state(AccountState.CHECKPOINT, AccountTransition.VERIFICATION_FAILED) is AccountState.BANNED,
    )
    try:
        next_state(AccountState.BANNED, AccountTransition.COOLDOWN_EXPIRED)
        check("banned khong the quay lai active", False)
    except InvalidTransitionError:
        check("banned khong the quay lai active", True)

    hours = cooldown_duration(AccountTransition.VERIFICATION_SUCCESS).total_seconds() / 3600
    check("Sau checkpoint nghi dung 48h", abs(hours - 48) < 0.001)

    from app.services.anti_ban import (
        compute_delay,
        detect_checkpoint_title,
        detect_checkpoint_url,
        is_visible_in_page,
    )

    check("Phat hien checkpoint qua URL", detect_checkpoint_url("https://facebook.com/checkpoint/123") is not None)
    check("URL binh thuong khong bao dong", detect_checkpoint_url("https://facebook.com/groups/abc") is None)
    check("Phat hien qua tieu de tieng Viet", detect_checkpoint_title("Xác minh danh tính") is not None)
    check("Phat hien qua tieu de tieng Anh", detect_checkpoint_title("Security Check") is not None)

    fixed = random.Random(7)
    fast = compute_delay(0.99, jitter_rng=fixed)
    slow = compute_delay(0.10, jitter_rng=fixed)
    check("Ti le thanh cong cao -> delay ngan hon", fast < 600)
    check("Ti le thanh cong thap -> delay kich tran", slow >= 1440)
    check("Delay luon trong [180, 1800]", all(180 <= compute_delay(r) <= 1800 for r in (0.0, 0.5, 0.85, 1.0)))

    check(
        "Shadowban: comment hien thi tren trang",
        is_visible_in_page("truoc do  Chao ban minh nhan viet   nhe sau do", "Chao ban minh nhan viet nhe"),
    )
    check(
        "Shadowban: comment khong hien thi",
        not is_visible_in_page("noi dung khac han", "Chao ban minh nhan viet nhe"),
    )

    from app.services.facebook_utils import (
        InvalidCookieFile,
        InvalidGroupURL,
        parse_cookie_payload,
        parse_group_ref,
    )

    check("Parse group tu URL day du", parse_group_ref("https://www.facebook.com/groups/123456/")[0] == "123456")
    check("Parse group tu ma so", parse_group_ref("mygroup")[1] == "https://www.facebook.com/groups/mygroup/")
    try:
        parse_group_ref("https://twitter.com/groups/1")
        check("Chan URL khong phai Facebook", False)
    except InvalidGroupURL:
        check("Chan URL khong phai Facebook", True)

    netscape = (
        "# Netscape HTTP Cookie File\n"
        ".facebook.com\tTRUE\t/\tTRUE\t1799999999\tc_user\t100099\n"
        ".facebook.com\tTRUE\t/\tTRUE\t1799999999\txs\tsecret\n"
    )
    cookies = parse_cookie_payload(netscape)
    check("Doc duoc cookie dinh dang Netscape", len(cookies) == 2)
    try:
        parse_cookie_payload("khong-phai-cookie")
        check("File cookie rac bi tu choi", False)
    except InvalidCookieFile:
        check("File cookie rac bi tu choi", True)

    from app.services.crypto import decrypt_cookies, encrypt_cookies

    blob = encrypt_cookies(cookies)
    check("Cookie duoc ma hoa (khong con plaintext)", "c_user" not in blob)
    check("Giai ma tra ve dung du lieu", decrypt_cookies(blob) == cookies)

    from app.services.warmup_service import TOTAL_WARMUP_DAYS, get_step

    check("Lich u am du 7 ngay", TOTAL_WARMUP_DAYS == 7)
    check("Ngay 3 la like bai", get_step(3).like_posts == 3)
    check("Ngay 7 la health check", get_step(7).health_check is True)


    section("15b. Chong trung lap & xoay vong")
    from app.services.script_engine import (
        expand_all,
        is_too_similar,
        iter_groups,
        lint_template,
        normalize_for_dedup,
        render_unique,
        similarity,
    )

    check("Chuan hoa bo dau cau", normalize_for_dedup("Chào bạn!!!  Mình  nhận.") == "chào bạn mình nhận")
    check("Cau y het nhau -> giong 1.0", similarity("chao ban nhe", "chao ban nhe!") == 1.0)
    check("Dao trat tu van bi coi la trung", similarity("minh nhan viet truyen", "truyen viet nhan minh") == 1.0)
    check("Cau khac han -> giong thap", similarity("minh nhan viet truyen", "hom nay troi dep qua") < 0.2)
    check(
        "is_too_similar bat duoc cau na na",
        is_too_similar("chao ban minh nhan viet truyen", ["chao ban minh nhan viet truyen nhe"]),
    )
    check(
        "is_too_similar bo qua cau khac han",
        not is_too_similar("hom nay troi dep", ["chao ban minh nhan viet truyen"]),
    )

    check("Liet ke du 4 bien the", sorted(expand_all("{a|b} {1|2}")) == ["a 1", "a 2", "b 1", "b 2"])
    check("Liet ke ton trong gioi han", len(expand_all("{a|b} {c|d} {e|f}", limit=3)) == 3)
    check("Doc duoc cac nhom xoay", len(iter_groups("{a|b} giua {c|d|e}")) == 2)

    # render_unique phai NE cau da dung, khong duoc tra lai y het.
    used_before = ["Chao ban minh nhan viet the loai nay nhe ban oi"]
    picked = render_unique(
        "{Chao ban|Xin chao} minh {nhan viet|nhan lam} the loai nay nhe ban oi",
        used_before,
        random.Random(3),
    )
    check("render_unique tranh cau da dung", not is_too_similar(picked, used_before), picked)

    # Mau chi co dung 1 bien the: khong the tranh duoc, phai tra ve chu khong duoc treo.
    only_one = render_unique("cau nay khong the xoay duoc gi ca dau nhe ban oi", ["cau nay khong the xoay duoc gi ca dau nhe ban oi"], attempts=5)
    check("Mau ngheo bien the van tra ve ket qua (khong treo)", bool(only_one))

    report = lint_template("{Chao|Hi} ban, minh nhan viet truyen ngon tinh va co trang nhe ban oi")
    check("lint tra ve du khoa", set(report) == {"ok", "total_variants", "group_count", "shortest_words", "longest_words", "issues", "samples"})
    check("lint dem dung so tu ngan nhat", report["shortest_words"] == 14, str(report["shortest_words"]))
    check("lint mau rong -> loi", lint_template("")["ok"] is False)


    section("15c. Han dung cookie & chan doan tai khoan")
    from app.models.clone_account import CloneAccount
    from app.services.account_check import diagnose, grade, has_backup, rollup
    from app.services.facebook_utils import cookie_health, parse_cookie_payload as _parse

    future = int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp())
    past = int((datetime.now(timezone.utc) - timedelta(days=1)).timestamp())
    soon = int((datetime.now(timezone.utc) + timedelta(days=2)).timestamp())

    parsed = _parse(
        '[{"name":"c_user","value":"1","domain":".facebook.com","expirationDate":%d},'
        '{"name":"xs","value":"2","domain":".facebook.com","expirationDate":%d}]'
        % (future, future)
    )
    check("Giu lai han dung khi nap cookie JSON", parsed[0]["expires"] == float(future))

    ms = _parse(
        '[{"name":"c_user","value":"1","domain":".facebook.com","expirationDate":%d},'
        '{"name":"xs","value":"2","domain":".facebook.com"}]' % (future * 1000)
    )
    check("Han dung ghi bang mili-giay van doc dung", ms[0]["expires"] == float(future))
    check("Cookie phien (khong han) duoc danh dau -1", ms[1]["expires"] == -1)

    netscape = _parse(
        "# Netscape HTTP Cookie File\n"
        ".facebook.com\tTRUE\t/\tTRUE\t%d\tc_user\t100\n"
        ".facebook.com\tTRUE\t/\tTRUE\t%d\txs\tabc\n" % (future, future)
    )
    check("Doc duoc han dung tu file Netscape", netscape[0]["expires"] == float(future))

    healthy = cookie_health(parsed)
    check("Cookie con han -> ok", healthy["ok"] is True)
    check("Tinh duoc so ngay con lai", 29 <= healthy["days_left"] <= 30, str(healthy["days_left"]))

    expired = cookie_health(
        [{"name": "c_user", "value": "1", "expires": past},
         {"name": "xs", "value": "2", "expires": past}]
    )
    check("Cookie het han -> khong ok", expired["ok"] is False)
    check("Neu ten cookie da het han", expired["expired"] == ["c_user", "xs"])

    check("Khong co cookie -> bao chua nap", cookie_health([])["reason"] == "Chưa nạp cookie")
    check(
        "Thieu xs -> bao thieu cookie phien",
        cookie_health([{"name": "c_user", "value": "1"}])["missing"] == ["xs"],
    )

    ok_cookie = cookie_health(parsed)
    soon_cookie = cookie_health(
        [{"name": "c_user", "value": "1", "expires": soon},
         {"name": "xs", "value": "2", "expires": soon}]
    )

    def _clone(**kw) -> CloneAccount:
        base = dict(
            id="c1", display_name="Clone", user_id="u1", role="shooter",
            status="active", proxy_address="socks5://1.2.3.4:1080",
            daily_comment_count=0, daily_comment_limit=20, consecutive_failures=0,
            warmup_day=0, is_backup=False,
        )
        base.update(kw)
        return CloneAccount(**base)

    good = diagnose(_clone(), cookie=ok_cookie)
    check("Clone khoe -> 100 diem", good["score"] == 100, str(good["score"]))
    check("Clone khoe -> san sang", good["ready"] is True)

    banned = diagnose(_clone(status="banned"), cookie=ok_cookie)
    check("Clone bi ban -> 0 diem", banned["score"] == 0)
    check("Clone bi ban -> khong san sang", banned["ready"] is False)

    expiring = diagnose(_clone(), cookie=soon_cookie)
    check(
        "Cookie sap het han -> canh bao truoc",
        any(i["code"] == "cookie_expiring" for i in expiring["issues"]),
    )
    check("Sap het han van chay duoc", expiring["ready"] is True)

    risky = diagnose(_clone(consecutive_failures=5), cookie=ok_cookie)
    check(
        "Hong 5 luot lien tiep -> loi nghiem trong",
        risky["issues"][0]["code"] == "failures_critical",
    )
    check("Hong nhieu -> khong san sang", risky["ready"] is False)

    full = diagnose(_clone(daily_comment_count=20), cookie=ok_cookie)
    check("Het quota -> khong san sang nhung khong phai loi nang", full["ready"] is False)
    check("Het quota chi la thong tin",
          all(i["severity"] != "critical" for i in full["issues"]))

    stalled = diagnose(
        _clone(status="warming_up", warmup_day=2,
               warmup_started_at=datetime.now(timezone.utc) - timedelta(days=6)),
        cookie=ok_cookie,
    )
    check(
        "U am ket lai -> phat hien Beat khong chay",
        any(i["code"] == "warmup_stalled" for i in stalled["issues"]),
    )

    overdue = diagnose(
        _clone(status="cooldown",
               cooldown_until=datetime.now(timezone.utc) - timedelta(hours=5)),
        cookie=ok_cookie,
    )
    check(
        "Het gio nghi ma chua day -> canh bao",
        any(i["code"] == "cooldown_overdue" for i in overdue["issues"]),
    )

    check("Loi nang duoc xep len dau", risky["issues"][0]["severity"] == "critical")
    check("Quy diem ve muc mau", (grade(95), grade(60), grade(10)) == ("good", "warn", "bad"))

    others = [_clone(id="c1"), _clone(id="c2", status="cooldown")]
    check("Con clone khac dang chay -> co du phong", has_backup(others[0], others) is True)
    check("Clone duy nhat -> khong co du phong", has_backup(others[0], [others[0]]) is False)
    check(
        "Vai tro khac nhau thi khong the thay the",
        has_backup(_clone(id="c1", role="scout"), [_clone(id="c2", role="shooter")]) is False,
    )

    summary = rollup([good, banned, full])
    check("Gop bao cao: dem dung clone", summary["clone_count"] == 3)
    check("Gop bao cao: chi 1 clone san sang", summary["ready_count"] == 1)
    check("Nang luc chi tinh clone san sang", summary["capacity_total"] == 20)
    check("Diem trung binh", summary["average_score"] == round((100 + 0 + 95) / 3),
          str(summary["average_score"]))
    check("Van de nang duoc xep len dau", summary["top_issues"][0]["severity"] == "critical")
    check("Khong co clone nao -> khong vo", rollup([])["clone_count"] == 0)

    section("16. Logic worker (dinh gio, quota clone)")
    from app.workers.bump_task import is_bump_due, pick_message
    from app.workers.health_check_task import cookies_look_valid
    from app.workers.scout_task import is_due
    from app.workers.shooter_task import clone_can_shoot
    from app.models.campaign import BumpSchedule, CampaignGroup
    from app.models.clone_account import CloneAccount

    now = datetime.now(timezone.utc)
    group = CampaignGroup(
        campaign_id="x", group_url="u", group_key="k", status="active", scan_interval_minutes=10
    )
    group.last_scanned_at = None
    check("Group chua quet lan nao -> den han", is_due(group, now) is True)
    group.last_scanned_at = now - timedelta(minutes=3)
    check("Group vua quet 3 phut truoc -> chua den han", is_due(group, now) is False)
    group.last_scanned_at = now - timedelta(minutes=11)
    check("Group quet 11 phut truoc (chu ky 10) -> den han", is_due(group, now) is True)
    group.status = "paused"
    check("Group dang paused khong quet", is_due(group, now) is False)

    clone = CloneAccount(
        user_id="u", display_name="c", role="shooter", status="active",
        daily_comment_count=0, daily_comment_limit=5, daily_counter_date="",
    )
    check("Clone active con quota -> ban duoc", clone_can_shoot(clone, now) is True)
    clone.daily_counter_date = now.date().isoformat()
    clone.daily_comment_count = 5
    check("Clone het quota ngay -> khong ban", clone_can_shoot(clone, now) is False)
    clone.daily_comment_count = 0
    clone.cooldown_until = now + timedelta(hours=2)
    check("Clone dang cooldown -> khong ban", clone_can_shoot(clone, now) is False)
    clone.cooldown_until = None
    clone.status = "checkpoint"
    check("Clone checkpoint -> khong ban", clone_can_shoot(clone, now) is False)

    local_now = datetime(2026, 9, 8, 12, 30, tzinfo=timezone.utc)  # 19:30 gio VN
    bump = BumpSchedule(campaign_id="x", target_post_url="u", cron_schedule=[19], bump_messages=["a"], is_active=True)
    bump.last_bumped_at = None
    check("Dung khung gio -> den han bump", is_bump_due(bump, local_now) is True)
    bump.last_bumped_at = local_now - timedelta(minutes=10)
    check("Da bump trong chinh gio do -> khong bump lai", is_bump_due(bump, local_now) is False)
    bump.cron_schedule = [3]
    bump.last_bumped_at = None
    check("Sai khung gio -> khong bump", is_bump_due(bump, local_now) is False)
    bump.bump_messages = ["{Up|Len} bai"]
    check("Bump message ho tro spintax", pick_message(bump, random.Random(1)) in ("Up bai", "Len bai"))

    check("Cookie du c_user+xs -> hop le", cookies_look_valid([{"name": "c_user"}, {"name": "xs"}]) is True)
    check("Cookie thieu xs -> khong hop le", cookies_look_valid([{"name": "c_user"}]) is False)

    from app.services.publisher_service import clone_can_post
    from app.services.account_check import is_role_compatible

    poster_clone = CloneAccount(
        user_id="u", display_name="p", role="poster", status="active",
        daily_post_count=0, daily_post_limit=5, daily_counter_date="",
    )
    check("Clone poster active con quota -> duoc dang bai", clone_can_post(poster_clone, now) is True)
    poster_clone.daily_counter_date = now.date().isoformat()
    poster_clone.daily_post_count = 5
    check("Clone poster het quota ngay -> khong cho dang", clone_can_post(poster_clone, now) is False)
    poster_clone.daily_post_count = 0
    poster_clone.cooldown_until = now + timedelta(hours=1)
    check("Clone poster dang cooldown -> khong cho dang", clone_can_post(poster_clone, now) is False)

    check("Tuong thich role: poster voi poster -> hop le", is_role_compatible("poster", "poster") is True)
    check("Tuong thich role: all voi poster -> hop le", is_role_compatible("all", "poster") is True)
    check("Tuong thich role: scout voi poster -> khong hop le", is_role_compatible("scout", "poster") is False)


if __name__ == "__main__":
    asyncio.run(main())
    run_unit_tests()
    print(f"\n{'=' * 52}\nKET QUA BACKEND: {ok} PASS / {fail} FAIL\n{'=' * 52}")
    sys.exit(1 if fail else 0)
