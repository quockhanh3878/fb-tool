# -*- coding: utf-8 -*-
"""Test TemplatePool — chọn ngẫu nhiên câu mẫu, tránh lặp gần đây."""
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from comment_templates import TemplatePool, load_templates

ok = fail = 0


def check(label, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  PASS  {label}")
    else:
        fail += 1
        print(f"  FAIL  {label} {extra}")


tmp = Path(tempfile.mkdtemp(prefix="tpl_"))
f = tmp / "t.txt"
f.write_text(
    "# comment\n\nCâu một\nCâu hai\nCâu ba\nCâu bốn\nCâu một\n  \nCâu năm\n",
    encoding="utf-8",
)

print("\n=== load_templates ===")
tpls = load_templates(str(f))
check("bỏ dòng #, dòng trống, trùng", tpls == ["Câu một", "Câu hai", "Câu ba", "Câu bốn", "Câu năm"], tpls)

print("\n=== TemplatePool.pick tránh lặp gần đây ===")
pool = TemplatePool(str(f), avoid_recent=3)
check("len = 5", len(pool) == 5)
seq = [pool.pick() for _ in range(4)]
# 3 lần liên tiếp không được trùng nhau
check("3 câu liên tiếp khác nhau", len(set(seq[:3])) == 3, seq)
check("câu thứ 4 khác câu thứ 3, 2", seq[3] != seq[2] and seq[3] != seq[1], seq)

print("\n=== usage.json giữ trạng thái qua phiên ===")
check("tạo file usage", (tmp / "t.txt.usage.json").exists())
pool2 = TemplatePool(str(f), avoid_recent=3)
nxt = pool2.pick()
check("phiên mới vẫn né các câu gần nhất", nxt not in seq[-2:], f"{nxt} vs {seq}")

print("\n=== phân phối tương đối đều ===")
f2 = tmp / "t2.txt"
f2.write_text("A\nB\nC\nD\nE\n", encoding="utf-8")
p = TemplatePool(str(f2), avoid_recent=2)
c = Counter(p.pick() for _ in range(250))
check("cả 5 câu đều được dùng", len(c) == 5, dict(c))
check("không câu nào bị lạm dụng (>2x mức đều)", max(c.values()) < 100, dict(c))

print("\n" + "=" * 50)
print(f"KET QUA: {ok} PASS / {fail} FAIL")
print("=" * 50)
sys.exit(1 if fail else 0)
