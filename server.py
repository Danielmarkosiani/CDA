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
import math
import os
import re
import secrets
import sqlite3
import threading
import time
from urllib.parse import urlsplit

from flask import Flask, Response, jsonify, request

import envfile  # noqa: F401  (.env-ის ჩატვირთვა სხვა ცვლადების წაკითხვამდე; უნდა იყოს პირველი)
import courses
import db
import mailer
from auth import MIN_PW_LEN, client_ip, hash_pw, same, strong_pw, th, valid_url
from plans import PLANS

PORT = int(os.environ.get('PORT') or 3000)
PAY_INFO = os.environ.get('PAY_INFO', '')
CONTACT = os.environ.get('CONTACT', '')
MENTOR_NAME = os.environ.get('MENTOR_NAME', '')
TRUST_PROXY = os.environ.get('TRUST_PROXY') == '1'
PROXY_COUNT = max(1, int(os.environ.get('TRUST_PROXY_COUNT') or 1)) if TRUST_PROXY else 0  # სანდო პროქსების რაოდენობა
BASE_URL = (os.environ.get('BASE_URL') or f'http://localhost:{PORT}').rstrip('/')  # ბმულებისთვის წერილებში (Host-ს არ ვენდობით)
REQUIRE_VERIFY = os.environ.get('REQUIRE_EMAIL_VERIFY') != '0'  # გამორთვა: REQUIRE_EMAIL_VERIFY=0
# კოდები (დადასტურება და პაროლის აღდგენა): 6 ციფრი, ბაზაში მხოლოდ ჰეში, 10 წუთი, ერთჯერადი, 5 არასწორი მცდელობა
CODE_TTL_MS = 10 * 60_000
CODE_MAX_ATTEMPTS = 5
RESEND_GAP = max(1, int(os.environ.get('CODE_RESEND_SECONDS') or 60))   # კოდის ხელახლა გაგზავნა არაუადრეს ამდენი წამისა (ტესტებში მცირდება)
SENDS_PER_HOUR = 5            # კოდის გაგზავნა ერთი IP+ელფოსტიდან საათში
IP_SENDS_PER_HOUR = int(os.environ.get('CODE_IP_SENDS_PER_HOUR') or 30)   # ერთი IP-დან საათში (ყველა ელფოსტა ერთად; კლასი ერთი NAT-ის უკან ბევრ ადგილს მოითხოვს)
VERIFY_IP_LIMIT = int(os.environ.get('CODE_VERIFY_IP_LIMIT') or 30)       # კოდის შეყვანის მოთხოვნა ერთი IP-დან 10 წუთში (კოდის გამოცნობას მთავარად 5 მცდელობა ზღუდავს)
ACCOUNT_SENDS_PER_HOUR = 10   # ერთი ანგარიშის კოდები საათში, IP-ს მიუხედავად: ახალ-ახალი IP-ებით კოდის გამოცნობას ზღუდავს (მაქს. 10×5 მცდელობა)
AUDIT_DAYS = int(os.environ.get('AUDIT_DAYS') or 90)  # რამდენ დღეს ინახება უსაფრთხოების ჟურნალი
REGISTER_LIMIT = int(os.environ.get('REGISTER_LIMIT') or 10)  # რეგისტრაციები ერთი IP-დან 10 წუთში
QUIZ_PICK, PASS_PCT = 5, 70                                       # კითხვა თითო მცდელობაში; გასავლელი ზღვარი (%)
QUIZ_MAX_FAILS = int(os.environ.get('QUIZ_MAX_FAILS') or 3)       # ყოველი ამდენი წარუმატებელი მცდელობის შემდეგ: განმარტებები + პაუზა
QUIZ_PAUSE_MS = int(float(os.environ.get('QUIZ_PAUSE_MINUTES') or 20) * 60_000)
QUIZ_ATTEMPT_TTL = 2 * 3_600_000                                  # დაწყებული მცდელობა 2 საათში უნდა დასრულდეს
LOGIN_IP_LIMIT = int(os.environ.get('LOGIN_IP_LIMIT') or 30)    # ერთი IP-დან ლოგინის მცდელობა 10 წუთში
LOGIN_PAIR_LIMIT = int(os.environ.get('LOGIN_PAIR_LIMIT') or 10)  # ერთი IP + ერთი ელფოსტა 10 წუთში
ALLOWED_HOSTS = {h.strip().lower() for h in os.environ.get('ALLOWED_HOSTS', '').split(',') if h.strip()}
AUTO_BACKUP = os.environ.get('AUTO_BACKUP') != '0'
PUB = os.path.realpath(os.path.join(db.HERE, 'public'))
SANDBOX = os.path.join(PUB, 'sandbox')
DAY = 86_400_000
LEVEL = {p['id']: p['level'] for p in PLANS}
PAID = [p['id'] for p in PLANS if p['level'] > 0]
MIME = {'.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
        '.png': 'image/png', '.woff2': 'font/woff2', '.svg': 'image/svg+xml', '.ico': 'image/x-icon', '.txt': 'text/plain; charset=utf-8',
        '.py': 'text/plain; charset=utf-8', '.json': 'application/json', '.wasm': 'application/wasm', '.zip': 'application/zip', '.mjs': 'text/javascript; charset=utf-8'}
CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; "
       "font-src 'self'; img-src 'self' data: https:; "
       "frame-src 'self' https://www.youtube-nocookie.com https://www.youtube.com https://player.vimeo.com; "
       "media-src https:; connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")
SEC = {'X-Permitted-Cross-Domain-Policies': 'none', 'X-Content-Type-Options': 'nosniff', 'X-Frame-Options': 'DENY', 'Referrer-Policy': 'same-origin',
       'Permissions-Policy': 'camera=(), microphone=(), geolocation=(), payment=(), usb=()',
       'Cross-Origin-Opener-Policy': 'same-origin', 'Cross-Origin-Resource-Policy': 'same-origin'}


def sandbox_csp(page):
    """/sandbox/*.html-ის საკუთარი CSP (მთავარი საიტის CSP აქ არ გამოიყენება). გვერდები iframe-ებს ჩვეულებრივი URL-ით (src) ვტვირთავთ და არა
    srcdoc/blob-ით: მათი პოლიტიკა მშობლისგან იღებს მემკვიდრეობას და ეს ბრაუზერებზეა დამოკიდებული, URL-ით ჩატვირთულ გვერდს კი მხოლოდ საკუთარი ჰედერი ეხება."""
    # preview.html: frame-ancestors 'self' აქ არ ვარგა (წინაპრად გაუმჭვირვალე წარმოშობის editor.html ჰყავს და ბრაუზერი მას 'self'-ად არ თვლის);
    # ამის ნაცვლად CSP sandbox: გვერდი ყოველთვის გაუმჭვირვალე წარმოშობით იხსნება, ვინც უნდა ის ჩადგას, ჩვენს წარმოშობაზე წვდომა არავის რჩება
    if page == 'preview.html':   # მოსწავლის HTML იწერება ამ დოკუმენტში: ინლაინ სკრიპტი/სტილი ვარგა, ქსელი, გარე რესურსი, ფორმა, iframe აკრძალულია
        return ("default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; font-src data:; media-src data:; "
                "base-uri 'none'; form-action 'none'; sandbox allow-scripts")
    host = (request.headers.get('X-Forwarded-Host') if TRUST_PROXY else None) or request.host
    o = ('https://' if secure() else 'http://') + host   # connect-src მხოლოდ სამ კონკრეტულ მისამართს ეხება: კოდიდან სხვა ქსელი მიუწვდომელია
    return ("default-src 'none'; script-src 'self' 'wasm-unsafe-eval'; style-src 'self'; worker-src blob:; "
            f"connect-src {o}/sandbox/pyworker.js {o}/sandbox/runner.py {o}/vendor/pyodide/; "
            "frame-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'self'; sandbox allow-scripts")


CTRL_RE = re.compile(r'[\x00-\x1f\x7f\u200b-\u200f\u202a-\u202e]')
EMAIL_RE = re.compile(r'\S+@\S+\.\S+')
SID_RE = re.compile(r'(?:^|; )sid=([a-f0-9]+)')

app = Flask(__name__, static_folder=None)
app.config['MAX_CONTENT_LENGTH'] = 100_000
app.json.ensure_ascii = False
app.json.sort_keys = False

_warn = mailer.startup_warning()
if _warn:
    print(_warn, flush=True)   # გაშვებისას ერთხელ
if envfile.LOADED:
    print('.env ჩაიტვირთა:', ', '.join(sorted(envfile.LOADED)), flush=True)   # მხოლოდ სახელები, მნიშვნელობების გარეშე
db.purge_audit(AUDIT_DAYS)
if AUTO_BACKUP:
    try:
        if db.last_backup_age() > 86400:
            db.backup()
    except Exception as e:  # noqa: BLE001
        print('backup:', e)


def now_ms():
    return int(time.time() * 1000)


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
            db.run('DELETE FROM tokens WHERE expires<?', now_ms())
            db.run('DELETE FROM codes WHERE hour_start<?', now_ms() - 3_600_000)   # საათობრივი მრიცხველიც ამ დროს იწურება
            _gate_sweep()
            db.purge_audit(AUDIT_DAYS)
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
    return client_ip(request.remote_addr, request.headers.get('X-Forwarded-For'), PROXY_COUNT)


def secure():
    return (os.environ.get('SECURE_COOKIE') == '1' or request.is_secure
            or (TRUST_PROXY and request.headers.get('X-Forwarded-Proto') == 'https'))


def body():
    d = request.get_json(silent=True, force=True)
    return d if isinstance(d, dict) else {}


def user_by_token(token):
    u = db.one('SELECT u.id,u.email,u.name,u.role,u.plan,u.plan_expires,u.email_verified,u.notify FROM sessions s JOIN users u ON u.id=s.user_id '
               'WHERE s.token=? AND s.expires>?', th(token), now_ms())
    if not u:
        return None
    expired = u['plan'] != 'free' and u['plan_expires'] and u['plan_expires'] < now_ms()
    plan = 'free' if expired else (u['plan'] if u['plan'] in LEVEL else 'free')
    verified = bool(u['email_verified']) or u['role'] == 'admin' or not REQUIRE_VERIFY
    return {**u, 'plan': plan, 'level': 3 if u['role'] == 'admin' else (LEVEL[plan] if verified else 0), 'verified': verified}   # დაუდასტურებელს ფასიანი წვდომა არ აქვს


def current_token():
    m = SID_RE.search(request.headers.get('Cookie') or '')
    return m.group(1) if m else None


def user_of():
    t = current_token()
    return user_by_token(t) if t else None


def pub(u):
    return u and {k: u[k] for k in ('id', 'email', 'name', 'role', 'plan', 'plan_expires', 'level', 'verified', 'notify')}


def lesson_level(l):
    return 0 if l['free'] else 1


# ---- კურსები (courses.py). status='soon' კურსი ჩვეულებრივ მოსწავლეს არ ჩანს: ადმინი ხსნის ყველა კურსს, რომელსაც გაკვეთილები აქვს.
def is_admin(u):
    return bool(u and u.get('role') == 'admin')


def course_has_lessons(cid):
    return bool(db.one('SELECT 1 FROM lessons WHERE course=? LIMIT 1', cid))


def course_open(u, cid):
    """შეუძლია თუ არა ამ მომხმარებელს (None = სტუმარი) კურსის გახსნა."""
    c = courses.get(cid)
    return bool(c and course_has_lessons(cid) and (c['status'] == 'available' or is_admin(u)))


def course_arg(default=courses.DEFAULT_COURSE):
    """?course=<id>: ცარიელი → default; უცნობი id → None."""
    v = (request.args.get('course') or '').strip()
    if not v:
        return default
    return v if courses.get(v) else None


def lesson_for(u, lid):
    """გაკვეთილის სრული ჩანაწერი ან None, თუ არ არსებობს ან მისი კურსი ამ მომხმარებლისთვის დახურულია (soon)."""
    l = db.one('SELECT * FROM lessons WHERE id=?', lid) if lid is not None else None
    return l if l and course_open(u, l['course']) else None


def course_stats(cid):
    r = db.one('SELECT COUNT(*) n, COALESCE(SUM(minutes),0) m FROM lessons WHERE course=?', cid)
    return {'stages': db.one('SELECT COUNT(*) c FROM stages WHERE course=?', cid)['c'], 'lessons': r['n'], 'minutes': r['m']}


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
    row = db.one('SELECT email FROM users WHERE id=?', uid)
    with db.tx():
        for t in ('sessions', 'progress', 'quiz_results', 'quiz_attempts', 'questions', 'tokens', 'codes'):
            db.run(f'DELETE FROM {t} WHERE user_id=?', uid)
        # ფინანსური ჩანაწერები რჩება ანონიმურად (user_id=0: თანხა, გეგმა და თარიღი უცვლელია); განუხილველ განაცხადს არავინ სჭირდება
        db.run("DELETE FROM orders WHERE user_id=? AND status='pending'", uid)
        db.run('UPDATE orders SET user_id=0 WHERE user_id=?', uid)
        # სერტიფიკატი რჩება გადამოწმებისთვის, მაგრამ სახელისა და მფლობელის გარეშე (უნიკალური უარყოფითი მარკერი)
        db.run("UPDATE certificates SET user_id=-rowid, name='' WHERE user_id=?", uid)
        db.run('DELETE FROM users WHERE id=?', uid)
        db.anonymize_audit(uid, row['email'] if row else '')


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
    if request.path.startswith(('/sandbox/', '/vendor/')):
        # გაუმჭვირვალე წარმოშობის (sandbox) გვერდს სჭირდება: CORP/CORS ღიაა მხოლოდ ამ ორ საქაღალდეზე (საჯარო სტატიკური ფაილებია, cookie-ს არ ატარებს)
        r.headers['Cross-Origin-Resource-Policy'] = 'cross-origin'
        r.headers['Access-Control-Allow-Origin'] = '*'
        if request.path.startswith('/sandbox/'):
            r.headers.pop('X-Frame-Options', None)   # ჩადგმა იმართება CSP frame-ancestors 'self'-ით; XFO SAMEORIGIN sandbox-იან მშობელზე ვერ მუშაობს
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
    return send(200, {'plans': PLANS, 'payInfo': PAY_INFO, 'contact': CONTACT, 'mentor': MENTOR_NAME,
                      'requireVerify': REQUIRE_VERIFY, 'minPw': MIN_PW_LEN, 'codeMinutes': CODE_TTL_MS // 60_000, 'resendSeconds': RESEND_GAP,
                      'quizPassPct': PASS_PCT, 'quizMaxFails': QUIZ_MAX_FAILS, 'quizPauseMinutes': QUIZ_PAUSE_MS // 60000})


@app.post('/api/register')
def r_register():
    if limited('r' + ip_of(), REGISTER_LIMIT):
        return send(429, {'error': 'ძალიან ბევრი მცდელობა. სცადე მოგვიანებით.'})
    d = body()
    email, name, password, terms = d.get('email', ''), d.get('name', ''), d.get('password', ''), d.get('terms')
    if isinstance(name, str):
        name = CTRL_RE.sub('', name)
    if REQUIRE_VERIFY:
        # ახალი ნაკადი: სახელი + ელფოსტა → 6-ნიშნა კოდი ფოსტაზე → კოდის გვერდზე პაროლს მომხმარებელი თავად ირჩევს (POST /api/verify).
        # რეგისტრაციისას გამოგზავნილ პაროლს ვერ ვიღებთ და ვერ ვინახავთ: სხვისი ელფოსტით რეგისტრაცია ანგარიშზე წვდომას ვერ იძლევა.
        if (not isinstance(email, str) or not isinstance(name, str) or not EMAIL_RE.fullmatch(email.strip()) or len(email) > 120 or len(name.strip()) < 2):
            return send(400, {'error': 'შეავსე სწორად: სახელი და ელფოსტა.'})
        if terms is not True:
            return send(400, {'error': 'გაგრძელებისთვის დაეთანხმე წესებს.'})
        e, ip = email.strip().lower(), ip_of()
        wait = mail_gate('v', ip, e)
        if wait:
            return gate_error(wait)
        threading.Thread(target=_register_job, args=(e, name.strip()[:60], ip), daemon=True).start()   # ფონურად: პასუხის დრო არ ავლენს, არსებობს თუ არა ანგარიში
        return send(200, {'ok': True, 'message': REGISTER_MSG, 'resend_in': RESEND_GAP})
    # დადასტურება გამორთულია (REQUIRE_EMAIL_VERIFY=0): ძველი ნაკადი (პაროლი რეგისტრაციისას, ავტომატური შესვლა, 409 არსებულ ელფოსტაზე)
    if isinstance(password, str) and MIN_PW_LEN <= len(password) <= 200 and isinstance(email, str) and not strong_pw(password, email, name if isinstance(name, str) else ''):
        return send(400, {'error': 'ეს პაროლი ძალიან მარტივია. აირჩიე უფრო რთული.'})
    if (not isinstance(email, str) or not isinstance(name, str) or not EMAIL_RE.fullmatch(email) or len(email) > 120
            or len(name.strip()) < 2 or not strong_pw(password, email, name)):
        return send(400, {'error': f'შეავსე სწორად: სახელი, ელფოსტა და პაროლი (მინ. {MIN_PW_LEN} სიმბოლო).'})
    if terms is not True:
        return send(400, {'error': 'გაგრძელებისთვის დაეთანხმე წესებს.'})
    e, salt = email.strip().lower(), secrets.token_hex(16)
    pw_hash = hash_pw(password, salt)
    nm = name.strip()[:60]
    if db.one('SELECT 1 FROM users WHERE email=?', e):
        return send(409, {'error': 'ეს ელფოსტა უკვე რეგისტრირებულია.'})
    try:
        db.run('INSERT INTO users(email,name,hash,salt,role,created,email_verified) VALUES(?,?,?,?,?,?,1)', e, nm, pw_hash, salt, 'student', now_ms())
    except sqlite3.IntegrityError:
        return send(409, {'error': 'ეს ელფოსტა უკვე რეგისტრირებულია.'})
    db.audit(db.one('SELECT id FROM users WHERE email=?', e)['id'], 'register', '', ip_of())
    return login(e)


REGISTER_MSG = ('თუ ეს ელფოსტა თავისუფალია, გამოგიგზავნეთ 6-ნიშნა კოდი. შეამოწმე შემომავალი და სპამის საქაღალდე. კოდი 10 წუთი მოქმედებს. '
                'კოდის შეყვანისას თავად აირჩევ პაროლს; მანამდე ანგარიშს პაროლი არ აქვს.')
PW_HELP = f'პაროლი მინიმუმ {MIN_PW_LEN} სიმბოლო უნდა იყოს (ჰარებიანი ფრაზაც ვარგა), არ უნდა იყოს გავრცელებული პაროლი და არ უნდა შეიცავდეს ელფოსტის სახელს.'
NO_PASSWORD = '!'   # არ არის scrypt-ის შესაძლო შედეგი (ის 128 თექვსმეტობითი სიმბოლოა): ასეთი ჰეში არცერთ პაროლს არ ემთხვევა


def _register_job(e, nm, ip):
    try:
        u = db.one('SELECT id,name,role,email_verified FROM users WHERE email=?', e)
        if not u:
            try:
                db.run('INSERT INTO users(email,name,hash,salt,role,created,email_verified) VALUES(?,?,?,?,?,?,0)',
                       e, nm, NO_PASSWORD, secrets.token_hex(16), 'student', now_ms())
            except sqlite3.IntegrityError:
                return   # პარალელური მოთხოვნა იგივე ელფოსტით
            u = db.one('SELECT id,name,role,email_verified FROM users WHERE email=?', e)
            db.audit(u['id'], 'register', '', ip)
        if u['role'] != 'admin' and not u['email_verified']:
            send_code(u['id'], e, u['name'], 'verify')    # ახალი ან ჯერ დაუდასტურებელი ანგარიში
        elif not limited('rn' + e, 2):
            mailer.send_now(e, 'CDA: ანგარიში უკვე არსებობს',
                            f'ვიღაცამ (შესაძლოა შენ) სცადა რეგისტრაცია ამ ელფოსტით, მაგრამ ანგარიში უკვე არსებობს.\nშესვლა: {BASE_URL}/#/login\nპაროლი დაგავიწყდა: {BASE_URL}/#/forgot\n\nთუ ეს შენ არ იყავი, უგულებელყავი ეს წერილი.')
    except Exception as ex:  # noqa: BLE001
        print('register job:', ex)


def notify_mentors(subject, text):
    """მენტორს (MENTOR_EMAIL ან ყველა ადმინს) ახალი კითხვა/დავალება. თემა მუდმივი ტექსტია: მომხმარებლის მონაცემი სათაურში არ ხვდება."""
    to = [x.strip() for x in (os.environ.get('MENTOR_EMAIL') or '').split(',') if x.strip()] or [r['email'] for r in db.all_("SELECT email FROM users WHERE role='admin'")]
    for e in to:
        mailer.send(e, subject, text)


def notify_student(uid, subject, text):
    r = db.one('SELECT email,notify FROM users WHERE id=?', uid)
    if r and r['notify']:
        mailer.send(r['email'], subject, text + '\n\nშეტყობინებების გამორთვა შეგიძლია ანგარიშის გვერდზე.')


# ---------------------------------------------------------------- 6-ნიშნა კოდები (დადასტურება, პაროლის აღდგენა)
CODE_RE = re.compile(r'\d{6}')
CODE_ERR = 'კოდი არასწორია ან ვადა გაუვიდა. საჭიროების შემთხვევაში მოითხოვე ახალი კოდი.'
_win = {}                 # გაგზავნის მრიცხველები (წამი): გასაღები -> დროების სია; მეხსიერებაში, როგორც სხვა ლიმიტები (gunicorn -w 1)
_win_lock = threading.Lock()


def mail_gate(kind, ip, email):
    """კოდის გაგზავნის ლიმიტი IP+ელფოსტაზე: არაუადრეს RESEND_GAP წამისა და საათში მაქს. SENDS_PER_HOUR; დამატებით IP-ზე IP_SENDS_PER_HOUR.
    გასაღები მხოლოდ შეყვანილ მონაცემზეა დამოკიდებული და არა იმაზე, არსებობს თუ არა ანგარიში, ამიტომ პასუხი არსებობას არ ავლენს.
    აბრუნებს None-ს (შეიძლება გაგზავნა) ან (მიზეზი, წამები)."""
    now = time.time()
    kp, ki = f'p|{kind}|{ip}|{email}', f'i|{ip}'
    with _win_lock:
        ts = [t for t in _win.get(kp, ()) if now - t < 3600]
        its = [t for t in _win.get(ki, ()) if now - t < 3600]
        if ts and now - ts[-1] < RESEND_GAP:
            return 'gap', math.ceil(RESEND_GAP - (now - ts[-1]))
        if len(ts) >= SENDS_PER_HOUR:
            return 'hour', math.ceil(3600 - (now - ts[0]))
        if len(its) >= IP_SENDS_PER_HOUR:
            return 'hour', math.ceil(3600 - (now - its[0]))
        ts.append(now)
        its.append(now)
        _win[kp], _win[ki] = ts, its
    return None


def _gate_sweep():
    now = time.time()
    with _win_lock:
        for k in [k for k, v in _win.items() if not v or now - v[-1] >= 3600]:
            del _win[k]


def gate_error(wait):
    why, sec = wait
    if why == 'gap':
        return send(429, {'error': f'კოდი ახლახან გაიგზავნა. ახალი კოდის მოთხოვნა შეგიძლია {sec} წამში.', 'retry_after': sec})
    return send(429, {'error': f'ამ ელფოსტაზე საათში მაქსიმუმ {SENDS_PER_HOUR} კოდის გაგზავნაა შესაძლებელი. სცადე დაახლოებით {math.ceil(sec / 60)} წუთის შემდეგ.', 'retry_after': sec})


def code_hash(salt, uid, kind, code):
    return hmac.new(salt.encode(), f'{uid}:{kind}:{code}'.encode(), hashlib.sha256).hexdigest()


def issue_code(uid, kind):
    """ახალი 6-ნიშნა კოდი (secrets). ბაზაში მხოლოდ მარილიანი HMAC-ჰეში ინახება; წინა კოდი უქმდება, მცდელობები ნულდება.
    აბრუნებს ტექსტს, ან None-ს, თუ ამ ანგარიშს საათში უკვე ACCOUNT_SENDS_PER_HOUR კოდი გაეგზავნა."""
    now = now_ms()
    with db.tx():
        row = db.one('SELECT hour_start,hour_sends FROM codes WHERE user_id=? AND kind=?', uid, kind)
        hs, hn = (row['hour_start'], row['hour_sends']) if row else (0, 0)
        if now - hs >= 3_600_000:
            hs, hn = now, 0
        if hn >= ACCOUNT_SENDS_PER_HOUR:
            return None
        code, salt = f'{secrets.randbelow(10 ** 6):06d}', secrets.token_hex(16)
        db.run('INSERT OR REPLACE INTO codes(user_id,kind,salt,hash,expires,attempts,hour_start,hour_sends) VALUES(?,?,?,?,?,0,?,?)',
               uid, kind, salt, code_hash(salt, uid, kind, code), now + CODE_TTL_MS, hs, hn + 1)
    return code


def send_code(uid, email, name, kind):
    """კოდს ქმნის და წერილით აგზავნის (მიმდინარე ნაკადში: გამოიძახე ფონურიდან). თემა მუდმივია და კოდს არ შეიცავს."""
    code = issue_code(uid, kind)
    if code is None:
        return False
    mins = CODE_TTL_MS // 60_000
    if kind == 'verify':
        mailer.send_now(email, 'CDA: ელფოსტის დადასტურება',
                        f'გამარჯობა, {name}!\n\nშენი დადასტურების კოდი: {code}\n\nკოდი მოქმედებს {mins} წუთი და მხოლოდ ერთხელ გამოიყენება. შეიყვანე ის საიტზე და აირჩიე პაროლი. არავის გადასცე ეს კოდი.\n\n'
                        'თუ ეს შენ არ იყავი, უგულებელყავი ეს წერილი.')
    else:
        mailer.send_now(email, 'CDA: პაროლის აღდგენა',
                        f'შენი პაროლის აღდგენის კოდი: {code}\n\nკოდი მოქმედებს {mins} წუთი და მხოლოდ ერთხელ გამოიყენება. შეიყვანე ის საიტზე და აირჩიე ახალი პაროლი. არავის გადასცე ეს კოდი.\n\n'
                        'თუ ეს შენ არ იყავი, უგულებელყავი ეს წერილი: პაროლი არ შეიცვლება.')
    return True


def redeem_code(kind):
    """კოდის შემოწმება და პაროლის დაყენება (დადასტურება და აღდგენა ერთნაირად).
    აბრუნებს (პასუხი, user_id): პასუხი None-ია წარმატებისას, სხვა შემთხვევაში მზა HTTP პასუხი."""
    d = body()
    email, code, pw = d.get('email'), d.get('code'), d.get('password')
    ip = ip_of()
    if not isinstance(email, str) or not EMAIL_RE.fullmatch(email.strip()) or len(email) > 120 or not isinstance(code, str) or not isinstance(pw, str):
        return send(400, {'error': 'შეავსე ელფოსტა, კოდი და პაროლი.'}), None
    e, code = email.strip().lower(), code.strip()
    u = db.one('SELECT id,email,name,role,email_verified FROM users WHERE email=?', e)
    # პაროლის სიძლიერე ანგარიშის არსებობაზე და კოდზე არ არის დამოკიდებული, ამიტომ მისი შეტყობინება არაფერს ავლენს და ლიმიტში არ ითვლება
    if not strong_pw(pw, e, u['name'] if u else ''):
        return send(400, {'error': PW_HELP}), None
    if limited('vc' + ip, VERIFY_IP_LIMIT) or limited('vce' + ip + '|' + e, 10):
        return send(429, {'error': 'ძალიან ბევრი მცდელობა. სცადე მოგვიანებით.'}), None
    salt = secrets.token_hex(16)
    new_hash = hash_pw(pw, salt)   # ყოველთვის ითვლება (ერთნაირი დრო არსებულ და არარსებულ ანგარიშზე)
    bad = send(400, {'error': CODE_ERR})
    if not CODE_RE.fullmatch(code) or not u or u['role'] == 'admin' or (kind == 'verify' and u['email_verified']):
        return bad, None   # ადმინის პაროლი კოდით არ იცვლება (make_admin.py); დადასტურებულს დადასტურება აღარ სჭირდება
    now = now_ms()
    with db.tx():   # ტრანზაქციაში: პარალელური მოთხოვნებით 5 მცდელობაზე მეტი ვერავინ გააკეთებს, კოდი ერთხელ იხარჯება
        row = db.one('SELECT salt,hash,expires,attempts FROM codes WHERE user_id=? AND kind=?', u['id'], kind)
        if not row or row['expires'] <= now or row['attempts'] >= CODE_MAX_ATTEMPTS:
            return bad, None
        if not same(code_hash(row['salt'], u['id'], kind, code), row['hash']):
            n = row['attempts'] + 1
            # მე-5 არასწორის შემდეგ კოდი უქმდება (expires=0), მწკრივი კი რჩება: საათობრივი მრიცხველი არ ნულდება
            db.run('UPDATE codes SET attempts=?, expires=CASE WHEN ?>=? THEN 0 ELSE expires END WHERE user_id=? AND kind=?', n, n, CODE_MAX_ATTEMPTS, u['id'], kind)
            if n >= CODE_MAX_ATTEMPTS:
                db.audit(u['id'], 'code_locked', kind, ip)
            return bad, None
        db.run('UPDATE users SET hash=?,salt=?,email_verified=1 WHERE id=?', new_hash, salt, u['id'])   # წერილის მიღება ელფოსტას ადასტურებს
        db.run('DELETE FROM sessions WHERE user_id=?', u['id'])                                           # ყველა ძველი სესია იშლება
        db.run('DELETE FROM codes WHERE user_id=?', u['id'])                                              # დარჩენილი კოდები აღარ გამოდგება
    return None, u


@app.post('/api/login')
def r_login():
    d = body()
    email, password = d.get('email', ''), d.get('password', '')
    if not isinstance(email, str) or not isinstance(password, str):
        return send(400, {'error': 'არასწორი მონაცემი.'})
    ip = ip_of()
    # ელფოსტაზე ცალკე ლიმიტი არ გვაქვს: სხვის ანგარიშს ვერავინ დაბლოკავს. ლიმიტი IP-ზე და IP+ელფოსტის წყვილზეა
    if limited('l' + ip, LOGIN_IP_LIMIT) or limited('le' + ip + '|' + email.strip().lower()[:120], LOGIN_PAIR_LIMIT):
        return send(429, {'error': 'ძალიან ბევრი მცდელობა. სცადე მოგვიანებით.'})
    u = db.one('SELECT * FROM users WHERE email=?', email.strip().lower())
    hh = hash_pw(password, u['salt'] if u else DUMMY_SALT)  # ერთნაირი დრო არსებული და არარსებული ანგარიშისთვის
    # პაროლი აქტიურია მხოლოდ ელფოსტის დადასტურების შემდეგ (ადმინი make_admin.py-ით ყოველთვის დადასტურებულია).
    # შეტყობინება ყველა შემთხვევაში ერთნაირია, რომ არსებობა/დაუდასტურებლობა არ გამჟღავნდეს.
    inactive = bool(u) and REQUIRE_VERIFY and not u['email_verified'] and u['role'] != 'admin'
    if not u or not same(hh, u['hash']) or inactive:
        db.audit(u['id'] if u else None, 'login_fail' if not inactive else 'login_unverified', email.strip().lower()[:80], ip_of())
        return send(401, {'error': 'ელფოსტა ან პაროლი არასწორია (ან ელფოსტა ჯერ არ არის დადასტურებული).'})
    return login(u['email'])


@app.post('/api/verify')
def r_verify():
    """ელფოსტის დადასტურება კოდით + პაროლის არჩევა; წარმატებისას ანგარიში დადასტურებულია და მომხმარებელი შედის (ახალი სესიით)."""
    if not REQUIRE_VERIFY:
        return send(400, {'error': 'ელფოსტის დადასტურება გამორთულია.'})
    err, u = redeem_code('verify')
    if err:
        return err
    db.audit(u['id'], 'email_verified', '', ip_of())
    return login(u['email'])


@app.post('/api/verify/resend')
def r_verify_resend():
    """დადასტურების კოდის ხელახლა გაგზავნა: შესვლა დაუდასტურებელს არ შეუძლია, ამიტომ ელფოსტით მუშაობს და პასუხი ნეიტრალურია."""
    if not REQUIRE_VERIFY:
        return send(400, {'error': 'ელფოსტის დადასტურება გამორთულია.'})
    email = body().get('email')
    if not isinstance(email, str) or not EMAIL_RE.fullmatch(email.strip()) or len(email) > 120:
        return send(400, {'error': 'შეიყვანე სწორი ელფოსტა.'})
    e = email.strip().lower()
    wait = mail_gate('v', ip_of(), e)
    if wait:
        return gate_error(wait)

    def job():
        try:
            u = db.one('SELECT id,name,role,email_verified FROM users WHERE email=?', e)
            if u and u['role'] != 'admin' and not u['email_verified']:
                send_code(u['id'], e, u['name'], 'verify')
        except Exception as ex:  # noqa: BLE001
            print('resend job:', ex)
    threading.Thread(target=job, daemon=True).start()
    return send(200, {'ok': True, 'message': 'თუ ეს ელფოსტა დადასტურებას ელოდება, ახალი კოდი გამოგიგზავნეთ.', 'resend_in': RESEND_GAP})


FORGOT_MSG = 'თუ ეს ელფოსტა რეგისტრირებულია, პაროლის აღდგენის კოდი გამოგიგზავნეთ. შეამოწმე შემომავალი და სპამის საქაღალდე. კოდი 10 წუთი მოქმედებს.'


def _forgot_job(email):
    """ფონურ ნაკადში, რომ პასუხის დრო არსებულ და არარსებულ ანგარიშზე ერთნაირი იყოს."""
    try:
        u = db.one('SELECT id,name,role FROM users WHERE email=?', email)
        if not u or u['role'] == 'admin':  # ადმინის პაროლი ელფოსტით არ აღდგება: მხოლოდ make_admin.py-ით
            return
        send_code(u['id'], email, u['name'], 'reset')
    except Exception as e:  # noqa: BLE001
        print('forgot job:', e)


@app.post('/api/password/forgot')
def r_forgot():
    email = body().get('email')
    if not isinstance(email, str) or not EMAIL_RE.fullmatch(email.strip()) or len(email) > 120:
        return send(400, {'error': 'შეიყვანე სწორი ელფოსტა.'})
    e = email.strip().lower()
    wait = mail_gate('r', ip_of(), e)
    if wait:
        return gate_error(wait)
    threading.Thread(target=_forgot_job, args=(e,), daemon=True).start()
    return send(200, {'ok': True, 'message': FORGOT_MSG, 'resend_in': RESEND_GAP})  # პასუხი იგივეა, ანგარიში არსებობს თუ არა


@app.post('/api/password/reset')
def r_reset():
    """ახალი პაროლი კოდით; ყველა სესია წყდება. ავტომატური შესვლა არ ხდება."""
    err, u = redeem_code('reset')
    if err:
        return err
    db.audit(u['id'], 'password_reset', '', ip_of())
    return send(200, {'ok': True})


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
    db.audit(None, 'account_delete', '', '')  # ელფოსტა და IP ჟურნალში არ რჩება
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


@app.post('/api/notify')
def r_notify():
    u = user_of()
    if not u:
        return need_login()
    db.run('UPDATE users SET notify=? WHERE id=?', 1 if body().get('on') else 0, u['id'])
    return send(200, {'ok': True})


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
        return send(400, {'error': PW_HELP})
    salt = secrets.token_hex(16)
    db.run('UPDATE users SET hash=?,salt=? WHERE id=?', hash_pw(nxt, salt), salt, u['id'])
    db.run('DELETE FROM sessions WHERE user_id=? AND token<>?', u['id'], th(current_token()))  # სხვა სესიები წყდება
    db.audit(u['id'], 'password_change', '', ip_of())
    return send(200, {'ok': True})


def _quiz_passed(uid, lid):
    r = db.one('SELECT passed FROM quiz_results WHERE user_id=? AND lesson_id=?', uid, lid)
    return bool(r and r['passed'])


@app.get('/api/courses')
def r_courses():
    """კურსების სია. მოსწავლეს: ყველა კურსი სტატუსით (available ან soon; ხელმისაწვდომს რიცხვებიც აქვს). ადმინს: ასევე has_content და
    open (შეუძლია გახსნა — soon კურსიც, თუ გაკვეთილები აქვს). available კურსი, რომელსაც შიგთავსი არ აქვს, მოსწავლეს ჩანს როგორც soon."""
    u = user_of()
    out = []
    for c in courses.COURSES:
        has = course_has_lessons(c['id'])
        st = c['status'] if has or c['status'] != 'available' else 'soon'
        row = {'id': c['id'], 'title': c['title'], 'description': c['description'], 'status': st}
        if has and (st == 'available' or is_admin(u)):
            row.update(course_stats(c['id']))
        if is_admin(u):
            row.update({'has_content': has, 'open': has, 'configured_status': c['status']})
        out.append(row)
    return send(200, {'courses': out, 'default': courses.DEFAULT_COURSE})


@app.get('/api/lessons')
def r_lessons():
    """მხოლოდ მეტამონაცემები (ტექსტი და ქვიზი ცალკე: /api/lesson/<id>). ?course=<id> (ნაგულისხმევი cybersecurity-beginners)."""
    u = user_of()
    cid = course_arg()
    if not cid or not course_open(u, cid):
        return send(404, {'error': 'კურსი ვერ მოიძებნა.'})
    lv = u['level'] if u else 0
    done = [r['lesson_id'] for r in db.all_('SELECT p.lesson_id FROM progress p JOIN lessons l ON l.id=p.lesson_id WHERE p.user_id=? AND l.course=?', u['id'], cid)] if u else []
    sc = db.all_('SELECT r.lesson_id,r.score,r.total,r.passed FROM quiz_results r JOIN lessons l ON l.id=r.lesson_id WHERE r.user_id=? AND l.course=?', u['id'], cid) if u else []
    scores = {str(r['lesson_id']): [r['score'], r['total']] for r in sc}
    passed = [r['lesson_id'] for r in sc if r['passed']]
    rows = []
    for l in db.all_('SELECT id,week,pos,title,summary,free,minutes,quiz FROM lessons WHERE course=? ORDER BY week,pos', cid):
        rows.append({'id': l['id'], 'stage': l['week'], 'pos': l['pos'], 'title': l['title'], 'summary': l['summary'],
                     'free': bool(l['free']), 'minutes': l.get('minutes') or 0, 'locked': lv < lesson_level(l),
                     'quiz_n': len(parse_quiz(l))})
    stages = db.all_('SELECT id,title,description FROM stages WHERE course=? ORDER BY id', cid)
    return send(200, {'course': cid, 'stages': stages, 'lessons': rows, 'done': done, 'scores': scores, 'passed': passed})


@app.get('/api/lesson/<int:lid>')
def r_lesson(lid):
    u = user_of()
    lv = u['level'] if u else 0
    l = lesson_for(u, lid)
    if not l:
        return send(404, {'error': 'გაკვეთილი ვერ მოიძებნა.'})
    if lv < lesson_level(l):
        return send(403, {'error': 'ეს გაკვეთილი გადახდილი გეგმის მფლობელებისთვისაა.', 'locked': True})
    try:
        obj = json.loads(l.get('objectives') or '[]')
    except ValueError:
        obj = []
    q = {'best': None, 'passed': False, 'retry_at': None}
    if u:
        r = db.one('SELECT score,total,passed FROM quiz_results WHERE user_id=? AND lesson_id=?', u['id'], lid)
        if r:
            q.update(best=[r['score'], r['total']], passed=bool(r['passed']))
        q['retry_at'] = _quiz_block(u['id'], lid)
    return send(200, {'id': l['id'], 'content': l['content'], 'task': l['task'], 'video_url': l['video_url'], 'pdf_url': l['pdf_url'],
                      'video_title': l.get('video_title') or '', 'video_channel': l.get('video_channel') or '',
                      'video2_url': l.get('video2_url') or '', 'video2_title': l.get('video2_title') or '', 'video2_channel': l.get('video2_channel') or '',
                      'objectives': obj if isinstance(obj, list) else [], 'quiz_n': len(parse_quiz(l)), 'quiz': q,
                      'bonus': l['bonus'] if lv >= 2 else '', 'bonus_locked': lv < 2 and bool(l['bonus']),
                      'exercises': [{k: v for k, v in x.items() if k != 'solution'} for x in _exercises(l)]})


def _exercises(l):
    try:
        v = json.loads(l.get('exercises') or '[]')
    except ValueError:
        return []
    return [x for x in v if isinstance(x, dict)] if isinstance(v, list) else []


@app.get('/api/lesson/<int:lid>/exercise/<eid>/solution')
def r_solution(lid, eid):
    """ამოხსნა ცალკე და მხოლოდ მოთხოვნით იგზავნება (გაკვეთილის JSON-ში solution არ არის); წვდომა იგივეა, რაც გაკვეთილზე."""
    u = user_of()
    l = lesson_for(u, lid)
    if not l:
        return send(404, {'error': 'გაკვეთილი ვერ მოიძებნა.'})
    if (u['level'] if u else 0) < lesson_level(l):
        return send(403, {'error': 'ეს გაკვეთილი გადახდილი გეგმის მფლობელებისთვისაა.', 'locked': True})
    for x in _exercises(l):
        if x.get('id') == eid:
            return send(200, {'solution': x.get('solution', '')})
    return send(404, {'error': 'სავარჯიშო ვერ მოიძებნა.'})


def _accessible_lesson(u, lesson_id):
    l = lesson_for(u, tint(lesson_id))
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
        # გაკვეთილი მხოლოდ ქვიზის გავლის (>=70%) შემდეგ მთავრდება. უკვე დასრულებული ჩანაწერი უცვლელია (ძველი პროგრესი)
        if parse_quiz(l) and not _quiz_passed(u['id'], l['id']) and not db.one('SELECT 1 FROM progress WHERE user_id=? AND lesson_id=?', u['id'], l['id']):
            return send(403, {'error': f'გაკვეთილის დასასრულებლად ქვიზში მინიმუმ {PASS_PCT}% უნდა დააგროვო.', 'need_quiz': True})
        db.run('INSERT OR IGNORE INTO progress(user_id,lesson_id,done_at) VALUES(?,?,?)', u['id'], l['id'], now_ms())
    else:
        db.run('DELETE FROM progress WHERE user_id=? AND lesson_id=?', u['id'], l['id'])
    return send(200, {'ok': True})


def _quiz_fails(uid, lid):
    r = db.one('SELECT COUNT(*) n, MAX(finished_at) t FROM quiz_attempts WHERE user_id=? AND lesson_id=? AND finished=1 AND passed=0', uid, lid)
    return r['n'], r['t']


def _quiz_block(uid, lid):
    """ყოველი QUIZ_MAX_FAILS-ურ წარუმატებელ მცდელობას მოსდევს პაუზა (QUIZ_PAUSE_MINUTES). აბრუნებს განბლოკვის დროს (ms) ან None-ს.
    გავლილ გაკვეთილზე პაუზა აღარ მოქმედებს."""
    if _quiz_passed(uid, lid):
        return None
    n, t = _quiz_fails(uid, lid)
    if n and n % QUIZ_MAX_FAILS == 0 and t and now_ms() < t + QUIZ_PAUSE_MS:
        return t + QUIZ_PAUSE_MS
    return None


def _qhash(x):
    return hashlib.sha256((str(x.get('q')) + '\x00' + '\x00'.join(map(str, x.get('o') or []))).encode()).hexdigest()[:12]


def _quiz_payload(bank, items):
    return [{'q': bank[it['i']]['q'], 'o': [bank[it['i']]['o'][k] for k in it['p']]} for it in items]


@app.post('/api/quiz/start')
def r_quiz_start():
    """ქვიზის ახალი მცდელობა: ბანკიდან შემთხვევითი კითხვები და შემთხვევითი თანმიმდევრობის პასუხები. სწორი პასუხი კლიენტს არ ეგზავნება."""
    u = user_of()
    if not u:
        return need_login()
    l = _accessible_lesson(u, body().get('lesson_id'))
    if not l:
        return send(403, {'error': 'წვდომა არ გაქვს.'})
    bank = parse_quiz(l)
    if not bank:
        return send(400, {'error': 'ამ გაკვეთილს ქვიზი არ აქვს.'})
    if limited('qs' + str(u['id']), 60):
        return send(429, {'error': 'ძალიან ბევრი მოთხოვნა. სცადე მოგვიანებით.'})
    retry = _quiz_block(u['id'], l['id'])
    if retry:
        return send(429, {'error': 'ქვიზს მცირე პაუზა აქვს. ამ დროს გადაიკითხე გაკვეთილი და განმარტებები, მერე სცადე ახალი კითხვებით.', 'retry_at': retry})
    cur = db.one('SELECT id,items FROM quiz_attempts WHERE user_id=? AND lesson_id=? AND finished=0 AND created>? ORDER BY id DESC',
                 u['id'], l['id'], now_ms() - QUIZ_ATTEMPT_TTL)
    items = None
    if cur:  # გვერდის განახლებისას იგივე მცდელობა გრძელდება (კითხვების „გადანაწილებით“ ბანკს ვერავინ შეისწავლის)
        try:
            items = json.loads(cur['items'])
            if any(it['i'] >= len(bank) or it['h'] != _qhash(bank[it['i']]) for it in items):
                items = None
        except (ValueError, KeyError, TypeError):
            items = None
    if items is None:
        rnd = secrets.SystemRandom()
        items = []
        pool = list(range(len(bank)))
        n_fail, _t = _quiz_fails(u['id'], l['id'])
        if n_fail and n_fail % QUIZ_MAX_FAILS == 0 and not _quiz_passed(u['id'], l['id']):   # განმარტებები ეს-ესაა ნახა: ახალი კითხვები, თუ ბანკი იძლევა
            last = db.one('SELECT items FROM quiz_attempts WHERE user_id=? AND lesson_id=? AND finished=1 ORDER BY id DESC', u['id'], l['id'])
            try:
                seen = {it['i'] for it in json.loads(last['items'])}
            except (ValueError, KeyError, TypeError):
                seen = set()
            fresh = [i for i in pool if i not in seen]
            if len(fresh) >= min(QUIZ_PICK, len(bank)):
                pool = fresh
        for i in rnd.sample(pool, min(QUIZ_PICK, len(bank))):
            p = list(range(len(bank[i]['o'])))
            rnd.shuffle(p)
            items.append({'i': i, 'h': _qhash(bank[i]), 'p': p})
        db.run('UPDATE quiz_attempts SET finished=2 WHERE user_id=? AND lesson_id=? AND finished=0', u['id'], l['id'])  # ძველი დაუსრულებელი უქმდება
        db.run('INSERT INTO quiz_attempts(user_id,lesson_id,created,items) VALUES(?,?,?,?)', u['id'], l['id'], now_ms(), json.dumps(items))
        cur = db.one('SELECT id FROM quiz_attempts WHERE user_id=? AND lesson_id=? ORDER BY id DESC', u['id'], l['id'])
    return send(200, {'attempt_id': cur['id'], 'questions': _quiz_payload(bank, items), 'pass_pct': PASS_PCT})


@app.post('/api/quiz')
def r_quiz():
    u = user_of()
    if not u:
        return need_login()
    d = body()
    aid = tint(d.get('attempt_id'))
    at = db.one('SELECT * FROM quiz_attempts WHERE id=? AND user_id=?', aid, u['id']) if aid is not None else None
    if not at or at['finished'] != 0:
        return send(400, {'error': 'მცდელობა ვერ მოიძებნა ან უკვე დასრულებულია. დაიწყე ახალი.'})
    l = _accessible_lesson(u, at['lesson_id'])
    if not l:
        return send(403, {'error': 'წვდომა არ გაქვს.'})
    if at['created'] < now_ms() - QUIZ_ATTEMPT_TTL:
        return send(400, {'error': 'მცდელობას ვადა გაუვიდა. დაიწყე ახალი.'})
    bank, items, answers = parse_quiz(l), json.loads(at['items']), d.get('answers')
    if any(it['i'] >= len(bank) or it['h'] != _qhash(bank[it['i']]) for it in items):
        return send(400, {'error': 'ქვიზი განახლდა. დაიწყე თავიდან.'})
    if not isinstance(answers, list) or len(answers) != len(items):
        return send(400, {'error': 'უპასუხე ყველა კითხვას.'})
    res = []
    for it, ans in zip(items, answers):
        k = tint(ans)
        if k is None or not 0 <= k < len(it['p']):
            return send(400, {'error': 'უპასუხე ყველა კითხვას.'})
        x = bank[it['i']]
        res.append({'ok': it['p'][k] == x.get('a'), 'correct': it['p'].index(x.get('a')) if x.get('a') in it['p'] else None, 'e': x.get('e')})
    score, total = sum(1 for r in res if r['ok']), len(res)
    passed = total > 0 and score * 100 >= total * PASS_PCT
    with db.tx():
        if db.run('UPDATE quiz_attempts SET finished=1,score=?,total=?,passed=?,finished_at=? WHERE id=? AND finished=0', score, total, int(passed), now_ms(), at['id']) != 1:
            return send(400, {'error': 'მცდელობა უკვე დასრულებულია.'})  # პარალელური ორმაგი გაგზავნა
        old = db.one('SELECT score,total,passed FROM quiz_results WHERE user_id=? AND lesson_id=?', u['id'], l['id'])
        if not old:
            db.run('INSERT INTO quiz_results(user_id,lesson_id,score,total,passed) VALUES(?,?,?,?,?)', u['id'], l['id'], score, total, int(passed))
        else:
            better = score * old['total'] > old['score'] * total
            db.run('UPDATE quiz_results SET score=?,total=?,passed=? WHERE user_id=? AND lesson_id=?',
                   score if better else old['score'], total if better else old['total'], int(passed or old['passed']), u['id'], l['id'])
    retry = None if passed else _quiz_block(u['id'], l['id'])
    reveal = passed or retry is not None   # გავლისას ან ყოველი მესამე წარუმატებლობის შემდეგ ჩანს სწორი პასუხები და განმარტებები
    out = [{'ok': r['ok'], **({'correct': r['correct'], 'e': r['e']} if reveal else {})} for r in res]
    left = 0 if passed else QUIZ_MAX_FAILS - (_quiz_fails(u['id'], l['id'])[0] % QUIZ_MAX_FAILS) % QUIZ_MAX_FAILS
    return send(200, {'score': score, 'total': total, 'passed': passed, 'pass_pct': PASS_PCT, 'reveal': reveal, 'results': out, 'retry_at': retry, 'pause_minutes': QUIZ_PAUSE_MS // 60000, 'tries_before_pause': left})


@app.get('/api/questions')
def r_questions_get():
    u = user_of()
    if not u:
        return need_login()
    is_a = u['role'] == 'admin'
    cf = None   # ადმინი: ?course=<id> ფილტრავს კურსის გაკვეთილებზე დასმულ კითხვებს; გაკვეთილის გარეშე (ზოგადი/შემაჯამებელი) კითხვები ყველა კურსში ჩანს
    if is_a and request.args.get('course'):
        cf = course_arg()
        if not cf:
            return send(404, {'error': 'კურსი ვერ მოიძებნა.'})
    sql = ('SELECT q.id,q.text,q.answer,q.created,q.kind,q.status,q.lesson_id,l.title lesson_title,u.name,u.plan,u.plan_expires,u.role '
           'FROM questions q JOIN users u ON u.id=q.user_id LEFT JOIN lessons l ON l.id=q.lesson_id '
           + ('WHERE (l.course=? OR q.lesson_id IS NULL) ' if cf else '' if is_a else 'WHERE q.user_id=? ')
           + 'ORDER BY ' + ("(q.answer='') DESC," if is_a else '') + ' q.id DESC LIMIT 200')
    rows = []
    for r in (db.all_(sql, cf) if cf else db.all_(sql) if is_a else db.all_(sql, u['id'])):
        exp = r['plan'] != 'free' and r['plan_expires'] and r['plan_expires'] < now_ms()
        rows.append({'id': r['id'], 'text': r['text'], 'answer': r['answer'], 'created': r['created'], 'kind': r['kind'], 'status': r['status'] or '',
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
    if not u['verified']:
        return send(403, {'error': 'ჯერ დაადასტურე ელფოსტა (შეამოწმე შემომავალი წერილები).'})
    d = body()
    text, lesson_id, kind = d.get('text'), d.get('lesson_id'), d.get('kind')
    k = kind if kind in ('task', 'capstone') else 'question'
    t = (str(text) if text else '').strip()[:800 if k == 'question' else 4000]
    if not t:
        return send(400, {'error': 'ტექსტი ცარიელია.'})
    if k == 'question' and u['level'] < 1:
        return send(403, {'error': 'კითხვების დასმა Start გეგმიდან არის ხელმისაწვდომი.'})
    if k != 'question' and u['level'] < 2:
        return send(403, {'error': 'დავალების გაგზავნა Pro და Mentor გეგმებშია.'})
    lid = tint(lesson_id)
    lid = lid if lid is not None and lesson_for(u, lid) else None
    if k == 'capstone':
        lid = None
    if k == 'task' and not lid:
        return send(400, {'error': 'აირჩიე გაკვეთილი.'})
    if limited('q' + str(u['id']), 15):
        return send(429, {'error': 'ძალიან ბევრი შეტყობინება. სცადე მოგვიანებით.'})
    db.run('INSERT INTO questions(user_id,lesson_id,text,created,kind) VALUES(?,?,?,?,?)', u['id'], lid, t, now_ms(), k)
    what = {'question': 'კითხვა', 'task': 'დავალება', 'capstone': 'შემაჯამებელი პროექტი'}[k]
    notify_mentors(f'CDA: ახალი {what}', f"{u['name']} ({u['email']}) გამოგიგზავნა: {what}.\nგაკვეთილი: {db.one('SELECT title FROM lessons WHERE id=?', lid)['title'] if lid else '-'}\n\n{t[:300]}\n\nპასუხი: {BASE_URL}/#/admin")
    return send(200, {'ok': True})


@app.post('/api/orders')
def r_orders():
    u = user_of()
    if not u:
        return need_login()
    if not u['verified']:
        return send(403, {'error': 'ჯერ დაადასტურე ელფოსტა (შეამოწმე შემომავალი წერილები).'})
    plan = body().get('plan')
    if not isinstance(plan, str) or plan not in PAID:
        return send(400, {'error': 'არასწორი გეგმა.'})
    p = db.one("SELECT id FROM orders WHERE user_id=? AND status='pending'", u['id'])
    if p:
        db.run('UPDATE orders SET plan=?,created=? WHERE id=?', plan, now_ms(), p['id'])
    else:
        db.run('INSERT INTO orders(user_id,plan,created) VALUES(?,?,?)', u['id'], plan, now_ms())
    return send(200, {'ok': True})


COURSE_NAME = 'Cybersecurity: Beginner Path'
CERT_RE = re.compile(r'CDA-[0-9A-F]{12}')


def _cert_course():
    """?course=<id> (ნაგულისხმევი cybersecurity-beginners) → კურსის ჩანაწერი ან None (უცნობი/დახურული — 404)."""
    cid = course_arg()
    return courses.get(cid) if cid else None


def _cert_state(u, c):
    cid = c['id']
    total = db.one('SELECT COUNT(*) c FROM lessons WHERE course=?', cid)['c']
    d = db.one('SELECT COUNT(*) c, MAX(p.done_at) t FROM progress p JOIN lessons l ON l.id=p.lesson_id WHERE p.user_id=? AND l.course=?', u['id'], cid)
    if c.get('capstone'):   # შემაჯამებელი პროექტი მოითხოვება მხოლოდ იმ კურსზე, სადაც capstone=True (Beginners); კითხვა კურსზე არ არის მიბმული
        cap = db.all_("SELECT status FROM questions WHERE user_id=? AND kind='capstone'", u['id'])
        cap_state = 'approved' if any(x['status'] == 'approved' for x in cap) else 'pending' if cap else 'none'
    else:
        cap_state = 'not_required'
    return {'course': cid, 'plan_ok': u['level'] >= 2, 'done': d['c'], 'total': total, 'capstone': cap_state,
            'eligible': u['level'] >= 2 and total > 0 and d['c'] >= total and cap_state in ('approved', 'not_required')}


@app.get('/api/certificate/status')
def r_cert_status():
    u = user_of()
    if not u:
        return need_login()
    if not u['verified']:
        return send(403, {'error': 'ჯერ დაადასტურე ელფოსტა.'})
    c = _cert_course()
    if not c or not course_open(u, c['id']):
        return send(404, {'error': 'კურსი ვერ მოიძებნა.'})
    cert = db.one('SELECT id FROM certificates WHERE user_id=? AND course_id=?', u['id'], c['id'])
    return send(200, {**_cert_state(u, c), 'issued': bool(cert)})


@app.get('/api/certificate')
def r_certificate():
    """სერტიფიკატი გაიცემა კურსის მიხედვით (?course=<id>, ნაგულისხმევი cybersecurity-beginners): Pro/Mentor + კურსის ყველა გაკვეთილი დასრულებული
    + (მხოლოდ capstone კურსზე) შემაჯამებელი პროექტი მენტორის მიერ დადასტურებული. ნომერი შემთხვევითია და ბაზაში ინახება; თარიღი და სახელი გაცემისას ფიქსირდება."""
    u = user_of()
    if not u:
        return need_login()
    if not u['verified']:
        return send(403, {'error': 'ჯერ დაადასტურე ელფოსტა.'})
    c = _cert_course()
    if not c or not course_open(u, c['id']):
        return send(404, {'error': 'კურსი ვერ მოიძებნა.'})
    if u['level'] < 2:
        return send(403, {'error': 'სერტიფიკატი Pro და Mentor გეგმებშია.'})
    cid = c['id']
    st = _cert_state(u, c)
    cert = db.one('SELECT * FROM certificates WHERE user_id=? AND course_id=?', u['id'], cid)
    if not cert:
        if st['done'] < st['total']:
            return send(403, {'error': f"დაასრულე ყველა გაკვეთილი ({st['done']}/{st['total']}).", **st})
        if st['capstone'] not in ('approved', 'not_required'):
            return send(403, {'error': 'სერტიფიკატისთვის შემაჯამებელი პროექტი მენტორმა უნდა დაადასტუროს.', **st})
        for _ in range(5):
            try:
                db.run('INSERT INTO certificates(id,user_id,name,issued,course,course_id) VALUES(?,?,?,?,?,?)',
                       'CDA-' + secrets.token_hex(6).upper(), u['id'], u['name'], now_ms(), courses.cert_name(c), cid)
                break
            except sqlite3.IntegrityError:
                if db.one('SELECT 1 FROM certificates WHERE user_id=? AND course_id=?', u['id'], cid):
                    break  # პარალელური მოთხოვნა უკვე გასცა
        cert = db.one('SELECT * FROM certificates WHERE user_id=? AND course_id=?', u['id'], cid)
        db.audit(u['id'], 'certificate_issued', cert['id'], ip_of())
    cs = course_stats(cid)
    return send(200, {'name': cert['name'], 'date': cert['issued'], 'id': cert['id'], 'course': cert['course'], 'course_id': cid,
                      'lessons': st['total'], 'stages': cs['stages'], 'minutes': cs['minutes']})


@app.get('/api/cert/<cid>')
def r_cert_public(cid):
    """საჯარო გადამოწმება: მხოლოდ სახელი, თარიღი და კურსი."""
    if limited('cv' + ip_of(), 30):
        return send(429, {'error': 'ძალიან ბევრი მოთხოვნა. სცადე მოგვიანებით.'})
    c = db.one('SELECT name,issued,course FROM certificates WHERE id=?', cid.upper()) if CERT_RE.fullmatch(cid.upper()) else None
    if not c:
        return send(404, {'valid': False, 'error': 'ასეთი ნომრის სერტიფიკატი ვერ მოიძებნა.'})
    return send(200, {'valid': True, 'name': c['name'], 'date': c['issued'], 'course': c['course']})  # name='' თუ მოსწავლემ ანგარიში წაშალა


# მხოლოდ ადმინისთვის
@app.post('/api/admin/answer')
@admin_only
def r_a_answer(u):
    d = body()
    qid = tint(d.get('id'))
    ans = str(d.get('answer', '')).strip()[:4000]
    if qid is None or not db.one('SELECT 1 FROM questions WHERE id=?', qid):
        return send(400, {'error': 'არასწორი მონაცემი.'})
    prev = db.one('SELECT answer,user_id FROM questions WHERE id=?', qid)
    db.run('UPDATE questions SET answer=?,answered_at=? WHERE id=?', ans, now_ms() if ans else None, qid)
    db.audit(u['id'], 'admin_answer', f'question {qid}', ip_of())
    if ans and ans != prev['answer']:
        notify_student(prev['user_id'], 'CDA: მენტორმა გიპასუხა', f'მენტორმა უპასუხა შენს შეტყობინებას.\nნახვა: {BASE_URL}/#/qa')
    return send(200, {'ok': True})


@app.post('/api/admin/task_status')
@admin_only
def r_a_task_status(u):
    d = body()
    qid, st = tint(d.get('id')), d.get('status')
    q = db.one("SELECT kind FROM questions WHERE id=?", qid) if qid is not None else None
    if not q or q['kind'] not in ('task', 'capstone') or st not in ('', 'approved'):
        return send(400, {'error': 'არასწორი მონაცემი.'})
    prev = db.one('SELECT status,user_id,kind FROM questions WHERE id=?', qid)
    db.run('UPDATE questions SET status=? WHERE id=?', st, qid)
    db.audit(u['id'], 'admin_task_' + ('approve' if st else 'unapprove'), f'question {qid}', ip_of())
    if st == 'approved' and prev['status'] != 'approved':
        if prev['kind'] == 'capstone':
            notify_student(prev['user_id'], 'CDA: შემაჯამებელი პროექტი დადასტურდა', f'მენტორმა დაადასტურა შენი შემაჯამებელი პროექტი. თუ ყველა გაკვეთილი დასრულებული გაქვს, სერტიფიკატი ხელმისაწვდომია: {BASE_URL}/#/certificate')
        else:
            notify_student(prev['user_id'], 'CDA: დავალება დადასტურდა', f'მენტორმა დაადასტურა შენი დავალება.\nნახვა: {BASE_URL}/#/qa')
    return send(200, {'ok': True})


@app.get('/api/admin/lessons')
@admin_only
def r_a_lessons(u):
    """მასალების ცხრილი. ?course=<id>; ნაგულისხმევი cybersecurity-beginners (როგორც ადრე იყო: ერთადერთი კურსი), რომ შიგთავსის მქონე მეორე კურსი ცხრილს არ აურიოს."""
    cid = course_arg()
    if not cid:
        return send(404, {'error': 'კურსი ვერ მოიძებნა.'})
    return send(200, {'course': cid, 'lessons': db.all_('SELECT id,week stage,pos,title,video_url,pdf_url,video_title,video_channel,video2_url,video2_title,video2_channel FROM lessons WHERE course=? ORDER BY week,pos', cid)})


@app.post('/api/admin/lesson')
@admin_only
def r_a_lesson(u):
    d = body()
    lid, video, pdf = tint(d.get('id')), d.get('video_url', ''), d.get('pdf_url', '')
    cur = db.one('SELECT video_url,video2_url FROM lessons WHERE id=?', lid) if lid is not None else None
    if not cur or not valid_url(video) or not valid_url(pdf) or not valid_url(d.get('video2_url', '')):
        return send(400, {'error': 'ბმული უნდა იწყებოდეს https://-ით.'})
    txt = {}
    for k in ('video_title', 'video_channel', 'video2_title', 'video2_channel'):
        if k in d:
            if not isinstance(d[k], str) or len(d[k]) > 200 or CTRL_RE.search(d[k]):
                return send(400, {'error': 'სათაური/არხი არასწორია (მაქს. 200 სიმბოლო).'})
            txt[k] = d[k].strip()
    video = video.strip()
    sets, args = ['video_url=?', 'pdf_url=?'], [video, pdf.strip()]
    if video != cur['video_url'] and 'video_title' not in txt:   # ბმული შეიცვალა: ძველი სათაური/არხი სხვა ვიდეოს არ უნდა მიეწეროს
        txt['video_title'] = ''
    if video != cur['video_url'] and 'video_channel' not in txt:
        txt['video_channel'] = ''
    if 'video2_url' in d:
        v2 = d['video2_url'].strip()
        sets.append('video2_url=?'); args.append(v2)
        if v2 != cur['video2_url']:   # სათადარიგო ბმული შეიცვალა: ძველი სათაური/არხი სხვა ვიდეოს არ უნდა მიეწეროს
            txt.setdefault('video2_title', ''); txt.setdefault('video2_channel', '')
    for k, v in txt.items():
        sets.append(k + '=?'); args.append(v)
    db.run(f"UPDATE lessons SET {','.join(sets)} WHERE id=?", *args, lid)
    db.audit(u['id'], 'admin_lesson', f'lesson {lid}', ip_of())
    return send(200, {'ok': True})


def _user_query(cid):
    q = (request.args.get('q') or '').strip().lower()[:80]
    plan = request.args.get('plan') or ''
    sql = ('SELECT u.id,u.name,u.email,u.role,u.plan,u.plan_expires,u.created,u.last_login,'
           '(SELECT COUNT(*) FROM progress p JOIN lessons l ON l.id=p.lesson_id WHERE p.user_id=u.id AND l.course=?) done FROM users u WHERE 1=1')
    args = [cid]
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
    """მომხმარებლები; done/lessons ითვლება ?course=<id>-ის მიხედვით (ნაგულისხმევი cybersecurity-beginners, როგორც ადრე: ერთადერთი კურსი)."""
    cid = course_arg()
    if not cid:
        return send(404, {'error': 'კურსი ვერ მოიძებნა.'})
    sql, args = _user_query(cid)
    page = max(0, tint(request.args.get('page', 0)) or 0)
    total = db.one('SELECT COUNT(*) c FROM (' + sql + ')', *args)['c']
    rows = db.all_(sql + ' ORDER BY u.id DESC LIMIT 50 OFFSET ?', *args, page * 50)
    return send(200, {'users': rows, 'total': total, 'page': page, 'per': 50,
                      'course': cid, 'lessons': db.one('SELECT COUNT(*) c FROM lessons WHERE course=?', cid)['c']})


def _csv_cell(v):
    v = '' if v is None else str(v)
    return "'" + v if v[:1] in ('=', '+', '-', '@', '\t', '\r') else v  # Excel-ის ფორმულების ინექციისგან დაცვა


@app.get('/api/admin/users.csv')
@admin_only
def r_a_users_csv(u):
    cid = course_arg()
    if not cid:
        return send(404, {'error': 'კურსი ვერ მოიძებნა.'})
    sql, args = _user_query(cid)
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
    tu = db.one('SELECT email_verified,role FROM users WHERE id=?', uid)
    if not tu:
        return send(400, {'error': 'მომხმარებელი ვერ მოიძებნა.'})
    if REQUIRE_VERIFY and not tu['email_verified'] and tu['role'] != 'admin' and plan != 'free':
        return send(400, {'error': 'მომხმარებლის ელფოსტა დაუდასტურებელია: გეგმას ვერ მიანიჭებ.'})
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
    db.audit(u['id'], 'admin_user_delete', f"user {uid}", ip_of())
    return send(200, {'ok': True})


@app.get('/api/admin/orders')
@admin_only
def r_a_orders(u):
    allv = request.args.get('all') == '1'
    sql = ("SELECT o.id,o.plan,o.status,o.amount,o.created,o.decided_at,COALESCE(u.name,'') name,COALESCE(u.email,'') email FROM orders o LEFT JOIN users u ON u.id=o.user_id "
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
    if action == 'approve':
        tu = db.one('SELECT email_verified FROM users WHERE id=?', o['user_id'])
        if not tu or (REQUIRE_VERIFY and not tu['email_verified']):
            return send(400, {'error': 'მომხმარებლის ელფოსტა დაუდასტურებელია ან ანგარიში აღარ არსებობს.'})
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
    """სტატისტიკა. ?course=<id>: გაკვეთილების/პროგრესის/ქვიზის/ეტაპების რიცხვები ამ კურსზეა (ნაგულისხმევი cybersecurity-beginners, როგორც ადრე);
    მომხმარებლები, გეგმები, შემოსავალი და შეკვეთები გლობალურია."""
    cid = course_arg()
    if not cid:
        return send(404, {'error': 'კურსი ვერ მოიძებნა.'})
    users, now, by, mrr = db.all_("SELECT plan,plan_expires,created,last_login FROM users WHERE role<>'admin'"), now_ms(), {}, 0
    prices = {p['id']: p['price'] for p in PLANS}
    for x in users:
        active = x['plan'] != 'free' and (not x['plan_expires'] or x['plan_expires'] > now)
        p = x['plan'] if active else 'free'
        by[p] = by.get(p, 0) + 1
        if active:
            mrr += prices.get(p, 0)
    lessons = db.one('SELECT COUNT(*) c FROM lessons WHERE course=?', cid)['c']
    prog = db.one("SELECT COUNT(*) c FROM progress p JOIN lessons l ON l.id=p.lesson_id WHERE l.course=? AND p.user_id IN (SELECT id FROM users WHERE role<>'admin')", cid)['c']
    stages = db.all_("SELECT s.id stage,s.title,(SELECT COUNT(*) FROM lessons l WHERE l.course=s.course AND l.week=s.id) lessons,"
                     "(SELECT COUNT(*) FROM progress p JOIN lessons l ON l.id=p.lesson_id WHERE l.course=s.course AND l.week=s.id) done,"
                     "(SELECT COUNT(DISTINCT p.user_id) FROM progress p JOIN lessons l ON l.id=p.lesson_id WHERE l.course=s.course AND l.week=s.id) learners "
                     "FROM stages s WHERE s.course=? ORDER BY s.id", cid)
    week = 7 * DAY
    signups = [sum(1 for x in users if now - (i + 1) * week <= (x['created'] or 0) < now - i * week) for i in range(7, -1, -1)]
    qz = db.one('SELECT AVG(r.score*100.0/r.total) a FROM quiz_results r JOIN lessons l ON l.id=r.lesson_id WHERE r.total>0 AND l.course=?', cid)['a']
    return send(200, {'users': len(users), 'by': by, 'mrr': mrr,
                      'orders': db.one("SELECT COUNT(*) c FROM orders WHERE status='pending'")['c'],
                      'open': db.one("SELECT COUNT(*) c FROM questions q LEFT JOIN lessons l ON l.id=q.lesson_id WHERE q.answer='' AND (l.course=? OR q.lesson_id IS NULL)", cid)['c'],
                      'new7': sum(1 for x in users if (x['created'] or 0) > now - week),
                      'new30': sum(1 for x in users if (x['created'] or 0) > now - 30 * DAY),
                      'active7': sum(1 for x in users if (x['last_login'] or 0) > now - week),
                      'completion': round(prog * 100 / (lessons * len(users))) if lessons and users else 0,
                      'quiz_avg': round(qz) if qz is not None else None, 'lessons': lessons, 'course': cid,
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
        hd['Content-Security-Policy'] = (sandbox_csp(os.path.basename(f)) if f.startswith(SANDBOX + os.sep) else CSP) + ('; upgrade-insecure-requests' if secure() else '')
    if request.headers.get('If-None-Match') == tag:
        return Response(status=304, headers=hd)
    with open(f, 'rb') as fh:
        buf = fh.read()
    if re.search(r'\bgzip\b', request.headers.get('Accept-Encoding') or '') and ext in ('.html', '.css', '.js', '.svg', '.wasm', '.json', '.py'):
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
