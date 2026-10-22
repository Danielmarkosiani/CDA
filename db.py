# მონაცემთა ბაზა: SQLite (Python-ის ჩაშენებული sqlite3; დამატებითი პაკეტები არ სჭირდება)
# ძველი cda.db უცვლელად მუშაობს: სტრუქტურა თავისით განახლდება (ახალი სვეტები, ცხრილები, ინდექსები).
# შენიშვნა: ბაზის სვეტი `week` ისტორიულია და ნიშნავს ეტაპის ნომერს.
import contextlib
import glob
import json
import os
import sqlite3
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.environ.get('DB_FILE') or os.path.join(HERE, 'cda.db')
BACKUP_DIR = os.environ.get('BACKUP_DIR') or os.path.join(os.path.dirname(os.path.abspath(DB_FILE)), 'backups')
SCHEMA_VERSION = 3

_lock = threading.RLock()
_c = sqlite3.connect(DB_FILE, check_same_thread=False, isolation_level=None, timeout=10)
_c.row_factory = sqlite3.Row
try:
    os.chmod(DB_FILE, 0o600)  # ბაზა მხოლოდ მფლობელს უნდა იკითხავდეს
except OSError:
    pass


def one(sql, *args):
    with _lock:
        r = _c.execute(sql, args).fetchone()
    return dict(r) if r else None


def all_(sql, *args):
    with _lock:
        return [dict(r) for r in _c.execute(sql, args).fetchall()]


def run(sql, *args):
    with _lock:
        return _c.execute(sql, args).rowcount


@contextlib.contextmanager
def tx():
    """ატომური ტრანზაქცია: ან ყველაფერი შესრულდება, ან არაფერი."""
    with _lock:
        _c.execute('BEGIN IMMEDIATE')
        try:
            yield
        except BaseException:
            _c.execute('ROLLBACK')
            raise
        else:
            _c.execute('COMMIT')


with _lock:
    _c.executescript("""
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA busy_timeout=10000;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT NOT NULL, hash TEXT NOT NULL, salt TEXT NOT NULL, role TEXT DEFAULT 'student', plan TEXT DEFAULT 'free', created INTEGER);
CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, user_id INTEGER NOT NULL, expires INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS lessons(id INTEGER PRIMARY KEY, week INTEGER, pos INTEGER, title TEXT, summary TEXT, task TEXT, free INTEGER DEFAULT 0, video_url TEXT DEFAULT '', pdf_url TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS progress(user_id INTEGER, lesson_id INTEGER, PRIMARY KEY(user_id,lesson_id));
CREATE TABLE IF NOT EXISTS questions(id INTEGER PRIMARY KEY, user_id INTEGER, lesson_id INTEGER, text TEXT, answer TEXT DEFAULT '', created INTEGER);
CREATE TABLE IF NOT EXISTS quiz_results(user_id INTEGER, lesson_id INTEGER, score INTEGER, total INTEGER, PRIMARY KEY(user_id,lesson_id));
CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, plan TEXT NOT NULL, status TEXT DEFAULT 'pending', created INTEGER);
CREATE TABLE IF NOT EXISTS stages(id INTEGER PRIMARY KEY, title TEXT NOT NULL, description TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, user_id INTEGER, action TEXT NOT NULL, detail TEXT DEFAULT '', ip TEXT DEFAULT '', created INTEGER NOT NULL);
""")


def add_col(table, col, ddl):
    if not any(c['name'] == col for c in all_(f'PRAGMA table_info({table})')):
        run(f'ALTER TABLE {table} ADD COLUMN {col} {ddl}')


# მარტივი მიგრაცია: ძველ ბაზებს აკლია სვეტები
add_col('users', 'plan_expires', 'INTEGER')
add_col('users', 'last_login', 'INTEGER')
add_col('lessons', 'content', "TEXT DEFAULT ''")
add_col('lessons', 'quiz', "TEXT DEFAULT '[]'")
add_col('lessons', 'bonus', "TEXT DEFAULT ''")
add_col('lessons', 'objectives', "TEXT DEFAULT '[]'")
add_col('lessons', 'minutes', 'INTEGER DEFAULT 0')
add_col('questions', 'kind', "TEXT DEFAULT 'question'")
add_col('questions', 'answered_at', 'INTEGER')
add_col('progress', 'done_at', 'INTEGER')
add_col('orders', 'amount', 'INTEGER DEFAULT 0')
add_col('orders', 'decided_at', 'INTEGER')
add_col('orders', 'decided_by', 'INTEGER')
with _lock:
    _c.executescript("""
CREATE INDEX IF NOT EXISTS i_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS i_sessions_exp ON sessions(expires);
CREATE INDEX IF NOT EXISTS i_questions_user ON questions(user_id);
CREATE INDEX IF NOT EXISTS i_questions_open ON questions(answer, id);
CREATE INDEX IF NOT EXISTS i_progress_lesson ON progress(lesson_id);
CREATE INDEX IF NOT EXISTS i_quiz_lesson ON quiz_results(lesson_id);
CREATE INDEX IF NOT EXISTS i_orders_user ON orders(user_id, status);
CREATE INDEX IF NOT EXISTS i_users_created ON users(created);
CREATE INDEX IF NOT EXISTS i_audit_created ON audit(created);
CREATE UNIQUE INDEX IF NOT EXISTS i_lessons_wp ON lessons(week,pos);
UPDATE users SET plan='start' WHERE plan='active';
""")

# სქემის ვერსია. v1: სესიის ტოკენები ჰეშირებულია (ძველი ღია სესიები ერთხელ იშლება)
_v = (one('PRAGMA user_version') or {}).get('user_version', 0)
if _v < 1:
    run('DELETE FROM sessions')
if _v < SCHEMA_VERSION:
    run(f'PRAGMA user_version={SCHEMA_VERSION}')


def audit(user_id, action, detail='', ip=''):
    run('INSERT INTO audit(user_id,action,detail,ip,created) VALUES(?,?,?,?,?)',
        user_id, action, str(detail)[:300], str(ip)[:64], int(time.time() * 1000))


def backup():
    """ბაზის თანმიმდევრული ასლი (SQLite backup API); ინახება ბოლო 14."""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    path = os.path.join(BACKUP_DIR, time.strftime('cda-%Y%m%d-%H%M%S.db'))
    dst = sqlite3.connect(path)
    try:
        with _lock:
            _c.backup(dst)
    finally:
        dst.close()
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    for old in sorted(glob.glob(os.path.join(BACKUP_DIR, 'cda-*.db')))[:-14]:
        try:
            os.remove(old)
        except OSError:
            pass
    return os.path.basename(path)


def last_backup_age():
    files = glob.glob(os.path.join(BACKUP_DIR, 'cda-*.db'))
    return time.time() - max((os.path.getmtime(f) for f in files), default=0)


# კურსის მასალა იტვირთება/ახლდება content.json-იდან; ადმინის მიერ ჩასმული ვიდეო და PDF ბმულები არ იშლება
with open(os.path.join(HERE, 'content.json'), encoding='utf-8') as f:
    COURSE = json.load(f)

_UPSERT = ('INSERT INTO lessons(week,pos,title,summary,task,free,content,quiz,bonus,objectives,minutes) VALUES(?,?,?,?,?,?,?,?,?,?,?) '
           'ON CONFLICT(week,pos) DO UPDATE SET title=excluded.title, summary=excluded.summary, task=excluded.task, '
           'free=excluded.free, content=excluded.content, quiz=excluded.quiz, bonus=excluded.bonus, '
           'objectives=excluded.objectives, minutes=excluded.minutes')
_dumps = lambda v: json.dumps(v, ensure_ascii=False, separators=(',', ':'))  # noqa: E731
with tx():
    for s in COURSE:
        n = s.get('stage', s.get('week'))  # ძველი ფორმატის (week) მხარდაჭერა
        run('INSERT INTO stages(id,title,description) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET '
            'title=excluded.title, description=excluded.description', n, s['title'], s.get('description', ''))
        for j, l in enumerate(s['lessons']):
            run(_UPSERT, n, j + 1, l['title'], s['title'], l['task'], 1 if n == 1 else 0, l['content'],
                _dumps(l['quiz']), l.get('bonus', ''), _dumps(l.get('objectives', [])), int(l.get('minutes', 0)))
