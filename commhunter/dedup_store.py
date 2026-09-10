"""
Dedup Store — Lưu trữ trạng thái bài viết đã xử lý bằng SQLite.
Kế thừa pattern từ fbn/state.py + openclaw post_hash.
"""
import hashlib
import sqlite3
from datetime import datetime, date
from pathlib import Path
from typing import Optional

from loguru import logger

from constants import DEFAULT_DB_PATH
from models import DiscoveredPost, PostStatus, CommentStatus

# Whitelist các cột thống kê hàng ngày hợp lệ (phòng chống SQL injection N-10)
ALLOWED_STAT_COLUMNS = {
    "posts_scanned",
    "posts_matched",
    "comments_sent",
    "comments_success",
    "comments_failed",
}


# ── Schema ──────────────────────────────────────────────────────────────────
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS discovered_posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content_hash TEXT UNIQUE NOT NULL,
    post_id_fb TEXT,
    post_url TEXT,
    group_url TEXT NOT NULL,
    group_name TEXT,
    author_name TEXT,
    content_text TEXT,
    existing_comment_count INTEGER DEFAULT 0,
    ai_relevance_score REAL DEFAULT 0.0,
    ai_reason TEXT,
    status TEXT DEFAULT 'new',
    discovered_at TEXT NOT NULL,
    notified_at TEXT,
    commented_at TEXT
);

CREATE TABLE IF NOT EXISTS comment_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_hash TEXT NOT NULL,
    comment_content TEXT NOT NULL,
    status TEXT DEFAULT 'queued',
    error_message TEXT,
    scheduled_at TEXT,
    executed_at TEXT
);

CREATE TABLE IF NOT EXISTS daily_stats (
    date TEXT PRIMARY KEY,
    posts_scanned INTEGER DEFAULT 0,
    posts_matched INTEGER DEFAULT 0,
    comments_sent INTEGER DEFAULT 0,
    comments_success INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_posts_hash ON discovered_posts(content_hash);
CREATE INDEX IF NOT EXISTS idx_posts_status ON discovered_posts(status);
CREATE INDEX IF NOT EXISTS idx_posts_group ON discovered_posts(group_url);
CREATE INDEX IF NOT EXISTS idx_comments_post ON comment_actions(post_hash);
"""


def compute_content_hash(author: str, text: str) -> str:
    """Tính MD5 hash cho dedup, dùng author:text[:200]."""
    content = f"{author}:{text[:200]}"
    return hashlib.md5(content.encode("utf-8")).hexdigest()


def row_to_post(row) -> DiscoveredPost:
    """Chuyển 1 dòng sqlite3.Row của discovered_posts thành DiscoveredPost."""
    try:
        discovered_at = datetime.fromisoformat(row["discovered_at"])
    except (TypeError, ValueError):
        discovered_at = datetime.now()

    try:
        status = PostStatus(row["status"])
    except ValueError:
        status = PostStatus.NEW

    return DiscoveredPost(
        post_id=row["post_id_fb"] or "",
        post_url=row["post_url"] or "",
        group_url=row["group_url"] or "",
        group_name=row["group_name"] or "",
        author_name=row["author_name"] or "Unknown",
        content_text=row["content_text"] or "",
        existing_comment_count=row["existing_comment_count"] or 0,
        ai_relevance_score=row["ai_relevance_score"] or 0.0,
        ai_reason=row["ai_reason"] or "",
        status=status,
        discovered_at=discovered_at,
        content_hash=row["content_hash"],
    )


class DedupStore:
    """SQLite-backed store cho dedup, tracking trạng thái bài viết và thống kê.
    
    LƯU Ý ĐƠN LUỒNG (Single-Thread Concurrency Constraint - N-13):
    Class này sử dụng một kết nối sqlite3 đồng bộ duy nhất trên event loop chính (check_same_thread=True).
    Mô hình hiện tại an toàn tuyệt đối vì toàn bộ coroutine trong asyncio chạy trên cùng một thread.
    Khi chuyển sang Phase 2 với Celery background workers đa tiến trình/luồng, mỗi worker process
    bắt buộc phải sở hữu connection riêng hoặc chuyển sang connection pool bất đồng bộ (PostgreSQL/asyncpg).
    """

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()
        logger.info(f"DedupStore khởi tạo tại {db_path}")

    def _init_schema(self):
        """Tạo bảng nếu chưa tồn tại."""
        self.conn.executescript(SCHEMA_SQL)
        self.conn.commit()

    def close(self):
        """Đóng kết nối database."""
        self.conn.close()

    # ── Dedup ────────────────────────────────────────────────────────────
    def is_seen(self, content_hash: str) -> bool:
        """Kiểm tra bài viết đã được xử lý chưa (< 1ms)."""
        cur = self.conn.execute(
            "SELECT 1 FROM discovered_posts WHERE content_hash = ?",
            (content_hash,),
        )
        return cur.fetchone() is not None

    def insert_post(self, post: DiscoveredPost) -> bool:
        """Lưu bài viết mới. Trả về True nếu insert thành công, False nếu đã tồn tại."""
        try:
            self.conn.execute(
                """INSERT INTO discovered_posts 
                   (content_hash, post_id_fb, post_url, group_url, group_name,
                    author_name, content_text, existing_comment_count,
                    ai_relevance_score, ai_reason, status, discovered_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    post.content_hash,
                    post.post_id,
                    post.post_url,
                    post.group_url,
                    post.group_name,
                    post.author_name,
                    post.content_text,
                    post.existing_comment_count,
                    post.ai_relevance_score,
                    post.ai_reason,
                    post.status.value,
                    post.discovered_at.isoformat(),
                ),
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    # ── Status Updates ───────────────────────────────────────────────────
    def mark_notified(self, post: DiscoveredPost):
        """Đánh dấu bài viết đã gửi thông báo Telegram."""
        self.conn.execute(
            "UPDATE discovered_posts SET status = ?, notified_at = ? WHERE content_hash = ?",
            (PostStatus.NOTIFIED.value, datetime.now().isoformat(), post.content_hash),
        )
        self.conn.commit()

    def record_attempt(self, post_hash: str, comment_text: str) -> int:
        """Ghi nhận một lượt bắt đầu thực thi comment (trước cả warmup).
        
        Returns:
            id (int) của bản ghi comment_actions vừa tạo để cập nhật sau này.
        """
        now = datetime.now().isoformat()
        cur = self.conn.execute(
            "INSERT INTO comment_actions (post_hash, comment_content, status, executed_at) VALUES (?, ?, ?, ?)",
            (post_hash, comment_text, CommentStatus.IN_PROGRESS.value, now),
        )
        self.conn.commit()
        return cur.lastrowid

    def finish_attempt(
        self,
        attempt_id: int,
        status: CommentStatus,
        error: Optional[str] = None,
    ) -> None:
        """Cập nhật kết quả cuối cùng cho một lượt thực thi comment."""
        status_str = status.value if isinstance(status, CommentStatus) else str(status)
        now = datetime.now().isoformat()
        self.conn.execute(
            "UPDATE comment_actions SET status = ?, error_message = ?, executed_at = ? WHERE id = ?",
            (status_str, error, now, attempt_id),
        )
        self.conn.commit()

    def mark_commented(self, post: DiscoveredPost, comment_text: str = ""):
        """Đánh dấu bài viết đã comment thành công (bản ghi comment_actions đã được cập nhật bởi finish_attempt)."""
        now = datetime.now().isoformat()
        self.conn.execute(
            "UPDATE discovered_posts SET status = ?, commented_at = ? WHERE content_hash = ?",
            (PostStatus.COMMENTED.value, now, post.content_hash),
        )
        self.conn.commit()
        self._increment_daily_stat("comments_success")

    def mark_skipped(self, post: DiscoveredPost, reason: str = ""):
        """Đánh dấu bài viết bị bỏ qua."""
        self.conn.execute(
            "UPDATE discovered_posts SET status = ?, ai_reason = ? WHERE content_hash = ?",
            (PostStatus.SKIPPED.value, reason, post.content_hash),
        )
        self.conn.commit()

    def mark_comment_failed(self, post_hash: str, comment_text: str, error: str):
        """Ghi nhận comment thất bại."""
        self.conn.execute(
            "INSERT INTO comment_actions (post_hash, comment_content, status, error_message, executed_at) VALUES (?, ?, ?, ?, ?)",
            (post_hash, comment_text, "failed", error, datetime.now().isoformat()),
        )
        self.conn.commit()

    # ── Query ────────────────────────────────────────────────────────────
    def get_today_action_count(self) -> int:
        """Đếm tổng số LƯỢT thao tác hôm nay (bất kể thành công hay thất bại).
        
        Đây là hàm gác quota mới theo N-04.
        """
        today = date.today().isoformat()
        cur = self.conn.execute(
            "SELECT COUNT(*) FROM comment_actions WHERE executed_at LIKE ?",
            (f"{today}%",),
        )
        return cur.fetchone()[0]

    def get_today_comment_count(self) -> int:
        """Đếm số comment đã gửi hôm nay."""
        today = date.today().isoformat()
        cur = self.conn.execute(
            "SELECT COUNT(*) FROM comment_actions WHERE status = 'success' AND executed_at LIKE ?",
            (f"{today}%",),
        )
        return cur.fetchone()[0]

    def get_consecutive_failures(self, lookback: int = 10) -> int:
        """Đếm số lượt thất bại liên tiếp tính từ dòng mới nhất về trước."""
        cur = self.conn.execute(
            "SELECT status FROM comment_actions WHERE status != ? ORDER BY id DESC LIMIT ?",
            (CommentStatus.IN_PROGRESS.value, lookback),
        )
        count = 0
        for row in cur.fetchall():
            if row["status"] == CommentStatus.SUCCESS.value:
                break
            count += 1
        return count

    def get_post_by_hash(self, content_hash: str) -> Optional[DiscoveredPost]:
        """Dựng lại DiscoveredPost từ DB theo content_hash.

        Cần cho luồng Semi-Auto: callback Telegram chỉ mang theo content_hash,
        orchestrator phải tra ngược ra bài viết đầy đủ để sinh comment.

        Returns:
            DiscoveredPost, hoặc None nếu không tìm thấy.
        """
        cur = self.conn.execute(
            "SELECT * FROM discovered_posts WHERE content_hash = ?",
            (content_hash,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return row_to_post(row)

    def get_pending_posts(self, limit: int = 10) -> list:
        """Lấy bài viết đang chờ xử lý (status = notified, chưa comment)."""
        cur = self.conn.execute(
            "SELECT * FROM discovered_posts WHERE status = ? ORDER BY discovered_at DESC LIMIT ?",
            (PostStatus.NOTIFIED.value, limit),
        )
        return [dict(row) for row in cur.fetchall()]

    def get_stats(self) -> dict:
        """Thống kê tổng quan."""
        stats = {}
        for status in PostStatus:
            cur = self.conn.execute(
                "SELECT COUNT(*) FROM discovered_posts WHERE status = ?",
                (status.value,),
            )
            stats[status.value] = cur.fetchone()[0]

        stats["today_comments"] = self.get_today_comment_count()
        stats["today_actions"] = self.get_today_action_count()
        stats["consecutive_failures"] = self.get_consecutive_failures()

        today = date.today().isoformat()
        cur = self.conn.execute(
            "SELECT * FROM daily_stats WHERE date = ?", (today,)
        )
        row = cur.fetchone()
        if row:
            stats["today_scanned"] = row["posts_scanned"]
            stats["today_matched"] = row["posts_matched"]
        else:
            stats["today_scanned"] = 0
            stats["today_matched"] = 0

        return stats

    # ── Daily Stats ──────────────────────────────────────────────────────
    def _increment_daily_stat(self, column: str, amount: int = 1):
        """Tăng giá trị thống kê hàng ngày với kiểm tra whitelist tên cột."""
        if column not in ALLOWED_STAT_COLUMNS:
            raise ValueError(
                f"Cột thống kê '{column}' không hợp lệ. Chỉ chấp nhận các cột trong whitelist: {ALLOWED_STAT_COLUMNS}"
            )
        today = date.today().isoformat()
        self.conn.execute(
            f"""INSERT INTO daily_stats (date, {column}) VALUES (?, ?)
                ON CONFLICT(date) DO UPDATE SET {column} = {column} + ?""",
            (today, amount, amount),
        )
        self.conn.commit()

    def increment_scanned(self, amount: int = 1):
        """Tăng số bài đã quét."""
        self._increment_daily_stat("posts_scanned", amount)

    def increment_matched(self, amount: int = 1):
        """Tăng số bài phù hợp."""
        self._increment_daily_stat("posts_matched", amount)

    def increment_comments_sent(self, amount: int = 1):
        """Tăng số comment đã gửi."""
        self._increment_daily_stat("comments_sent", amount)
