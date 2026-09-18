import hashlib
import sqlite3
import time
from contextlib import closing
from pathlib import Path


XP_PER_MESSAGE = 20
XP_COOLDOWN_SECONDS = 60
DUPLICATE_WINDOW_SECONDS = 600


def xp_for_next(level: int) -> int:
    level = max(0, int(level))
    return 100 + (50 * level) + (5 * level * level)


def level_from_total(total_xp: int):
    total_xp = max(0, int(total_xp))
    level = 0
    remaining = total_xp

    while True:
        needed = xp_for_next(level)
        if remaining < needed:
            return level, remaining, needed
        remaining -= needed
        level += 1


def message_fingerprint(content: str, attachment_names=None) -> str:
    clean = " ".join((content or "").casefold().split())
    attachments = "|".join(sorted(str(x).casefold() for x in (attachment_names or [])))
    raw = f"{clean}\n{attachments}"
    return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()


class LevelStore:
    def __init__(self, path):
        self.path = Path(path)

    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=NORMAL")
        db.execute("PRAGMA busy_timeout=15000")
        return db

    def initialise(self):
        with closing(self.connect()) as db, db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS members (
                    guild_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    total_xp INTEGER NOT NULL DEFAULT 0,
                    last_award REAL,
                    last_hash TEXT,
                    last_hash_at REAL,
                    updated REAL NOT NULL,
                    PRIMARY KEY(guild_id, user_id)
                );

                CREATE INDEX IF NOT EXISTS idx_members_rank
                ON members(guild_id, total_xp DESC, updated ASC);
                """
            )

    def award(
        self,
        guild_id,
        user_id,
        fingerprint,
        *,
        amount=XP_PER_MESSAGE,
        now=None,
        cooldown=XP_COOLDOWN_SECONDS,
        duplicate_window=DUPLICATE_WINDOW_SECONDS,
    ):
        amount = max(0, int(amount))
        if amount <= 0:
            return None

        now = time.time() if now is None else float(now)
        gid = str(guild_id)
        uid = str(user_id)

        with closing(self.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM members WHERE guild_id=? AND user_id=?",
                (gid, uid),
            ).fetchone()

            if row:
                if row["last_award"] is not None and now - float(row["last_award"]) < cooldown:
                    return None
                if (
                    fingerprint
                    and row["last_hash"] == fingerprint
                    and row["last_hash_at"] is not None
                    and now - float(row["last_hash_at"]) < duplicate_window
                ):
                    return None
                before_total = int(row["total_xp"])
            else:
                before_total = 0

            after_total = before_total + amount
            db.execute(
                """
                INSERT INTO members(guild_id, user_id, total_xp, last_award, last_hash, last_hash_at, updated)
                VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(guild_id, user_id) DO UPDATE SET
                    total_xp=excluded.total_xp,
                    last_award=excluded.last_award,
                    last_hash=excluded.last_hash,
                    last_hash_at=excluded.last_hash_at,
                    updated=excluded.updated
                """,
                (gid, uid, after_total, now, fingerprint, now, now),
            )

            before_level, _, _ = level_from_total(before_total)
            after_level, progress, needed = level_from_total(after_total)
            return {
                "awarded": amount,
                "before_total": before_total,
                "total_xp": after_total,
                "before_level": before_level,
                "level": after_level,
                "progress": progress,
                "needed": needed,
                "leveled_up": after_level > before_level,
            }

    def get(self, guild_id, user_id):
        gid = str(guild_id)
        uid = str(user_id)
        with closing(self.connect()) as db:
            row = db.execute(
                "SELECT * FROM members WHERE guild_id=? AND user_id=?",
                (gid, uid),
            ).fetchone()
            total = int(row["total_xp"]) if row else 0
            level, progress, needed = level_from_total(total)
            rank = 1 + int(
                db.execute(
                    """
                    SELECT COUNT(*) FROM members
                    WHERE guild_id=? AND total_xp>?
                    """,
                    (gid, total),
                ).fetchone()[0]
            )
            return {
                "guild_id": gid,
                "user_id": uid,
                "total_xp": total,
                "level": level,
                "progress": progress,
                "needed": needed,
                "rank": rank,
            }

    def leaderboard(self, guild_id, limit=10):
        gid = str(guild_id)
        limit = max(1, min(int(limit), 25))
        with closing(self.connect()) as db:
            rows = db.execute(
                """
                SELECT user_id, total_xp, updated
                FROM members
                WHERE guild_id=?
                ORDER BY total_xp DESC, updated ASC
                LIMIT ?
                """,
                (gid, limit),
            ).fetchall()

            result = []
            for index, row in enumerate(rows, start=1):
                level, progress, needed = level_from_total(int(row["total_xp"]))
                result.append(
                    {
                        "rank": index,
                        "user_id": row["user_id"],
                        "total_xp": int(row["total_xp"]),
                        "level": level,
                        "progress": progress,
                        "needed": needed,
                    }
                )
            return result

    def adjust(self, guild_id, user_id, delta, now=None):
        now = time.time() if now is None else float(now)
        gid = str(guild_id)
        uid = str(user_id)
        delta = int(delta)

        with closing(self.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT total_xp FROM members WHERE guild_id=? AND user_id=?",
                (gid, uid),
            ).fetchone()
            before = int(row["total_xp"]) if row else 0
            after = max(0, before + delta)

            db.execute(
                """
                INSERT INTO members(guild_id, user_id, total_xp, updated)
                VALUES(?,?,?,?)
                ON CONFLICT(guild_id, user_id) DO UPDATE SET
                    total_xp=excluded.total_xp,
                    updated=excluded.updated
                """,
                (gid, uid, after, now),
            )

            level, progress, needed = level_from_total(after)
            return {
                "before_total": before,
                "total_xp": after,
                "level": level,
                "progress": progress,
                "needed": needed,
            }

    def levels(self, guild_id):
        gid = str(guild_id)
        with closing(self.connect()) as db:
            rows = db.execute(
                "SELECT user_id, total_xp FROM members WHERE guild_id=?",
                (gid,),
            ).fetchall()
            return {
                row["user_id"]: level_from_total(int(row["total_xp"]))[0]
                for row in rows
            }

    def stats(self, guild_id):
        gid = str(guild_id)
        with closing(self.connect()) as db:
            return {
                "members": int(
                    db.execute(
                        "SELECT COUNT(*) FROM members WHERE guild_id=?",
                        (gid,),
                    ).fetchone()[0]
                ),
                "total_xp": int(
                    db.execute(
                        "SELECT COALESCE(SUM(total_xp),0) FROM members WHERE guild_id=?",
                        (gid,),
                    ).fetchone()[0]
                ),
                "integrity": db.execute("PRAGMA quick_check").fetchone()[0],
            }
