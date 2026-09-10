"""
Xưởng kịch bản comment (Script Studio).

Hai loại kịch bản theo Master Plan:
  • spintax        — mẫu {a|b|c} sinh biến thể ngẫu nhiên, không tốn tiền AI
  • ai_contextual  — nhờ AI viết bám nội dung bài (xử lý ở ai_service)

Spintax hỗ trợ lồng nhau: "{Chào|Hi} {bạn|cậu}, mình {nhận|làm} {viết|content}".
Việc render là thuần logic => test offline được, và là hàng rào chặn spam:
mọi comment sinh ra đều bị kiểm tra không chứa link trước khi trả về.
"""
import random
import re

LINK_PATTERN = re.compile(
    r"(https?://|www\.|\b[\w-]+\.(?:com|net|vn|org|io|xyz|shop|me)\b)", re.IGNORECASE
)

_MAX_DEPTH = 12


class ScriptError(ValueError):
    """Mẫu kịch bản không hợp lệ."""


def _find_innermost(template: str) -> tuple[int, int] | None:
    """Tìm cặp ngoặc {} trong cùng (không chứa ngoặc con)."""
    start = -1
    for index, char in enumerate(template):
        if char == "{":
            start = index
        elif char == "}" and start != -1:
            return start, index
    return None


def render_spintax(template: str, rng: random.Random | None = None) -> str:
    """Sinh 1 biến thể từ mẫu spintax.

    Raises:
        ScriptError: nếu mẫu rỗng hoặc lồng quá sâu (dấu hiệu ngoặc lệch).
    """
    if not (template or "").strip():
        raise ScriptError("Mẫu kịch bản đang trống")

    rng = rng or random
    text = template
    for _ in range(_MAX_DEPTH * 50):
        found = _find_innermost(text)
        if found is None:
            break
        start, end = found
        options = text[start + 1 : end].split("|")
        text = text[:start] + rng.choice(options) + text[end + 1 :]
    else:  # pragma: no cover - chỉ xảy ra với mẫu bệnh hoạn
        raise ScriptError("Mẫu spintax lồng quá sâu hoặc thiếu dấu đóng ngoặc")

    return re.sub(r"\s+", " ", text).strip()


def count_variants(template: str) -> int:
    """Đếm (xấp xỉ) số biến thể mẫu có thể sinh — hiển thị trong Script Studio."""
    total = 1
    text = template
    while True:
        found = _find_innermost(text)
        if found is None:
            return total
        start, end = found
        total *= max(1, len(text[start + 1 : end].split("|")))
        text = text[:start] + "\x00" + text[end + 1 :]


def contains_link(text: str) -> bool:
    """Comment chứa link là con đường ngắn nhất tới việc bị admin xoá + ban."""
    return bool(LINK_PATTERN.search(text or ""))


def validate_comment(text: str, *, min_words: int = 8, max_words: int = 220) -> str:
    """Kiểm tra comment trước khi cho vào hàng đợi.

    Raises:
        ScriptError: nếu rỗng, chứa link, hoặc độ dài bất thường.
    """
    cleaned = re.sub(r"\s+", " ", (text or "")).strip()
    if not cleaned:
        raise ScriptError("Nội dung comment rỗng")
    if contains_link(cleaned):
        raise ScriptError("Comment chứa link — vi phạm quy tắc chống spam")
    words = len(cleaned.split())
    if words < min_words:
        raise ScriptError(f"Comment quá ngắn ({words} từ, tối thiểu {min_words})")
    if words > max_words:
        raise ScriptError(f"Comment quá dài ({words} từ, tối đa {max_words})")
    return cleaned


def preview_variants(template: str, count: int = 3, seed: int | None = None) -> list[str]:
    """Sinh nhiều mẫu khác nhau cho nút 'Preview' trên dashboard."""
    rng = random.Random(seed)
    seen: list[str] = []
    for _ in range(count * 8):
        if len(seen) >= count:
            break
        variant = render_spintax(template, rng)
        if variant not in seen:
            seen.append(variant)
    return seen or [render_spintax(template, rng)]


# ═══════════════════════════════════════════════════════════════════════════
# Phân tích mẫu & chống trùng lặp
#
# Hai bài toán khác nhau, đừng lẫn:
#   1. TRÙNG TRONG MẪU  — người dùng gõ {chào bạn|chào bạn}: nhóm 2 lựa chọn
#      nhưng thực chất chỉ 1. Bắt lỗi lúc soạn, bằng lint_template().
#   2. TRÙNG KHI GỬI    — mẫu tốt nhưng random rơi trúng câu vừa dùng hôm qua
#      ở cùng group. Bắt lúc chạy, bằng render_unique().
# ═══════════════════════════════════════════════════════════════════════════

# Ngưỡng coi hai comment là "na ná nhau". 0.82 chọn theo kinh nghiệm: đổi vài
# từ nối vẫn bị coi là trùng, nhưng đổi hẳn ý thì lọt.
SIMILARITY_THRESHOLD = 0.82

_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)


def normalize_for_dedup(text: str) -> str:
    """Chuẩn hoá để so trùng: bỏ dấu câu, gộp khoảng trắng, hạ chữ thường."""
    return re.sub(r"\s+", " ", _PUNCT.sub(" ", (text or "").lower())).strip()


def similarity(left: str, right: str) -> float:
    """Độ giống nhau 0..1 theo tập từ (Jaccard).

    Cố tình KHÔNG dùng difflib: so theo tập từ thì đảo trật tự câu vẫn bị coi
    là trùng — đúng thứ ta cần, vì Facebook nhìn nội dung chứ không nhìn trật tự.
    """
    a = set(normalize_for_dedup(left).split())
    b = set(normalize_for_dedup(right).split())
    if not a or not b:
        return 1.0 if a == b else 0.0
    return len(a & b) / len(a | b)


def is_too_similar(
    text: str, used: list[str], threshold: float = SIMILARITY_THRESHOLD
) -> bool:
    """Câu này có na ná câu nào đã dùng không?"""
    return any(similarity(text, old) >= threshold for old in used)


def render_unique(
    template: str,
    used: list[str] | None = None,
    rng: random.Random | None = None,
    attempts: int = 40,
    threshold: float = SIMILARITY_THRESHOLD,
) -> str:
    """Sinh biến thể KHÁC những câu đã dùng gần đây.

    Thử tối đa `attempts` lần; hết lượt vẫn trùng thì trả câu ít giống nhất
    thay vì ném lỗi — bỏ lỡ khách hàng còn tệ hơn một comment hơi giống.
    """
    used = used or []
    rng = rng or random
    best, best_score = "", 2.0
    for _ in range(max(1, attempts)):
        candidate = render_spintax(template, rng)
        if not used:
            return candidate
        score = max(similarity(candidate, old) for old in used)
        if score < threshold:
            return candidate
        if score < best_score:
            best, best_score = candidate, score
    return best or render_spintax(template, rng)


def expand_all(template: str, limit: int = 200) -> list[str]:
    """Liệt kê TẤT CẢ biến thể (tối đa `limit`) để khách soi bằng mắt.

    Dùng cho panel "xem toàn bộ" trong Script Studio; mẫu lớn thì cắt bớt và
    số thật vẫn tra được qua count_variants().
    """
    if not (template or "").strip():
        raise ScriptError("Mẫu kịch bản đang trống")

    results = [template]
    for _ in range(_MAX_DEPTH * 50):
        if _find_innermost(results[0]) is None:
            break
        expanded: list[str] = []
        for text in results:
            spot = _find_innermost(text)
            if spot is None:
                expanded.append(text)
                continue
            begin, close = spot
            for option in text[begin + 1 : close].split("|"):
                expanded.append(text[:begin] + option + text[close + 1 :])
            if len(expanded) > limit * 4:
                break
        results = expanded
    else:  # pragma: no cover - chỉ xảy ra với mẫu bệnh hoạn
        raise ScriptError("Mẫu spintax lồng quá sâu hoặc thiếu dấu đóng ngoặc")

    seen: list[str] = []
    for text in results:
        cleaned = re.sub(r"\s+", " ", text).strip()
        if cleaned and cleaned not in seen:
            seen.append(cleaned)
        if len(seen) >= limit:
            break
    return seen


def iter_groups(template: str) -> list[list[str]]:
    """Trả về danh sách các nhóm xoay {…|…} có trong mẫu (mỗi nhóm là list lựa chọn)."""
    groups: list[list[str]] = []
    text = template
    for _ in range(_MAX_DEPTH * 50):
        found = _find_innermost(text)
        if found is None:
            return groups
        start, end = found
        groups.append(text[start + 1 : end].split("|"))
        text = text[:start] + "\x00" + text[end + 1 :]
    return groups


def _empty_report(issues: list[dict]) -> dict:
    return {
        "ok": False,
        "total_variants": 0,
        "group_count": 0,
        "shortest_words": 0,
        "longest_words": 0,
        "issues": issues,
        "samples": [],
    }


def lint_template(template: str, *, min_words: int = 8, max_words: int = 220) -> dict:
    """Soi mẫu spintax, trả về mọi thứ Script Studio cần hiển thị.

    Trả dict thay vì ném lỗi: người đang gõ dở cần thấy TẤT CẢ vấn đề cùng
    lúc, chứ không phải sửa xong lỗi này mới lộ lỗi kia.

    Returns:
        {"ok", "total_variants", "group_count", "shortest_words",
         "longest_words", "issues": [{"level", "message"}], "samples": [...]}
    """
    issues: list[dict] = []
    raw = template or ""

    def add(level: str, message: str) -> None:
        issues.append({"level": level, "message": message})

    if not raw.strip():
        add("error", "Mẫu kịch bản đang trống.")
        return _empty_report(issues)

    # Ngoặc lệch là lỗi hay gặp nhất khi gõ tay — báo trước, vì mọi phân tích
    # sau đó đều vô nghĩa nếu cấu trúc đã hỏng.
    opens, closes = raw.count("{"), raw.count("}")
    if opens != closes:
        add(
            "error",
            f"Ngoặc lệch: {opens} dấu mở nhưng {closes} dấu đóng. Mỗi nhóm xoay cần đủ cặp.",
        )
        return _empty_report(issues)

    groups = iter_groups(raw)
    for options in groups:
        stripped = [option.strip() for option in options]
        preview = "|".join(options)[:40]

        if any(not option for option in stripped):
            add("warning", f"Nhóm «{preview}» có lựa chọn rỗng — sẽ sinh ra câu cụt.")
        if len(stripped) == 1:
            add("warning", f"Nhóm «{preview}» chỉ có 1 lựa chọn — không xoay được gì.")

        lowered = [normalize_for_dedup(option) for option in stripped if option]
        duplicates = sorted({value for value in lowered if lowered.count(value) > 1})
        if duplicates:
            add(
                "warning",
                f"Nhóm «{preview}» có lựa chọn lặp lại ({', '.join(duplicates)}) "
                "— số biến thể thật ít hơn con số hiển thị.",
            )

    if not groups:
        add(
            "warning",
            "Mẫu chưa có nhóm xoay nào — mọi comment sẽ giống hệt nhau, "
            "rất dễ bị Facebook gắn cờ spam.",
        )

    if contains_link(raw):
        add(
            "error",
            "Mẫu chứa link — comment có link sẽ bị admin xoá và tài khoản dễ ăn gậy.",
        )

    total = count_variants(raw)
    samples = expand_all(raw, limit=60)
    word_counts = [len(text.split()) for text in samples] or [0]
    shortest, longest = min(word_counts), max(word_counts)

    if shortest < min_words:
        add(
            "error",
            f"Có biến thể chỉ {shortest} từ (tối thiểu {min_words}) — comment quá "
            "ngắn trông như spam và sẽ bị chặn khi đưa vào hàng đợi.",
        )
    if longest > max_words:
        add("error", f"Có biến thể dài tới {longest} từ (tối đa {max_words}).")

    if total < 10:
        add(
            "warning",
            f"Chỉ {total} biến thể — nên tăng lên ít nhất 10 để tránh lặp lại "
            "trong cùng một group.",
        )

    return {
        "ok": not any(issue["level"] == "error" for issue in issues),
        "total_variants": total,
        "group_count": len(groups),
        "shortest_words": shortest,
        "longest_words": longest,
        "issues": issues,
        "samples": preview_variants(raw, count=5),
    }
