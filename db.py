# მონაცემთა ბაზა: SQLite (Python-ის ჩაშენებული sqlite3; დამატებითი პაკეტები არ სჭირდება)
# ძველი cda.db უცვლელად მუშაობს: სტრუქტურა თავისით განახლდება (ახალი სვეტები, ცხრილები, ინდექსები).
# შენიშვნა: ბაზის სვეტი `week` ისტორიულია და ნიშნავს ეტაპის ნომერს.
import envfile  # noqa: F401  (.env-ის ჩატვირთვა: DB_FILE და BACKUP_DIR შეიძლება იქ იყოს)
import contextlib
import glob
import json
import os
import sqlite3
import threading
import time

import courses

HERE = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.environ.get('DB_FILE') or os.path.join(HERE, 'cda.db')
BACKUP_DIR = os.environ.get('BACKUP_DIR') or os.path.join(os.path.dirname(os.path.abspath(DB_FILE)), 'backups')
SCHEMA_VERSION = 9  # v9: მრავალი კურსი (lessons.course, stages(course,id), certificates.course_id, უნიკალური (course,week,pos)). v8: codes (6-ნიშნა კოდები დადასტურებისა და პაროლის აღდგენისთვის). v7: quiz_attempts.finished_at (პაუზა წარუმატებელი მცდელობების შემდეგ). v4: email_verified, tokens. v5: quiz_attempts, quiz_results.passed, questions.status, certificates, users.notify. v6: ვიდეოს სათაური/არხი და სათადარიგო ვიდეო

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


def _backup_to(path):
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


# სქემის შეცვლამდე არსებულ ბაზას ვინახავთ. ფაილის სახელი არ ემთხვევა `cda-*.db`-ს, ამიტომ ყოველდღიური ბექაფის
# როტაცია (ბოლო 14) მას არასოდეს წაშლის.
_v = (one('PRAGMA user_version') or {}).get('user_version', 0)
if one("SELECT 1 FROM sqlite_master WHERE type='table' AND name='users'") and _v < SCHEMA_VERSION:
    os.makedirs(BACKUP_DIR, exist_ok=True)
    PREMIGRATION_BACKUP = os.path.join(BACKUP_DIR, time.strftime(f'premigrate-v{_v}-%Y%m%d-%H%M%S.db'))
    _backup_to(PREMIGRATION_BACKUP)
    print('db: სქემის განახლებამდე ბექაფი შენახულია:', PREMIGRATION_BACKUP)
else:
    PREMIGRATION_BACKUP = None

with _lock:
    _c.executescript("""
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA busy_timeout=10000;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT NOT NULL, hash TEXT NOT NULL, salt TEXT NOT NULL, role TEXT DEFAULT 'student', plan TEXT DEFAULT 'free', created INTEGER);
CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, user_id INTEGER NOT NULL, expires INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS lessons(id INTEGER PRIMARY KEY, course TEXT NOT NULL DEFAULT 'cybersecurity-beginners', week INTEGER, pos INTEGER, title TEXT, summary TEXT, task TEXT, free INTEGER DEFAULT 0, video_url TEXT DEFAULT '', pdf_url TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS progress(user_id INTEGER, lesson_id INTEGER, PRIMARY KEY(user_id,lesson_id));
CREATE TABLE IF NOT EXISTS questions(id INTEGER PRIMARY KEY, user_id INTEGER, lesson_id INTEGER, text TEXT, answer TEXT DEFAULT '', created INTEGER);
CREATE TABLE IF NOT EXISTS quiz_results(user_id INTEGER, lesson_id INTEGER, score INTEGER, total INTEGER, PRIMARY KEY(user_id,lesson_id));
CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, plan TEXT NOT NULL, status TEXT DEFAULT 'pending', created INTEGER);
CREATE TABLE IF NOT EXISTS stages(course TEXT NOT NULL DEFAULT 'cybersecurity-beginners', id INTEGER NOT NULL, title TEXT NOT NULL, description TEXT DEFAULT '', PRIMARY KEY(course,id));
CREATE TABLE IF NOT EXISTS tokens(hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL, kind TEXT NOT NULL, expires INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS codes(user_id INTEGER NOT NULL, kind TEXT NOT NULL, salt TEXT NOT NULL, hash TEXT NOT NULL, expires INTEGER NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, hour_start INTEGER NOT NULL DEFAULT 0, hour_sends INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(user_id,kind));
CREATE TABLE IF NOT EXISTS quiz_attempts(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, lesson_id INTEGER NOT NULL, created INTEGER NOT NULL, items TEXT NOT NULL, finished INTEGER DEFAULT 0, score INTEGER, total INTEGER, passed INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS certificates(id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, name TEXT NOT NULL, issued INTEGER NOT NULL, course TEXT NOT NULL, course_id TEXT NOT NULL DEFAULT 'cybersecurity-beginners', UNIQUE(user_id,course_id));
CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, user_id INTEGER, action TEXT NOT NULL, detail TEXT DEFAULT '', ip TEXT DEFAULT '', created INTEGER NOT NULL);
""")


def add_col(table, col, ddl):
    """ამატებს სვეტს, თუ არ არსებობს. აბრუნებს True-ს, თუ ახლა დაემატა."""
    if not any(c['name'] == col for c in all_(f'PRAGMA table_info({table})')):
        run(f'ALTER TABLE {table} ADD COLUMN {col} {ddl}')
        return True
    return False


# მარტივი მიგრაცია: ძველ ბაზებს აკლია სვეტები
add_col('users', 'plan_expires', 'INTEGER')
add_col('users', 'last_login', 'INTEGER')
# ელფოსტის დადასტურების შემოღებისას ყველა უკვე არსებული მომხმარებელი (ადმინის ჩათვლით) დადასტურებულად ითვლება
if add_col('users', 'email_verified', 'INTEGER DEFAULT 0'):
    run('UPDATE users SET email_verified=1')
add_col('lessons', 'content', "TEXT DEFAULT ''")
add_col('lessons', 'quiz', "TEXT DEFAULT '[]'")
add_col('lessons', 'bonus', "TEXT DEFAULT ''")
add_col('lessons', 'objectives', "TEXT DEFAULT '[]'")
add_col('lessons', 'minutes', 'INTEGER DEFAULT 0')
add_col('lessons', 'exercises', "TEXT DEFAULT '[]'")
if add_col('quiz_attempts', 'finished_at', 'INTEGER'):
    run('UPDATE quiz_attempts SET finished_at=created WHERE finished=1')
for _c_ in ('video_title', 'video_channel', 'video2_url', 'video2_title', 'video2_channel'):  # ვიდეოს მითითება გაკვეთილის გვერდზე + სათადარიგო ვიდეო
    add_col('lessons', _c_, "TEXT DEFAULT ''")
add_col('questions', 'kind', "TEXT DEFAULT 'question'")
add_col('questions', 'status', "TEXT DEFAULT ''")  # '' = მოლოდინში, 'approved' = მენტორმა დაადასტურა
add_col('users', 'notify', 'INTEGER DEFAULT 1')   # ელფოსტით შეტყობინებები პასუხზე
add_col('questions', 'answered_at', 'INTEGER')
add_col('progress', 'done_at', 'INTEGER')
# ქვიზის „გავლილია“ (>=70%) ახლა ცალკე ინახება; უკვე არსებული შედეგებიდან გამოითვლება ერთხელ
if add_col('quiz_results', 'passed', 'INTEGER DEFAULT 0'):
    run('UPDATE quiz_results SET passed=CASE WHEN total>0 AND score*10>=total*7 THEN 1 ELSE 0 END')
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
CREATE INDEX IF NOT EXISTS i_tokens_user ON tokens(user_id, kind);
CREATE INDEX IF NOT EXISTS i_attempts ON quiz_attempts(user_id, lesson_id, finished);
CREATE INDEX IF NOT EXISTS i_tokens_exp ON tokens(expires);
UPDATE users SET plan='start' WHERE plan='active';
""")

# v9: მრავალი კურსი. ყველაფერი იდემპოტენტურია (სვეტის/ინდექსის არსებობით განისაზღვრება) და ერთ ტრანზაქციაშია.
# lesson id-ები, პროგრესი, ქვიზები, კითხვები და სერტიფიკატები უცვლელია; არსებული ჩანაწერები ხდება 'cybersecurity-beginners'.
_DC = courses.DEFAULT_COURSE
_cols = lambda t: [c['name'] for c in all_(f'PRAGMA table_info({t})')]  # noqa: E731
with tx():
    if 'course' not in _cols('lessons'):
        run(f"ALTER TABLE lessons ADD COLUMN course TEXT NOT NULL DEFAULT '{_DC}'")
    if 'course' not in _cols('stages'):   # გასაღები id → (course,id): ცხრილი თავიდან იქმნება და მონაცემები გადაიწერება
        run(f"CREATE TABLE stages_v9(course TEXT NOT NULL DEFAULT '{_DC}', id INTEGER NOT NULL, title TEXT NOT NULL, description TEXT DEFAULT '', PRIMARY KEY(course,id))")
        run(f"INSERT INTO stages_v9(course,id,title,description) SELECT '{_DC}',id,title,description FROM stages")
        run('DROP TABLE stages')
        run('ALTER TABLE stages_v9 RENAME TO stages')
    if 'course_id' not in _cols('certificates'):   # ერთი სერტიფიკატი მომხმარებელზე → ერთი სერტიფიკატი მომხმარებელსა და კურსზე
        run(f"CREATE TABLE certificates_v9(id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, name TEXT NOT NULL, issued INTEGER NOT NULL, course TEXT NOT NULL, course_id TEXT NOT NULL DEFAULT '{_DC}', UNIQUE(user_id,course_id))")
        run(f"INSERT INTO certificates_v9(id,user_id,name,issued,course,course_id) SELECT id,user_id,name,issued,course,'{_DC}' FROM certificates ORDER BY rowid")
        run('DROP TABLE certificates')
        run('ALTER TABLE certificates_v9 RENAME TO certificates')
    run('DROP INDEX IF EXISTS i_lessons_wp')
    run('CREATE UNIQUE INDEX IF NOT EXISTS i_lessons_cwp ON lessons(course,week,pos)')
    run('CREATE INDEX IF NOT EXISTS i_lessons_course ON lessons(course)')

# სქემის ვერსია. v1: სესიის ტოკენები ჰეშირებულია (ძველი ღია სესიები ერთხელ იშლება)
if _v < 1:
    run('DELETE FROM sessions')
if _v < SCHEMA_VERSION:
    run(f'PRAGMA user_version={SCHEMA_VERSION}')


def audit(user_id, action, detail='', ip=''):
    run('INSERT INTO audit(user_id,action,detail,ip,created) VALUES(?,?,?,?,?)',
        user_id, action, str(detail)[:300], str(ip)[:64], int(time.time() * 1000))


def purge_audit(days):
    """ჟურნალი ვადიანია: days დღეზე ძველი ჩანაწერები იშლება (+ დამცავი ზღვარი 100 000 ჩანაწერი)."""
    run('DELETE FROM audit WHERE created<?', int((time.time() - days * 86400) * 1000))
    run('DELETE FROM audit WHERE id NOT IN (SELECT id FROM audit ORDER BY id DESC LIMIT 100000)')


def anonymize_audit(user_id, email):
    """ანგარიშის წაშლისას ჟურნალში მასთან დაკავშირებული მონაცემი იშლება: user_id, IP და ელფოსტა ტექსტში."""
    run("UPDATE audit SET user_id=NULL, ip='' WHERE user_id=?", user_id)
    e = (email or '').strip().lower()
    if e:
        run("UPDATE audit SET detail=replace(lower(detail), ?, '[წაშლილი]') WHERE instr(lower(detail), ?)>0", e, e)


def backup():
    """ბაზის თანმიმდევრული ასლი (SQLite backup API); ინახება ბოლო 14."""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    path = os.path.join(BACKUP_DIR, time.strftime('cda-%Y%m%d-%H%M%S.db'))
    _backup_to(path)
    for old in sorted(glob.glob(os.path.join(BACKUP_DIR, 'cda-*.db')))[:-14]:
        try:
            os.remove(old)
        except OSError:
            pass
    return os.path.basename(path)


def last_backup_age():
    files = glob.glob(os.path.join(BACKUP_DIR, 'cda-*.db'))
    return time.time() - max((os.path.getmtime(f) for f in files), default=0)


# კურსის მასალა იტვირთება/ახლდება კურსების content-ფაილებიდან (courses.py); ადმინის მიერ ჩასმული ვიდეო და PDF ბმულები არ იშლება.
# ცარიელი, არარსებული ან დაზიანებული ფაილი კურსს „შიგთავსის გარეშე“ ტოვებს და გაშვებას არ აჩერებს (ბაზაში უკვე არსებული გაკვეთილები რჩება).
_UPSERT = ('INSERT INTO lessons(course,week,pos,title,summary,task,free,content,quiz,bonus,objectives,minutes,exercises) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) '
           'ON CONFLICT(course,week,pos) DO UPDATE SET title=excluded.title, summary=excluded.summary, task=excluded.task, '
           'free=excluded.free, content=excluded.content, quiz=excluded.quiz, bonus=excluded.bonus, '
           'objectives=excluded.objectives, minutes=excluded.minutes, exercises=excluded.exercises')
_dumps = lambda v: json.dumps(v, ensure_ascii=False, separators=(',', ':'))  # noqa: E731
COURSE_WARNINGS = {}   # course id → მიზეზი, რატომ არ ჩაიტვირთა შიგთავსი


def load_course(c):
    """ტვირთავს ერთი კურსის შიგთავსს. აბრუნებს ჩატვირთული გაკვეთილების რაოდენობას ან None-ს (შიგთავსის გარეშე)."""
    path = courses.content_path(c)
    if not path:
        return None
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, list) or not data or not all(isinstance(s, dict) and isinstance(s.get('lessons'), list) for s in data):
            raise ValueError('ცარიელია ან სტრუქტურა არასწორია')
        first = min(s.get('stage', s.get('week')) for s in data)
        total = 0
        with tx():
            for s in data:
                n = s.get('stage', s.get('week'))  # ძველი ფორმატის (week) მხარდაჭერა
                run('INSERT INTO stages(course,id,title,description) VALUES(?,?,?,?) ON CONFLICT(course,id) DO UPDATE SET '
                    'title=excluded.title, description=excluded.description', c['id'], n, s['title'], s.get('description', ''))
                for j, l in enumerate(s['lessons']):   # უფასოა კურსის პირველი ეტაპი
                    run(_UPSERT, c['id'], n, j + 1, l['title'], s['title'], l['task'], 1 if n == first else 0, l['content'],
                        _dumps(l['quiz']), l.get('bonus', ''), _dumps(l.get('objectives', [])), int(l.get('minutes', 0)), _dumps(l.get('exercises', [])))
                    total += 1
        return total
    except (OSError, ValueError, KeyError, TypeError) as e:
        COURSE_WARNINGS[c['id']] = f'{type(e).__name__}: {e}'
        print(f"db: კურსი {c['id']}: შიგთავსი არ ჩაიტვირთა ({COURSE_WARNINGS[c['id']]})")
        return None


for _co in courses.COURSES:
    load_course(_co)
