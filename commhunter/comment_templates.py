"""
Comment Templates — Kho câu mẫu do người dùng nạp, chọn NGẪU NHIÊN không lặp.

Khác với AI Engine (sinh câu mới mỗi lần), đây là kho câu tĩnh: người dùng
nạp sẵn N mẫu, tool xoay vòng — luôn ưu tiên mẫu lâu chưa dùng nhất và tránh
đúng mẫu vừa gửi gần đây. Dùng khi khách muốn kiểm soát từng chữ, không cho
AI tự chế.

File mẫu: mỗi dòng 1 câu; dòng trống hoặc bắt đầu bằng `#` bị bỏ qua.
"""
import json
import random
import time
from pathlib import Path
from typing import List, Optional

from loguru import logger


def load_templates(path: str) -> List[str]:
    """Đọc file mẫu → list câu (đã bỏ trùng, giữ thứ tự)."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Không tìm thấy file mẫu comment: {path}")
    seen, out = set(), []
    for line in p.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s not in seen:
            seen.add(s)
            out.append(s)
    if not out:
        raise ValueError(f"File mẫu {path} không có câu nào hợp lệ")
    return out


class TemplatePool:
    """Xoay vòng câu mẫu, tránh lặp lại N câu gần nhất.

    Trạng thái "đã dùng" lưu ra `<file>.usage.json` để giữ qua các lần chạy.
    """

    def __init__(self, path: str, avoid_recent: int = 3):
        self.path = str(path)
        self.templates = load_templates(path)
        self.avoid_recent = max(0, min(avoid_recent, len(self.templates) - 1))
        self._usage_path = Path(f"{self.path}.usage.json")
        self._recent: List[str] = self._load_recent()

    def _load_recent(self) -> List[str]:
        try:
            data = json.loads(self._usage_path.read_text(encoding="utf-8"))
            return [t for t in data.get("recent", []) if t in self.templates]
        except (OSError, json.JSONDecodeError):
            return []

    def _save_recent(self) -> None:
        try:
            self._usage_path.write_text(
                json.dumps(
                    {"recent": self._recent[-20:], "updated": time.time()},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        except OSError as e:
            logger.debug(f"Không ghi được usage câu mẫu: {e}")

    def pick(self) -> str:
        """Chọn 1 câu: ưu tiên câu KHÔNG nằm trong `avoid_recent` câu gần nhất."""
        blocked = set(self._recent[-self.avoid_recent:]) if self.avoid_recent else set()
        pool = [t for t in self.templates if t not in blocked] or self.templates
        choice = random.choice(pool)
        self._recent.append(choice)
        self._save_recent()
        return choice

    def __len__(self) -> int:
        return len(self.templates)
