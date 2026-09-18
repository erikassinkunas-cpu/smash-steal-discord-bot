"""Transactional, persistent storage for the Smash & Steal community features."""
import json
import sqlite3
import time
from contextlib import closing
from pathlib import Path


class CommunityError(ValueError):
    """A validation error that is safe to show to a Discord user."""


def validate(kind, body, choices=None):
    body = body.strip()
    if kind == 'suggestion':
        if not 10 <= len(body) <= 1600:
            raise CommunityError('Write a suggestion between 10 and 1600 characters.')
        return body, ['Support', 'Oppose']
    if kind != 'poll':
        raise CommunityError('Unknown item type.')
    if not 5 <= len(body) <= 200:
        raise CommunityError('The poll question must contain 5 to 200 characters.')
    options = [str(x).strip() for x in (choices or [])]
    if not 2 <= len(options) <= 10 or any(not 1 <= len(x) <= 80 for x in options):
        raise CommunityError('Use 2 to 10 options, each containing 1 to 80 characters.')
    if len({x.casefold() for x in options}) != len(options):
        raise CommunityError('Poll options must be different.')
    return body, options


def code(item):
    prefix = 'SUG' if item['kind'] == 'suggestion' else 'POLL'
    return f"{prefix}-{item['number']:03d}"


class Store:
    def __init__(self, path):
        self.path = str(path)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        return db

    def initialise(self):
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as db, db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript('''
                CREATE TABLE IF NOT EXISTS counters(kind TEXT PRIMARY KEY, value INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS items(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL, number INTEGER NOT NULL,
                    guild_id TEXT NOT NULL, channel_id TEXT NOT NULL,
                    message_id TEXT UNIQUE, author_id TEXT NOT NULL,
                    body TEXT NOT NULL, choices TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'open',
                    reason TEXT NOT NULL DEFAULT '', actor_id TEXT,
                    created REAL NOT NULL, closes REAL, source_id TEXT UNIQUE,
                    revision INTEGER NOT NULL DEFAULT 1,
                    dirty INTEGER NOT NULL DEFAULT 1,
                    UNIQUE(kind, number)
                );
                CREATE TABLE IF NOT EXISTS votes(
                    item_id INTEGER NOT NULL REFERENCES items(id),
                    voter_id TEXT NOT NULL, choice INTEGER NOT NULL,
                    PRIMARY KEY(item_id, voter_id)
                );
                CREATE TABLE IF NOT EXISTS decisions(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_id INTEGER NOT NULL REFERENCES items(id),
                    actor_id TEXT NOT NULL, status TEXT NOT NULL,
                    reason TEXT NOT NULL, created REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS item_author ON items(kind, author_id, created);
                CREATE INDEX IF NOT EXISTS item_dirty ON items(dirty, id);
            ''')

    def _snapshot(self, db, row):
        if row is None:
            raise CommunityError('That suggestion or poll was not found.')
        result = dict(row)
        result['choices'] = json.loads(result['choices'])
        counts = [0] * len(result['choices'])
        for vote in db.execute('SELECT choice, COUNT(*) AS n FROM votes WHERE item_id=? GROUP BY choice', (result['id'],)):
            if 0 <= vote['choice'] < len(counts):
                counts[vote['choice']] = vote['n']
        result['counts'] = counts
        return result

    def get(self, item_id):
        with closing(self.connect()) as db:
            return self._snapshot(db, db.execute('SELECT * FROM items WHERE id=?', (item_id,)).fetchone())

    def lookup(self, value, kind):
        prefix = 'SUG-' if kind == 'suggestion' else 'POLL-'
        raw = value.strip().upper()
        if raw.startswith(prefix):
            raw = raw[len(prefix):]
        if not raw.isascii() or not raw.isdigit() or len(raw) > 9:
            raise CommunityError(f'Use an ID such as {prefix}001.')
        with closing(self.connect()) as db:
            return self._snapshot(db, db.execute('SELECT * FROM items WHERE kind=? AND number=?', (kind, int(raw))).fetchone())

    def create(self, kind, guild_id, channel_id, author_id, body, choices=None,
               hours=24, source_id=None, now=None):
        body, choices = validate(kind, body, choices)
        now = time.time() if now is None else now
        if kind == 'poll' and (not isinstance(hours, int) or not 1 <= hours <= 168):
            raise CommunityError('Poll duration must be 1 to 168 hours.')
        with closing(self.connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            if source_id:
                existing = db.execute('SELECT * FROM items WHERE source_id=?', (str(source_id),)).fetchone()
                if existing:
                    return self._snapshot(db, existing)
            last = db.execute('SELECT MAX(created) FROM items WHERE kind=? AND author_id=?', (kind, str(author_id))).fetchone()[0]
            cooldown = 60 if kind == 'suggestion' else 10
            if last is not None and now - last < cooldown:
                raise CommunityError(f'Please wait {max(1, int(cooldown - (now - last)) + 1)} seconds before posting again.')
            db.execute('INSERT OR IGNORE INTO counters(kind, value) VALUES(?, 0)', (kind,))
            db.execute('UPDATE counters SET value=value+1 WHERE kind=?', (kind,))
            number = db.execute('SELECT value FROM counters WHERE kind=?', (kind,)).fetchone()[0]
            cur = db.execute('''INSERT INTO items(kind, number, guild_id, channel_id, author_id, body, choices, created, closes, source_id)
                                VALUES(?,?,?,?,?,?,?,?,?,?)''',
                             (kind, number, str(guild_id), str(channel_id), str(author_id), body,
                              json.dumps(choices, ensure_ascii=False), now,
                              now + hours * 3600 if kind == 'poll' else None,
                              str(source_id) if source_id else None))
            return self._snapshot(db, db.execute('SELECT * FROM items WHERE id=?', (cur.lastrowid,)).fetchone())

    def attach(self, item_id, message_id):
        with closing(self.connect()) as db, db:
            db.execute('UPDATE items SET message_id=? WHERE id=? AND message_id IS NULL', (str(message_id), item_id))

    def mark_rendered(self, item_id, revision):
        with closing(self.connect()) as db, db:
            db.execute('UPDATE items SET dirty=0 WHERE id=? AND revision=?', (item_id, revision))

    def missing(self, item_id):
        with closing(self.connect()) as db, db:
            db.execute("UPDATE items SET status='removed', dirty=0, revision=revision+1 WHERE id=?", (item_id,))

    def vote(self, item_id, voter_id, choice, guild_id, channel_id, message_id, now=None):
        now = time.time() if now is None else now
        with closing(self.connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            item = self._snapshot(db, db.execute('SELECT * FROM items WHERE id=?', (item_id,)).fetchone())
            if (item['guild_id'], item['channel_id'], item['message_id']) != (str(guild_id), str(channel_id), str(message_id)):
                raise CommunityError('This is not the original voting message.')
            if item['status'] != 'open' or (item['closes'] is not None and now >= item['closes']):
                raise CommunityError('Voting has ended for this item.')
            if type(choice) is not int or not -1 <= choice < len(item['choices']):
                raise CommunityError('Invalid voting option.')
            if choice == -1:
                db.execute('DELETE FROM votes WHERE item_id=? AND voter_id=?', (item_id, str(voter_id)))
                action = 'Your vote has been removed.'
            else:
                db.execute('''INSERT INTO votes(item_id, voter_id, choice) VALUES(?,?,?)
                              ON CONFLICT(item_id, voter_id) DO UPDATE SET choice=excluded.choice''',
                           (item_id, str(voter_id), choice))
                action = 'Your vote has been saved. You can change or remove it.'
            db.execute('UPDATE items SET dirty=1, revision=revision+1 WHERE id=?', (item_id,))
            return action

    def decide(self, item_id, status, actor_id, reason, guild_id):
        reason = reason.strip()
        if not 3 <= len(reason) <= 400:
            raise CommunityError('Give a reason between 3 and 400 characters.')
        with closing(self.connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            item = self._snapshot(db, db.execute('SELECT * FROM items WHERE id=?', (item_id,)).fetchone())
            if item['guild_id'] != str(guild_id) or item['status'] == 'removed':
                raise CommunityError('That item is unavailable.')
            allowed = {'accepted', 'planned', 'denied'} if item['kind'] == 'suggestion' else {'closed'}
            if status not in allowed:
                raise CommunityError('Invalid status for this item.')
            db.execute('UPDATE items SET status=?, actor_id=?, reason=?, revision=revision+1, dirty=1 WHERE id=?',
                       (status, str(actor_id), reason, item_id))
            db.execute('INSERT INTO decisions(item_id, actor_id, status, reason, created) VALUES(?,?,?,?,?)',
                       (item_id, str(actor_id), status, reason, time.time()))

    def expire(self, now=None):
        now = time.time() if now is None else now
        with closing(self.connect()) as db, db:
            return db.execute("UPDATE items SET status='closed', reason='Voting period ended.', dirty=1, revision=revision+1 WHERE kind='poll' AND status='open' AND closes<=?", (now,)).rowcount

    def rows(self, dirty_only=False):
        sql = 'SELECT * FROM items WHERE dirty=1 ORDER BY id LIMIT 25' if dirty_only else "SELECT * FROM items WHERE status='open' OR dirty=1 ORDER BY id"
        with closing(self.connect()) as db:
            return [self._snapshot(db, row) for row in db.execute(sql).fetchall()]

    def meta(self, key, value=None):
        with closing(self.connect()) as db, db:
            if value is not None:
                db.execute('INSERT INTO metadata(key, value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, str(value)))
                return str(value)
            row = db.execute('SELECT value FROM metadata WHERE key=?', (key,)).fetchone()
            return row[0] if row else None

    def stats(self):
        with closing(self.connect()) as db:
            counts = {row['kind']: row['n'] for row in db.execute('SELECT kind, COUNT(*) AS n FROM items GROUP BY kind')}
            counts['votes'] = db.execute('SELECT COUNT(*) FROM votes').fetchone()[0]
            counts['pending'] = db.execute('SELECT COUNT(*) FROM items WHERE dirty=1').fetchone()[0]
            counts['integrity'] = db.execute('PRAGMA quick_check').fetchone()[0]
            return counts
