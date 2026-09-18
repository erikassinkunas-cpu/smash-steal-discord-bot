import sqlite3
import time
from contextlib import closing
from pathlib import Path


class ModerationError(Exception):
    pass


class ModerationStore:
    def __init__(self, path):
        self.path = Path(path)

    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=NORMAL")
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=15000")
        return db

    def initialise(self):
        with closing(self.connect()) as db, db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS warnings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    moderator_id TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    source TEXT NOT NULL,
                    created REAL NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    cleared_by TEXT,
                    cleared_at REAL
                );

                CREATE INDEX IF NOT EXISTS idx_warnings_member
                ON warnings(guild_id, user_id, active, id DESC);

                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )

    def add_warning(self, guild_id, user_id, moderator_id, reason, source, now=None):
        reason = (reason or "").strip()
        source = (source or "manual").strip().lower()
        if not 3 <= len(reason) <= 400:
            raise ModerationError("Warning reason must be 3 to 400 characters.")
        if not 2 <= len(source) <= 64:
            raise ModerationError("Invalid warning source.")
        created = time.time() if now is None else float(now)
        with closing(self.connect()) as db, db:
            cur = db.execute(
                """
                INSERT INTO warnings(guild_id, user_id, moderator_id, reason, source, created)
                VALUES(?,?,?,?,?,?)
                """,
                (str(guild_id), str(user_id), str(moderator_id), reason, source, created),
            )
            count = db.execute(
                """
                SELECT COUNT(*) FROM warnings
                WHERE guild_id=? AND user_id=? AND active=1
                """,
                (str(guild_id), str(user_id)),
            ).fetchone()[0]
            row = db.execute("SELECT * FROM warnings WHERE id=?", (cur.lastrowid,)).fetchone()
            return dict(row), int(count)

    def active_count(self, guild_id, user_id):
        with closing(self.connect()) as db:
            return int(
                db.execute(
                    """
                    SELECT COUNT(*) FROM warnings
                    WHERE guild_id=? AND user_id=? AND active=1
                    """,
                    (str(guild_id), str(user_id)),
                ).fetchone()[0]
            )

    def list_warnings(self, guild_id, user_id, active_only=True, limit=20):
        limit = max(1, min(int(limit), 50))
        where = "AND active=1" if active_only else ""
        with closing(self.connect()) as db:
            rows = db.execute(
                f"""
                SELECT * FROM warnings
                WHERE guild_id=? AND user_id=? {where}
                ORDER BY id DESC
                LIMIT ?
                """,
                (str(guild_id), str(user_id), limit),
            ).fetchall()
            return [dict(row) for row in rows]

    def clear_warning(self, guild_id, user_id, warning_id, actor_id, now=None):
        cleared_at = time.time() if now is None else float(now)
        with closing(self.connect()) as db, db:
            cur = db.execute(
                """
                UPDATE warnings
                SET active=0, cleared_by=?, cleared_at=?
                WHERE id=? AND guild_id=? AND user_id=? AND active=1
                """,
                (
                    str(actor_id),
                    cleared_at,
                    int(warning_id),
                    str(guild_id),
                    str(user_id),
                ),
            )
            return cur.rowcount == 1

    def clear_all(self, guild_id, user_id, actor_id, now=None):
        cleared_at = time.time() if now is None else float(now)
        with closing(self.connect()) as db, db:
            cur = db.execute(
                """
                UPDATE warnings
                SET active=0, cleared_by=?, cleared_at=?
                WHERE guild_id=? AND user_id=? AND active=1
                """,
                (str(actor_id), cleared_at, str(guild_id), str(user_id)),
            )
            return int(cur.rowcount)

    def stats(self):
        with closing(self.connect()) as db:
            return {
                "active_warnings": int(
                    db.execute("SELECT COUNT(*) FROM warnings WHERE active=1").fetchone()[0]
                ),
                "total_warnings": int(
                    db.execute("SELECT COUNT(*) FROM warnings").fetchone()[0]
                ),
                "members_with_warnings": int(
                    db.execute(
                        """
                        SELECT COUNT(DISTINCT user_id) FROM warnings
                        WHERE active=1
                        """
                    ).fetchone()[0]
                ),
                "integrity": db.execute("PRAGMA quick_check").fetchone()[0],
            }
