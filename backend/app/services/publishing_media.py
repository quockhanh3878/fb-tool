# plan: docs/plans/phase2_dashboard_detail.md
"""Lưu và phân giải ảnh đính kèm bài đăng trong thư mục riêng của khách."""

import hashlib
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException

from app.config import get_settings
from app.models.post import PublishingMedia

ALLOWED_MEDIA_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_MEDIA_BYTES = 10 * 1024 * 1024


def _extension(content_type: str, filename: str) -> str:
    suffix = Path(filename or "").suffix.lower()
    allowed_suffixes = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
    return suffix if suffix in allowed_suffixes else {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }[content_type]


def _looks_like_image(content_type: str, raw: bytes) -> bool:
    signatures = {
        "image/png": raw.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/jpeg": raw.startswith(b"\xff\xd8\xff"),
        "image/gif": raw.startswith((b"GIF87a", b"GIF89a")),
        "image/webp": raw.startswith(b"RIFF") and raw[8:12] == b"WEBP",
    }
    return signatures.get(content_type, False)


def save_media(*, user_id: str, filename: str, content_type: str, raw: bytes) -> PublishingMedia:
    if content_type not in ALLOWED_MEDIA_TYPES:
        raise HTTPException(status_code=422, detail="Chỉ nhận ảnh JPEG, PNG, WebP hoặc GIF")
    if not raw:
        raise HTTPException(status_code=422, detail="File ảnh rỗng")
    if len(raw) > MAX_MEDIA_BYTES:
        raise HTTPException(status_code=413, detail="Mỗi ảnh tối đa 10 MB")
    if not _looks_like_image(content_type, raw):
        raise HTTPException(status_code=422, detail="Nội dung file không khớp định dạng ảnh")

    media_id = uuid4().hex
    root = Path(get_settings().publishing_media_root).resolve()
    user_dir = root / user_id
    user_dir.mkdir(parents=True, exist_ok=True)
    path = user_dir / f"{media_id}{_extension(content_type, filename)}"
    path.write_bytes(raw)
    return PublishingMedia(
        id=media_id,
        user_id=user_id,
        original_filename=Path(filename or "image").name[:255],
        storage_path=str(path),
        content_type=content_type,
        size_bytes=len(raw),
        sha256=hashlib.sha256(raw).hexdigest(),
    )


def media_reference(media_id: str) -> str:
    return f"media://{media_id}"


def parse_media_reference(reference: str) -> str | None:
    if not isinstance(reference, str) or not reference.startswith("media://"):
        return None
    media_id = reference.removeprefix("media://")
    return media_id if len(media_id) == 32 and all(c in "0123456789abcdef" for c in media_id) else None
