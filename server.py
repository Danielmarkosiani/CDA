#!/usr/bin/env python3
# CDA სერვერი: Flask + SQLite
#   განვითარება: python3 server.py
#   პროდაქშენი:  gunicorn -w 1 --threads 8 -b 127.0.0.1:3000 server:app
import csv
import gzip
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import sqlite3
import threading
import time
from urllib.parse import urlsplit

from flask import Flask, Response, jsonify, request

import db
from plans import PLANS

PORT = int(os.environ.get('PORT') or 3000)
ADMIN_EMAIL = (os.environ.get('ADMIN_EMAIL') or '').strip().lower()
PAY_INFO = os.environ.get('PAY_INFO', '')
CONTACT = os.environ.get('CONTACT', '')
MENTOR_NAME = os.environ.get('MENTOR_NAME', '')
TRUST_PROXY = os.environ.get('TRUST_PROXY') == '1'
ALLOWED_HOSTS = {h.strip().lower() for h in os.environ.get('ALLOWED_HOSTS', '').split(',') if h.strip()}
AUTO_BACKUP = os.environ.get('AUTO_BACKUP') != '0'
PUB = os.path.realpath(os.path.join(db.HERE, 'public'))
DAY = 86_400_000
LEVEL = {p['id']: p['level'] for p in PLANS}
PAID = [p['id'] for p in PLANS if p['level'] > 0]
MIME = {'.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
        '.png': 'image/png', '.svg': 'image/svg+xml', '.ico': 'image/x-icon', '.txt': 'text/plain; charset=utf-8'}
CSP = ("default-src 'self'; script-src 'self'; style-src 'self' https://fonts.googleapis.com; "
       "font-src https://fonts.gstatic.com; img-src 'self' data: https:; "
       "frame-src https://www.youtube-nocookie.com https://www.youtube.com https://player.vimeo.com; "
       "media-src https:; connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")
SEC = {'X-Permitted-Cross-Domain-Policies': 'none', 'X-Content-Type-Options': 'nosniff', 'X-Frame-Options': 'DENY', 'Referrer-Policy': 'same-origin',
       'Permissions-Policy': 'camera=(), microphone=(), geolocation=(), payment=(), usb=()',
       'Cross-Origin-Opener-Policy': 'same-origin', 'Cross-Origin-Resource-Policy': 'same-origin'}
COMMON_PW = {'password', 'password1', 'password123', '12345678', '123456789', '1234567890', 'qwertyui', 'qwerty123',
             'abcd1234', 'iloveyou', '11111111', '00000000', 'asdfghjk', 'letmein1', 'admin123', 'welcome1'}
CTRL_RE = re.compile(r'[\x00-\x1f\x7f\u200b-\u200f\u202a-\u202e]')
EMAIL_RE = re.compile(r'\S+@\S+\.\S+')
SID_RE = re.compile(r'(?:^|; )sid=([a-f0-9]+)')

app = Flask(__name__, static_folder=None)
app.config['MAX_CONTENT_LENGTH'] = 100_000
app.json.ensure_ascii = False
app.json.sort_keys = False

if ADMIN_EMAIL:
    db.run("UPDATE users SET role='admin' WHERE email=?", ADMIN_EMAIL)
if AUTO_BACKUP:
    try:
        if db.last_backup_age() > 86400:
            db.backup()
    except Exception as e:  # noqa: BLE001
        print('backup:', e)


def now_ms():
    return int(time.time() * 1000)


def hash_pw(pw, salt):
    # Node-ის crypto.scryptSync(pw, salt, 64)-თან თავსებადია (salt გამოიყენება როგორც ტექსტი)
    return hashlib.scrypt(pw.encode(), salt=salt.encode(), n=16384, r=8, p=1, dklen=64, maxmem=64 * 1024 * 1024).hex()


def th(token):
    return hashlib.sha256(token.encode()).hexdigest()


def same(a, b):
    return hmac.compare_digest(a.encode(), b.encode())


DUMMY_SALT = secrets.token_hex(16)


def tint(v):
    """JS-ის Number.isInteger-ის ექვივალენტი (bool არ ითვლება)"""
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return None


# მარტივი შეზღუდვა: ერთი გასაღები max მცდელობა 10 წუთში
_hits = {}
_hits_lock = threading.Lock()


def limited(key, mx):
    with _hits_lock:
        n = _hits.get(key, 0) + 1
        _hits[key] = n
    return n > mx


def _janitor():
    while True:
        time.sleep(600)
        with _hits_lock:
            _hits.clear()
        try:
            db.run('DELETE FROM sessions WHERE expires<?', now_ms())
            db.run('DELETE FROM audit WHERE id NOT IN (SELECT id FROM audit ORDER BY id DESC LIMIT 5000)')
            if AUTO_BACKUP and db.last_backup_age() > 86400:
                db.backup()
        except Exception as e:  # noqa: BLE001
            print('janitor:', e)


threading.Thread(target=_janitor, daemon=True).start()


def send(code, data, **kw):
    r = jsonify(data)
    r.status_code = code
    r.headers['Cache-Control'] = 'no-store'
    return r


def ip_of():
    if TRUST_PROXY:
        x = (request.headers.get('X-Forwarded-For') or '').split(',')[0].strip()
        if x:
            return x
    return request.remote_addr or '?'


def secure():
    return os.environ.get('SECURE_COOKIE') == '1' or request.headers.get('X-Forwarded-Proto') == 'https'


def body():
    d = request.get_json(silent=True, force=True)
    return d if isinstance(d, dict) else {}


def user_by_token(token):
    u = db.one('SELECT u.id,u.email,u.name,u.role,u.plan,u.plan_expires FROM sessions s JOIN users u ON u.id=s.user_id '
               'WHERE s.token=? AND s.expires>?', th(token), now_ms())
    if not u:
        return None
    expired = u['plan'] != 'free' and u['plan_expires'] and u['plan_expires'] < now_ms()
    plan = 'free' if expired else (u['plan'] if u['plan'] in LEVEL else 'free')
    return {**u, 'plan': plan, 'level': 3 if u['role'] == 'admin' else LEVEL[plan]}


def current_token():
    m = SID_RE.search(request.headers.get('Cookie') or '')
    return m.group(1) if m else None


def user_of():
    t = current_token()
    return user_by_token(t) if t else None


def pub(u):
    return u and {k: u[k] for k in ('id', 'email', 'name', 'role', 'plan', 'plan_expires', 'level')}


def lesson_level(l):
    return 0 if l['free'] else 1


def need_login():
    return send(401, {'error': 'ჯერ შედი ანგარიშში.'})


def admin_only(fn):
    from functools import wraps

    @wraps(fn)
    def wrapped():
        u = user_of()
        if not u or u['role'] != 'admin':
            return send(403, {'error': 'მხოლოდ ადმინისთვის.'})
        return fn(u)
    return wrapped


def strong_pw(p, email='', name=''):
    if not (isinstance(p, str) and 8 <= len(p) <= 200 and p.lower() not in COMMON_PW and len(set(p)) > 2):
        return False
    low, local = p.lower(), (email or '').split('@')[0].lower()
    if low == (email or '').lower() or (len(local) >= 4 and local in low):
        return False  # პაროლი არ უნდა შეიცავდეს ელფოსტის სახელს
    return not (len(name or '') >= 4 and low == name.strip().lower())


def parse_quiz(l):
    import json
    try:
        q = json.loads(l.get('quiz') or '[]')
        return q if isinstance(q, list) else []
    except ValueError:
        return []


def login(email):
    u = db.one('SELECT id FROM users WHERE email=?', email)
    token = secrets.token_hex(32)
    db.run('INSERT INTO sessions VALUES(?,?,?)', th(token), u['id'], now_ms() + 30 * DAY)
    # ერთ მომხმარებელს მაქსიმუმ 10 აქტიური სესია
    db.run('DELETE FROM sessions WHERE user_id=? AND token NOT IN '
           '(SELECT token FROM sessions WHERE user_id=? ORDER BY expires DESC LIMIT 10)', u['id'], u['id'])
    db.run('UPDATE users SET last_login=? WHERE id=?', now_ms(), u['id'])
    db.audit(u['id'], 'login', '', ip_of())
    r = send(200, {'user': pub(user_by_token(token))})
    r.set_cookie('sid', token, httponly=True, samesite='Lax', path='/', max_age=30 * 86400, secure=secure())
    return r


def purge_user(uid):
    with db.tx():
        for t in ('sessions', 'progress', 'quiz_results', 'questions', 'orders'):
            db.run(f'DELETE FROM {t} WHERE user_id=?', uid)
        db.run('DELETE FROM users WHERE id=?', uid)


def grant(user_id, plan, days):
    cur = db.one('SELECT plan,plan_expires FROM users WHERE id=?', user_id)
    if plan == 'free':
        return db.run("UPDATE users SET plan='free',plan_expires=NULL WHERE id=?", user_id)
    base = cur['plan_expires'] if cur and cur['plan'] == plan and (cur['plan_expires'] or 0) > now_ms() else now_ms()
    db.run('UPDATE users SET plan=?,plan_expires=? WHERE id=?', plan, base + days * DAY if days > 0 else None, user_id)


# ---------------------------------------------------------------- უსაფრთხოების ჰედერები და შეცდომები
@app.after_request
def add_headers(r):
    for k, v in SEC.items():
        r.headers[k] = v
    if secure():
        r.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    return r


@app.before_request
def host_guard():
    if ALLOWED_HOSTS and request.host.split(':')[0].lower() not in ALLOWED_HOSTS:
        return Response('Bad host', status=400, mimetype='text/plain')
    return None


@app.before_request
def csrf_guard():
    """CSRF-ის დამატებითი ფენა: სხვა საიტიდან გამოგზავნილი POST იბლოკება; API იღებს მხოლოდ JSON-ს."""
    if request.method in ('GET', 'HEAD', 'OPTIONS'):
        return None
    origin = request.headers.get('Origin') or request.headers.get('Referer')
    if origin:
        host = (request.headers.get('X-Forwarded-Host') if TRUST_PROXY else None) or request.host
        if urlsplit(origin).netloc != host:
            return send(403, {'error': 'მოთხოვნა უარყოფილია.'})
    if request.path.startswith('/api/') and request.mimetype != 'application/json':
        return send(415, {'error': 'მხოლოდ JSON.'})
    if request.path.startswith('/api/') and request.headers.get('X-Requested-With') != 'cda':
        return send(403, {'error': 'მოთხოვნა უარყოფილია.'})
    return None


@app.errorhandler(413)
def too_big(e):
    return send(413, {'error': 'მოთხოვნა ძალიან დიდია.'})


@app.errorhandler(404)
@app.errorhandler(405)
def not_found(e):
    if request.path.startswith('/api/'):
        return send(404, {'error': 'ვერ მოიძებნა.'})
    return e


@app.errorhandler(Exception)
def crash(e):
    from werkzeug.exceptions import HTTPException
    if isinstance(e, HTTPException):
        return e
    import traceback
    traceback.print_exc()
    return send(500, {'error': 'სერვერის შეცდომა.'})


# ---------------------------------------------------------------- API
@app.get('/api/config')
def r_config():
    return send(200, {'plans': PLANS, 'payInfo': PAY_INFO, 'contact': CONTACT, 'mentor': MENTOR_NAME})


@app.post('/api/register')
def r_register():
    if limited('r' + ip_of(), 10):
        return send(429, {'error': 'ძალიან ბევრი მცდელობა. სცადე მოგვიანებით.'})
    d = body()
    email, name, password, terms = d.get('email', ''), d.get('name', ''), d.get('password', ''), d.get('terms')
    if isinstance(name, str):
        name = CTRL_RE.sub('', name)
    if isinstance(password, str) and 8 <= len(password) <= 200 and isinstance(email, str) and not strong_pw(password, email, name if isinstance(name, str) else ''):
        return send(400, {'error': 'ეს პაროლი ძალიან მარტივია. აირჩიე უფრო რთული.'})
    if (not isinstance(email, str) or not isinstance(name, str) or not EMAIL_RE.fullmatch(email) or len(email) > 120
            or len(name.strip()) < 2 or not strong_pw(password, email, name)):
        return send(400, {'error': 'შეავსე სწორად: სახელი, ელფოსტა და პაროლი (მინ. 8 სიმბოლო).'})
    if terms is not True:
        return send(400, {'error': 'გაგრძელებისთვის დაეთანხმე წესებს.'})
    e, salt = email.strip().lower(), secrets.token_hex(16)
    if db.one('SELECT 1 FROM users WHERE email=?', e):
        return send(409, {'error': 'ეს ელფოსტა უკვე რეგისტრირებულია.'})
    try:
        db.run('INSERT INTO users(email,name,hash,salt,role,created) VALUES(?,?,?,?,?,?)',
               e, name.strip()[:60], hash_pw(password, salt), salt, 'admin' if e == ADMIN_EMAIL else 'student', now_ms())
    except sqlite3.IntegrityError:
        return send(409, {'error': 'ეს ელფოსტა უკვე რეგისტრირებულია.'})
    db.audit(db.one('SELECT id FROM users WHERE email=?', e)['id'], 'register', '', ip_of())
    return login(e)


@app.post('/api/login')
def r_login():
    d = body()
    email, password = d.get('email', ''), d.get('password', '')
    if not isinstance(email, str) or not isinstance(password, str):
        return send(400, {'error': 'არასწორი მონაცემი.'})
    if limited('l' + ip_of(), 30) or limited('e' + email.lower(), 10):
        return send(429, {'error': 'ძალიან ბევრი მცდელობა. სცადე მოგვიანებით.'})
    u = db.one('SELECT * FROM users WHERE email=?', email.strip().lower())
    hh = hash_pw(password, u['salt'] if u else DUMMY_SALT)  # ერთნაირი დრო არსებული და არარსებული ანგარიშისთვის
    if not u or not same(hh, u['hash']):
        db.audit(u['id'] if u else None, 'login_fail', email.strip().lower()[:80], ip_of())
        return send(401, {'error': 'ელფოსტა ან პაროლი არასწორია.'})
    return login(u['email'])


@app.post('/api/logout')
def r_logout():
    t = current_token()
    if t:
        db.run('DELETE FROM sessions WHERE token=?', th(t))
    r = send(200, {'ok': True})
    r.set_cookie('sid', '', max_age=0, path='/')
    return r


@app.post('/api/logout_all')
def r_logout_all():
    u = user_of()
    if not u:
        return need_login()
    db.run('DELETE FROM sessions WHERE user_id=?', u['id'])
    db.audit(u['id'], 'logout_all', '', ip_of())
    r = send(200, {'ok': True})
    r.set_cookie('sid', '', max_age=0, path='/')
    return r


@app.post('/api/account/delete')
def r_account_delete():
    u = user_of()
    if not u:
        return need_login()
    if u['role'] == 'admin':
        return send(400, {'error': 'ადმინის ანგარიში აქედან არ იშლება.'})
    if limited('p' + str(u['id']), 8):
        return send(429, {'error': 'ძალიან ბევრი მცდელობა. სცადე მოგვიანებით.'})
    pw, row = body().get('password', ''), db.one('SELECT hash,salt FROM users WHERE id=?', u['id'])
    if not isinstance(pw, str) or not same(hash_pw(pw, row['salt']), row['hash']):
        return send(400, {'error': 'პაროლი არასწორია.'})
    purge_user(u['id'])
    db.audit(None, 'account_delete', u['email'], ip_of())
    r = send(200, {'ok': True})
    r.set_cookie('sid', '', max_age=0, path='/')
    return r


@app.get('/api/me')
def r_me():
    u = user_of()
    if not u:
        return send(200, {'user': None})
    p = db.one("SELECT plan FROM orders WHERE user_id=? AND status='pending' ORDER BY id DESC", u['id'])
    return send(200, {'user': pub(u), 'pending': p['plan'] if p else None})


@app.post('/api/password')
def r_password():
    u = user_of()
    if not u:
        return need_login()
    d = body()
    old, nxt = d.get('old', ''), d.get('next', '')
    row = db.one('SELECT hash,salt FROM users WHERE id=?', u['id'])
    if limited('p' + str(u['id']), 8):
        return send(429, {'error': 'ძალიან ბევრი მცდელობა. სცადე მოგვიანებით.'})
    if not isinstance(old, str) or not same(hash_pw(old, row['salt']), row['hash']):
        return send(400, {'error': 'ძველი პაროლი არასწორია.'})
    if not strong_pw(nxt, u['email'], u['name']):
        return send(400, {'error': 'ახალი პაროლი მინიმუმ 8 სიმბოლო უნდა იყოს, არ უნდა იყოს მარტივი და არ უნდა შეიცავდეს ელფოსტას.'})
    salt = secrets.token_hex(16)
    db.run('UPDATE users SET hash=?,salt=? WHERE id=?', hash_pw(nxt, salt), salt, u['id'])
    db.run('DELETE FROM sessions WHERE user_id=? AND token<>?', u['id'], th(current_token()))  # სხვა სესიები წყდება
    db.audit(u['id'], 'password_change', '', ip_of())
    return send(200, {'ok': True})


@app.get('/api/lessons')
def r_lessons():
    u = user_of()
    lv = u['level'] if u else 0
    done = [r['lesson_id'] for r in db.all_('SELECT lesson_id FROM progress WHERE user_id=?', u['id'])] if u else []
    scores = {str(r['lesson_id']): [r['score'], r['total']]
              for r in db.all_('SELECT lesson_id,score,total FROM quiz_results WHERE user_id=?', u['id'])} if u else {}
    rows = []
    for l in db.all_('SELECT * FROM lessons ORDER BY week,pos'):
        try:
            obj = json.loads(l.get('objectives') or '[]')
        except ValueError:
            obj = []
        base = {'id': l['id'], 'stage': l['week'], 'pos': l['pos'], 'title': l['title'], 'summary': l['summary'],
                'free': bool(l['free']), 'minutes': l.get('minutes') or 0}
        if lv < lesson_level(l):
            rows.append({**base, 'locked': True})
            continue
        quiz = [{'q': x.get('q'), 'o': x.get('o')} for x in parse_quiz(l)]
        rows.append({**base, 'locked': False, 'task': l['task'], 'content': l['content'], 'video_url': l['video_url'],
                     'pdf_url': l['pdf_url'], 'quiz': quiz, 'objectives': obj if isinstance(obj, list) else [],
                     'bonus': l['bonus'] if lv >= 2 else '', 'bonus_locked': lv < 2 and bool(l['bonus'])})
    stages = db.all_('SELECT id,title,description FROM stages ORDER BY id')
    return send(200, {'stages': stages, 'lessons': rows, 'done': done, 'scores': scores})


def _accessible_lesson(u, lesson_id):
    lid = tint(lesson_id)
    l = db.one('SELECT * FROM lessons WHERE id=?', lid) if lid is not None else None
    return l if l and u['level'] >= lesson_level(l) else None


@app.post('/api/progress')
def r_progress():
    u = user_of()
    if not u:
        return need_login()
    d = body()
    l = _accessible_lesson(u, d.get('lesson_id'))
    if not l:
        return send(403, {'error': 'წვდომა არ გაქვს.'})
    if d.get('done'):
        db.run('INSERT OR IGNORE INTO progress(user_id,lesson_id,done_at) VALUES(?,?,?)', u['id'], l['id'], now_ms())
    else:
        db.run('DELETE FROM progress WHERE user_id=? AND lesson_id=?', u['id'], l['id'])
    return send(200, {'ok': True})


@app.post('/api/quiz')
def r_quiz():
    u = user_of()
    if not u:
        return need_login()
    d = body()
    l = _accessible_lesson(u, d.get('lesson_id'))
    if not l:
        return send(403, {'error': 'წვდომა არ გაქვს.'})
    answers, quiz = d.get('answers'), parse_quiz(l)
    if not isinstance(answers, list) or len(answers) != len(quiz):
        return send(400, {'error': 'უპასუხე ყველა კითხვას.'})
    results = [{'ok': tint(answers[i]) is not None and tint(answers[i]) == x.get('a'), 'correct': x.get('a'), 'e': x.get('e')}
               for i, x in enumerate(quiz)]
    score = sum(1 for r in results if r['ok'])
    best = db.one('SELECT score FROM quiz_results WHERE user_id=? AND lesson_id=?', u['id'], l['id'])
    if not best or score > best['score']:
        db.run('INSERT OR REPLACE INTO quiz_results VALUES(?,?,?,?)', u['id'], l['id'], score, len(quiz))
    return send(200, {'score': score, 'total': len(quiz), 'results': results})


@app.get('/api/questions')
def r_questions_get():
    u = user_of()
    if not u:
        return need_login()
    is_a = u['role'] == 'admin'
    sql = ('SELECT q.id,q.text,q.answer,q.created,q.kind,q.lesson_id,l.title lesson_title,u.name,u.plan,u.plan_expires,u.role '
           'FROM questions q JOIN users u ON u.id=q.user_id LEFT JOIN lessons l ON l.id=q.lesson_id '
           + ('' if is_a else 'WHERE q.user_id=? ')
           + 'ORDER BY ' + ("(q.answer='') DESC," if is_a else '') + ' q.id DESC LIMIT 200')
    rows = []
    for r in (db.all_(sql) if is_a else db.all_(sql, u['id'])):
        exp = r['plan'] != 'free' and r['plan_expires'] and r['plan_expires'] < now_ms()
        rows.append({'id': r['id'], 'text': r['text'], 'answer': r['answer'], 'created': r['created'], 'kind': r['kind'],
                     'lesson_id': r['lesson_id'], 'lesson_title': r['lesson_title'], 'name': r['name'],
                     'plan': 'free' if exp else r['plan']})
    if is_a:  # უპასუხო და მაღალი გეგმა წინ
        rows.sort(key=lambda r: (bool(r['answer']), -LEVEL.get(r['plan'], 0), -r['id']))
    return send(200, {'questions': rows})


@app.post('/api/questions')
def r_questions_post():
    u = user_of()
    if not u:
        return need_login()
    d = body()
    text, lesson_id, kind = d.get('text'), d.get('lesson_id'), d.get('kind')
    k = 'task' if kind == 'task' else 'question'
    t = (str(text) if text else '').strip()[:4000 if k == 'task' else 800]
    if not t:
        return send(400, {'error': 'ტექსტი ცარიელია.'})
    if k == 'question' and u['level'] < 1:
        return send(403, {'error': 'კითხვების დასმა Start გეგმიდან არის ხელმისაწვდომი.'})
    if k == 'task' and u['level'] < 2:
        return send(403, {'error': 'დავალების გაგზავნა Pro და Mentor გეგმებშია.'})
    lid = tint(lesson_id)
    lid = lid if lid is not None and db.one('SELECT id FROM lessons WHERE id=?', lid) else None
    if k == 'task' and not lid:
        return send(400, {'error': 'აირჩიე გაკვეთილი.'})
    if limited('q' + str(u['id']), 15):
        return send(429, {'error': 'ძალიან ბევრი შეტყობინება. სცადე მოგვიანებით.'})
    db.run('INSERT INTO questions(user_id,lesson_id,text,created,kind) VALUES(?,?,?,?,?)', u['id'], lid, t, now_ms(), k)
    return send(200, {'ok': True})


@app.post('/api/orders')
def r_orders():
    u = user_of()
    if not u:
        return need_login()
    plan = body().get('plan')
    if not isinstance(plan, str) or plan not in PAID:
        return send(400, {'error': 'არასწორი გეგმა.'})
    p = db.one("SELECT id FROM orders WHERE user_id=? AND status='pending'", u['id'])
    if p:
        db.run('UPDATE orders SET plan=?,created=? WHERE id=?', plan, now_ms(), p['id'])
    else:
        db.run('INSERT INTO orders(user_id,plan,created) VALUES(?,?,?)', u['id'], plan, now_ms())
    return send(200, {'ok': True})


@app.get('/api/certificate')
def r_certificate():
    u = user_of()
    if not u:
        return need_login()
    total = db.one('SELECT COUNT(*) c FROM lessons')['c']
    d = db.one('SELECT COUNT(*) c, MAX(done_at) t FROM progress WHERE user_id=?', u['id'])
    if u['level'] < 2:
        return send(403, {'error': 'სერტიფიკატი Pro და Mentor გეგმებშია.'})
    if d['c'] < total:
        return send(403, {'error': f"დაასრულე ყველა გაკვეთილი ({d['c']}/{total})."})
    cid = 'CDA-' + hashlib.sha256(f"{u['id']}:{u['email']}".encode()).hexdigest()[:10].upper()
    return send(200, {'name': u['name'], 'date': d['t'] or now_ms(), 'id': cid, 'lessons': total,
                      'stages': db.one('SELECT COUNT(*) c FROM stages')['c'],
                      'minutes': db.one('SELECT COALESCE(SUM(minutes),0) m FROM lessons')['m']})


# მხოლოდ ადმინისთვის
@app.post('/api/admin/answer')
@admin_only
def r_a_answer(u):
    d = body()
    qid = tint(d.get('id'))
    ans = str(d.get('answer', '')).strip()[:4000]
    if qid is None or not db.one('SELECT 1 FROM questions WHERE id=?', qid):
        return send(400, {'error': 'არასწორი მონაცემი.'})
    db.run('UPDATE questions SET answer=?,answered_at=? WHERE id=?', ans, now_ms() if ans else None, qid)
    db.audit(u['id'], 'admin_answer', f'question {qid}', ip_of())
    return send(200, {'ok': True})


@app.get('/api/admin/lessons')
@admin_only
def r_a_lessons(u):
    return send(200, {'lessons': db.all_('SELECT id,week stage,pos,title,video_url,pdf_url FROM lessons ORDER BY week,pos')})


@app.post('/api/admin/lesson')
@admin_only
def r_a_lesson(u):
    d = body()
    lid, video, pdf = tint(d.get('id')), d.get('video_url', ''), d.get('pdf_url', '')
    ok = lambda s: isinstance(s, str) and len(s) <= 500 and (s == '' or s.startswith('https://'))  # noqa: E731
    if lid is None or not ok(video) or not ok(pdf) or not db.one('SELECT 1 FROM lessons WHERE id=?', lid):
        return send(400, {'error': 'ბმული უნდა იწყებოდეს https://-ით.'})
    db.run('UPDATE lessons SET video_url=?,pdf_url=? WHERE id=?', video.strip(), pdf.strip(), lid)
    db.audit(u['id'], 'admin_lesson', f'lesson {lid}', ip_of())
    return send(200, {'ok': True})


def _user_query():
    q = (request.args.get('q') or '').strip().lower()[:80]
    plan = request.args.get('plan') or ''
    sql = ('SELECT u.id,u.name,u.email,u.role,u.plan,u.plan_expires,u.created,u.last_login,'
           '(SELECT COUNT(*) FROM progress p WHERE p.user_id=u.id) done FROM users u WHERE 1=1')
    args = []
    if q:
        sql += " AND instr(lower(u.name||' '||u.email), ?)>0"
        args.append(q)
    if plan in LEVEL:
        sql += ' AND u.plan=?'
        args.append(plan)
    return sql, args


@app.get('/api/admin/users')
@admin_only
def r_a_users(u):
    sql, args = _user_query()
    page = max(0, tint(request.args.get('page', 0)) or 0)
    total = db.one('SELECT COUNT(*) c FROM (' + sql + ')', *args)['c']
    rows = db.all_(sql + ' ORDER BY u.id DESC LIMIT 50 OFFSET ?', *args, page * 50)
    return send(200, {'users': rows, 'total': total, 'page': page, 'per': 50,
                      'lessons': db.one('SELECT COUNT(*) c FROM lessons')['c']})


def _csv_cell(v):
    v = '' if v is None else str(v)
    return "'" + v if v[:1] in ('=', '+', '-', '@', '\t', '\r') else v  # Excel-ის ფორმულების ინექციისგან დაცვა


@app.get('/api/admin/users.csv')
@admin_only
def r_a_users_csv(u):
    sql, args = _user_query()
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(['id', 'name', 'email', 'role', 'plan', 'plan_expires', 'created', 'last_login', 'lessons_done'])
    fmt = lambda t: time.strftime('%Y-%m-%d', time.gmtime(t / 1000)) if t else ''  # noqa: E731
    for r in db.all_(sql + ' ORDER BY u.id', *args):
        w.writerow([r['id'], _csv_cell(r['name']), _csv_cell(r['email']), r['role'], r['plan'],
                    fmt(r['plan_expires']), fmt(r['created']), fmt(r['last_login']), r['done']])
    db.audit(u['id'], 'admin_export', 'users.csv', ip_of())
    return Response('\ufeff' + out.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': 'attachment; filename="cda-users.csv"', 'Cache-Control': 'no-store'})


@app.post('/api/admin/plan')
@admin_only
def r_a_plan(u):
    d = body()
    uid, plan, days = tint(d.get('id')), d.get('plan'), tint(d.get('days', 30))
    if uid is None or not isinstance(plan, str) or plan not in LEVEL or days is None or days < 0 or days > 3650:
        return send(400, {'error': 'არასწორი მონაცემი.'})
    if not db.one('SELECT 1 FROM users WHERE id=?', uid):
        return send(400, {'error': 'მომხმარებელი ვერ მოიძებნა.'})
    grant(uid, plan, days)
    db.audit(u['id'], 'admin_plan', f'user {uid} -> {plan}, {days} days', ip_of())
    return send(200, {'ok': True})


@app.post('/api/admin/user_delete')
@admin_only
def r_a_user_delete(u):
    uid = tint(body().get('id'))
    t = db.one('SELECT id,role,email FROM users WHERE id=?', uid) if uid is not None else None
    if not t or t['role'] == 'admin' or t['id'] == u['id']:
        return send(400, {'error': 'ამ ანგარიშის წაშლა შეუძლებელია.'})
    purge_user(uid)
    db.audit(u['id'], 'admin_user_delete', t['email'], ip_of())
    return send(200, {'ok': True})


@app.get('/api/admin/orders')
@admin_only
def r_a_orders(u):
    allv = request.args.get('all') == '1'
    sql = ('SELECT o.id,o.plan,o.status,o.amount,o.created,o.decided_at,u.name,u.email FROM orders o JOIN users u ON u.id=o.user_id '
           + ('' if allv else "WHERE o.status='pending' ") + 'ORDER BY ' + ('o.id DESC LIMIT 200' if allv else 'o.id'))
    return send(200, {'orders': db.all_(sql)})


@app.post('/api/admin/order')
@admin_only
def r_a_order(u):
    d = body()
    oid, action = tint(d.get('id')), d.get('action')
    o = db.one("SELECT * FROM orders WHERE id=? AND status='pending'", oid) if oid is not None else None
    if not o or action not in ('approve', 'reject'):
        return send(400, {'error': 'არასწორი მონაცემი.'})
    price = next((p['price'] for p in PLANS if p['id'] == o['plan']), 0)
    with db.tx():
        if action == 'approve':
            grant(o['user_id'], o['plan'], 30)
        db.run('UPDATE orders SET status=?,amount=?,decided_at=?,decided_by=? WHERE id=?',
               'approved' if action == 'approve' else 'rejected', price, now_ms(), u['id'], oid)
    db.audit(u['id'], 'admin_order_' + action, f"order {oid} ({o['plan']})", ip_of())
    return send(200, {'ok': True})


@app.post('/api/admin/resetpw')
@admin_only
def r_a_resetpw(u):
    uid = tint(body().get('id'))
    t = db.one('SELECT id,role FROM users WHERE id=?', uid) if uid is not None else None
    if not t:
        return send(400, {'error': 'არასწორი მონაცემი.'})
    if t['role'] == 'admin' and t['id'] != u['id']:
        return send(400, {'error': 'სხვა ადმინის პაროლს აქედან ვერ შეცვლი. გამოიყენე make_admin.py.'})
    tmp, salt = secrets.token_urlsafe(9), secrets.token_hex(16)
    db.run('UPDATE users SET hash=?,salt=? WHERE id=?', hash_pw(tmp, salt), salt, uid)
    db.run('DELETE FROM sessions WHERE user_id=?', uid)
    db.audit(u['id'], 'admin_resetpw', f'user {uid}', ip_of())
    return send(200, {'password': tmp})


@app.get('/api/admin/stats')
@admin_only
def r_a_stats(u):
    users, now, by, mrr = db.all_("SELECT plan,plan_expires,created,last_login FROM users WHERE role<>'admin'"), now_ms(), {}, 0
    prices = {p['id']: p['price'] for p in PLANS}
    for x in users:
        active = x['plan'] != 'free' and (not x['plan_expires'] or x['plan_expires'] > now)
        p = x['plan'] if active else 'free'
        by[p] = by.get(p, 0) + 1
        if active:
            mrr += prices.get(p, 0)
    lessons = db.one('SELECT COUNT(*) c FROM lessons')['c']
    prog = db.one("SELECT COUNT(*) c FROM progress WHERE user_id IN (SELECT id FROM users WHERE role<>'admin')")['c']
    stages = db.all_("SELECT s.id stage,s.title,(SELECT COUNT(*) FROM lessons l WHERE l.week=s.id) lessons,"
                     "(SELECT COUNT(*) FROM progress p JOIN lessons l ON l.id=p.lesson_id WHERE l.week=s.id) done,"
                     "(SELECT COUNT(DISTINCT p.user_id) FROM progress p JOIN lessons l ON l.id=p.lesson_id WHERE l.week=s.id) learners "
                     "FROM stages s ORDER BY s.id")
    week = 7 * DAY
    signups = [sum(1 for x in users if now - (i + 1) * week <= (x['created'] or 0) < now - i * week) for i in range(7, -1, -1)]
    qz = db.one('SELECT AVG(score*100.0/total) a FROM quiz_results WHERE total>0')['a']
    return send(200, {'users': len(users), 'by': by, 'mrr': mrr,
                      'orders': db.one("SELECT COUNT(*) c FROM orders WHERE status='pending'")['c'],
                      'open': db.one("SELECT COUNT(*) c FROM questions WHERE answer=''")['c'],
                      'new7': sum(1 for x in users if (x['created'] or 0) > now - week),
                      'new30': sum(1 for x in users if (x['created'] or 0) > now - 30 * DAY),
                      'active7': sum(1 for x in users if (x['last_login'] or 0) > now - week),
                      'completion': round(prog * 100 / (lessons * len(users))) if lessons and users else 0,
                      'quiz_avg': round(qz) if qz is not None else None, 'lessons': lessons,
                      'stages': stages, 'signups': signups})


@app.get('/api/admin/audit')
@admin_only
def r_a_audit(u):
    return send(200, {'events': db.all_('SELECT a.id,a.action,a.detail,a.ip,a.created,u.email FROM audit a '
                                        'LEFT JOIN users u ON u.id=a.user_id ORDER BY a.id DESC LIMIT 200')})


@app.post('/api/admin/backup')
@admin_only
def r_a_backup(u):
    name = db.backup()
    db.audit(u['id'], 'admin_backup', name, ip_of())
    return send(200, {'name': name})


# ---------------------------------------------------------------- სტატიკური ფაილები (+ SPA fallback)
_gz_cache = {}


def _plain(code, text):
    return Response(text, status=code, mimetype='text/plain', headers={'Content-Type': 'text/plain; charset=utf-8'})


@app.route('/', defaults={'p': ''}, methods=['GET', 'HEAD', 'POST', 'PUT', 'DELETE', 'PATCH'])
@app.route('/<path:p>', methods=['GET', 'HEAD', 'POST', 'PUT', 'DELETE', 'PATCH'])
def static_files(p):
    if p.startswith('api/'):
        return send(404, {'error': 'ვერ მოიძებნა.'})
    if request.method not in ('GET', 'HEAD'):
        return Response(status=405)
    rel = '/' + p
    if '\0' in rel:
        return Response(status=400)
    if any(seg.startswith('.') for seg in p.split('/')):
        return _plain(404, 'Not found')
    f = os.path.realpath(os.path.join(PUB, 'index.html' if rel == '/' else p))
    if not (f.startswith(PUB + os.sep) and os.path.isfile(f)):
        if os.path.splitext(rel)[1]:
            return _plain(404, 'Not found')
        f = os.path.join(PUB, 'index.html')  # SPA: გაფართოების გარეშე მისამართი → index.html
        if not os.path.isfile(f):
            return _plain(404, 'Not found')
    st = os.stat(f)
    tag = f'"{st.st_size:x}-{int(st.st_mtime * 1000):x}"'
    ext = os.path.splitext(f)[1]
    hd = {'Content-Type': MIME.get(ext, 'application/octet-stream'), 'ETag': tag, 'Cache-Control': 'no-cache'}
    if ext == '.html':
        hd['Content-Security-Policy'] = CSP + ('; upgrade-insecure-requests' if secure() else '')
    if request.headers.get('If-None-Match') == tag:
        return Response(status=304, headers=hd)
    with open(f, 'rb') as fh:
        buf = fh.read()
    if re.search(r'\bgzip\b', request.headers.get('Accept-Encoding') or '') and ext in ('.html', '.css', '.js', '.svg'):
        key = f + tag
        if key not in _gz_cache:
            _gz_cache[key] = gzip.compress(buf)
        buf = _gz_cache[key]
        hd['Content-Encoding'] = 'gzip'
        hd['Vary'] = 'Accept-Encoding'
    return Response(buf, status=200, headers=hd)


if __name__ == '__main__':
    print(f'CDA: http://localhost:{PORT}')
    app.run(host='0.0.0.0', port=PORT, threaded=True)
