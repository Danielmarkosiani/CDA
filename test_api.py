# სწრაფი API ტესტი: python3 test_api.py  (იყენებს დროებით ბაზას და სხვა პორტს)
import hashlib, hmac, http.client, json, os, re, shutil, sqlite3, subprocess, sys, tempfile, time

os.environ['CDA_NO_DOTENV'] = '1'   # ტესტი მთავარი .env-ს არ კითხულობს (რეალური SMTP პარამეტრები ტესტში არ უნდა მოხვდეს)
HERE = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(tempfile.gettempdir(), f'cda-test-{int(time.time() * 1000)}.db')
PORT = 3917
BACKUP_DIR = tempfile.mkdtemp(prefix='cda-bk-')
os.environ['DB_FILE'] = DB_FILE          # ყველა ქვეპროცესი (მათ შორის 'import db') დროებით ბაზას იღებს და არა პროექტის cda.db-ს
os.environ['BACKUP_DIR'] = BACKUP_DIR
PROJECT_DB = os.path.join(HERE, 'cda.db')   # დაცვა: ტესტის დროს პროექტის cda.db არ უნდა შეიცვალოს
_pdb0 = (os.stat(PROJECT_DB).st_mtime_ns, os.stat(PROJECT_DB).st_size) if os.path.exists(PROJECT_DB) else None
PW = 'Tr0ub4dor&3x-Orbit'
PW2 = 'Maple-Orbit-77x'   # მეორე პაროლი (ტესტებში პაროლის შეცვლა)
ENV = {**os.environ, 'PORT': str(PORT), 'DB_FILE': DB_FILE, 'BACKUP_DIR': BACKUP_DIR}
ENV.pop('ADMIN_EMAIL', None)
for _k in [k for k in ENV if k.startswith('SMTP_')]:
    del ENV[_k]   # ტესტის სერვერი SMTP-ს არ იყენებს: წერილები ლოგში იბეჭდება
ENV['LOGIN_IP_LIMIT'] = '1000'  # ტესტი ბევრჯერ შედის ერთი IP-დან (ლიმიტი IP+ელფოსტაზე უცვლელია)
ENV['REGISTER_LIMIT'] = '100'  # ტესტი ბევრ ანგარიშს ქმნის ერთი IP-დან
ENV['CODE_RESEND_SECONDS'] = '2'          # კოდის ხელახლა გაგზავნის ინტერვალი ტესტში 2 წამია (რეალური ნაგულისხმევი: 60)
ENV['CODE_IP_SENDS_PER_HOUR'] = '1000'    # ტესტი ბევრ კოდს ითხოვს ერთი IP-დან (ლიმიტი IP+ელფოსტაზე უცვლელია: 5 საათში)
ENV['CODE_VERIFY_IP_LIMIT'] = '1000'
# ადმინი იქმნება მხოლოდ make_admin.py-ით (ბაზაზე, სერვერის გაშვებამდე)
subprocess.run([sys.executable, 'make_admin.py', 'boss@test.ge', PW, 'Boss'], cwd=HERE, env=ENV, check=True, stdout=subprocess.DEVNULL)
LOG = os.path.join(tempfile.gettempdir(), f'cda-test-{int(time.time() * 1000)}.log')  # სერვერის კონსოლი: SMTP-ის გარეშე წერილები აქ იბეჭდება
srv = subprocess.Popen([sys.executable, 'server.py'], cwd=HERE, env=ENV, stdout=open(LOG, 'w', encoding='utf-8'), stderr=subprocess.STDOUT)
jar, failed = {}, False


def call(who, path, data=None, raw=False, extra=None):
    c = http.client.HTTPConnection('localhost', PORT, timeout=15)
    hd = {'Content-Type': 'application/json', 'X-Requested-With': 'cda'}
    if who in jar:
        hd['Cookie'] = jar[who]
    hd.update(extra or {})
    c.request('GET' if data is None else 'POST', path, None if data is None else json.dumps(data), hd)
    r = c.getresponse(); b = r.read()
    ck = r.getheader('Set-Cookie')
    if ck and re.search(r'sid=[a-f0-9]+', ck):
        jar[who] = ck.split(';')[0]
    if raw:
        return r, b
    try:
        j = json.loads(b)
    except ValueError:
        j = {}
    return {'s': r.status, **j}


def ok(name, fn):
    global failed
    try:
        fn(); print('✓', name)
    except Exception as e:  # noqa: BLE001
        failed = True; print('✗', name, '\n ', repr(e))
        if os.environ.get('TEST_TRACE'):   # TEST_TRACE=1: მიუთითებს, რომელ ხაზზე დაეცა
            import traceback; traceback.print_exc()


def eq(a, b):
    assert a == b, f'{a!r} != {b!r}'


for _ in range(80):
    try:
        call('x', '/api/config'); break
    except OSError:
        time.sleep(0.1)


SUBJ = {'verify': 'CDA: ელფოსტის დადასტურება', 'reset': 'CDA: პაროლის აღდგენა'}


def mail_code(kind, email, n=1, timeout=8):
    """კონსოლში დაბეჭდილი წერილებიდან იღებს n-ურ 6-ნიშნა კოდს (kind = verify | reset: განისაზღვრება თემით)."""
    end = time.time() + timeout
    while time.time() < end:
        txt = open(LOG, encoding='utf-8').read()
        found = re.findall(r'\[MAIL -> ' + re.escape(email) + r'\] ' + re.escape(SUBJ[kind]) + r'\n[^\[]*?კოდი: (\d{6})', txt)
        if len(found) >= n:
            return found[n - 1]
        time.sleep(0.1)
    return None


def mail_subjects(email):
    return re.findall(r'\[MAIL -> ' + re.escape(email) + r'\] (.*)\n', open(LOG, encoding='utf-8').read())


def code_mails(email):
    """მხოლოდ კოდიანი წერილები (მენტორის შეტყობინებები ადმინს სხვა თემით მიდის)"""
    return [x for x in mail_subjects(email) if x in SUBJ.values()]


def wrong_of(code):
    return '000000' if code != '000000' else '111111'


def mail_count(email):
    return len(re.findall(r'\[MAIL -> ' + re.escape(email) + r'\]', open(LOG, encoding='utf-8').read()))


def wait_mail(email, n, timeout=6):
    end = time.time() + timeout
    while time.time() < end and mail_count(email) < n:
        time.sleep(0.1)
    return mail_count(email)


def reg(who, email, verify=True):
    """რეგისტრაცია ნეიტრალურია და პაროლს არ იღებს: ელფოსტა → კოდი → კოდთან ერთად პაროლის არჩევა (PW); წარმატებისას სესიას იღებს `who`."""
    r = call(who, '/api/register', {'name': 'ტესტი ' + who, 'email': email, 'terms': True})
    if r['s'] == 200 and verify:
        code = mail_code('verify', email)
        assert code, 'დადასტურების წერილი არ დაიბეჭდა'
        v = call(who, '/api/verify', {'email': email, 'code': code, 'password': PW})
        assert v['s'] == 200 and v['user']['verified'] is True, v
    return r


ok('რეგისტრაცია წესებზე თანხმობის გარეშე იგდება', lambda: eq(call('x', '/api/register', {'name': 'აა', 'email': 'a@b.ge'})['s'], 400))
eq(call('boss', '/api/login', {'email': 'boss@test.ge', 'password': PW})['s'], 200); reg('stu', 'stu@test.ge')
assert call('stu', '/api/me')['user']['verified'] is True   # კოდით დადასტურებისას მომხმარებელი უკვე შესულია
ok('ადმინი make_admin.py-ით', lambda: eq(call('boss', '/api/me')['user']['role'], 'admin'))


def t_no_env_admin():
    # ADMIN_EMAIL აღარ აძლევს ადმინობას: იგივე მისამართით რეგისტრაცია მხოლოდ სტუდენტს ქმნის
    p = 3918; db2 = DB_FILE + '.noenv'
    e2 = {**ENV, 'PORT': str(p), 'DB_FILE': db2, 'ADMIN_EMAIL': 'first@test.ge'}
    s2 = subprocess.Popen([sys.executable, 'server.py'], cwd=HERE, env=e2, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(80):
            try:
                http.client.HTTPConnection('localhost', p, timeout=2).request('GET', '/api/config'); break
            except OSError:
                time.sleep(0.1)
        c = http.client.HTTPConnection('localhost', p, timeout=15)
        c.request('POST', '/api/register', json.dumps({'name': 'პირველი', 'email': 'first@test.ge', 'password': PW, 'terms': True}),
                  {'Content-Type': 'application/json', 'X-Requested-With': 'cda'})
        r = c.getresponse(); r.read(); eq(r.status, 200)
        d = sqlite3.connect(db2); role = d.execute("SELECT role FROM users WHERE email='first@test.ge'").fetchone()[0]; d.close()
        eq(role, 'student')
    finally:
        s2.terminate(); s2.wait()
        for f in (db2, db2 + '-wal', db2 + '-shm'):
            try: os.remove(f)
            except OSError: pass
ok('ADMIN_EMAIL არ აძლევს ადმინობას პირველ დარეგისტრირებულს', t_no_env_admin)


COURSE = json.load(open(os.path.join(HERE, 'content.json'), encoding='utf-8'))


def bank_of(l):
    s = next(x for x in COURSE if x.get('stage', x.get('week')) == l['stage']); return s['lessons'][l['pos'] - 1]['quiz']


def take(who, l, right=True):
    """ქვიზის ერთი მცდელობა. პასუხებს content.json-ის ბანკიდან ვპოულობთ ტექსტით (ვარიანტები ამოშლილია და არეული)."""
    r = call(who, '/api/quiz/start', {'lesson_id': l['id']})
    if r['s'] != 200:
        return r, r
    bank, ans = bank_of(l), []
    for q in r['questions']:
        b = next(x for x in bank if x['q'] == q['q']); k = q['o'].index(b['o'][b['a']])
        ans.append(k if right else (k + 1) % len(q['o']))
    return call(who, '/api/quiz', {'attempt_id': r['attempt_id'], 'answers': ans}), r


def lessons_of(who):
    return call(who, '/api/lessons')['lessons']


def finish_all(who):
    d = sqlite3.connect(DB_FILE); d.execute('DELETE FROM quiz_attempts WHERE passed=0'); d.commit(); d.close()   # ტესტში ლიმიტის ბლოკს ვხსნით
    for l in lessons_of(who):
        if l['quiz_n']:
            res, _ = take(who, l); assert res['s'] == 200 and res['passed'], res
        eq(call(who, '/api/progress', {'lesson_id': l['id'], 'done': True})['s'], 200)


def t_free():
    d = call('stu', '/api/lessons'); L = d['lessons']
    l1 = next(l for l in L if l['stage'] == 1); l3 = next(l for l in L if l['stage'] == 3)
    eq(len(L), 28); eq(len(d['stages']), 8); assert l1['minutes'] > 0 and not l1['locked'] and l1['quiz_n'] >= 1 and l3['locked']
    for l in L:   # სია მხოლოდ მეტამონაცემებია: ტექსტი, ქვიზი, ვიდეო, დავალება არ ჩანს
        assert not ({'content', 'quiz', 'task', 'video_url', 'pdf_url', 'bonus', 'objectives'} & set(l)), l
    assert len(json.dumps(d)) < 20000
    det = call('stu', '/api/lesson/%d' % l1['id']); eq(det['s'], 200)
    assert len(det['content']) > 200 and det['objectives'] and det['task'] and 'quiz' in det and not isinstance(det['quiz'], list)
    assert '"a"' not in json.dumps(det), 'სწორი პასუხები არ უნდა გაიგზავნოს'
    r = call('stu', '/api/lesson/%d' % l3['id']); eq(r['s'], 403); assert r['locked'] and 'content' not in r
    eq(call('stu', '/api/lesson/99999')['s'], 404)
    eq(call('x', '/api/lesson/%d' % l1['id'])['s'], 200)       # უფასო გაკვეთილი რეგისტრაციის გარეშეც იხსნება
    eq(call('x', '/api/lesson/%d' % l3['id'])['s'], 403)
ok('/api/lessons მხოლოდ მეტამონაცემებია; /api/lesson/<id> იძლევა ტექსტს (დაბლოკილზე 403)', t_free)


def t_quiz():
    L = lessons_of('stu'); l = L[0]
    r = call('stu', '/api/quiz/start', {'lesson_id': l['id']}); eq(r['s'], 200)
    n = min(5, len(bank_of(l))); eq(len(r['questions']), n)
    assert not any(set(q) - {'q', 'o'} for q in r['questions']), 'სწორი პასუხი/განმარტება არ უნდა გაიგზავნოს'
    r2 = call('stu', '/api/quiz/start', {'lesson_id': l['id']}); eq(r2['attempt_id'], r['attempt_id']); eq(r2['questions'], r['questions'])  # განახლებაზე იგივე მცდელობა
    res, _ = take('stu', l); eq(res['s'], 200); assert res['passed'] and res['reveal'] and res['score'] == res['total'] == n
    assert all('correct' in x and x['e'] for x in res['results'])
    eq(call('stu', '/api/quiz', {'attempt_id': r['attempt_id'], 'answers': [0] * n})['s'], 400)   # დასრულებული მცდელობა ხელახლა არ ფასდება
    eq(call('boss', '/api/quiz', {'attempt_id': r['attempt_id'], 'answers': [0] * n})['s'], 400)  # სხვისი მცდელობა
    best = call('stu', '/api/lessons'); eq(best['scores'][str(l['id'])], [n, n]); assert l['id'] in best['passed']
ok('ქვიზი: შემთხვევითი კითხვები ბანკიდან, სწორი პასუხი მხოლოდ გავლის შემდეგ, მცდელობა ერთჯერადია', t_quiz)


def t_quiz_rules():
    L = lessons_of('stu'); a, b = L[1], L[2]
    eq(call('stu', '/api/progress', {'lesson_id': a['id'], 'done': True})['s'], 403)           # ქვიზის გარეშე დასრულება აკრძალულია
    n = min(5, len(bank_of(a)))
    r, st = take('stu', a, right=False); eq(r['score'], 0); assert not r['passed'] and not r['reveal'] and not any('correct' in x or 'e' in x for x in r['results'])
    r, _ = take('stu', a, right=False); assert not r['reveal']
    r, _ = take('stu', a, right=False); assert r['reveal'] and r['retry_at'] and all('correct' in x for x in r['results'])  # ლიმიტი: პასუხები იხსნება
    s = call('stu', '/api/quiz/start', {'lesson_id': a['id']}); eq(s['s'], 429); assert abs(s['retry_at'] - time.time() * 1000 - 20 * 60000) < 120000, 'პაუზა დაახლოებით 20 წუთია'
    eq(call('stu', '/api/progress', {'lesson_id': a['id'], 'done': True})['s'], 403)
    # სხვა გაკვეთილზე ლიმიტი არ ვრცელდება; ნაწილობრივი ქულაც ზღვარს ქვემოთაა
    ans = lambda: None
    res, _ = take('stu', b); assert res['passed']; eq(call('stu', '/api/progress', {'lesson_id': b['id'], 'done': True})['s'], 200)
    # არასწორი ფორმატი
    st = call('stu', '/api/quiz/start', {'lesson_id': L[0]['id']}); k = len(st['questions'])
    eq(call('stu', '/api/quiz', {'attempt_id': st['attempt_id'], 'answers': [0] * (k - 1)})['s'], 400)
    eq(call('stu', '/api/quiz', {'attempt_id': st['attempt_id'], 'answers': [99] * k})['s'], 400)
    eq(call('stu', '/api/quiz', {'attempt_id': 'x', 'answers': []})['s'], 400)
ok('ქვიზის წესები: 70%, ლიმიტი და პასუხების გახსნა, დასრულება მხოლოდ გავლის შემდეგ', t_quiz_rules)


def t_noask():
    eq(call('stu', '/api/questions', {'text': 'გამარჯობა'})['s'], 403)
    eq(call('stu', '/api/questions', {'text': 'ა', 'kind': 'task', 'lesson_id': 1})['s'], 403)
ok('უფასო ვერ სვამს კითხვას და ვერ აგზავნის დავალებას', t_noask)


def t_locked():
    l = next(l for l in call('stu', '/api/lessons')['lessons'] if l['stage'] == 3)
    eq(call('stu', '/api/progress', {'lesson_id': l['id'], 'done': True})['s'], 403)
    eq(call('stu', '/api/quiz/start', {'lesson_id': l['id']})['s'], 403)
ok('დაბლოკილ გაკვეთილზე პროგრესი/ქვიზი აკრძალულია', t_locked)


def t_order():
    eq(call('stu', '/api/orders', {'plan': 'start'})['s'], 200); eq(call('stu', '/api/orders', {'plan': 'hack'})['s'], 400)
    eq(call('stu', '/api/admin/orders')['s'], 403)
    o = call('boss', '/api/admin/orders')['orders']; eq(len(o), 1)
    eq(call('boss', '/api/admin/order', {'id': o[0]['id'], 'action': 'approve'})['s'], 200)
    me = call('stu', '/api/me'); eq(me['user']['plan'], 'start'); assert me['user']['plan_expires'] > time.time() * 1000
    assert not any(l['locked'] for l in call('stu', '/api/lessons')['lessons'])
    eq(call('stu', '/api/questions', {'text': 'კითხვა'})['s'], 200)
ok('შეკვეთა → ადმინი ადასტურებს → წვდომა იხსნება', t_order)


def t_quiz_pause():
    # 3 წარუმატებლობის შემდეგ პაუზა ~20 წუთია; პაუზის შემდეგ ახალი მცდელობა გაიხსნება; ყოველი მესამე წარუმატებლობა ისევ ხსნის განმარტებებს
    a = lessons_of('stu')[1]
    eq(call('stu', '/api/quiz/start', {'lesson_id': a['id']})['s'], 429)
    d = sqlite3.connect(DB_FILE); d.execute('UPDATE quiz_attempts SET finished_at=finished_at-?', (21 * 60000,)); d.commit(); d.close()   # პაუზა გავიდა
    r, _ = take('stu', a, right=False); eq(r['s'], 200); assert not r['reveal'] and r['retry_at'] is None                              # მე-4 წარუმატებლობა: პასუხები არ იხსნება
    assert r['tries_before_pause'] == 2
    r, _ = take('stu', a, right=False); assert not r['reveal']
    r, _ = take('stu', a, right=False); assert r['reveal'] and r['retry_at'] and r['pause_minutes'] == 20 and all('correct' in x and x['e'] for x in r['results'])   # მე-6: ისევ განმარტებები + პაუზა
    eq(call('stu', '/api/quiz/start', {'lesson_id': a['id']})['s'], 429)
    d = sqlite3.connect(DB_FILE); d.execute('UPDATE quiz_attempts SET finished_at=finished_at-?', (21 * 60000,)); d.commit(); d.close()
    res, _ = take('stu', a); assert res['passed']                                                                                      # პაუზის შემდეგ გავლა ჩვეულებრივად შეიძლება
    eq(call('stu', '/api/quiz/start', {'lesson_id': a['id']})['s'], 200)                                                              # გავლილზე პაუზა აღარ მოქმედებს
ok('ქვიზი: ყოველი მესამე წარუმატებლობის შემდეგ განმარტებები და 20 წუთის პაუზა, მერე ახალი მცდელობა', t_quiz_pause)


def t_register_neutral():
    body = {'name': 'ნეიტრალი', 'email': 'neutral@test.ge', 'terms': True, 'password': PW}   # რეგისტრაციაზე გამოგზავნილ პაროლს სერვერი ბაზაში არ ინახავს
    a = call('nn', '/api/register', body)
    eq(a['s'], 200); assert 'nn' not in jar, 'რეგისტრაცია სესიას არ იძლევა'
    c1 = mail_code('verify', 'neutral@test.ge'); assert c1 and re.fullmatch(r'\d{6}', c1), 'ახალს დადასტურების კოდი მიდის'
    assert not re.search(r'\d{6}', ' '.join(mail_subjects('neutral@test.ge'))), 'წერილის თემა კოდს არ უნდა შეიცავდეს'
    txt = open(LOG, encoding='utf-8').read(); i = txt.rindex('[MAIL -> neutral@test.ge]')
    assert 'თუ ეს შენ არ იყავი, უგულებელყავი' in txt[i:i + 900]
    d = sqlite3.connect(DB_FILE); h, v = d.execute("SELECT hash,email_verified FROM users WHERE email='neutral@test.ge'").fetchone(); d.close()
    eq((h, v), ('!', 0))                                                                       # დადასტურებამდე ანგარიშს პაროლი არ აქვს
    eq(call('nn', '/api/login', {'email': 'neutral@test.ge', 'password': PW})['s'], 401)       # გამოგზავნილი პაროლით შესვლა შეუძლებელია
    r = call('nn', '/api/register', body); eq(r['s'], 429); assert 0 < r['retry_after'] <= 2    # ხელახლა მაშინვე: ინტერვალი
    eq(call('x', '/api/register', {**body, 'email': 'არა-ელფოსტა'})['s'], 400); eq(call('x', '/api/register', {**body, 'name': 'ა', 'email': 'n2@test.ge'})['s'], 400)
    time.sleep(2.2)
    eq(call('nn', '/api/register', body)['s'], 200)                                            # დაუდასტურებელი ელფოსტით ხელახალი რეგისტრაცია ახალ კოდს აგზავნის
    c2 = mail_code('verify', 'neutral@test.ge', n=2); assert c2 and c2 != c1
    eq(call('nn', '/api/verify', {'email': 'neutral@test.ge', 'code': c1, 'password': PW})['s'], 400)   # ძველი კოდი აღარ მუშაობს
    v = call('nn', '/api/verify', {'email': 'neutral@test.ge', 'code': c2, 'password': PW}); eq(v['s'], 200); assert v['user']['verified'] is True
    assert call('nn', '/api/me')['user']['email'] == 'neutral@test.ge', 'დადასტურებისას მომხმარებელი შედის'
    eq(call('nn2', '/api/login', {'email': 'neutral@test.ge', 'password': PW})['s'], 200)      # არჩეული პაროლი მუშაობს
    # არსებული (დადასტურებული) ელფოსტა: პასუხი იგივეა, რაც ახალზე, არსებულს კი „ანგარიში უკვე არსებობს“ მიდის კოდის გარეშე
    time.sleep(2.2)
    ex = call('x', '/api/register', body); nw = call('x', '/api/register', {**body, 'email': 'neutral-new@test.ge'})
    eq(ex, nw); eq(ex['s'], 200)
    eq(wait_mail('neutral@test.ge', 3), 3)
    i = open(LOG, encoding='utf-8').read().rindex('[MAIL -> neutral@test.ge]'); last = open(LOG, encoding='utf-8').read()[i:].split('[/MAIL]')[0]
    assert 'ანგარიში უკვე არსებობს' in last and '/#/forgot' in last and not re.search(r'\d{6}', last), last
    eq(call('nn2', '/api/login', {'email': 'neutral@test.ge', 'password': PW})['s'], 200)      # არსებული ანგარიში არ შეხებია
ok('რეგისტრაცია კოდით: პაროლი არ ინახება, ახალ და არსებულ ელფოსტაზე პასუხი ერთნაირია, თემა კოდს არ შეიცავს, ძველი კოდი ახალით უქმდება', t_register_neutral)


def t_delete_keeps_financial():
    reg('fin', 'fin@test.ge')
    eq(call('fin', '/api/orders', {'plan': 'start'})['s'], 200)
    o = next(x for x in call('boss', '/api/admin/orders')['orders'] if x['email'] == 'fin@test.ge')
    eq(call('boss', '/api/admin/order', {'id': o['id'], 'action': 'approve'})['s'], 200)
    eq(call('fin', '/api/orders', {'plan': 'pro'})['s'], 200)                                        # მეორე, განუხილველი განაცხადი
    uid = call('fin', '/api/me')['user']['id']
    d = sqlite3.connect(DB_FILE)
    d.execute("INSERT INTO certificates(id,user_id,name,issued,course) VALUES('CDA-AAAAAAAAAAAA',?,'ფინ ტესტი',1700000000000,'Cybersecurity: Beginner Path')", (uid,)); d.commit()
    before = d.execute('SELECT plan,status,amount,created FROM orders WHERE id=?', (o['id'],)).fetchone()
    eq(call('fin', '/api/account/delete', {'password': PW})['s'], 200)
    eq(tuple(d.execute('SELECT plan,status,amount,created FROM orders WHERE id=?', (o['id'],)).fetchone()), tuple(before))       # თანხა, გეგმა, თარიღი უცვლელია
    eq(d.execute('SELECT user_id FROM orders WHERE id=?', (o['id'],)).fetchone()[0], 0)
    eq(d.execute('SELECT COUNT(*) FROM orders WHERE user_id=? OR user_id IN (SELECT id FROM users WHERE email=?)', (uid, 'fin@test.ge')).fetchone()[0], 0)
    eq(d.execute("SELECT COUNT(*) FROM orders WHERE status='pending' AND plan='pro' AND id>?", (o['id'],)).fetchone()[0], 0)      # განუხილველი წაიშალა
    c = d.execute("SELECT user_id,name,issued FROM certificates WHERE id='CDA-AAAAAAAAAAAA'").fetchone(); d.close()
    assert c[0] < 0 and c[1] == '' and c[2] == 1700000000000
    hist = next(x for x in call('boss', '/api/admin/orders?all=1')['orders'] if x['id'] == o['id'])
    eq((hist['name'], hist['email'], hist['amount'], hist['status']), ('', '', before[2], 'approved'))
    pub = call('x', '/api/cert/CDA-AAAAAAAAAAAA'); eq(pub['s'], 200); eq((pub['valid'], pub['name'], pub['date']), (True, '', 1700000000000))
ok('ანგარიშის წაშლა: შეკვეთები (თანხა, გეგმა, თარიღი) და სერტიფიკატი ანონიმურად რჩება; #/verify სახელის გარეშე ადასტურებს', t_delete_keeps_financial)


def t_grandfather():
    # ძველი პროგრესი უცვლელია: ქვიზის შედეგის გარეშე არსებული ჩანაწერი რჩება და ხელახლა დადასტურება ნებადართულია
    L = lessons_of('stu'); x = L[3]   # ეტაპი 2: stu-ს Start გეგმა აქვს
    eq(call('stu', '/api/progress', {'lesson_id': x['id'], 'done': True})['s'], 403)
    d = sqlite3.connect(DB_FILE); uid = call('stu', '/api/me')['user']['id']
    d.execute('INSERT OR IGNORE INTO progress(user_id,lesson_id) VALUES(?,?)', (uid, x['id'])); d.commit(); d.close()
    assert x['id'] in call('stu', '/api/lessons')['done']
    eq(call('stu', '/api/progress', {'lesson_id': x['id'], 'done': True})['s'], 200)
    eq(call('stu', '/api/progress', {'lesson_id': x['id'], 'done': False})['s'], 200)       # მოხსნის შემდეგ ახალი წესი მოქმედებს
    eq(call('stu', '/api/progress', {'lesson_id': x['id'], 'done': True})['s'], 403)
ok('ძველი პროგრესი უცვლელია: ქვიზის შედეგის გარეშე არსებული დასრულება რჩება', t_grandfather)


def t_pro():
    l = call('stu', '/api/lessons')['lessons'][0]; det = call('stu', '/api/lesson/%d' % l['id']); eq(det['bonus'], ''); assert det['bonus_locked']
    eq(call('stu', '/api/questions', {'text': 'ჩემი პასუხი', 'kind': 'task', 'lesson_id': l['id']})['s'], 403)
    u = next(x for x in call('boss', '/api/admin/users')['users'] if x['email'] == 'stu@test.ge')
    eq(call('boss', '/api/admin/plan', {'id': u['id'], 'plan': 'pro', 'days': 30})['s'], 200)
    assert len(call('stu', '/api/lesson/%d' % l['id'])['bonus']) > 10
    eq(call('stu', '/api/questions', {'text': 'ჩემი პასუხი', 'kind': 'task', 'lesson_id': l['id']})['s'], 200)
ok('Start-ზე ბონუსი და დავალების გაგზავნა დაკეტილია, Pro-ზე იხსნება', t_pro)


def t_expired():
    d = sqlite3.connect(DB_FILE); d.execute("UPDATE users SET plan_expires=1 WHERE email='stu@test.ge'"); d.commit(); d.close()
    eq(call('stu', '/api/me')['user']['plan'], 'free')
    u = next(x for x in call('boss', '/api/admin/users')['users'] if x['email'] == 'stu@test.ge')
    call('boss', '/api/admin/plan', {'id': u['id'], 'plan': 'pro', 'days': 30})
ok('ვადაგასული გეგმა = უფასო', t_expired)


def hashlib_old():
    import hashlib
    d = sqlite3.connect(DB_FILE); u = d.execute("SELECT id,email FROM users WHERE email='stu@test.ge'").fetchone(); d.close()
    return hashlib.sha256(f'{u[0]}:{u[1]}'.encode()).hexdigest()[:10].upper()


def t_cert():
    eq(call('stu', '/api/certificate')['s'], 403)
    finish_all('stu')
    tk = next(x for x in call('boss', '/api/questions')['questions'] if x['kind'] == 'task')
    eq(call('stu', '/api/admin/task_status', {'id': tk['id'], 'status': 'approved'})['s'], 403)      # მოსწავლე თვითონ ვერ ადასტურებს
    eq(call('boss', '/api/admin/task_status', {'id': tk['id'], 'status': 'approved'})['s'], 200)
    r = call('stu', '/api/certificate'); eq(r['s'], 403); eq(r['capstone'], 'none')                  # ჩვეულებრივი დავალების დადასტურება პროექტს არ ცვლის
    q0 = next(x for x in call('boss', '/api/questions')['questions'] if x['kind'] == 'question')
    eq(call('boss', '/api/admin/task_status', {'id': q0['id'], 'status': 'approved'})['s'], 400)     # კითხვას სტატუსი არ აქვს
    eq(call('stu', '/api/questions', {'text': 'ჩემი შემაჯამებელი პროექტი: ...', 'kind': 'capstone'})['s'], 200)
    r = call('stu', '/api/certificate'); eq(r['s'], 403); eq(r['capstone'], 'pending')
    st = call('stu', '/api/certificate/status'); assert st['done'] == st['total'] and not st['eligible'] and not st['issued']
    cap = next(x for x in call('boss', '/api/questions')['questions'] if x['kind'] == 'capstone')
    eq(call('boss', '/api/admin/task_status', {'id': cap['id'], 'status': 'approved'})['s'], 200)
    c = call('stu', '/api/certificate'); eq(c['s'], 200); assert re.fullmatch(r'CDA-[0-9A-F]{12}', c['id']), c['id']
    c2 = call('stu', '/api/certificate'); eq(c2['id'], c['id']); eq(c2['date'], c['date']); eq(c2['name'], c['name'])   # ნომერი და თარიღი ფიქსირებულია
    d = sqlite3.connect(DB_FILE); row = d.execute('SELECT id,issued FROM certificates WHERE user_id>0').fetchall(); d.close()
    eq(len(row), 1); eq(row[0][0], c['id'])
    assert c['id'] != 'CDA-' + hashlib_old(), 'ნომერი აღარ გამოითვლება ელფოსტიდან'
    pub = call('x', '/api/cert/' + c['id']); eq(pub['s'], 200); eq(set(pub), {'s', 'valid', 'name', 'date', 'course'}); eq(pub['name'], c['name'])
    eq(call('x', '/api/cert/' + c['id'].lower())['s'], 200)
    eq(call('x', '/api/cert/CDA-000000000000')['s'], 404); eq(call('x', '/api/cert/abc')['s'], 404); eq(call('x', "/api/cert/CDA-'OR'1")['s'], 404)
    assert call('stu', '/api/certificate/status')['issued']
ok('სერტიფიკატი: ყველა გაკვეთილი + მენტორისგან დადასტურებული პროექტი, შემთხვევითი ნომერი ბაზაში, საჯარო გადამოწმება', t_cert)


def t_notify():
    b0, s0 = mail_count('boss@test.ge'), mail_count('stu@test.ge')
    eq(call('stu', '/api/questions', {'text': 'ნოტიფიკაციის ტესტი'})['s'], 200)
    eq(wait_mail('boss@test.ge', b0 + 1), b0 + 1)                                   # მენტორს ახალი კითხვის შესახებ
    txt = open(LOG, encoding='utf-8').read(); i = txt.rindex('[MAIL -> boss@test.ge]'); assert 'ნოტიფიკაციის ტესტი' in txt[i:i + 900] and '/#/admin' in txt[i:i + 900]
    q = next(x for x in call('boss', '/api/questions')['questions'] if x['text'] == 'ნოტიფიკაციის ტესტი')
    eq(call('boss', '/api/admin/answer', {'id': q['id'], 'answer': 'პასუხი 1'})['s'], 200)
    eq(wait_mail('stu@test.ge', s0 + 1), s0 + 1)                                    # მოსწავლეს პასუხის შესახებ
    txt = open(LOG, encoding='utf-8').read(); i = txt.rindex('[MAIL -> stu@test.ge]'); assert 'პასუხი 1' not in txt[i:i + 600], 'პასუხის ტექსტი წერილში არ იგზავნება'
    call('boss', '/api/admin/answer', {'id': q['id'], 'answer': 'პასუხი 1'}); time.sleep(0.8)
    eq(mail_count('stu@test.ge'), s0 + 1)                                           # იგივე პასუხის ხელახლა შენახვა წერილს არ აგზავნის
    eq(call('stu', '/api/notify', {'on': False})['s'], 200); assert call('stu', '/api/me')['user']['notify'] == 0
    call('boss', '/api/admin/answer', {'id': q['id'], 'answer': 'პასუხი 2'}); time.sleep(0.8)
    eq(mail_count('stu@test.ge'), s0 + 1)                                           # გამორთული შეტყობინება
    eq(call('stu', '/api/notify', {'on': True})['s'], 200)
    L = lessons_of('stu')[0]
    eq(call('stu', '/api/questions', {'text': 'დავალების პასუხი', 'kind': 'task', 'lesson_id': L['id']})['s'], 200)
    tk = next(x for x in call('boss', '/api/questions')['questions'] if x['text'] == 'დავალების პასუხი')
    call('boss', '/api/admin/task_status', {'id': tk['id'], 'status': 'approved'})
    eq(wait_mail('stu@test.ge', s0 + 2), s0 + 2)                                    # დადასტურების შეტყობინება
    call('boss', '/api/admin/task_status', {'id': tk['id'], 'status': 'approved'}); time.sleep(0.8)
    eq(mail_count('stu@test.ge'), s0 + 2)
ok('ელფოსტით შეტყობინებები: მენტორს ახალ კითხვაზე, მოსწავლეს პასუხსა და დადასტურებაზე (ერთხელ, გამორთვის შესაძლებლობით)', t_notify)


def t_admin():
    q = call('boss', '/api/questions')['questions']; assert len(q) >= 2 and q[0]['kind']
    eq(call('boss', '/api/admin/answer', {'id': q[0]['id'], 'answer': 'პასუხი'})['s'], 200)
    assert call('boss', '/api/admin/stats')['mrr'] >= 49
    u = next(x for x in call('boss', '/api/admin/users')['users'] if x['email'] == 'stu@test.ge')
    r = call('boss', '/api/admin/resetpw', {'id': u['id']})
    assert call('stu', '/api/me')['user'] is None  # სესია გაუქმდა
    eq(call('stu', '/api/login', {'email': 'stu@test.ge', 'password': r['password']})['s'], 200)
ok('ადმინი: პასუხი, სტატისტიკა, პაროლის გადაყენება', t_admin)


def t_pw():
    eq(call('stu', '/api/password', {'old': 'არასწორი', 'next': 'Another-Pass-77'})['s'], 400)
    eq(call('stu', '/api/password', {'old': '', 'next': 'x'})['s'], 400)
ok('პაროლის შეცვლა', t_pw)


def t_video():
    eq(call('boss', '/api/admin/lesson', {'id': 1, 'video_url': 'javascript:alert(1)'})['s'], 400)
    eq(call('boss', '/api/admin/lesson', {'id': 1, 'video_url': 'https://youtu.be/dQw4w9WgXcQ'})['s'], 200)
ok('ვიდეო ბმული: მხოლოდ https', t_video)


def t_sec():
    r, _ = call('x', '/', raw=True); assert "default-src 'self'" in r.getheader('content-security-policy'); eq(r.getheader('x-frame-options'), 'DENY')
    eq(call('x', '/img/logo.png', raw=True)[0].status, 200)
    eq(call('x', '/img/ar-arsebobs.png', raw=True)[0].status, 404)
    eq(call('x', '/..%2fserver.py', raw=True)[0].status, 404)
    _, b = call('x', '/%2e%2e/%2e%2e/etc/passwd', raw=True); assert b'root:' not in b
    eq(call('x', '/server.py', raw=True)[0].status, 404)
    eq(call('x', '/db.py', raw=True)[0].status, 404)
ok('უსაფრთხოების ჰედერები და სტატიკა', t_sec)


def t_csrf():
    eq(call('x', '/api/login', {'email': 'a@b.ge', 'password': 'x'}, extra={'Origin': 'https://evil.example'})['s'], 403)
    eq(call('x', '/api/login', {'email': 'a@b.ge', 'password': 'x'}, extra={'Origin': f'http://localhost:{PORT}'})['s'], 401)
    eq(call('x', '/api/login', {'email': 'a@b.ge', 'password': 'x'}, extra={'Content-Type': 'text/plain'})['s'], 415)
    eq(call('x', '/api/login', {'email': 'a@b.ge', 'password': 'x'}, extra={'X-Requested-With': ''})['s'], 403)
ok('CSRF: სხვა საიტიდან POST იბლოკება, API მხოლოდ JSON-ს და ჰედერიან მოთხოვნას იღებს', t_csrf)


def t_weak():
    eq(call('x', '/api/register', {'name': 'აა ბბ', 'email': 'weak@test.ge', 'terms': True})['s'], 200); c = mail_code('verify', 'weak@test.ge')
    r = call('x', '/api/verify', {'email': 'weak@test.ge', 'code': c, 'password': 'password123'})
    eq(r['s'], 400); assert '15' in r['error'], r['error']   # მოკლეცაა (11) და გავრცელებულიც
    c = mail_code('verify', 'weak@test.ge')
    r = call('x', '/api/verify', {'email': 'weak@test.ge', 'code': c, 'password': 'qwertyuiopasdfg'})
    eq(r['s'], 400); assert 'გავრცელებული' in r['error'], r['error']   # გრძელია (15), მაგრამ მიმდევრობაა
ok('ძალიან მარტივი პაროლი იგდება', t_weak)


def t_hdr():
    r, _ = call('x', '/', raw=True)
    assert 'unsafe-inline' not in r.getheader('content-security-policy'); assert "object-src 'none'" in r.getheader('content-security-policy')
    eq(r.getheader('cross-origin-opener-policy'), 'same-origin')
    eq(call('x', '/css/.hidden', raw=True)[0].status, 404)
    eq(call('x', '/.git/config', raw=True)[0].status, 404)
ok('CSP ინლაინ სტილების გარეშე, დამატებითი ჰედერები, დამალული ფაილები', t_hdr)


def t_sessions_hashed():
    d = sqlite3.connect(DB_FILE); toks = [r[0] for r in d.execute('SELECT token FROM sessions')]; d.close()
    assert toks and not any(jar['stu'].endswith(t) for t in toks), 'ტოკენი ბაზაში ღიად არ უნდა ინახებოდეს'
ok('სესიის ტოკენები ბაზაში ჰეშირებულია', t_sessions_hashed)


def t_delete():
    reg('gone', 'gone@test.ge')
    eq(call('gone', '/api/account/delete', {'password': 'არასწორი'})['s'], 400)
    eq(call('gone', '/api/account/delete', {'password': PW})['s'], 200)
    assert call('gone', '/api/me')['user'] is None
    eq(call('gone', '/api/login', {'email': 'gone@test.ge', 'password': PW})['s'], 401)
    eq(call('boss', '/api/account/delete', {'password': PW})['s'], 400)
ok('ანგარიშის წაშლა (ადმინი ვერ იშლება)', t_delete)


def t_logout_all():
    call('stu', '/api/login', {'email': 'stu@test.ge', 'password': PW})
    eq(call('stu', '/api/logout_all', {})['s'], 200)
    assert call('stu', '/api/me')['user'] is None
ok('გასვლა ყველა მოწყობილობიდან', t_logout_all)


def t_rate():
    s = None
    for _ in range(12):
        s = call('x', '/api/login', {'email': 'victim@test.ge', 'password': 'bad'})['s']
    eq(s, 429)
ok('ლოგინის შეზღუდვა', t_rate)

def t_login_limit_pair():
    # ერთი IP-დან ერთ ელფოსტაზე ლიმიტი სხვა ელფოსტას არ ეხება (იგივე IP-დან)
    eq(call('x', '/api/login', {'email': 'someone-else@test.ge', 'password': 'bad'})['s'], 401)
ok('ლიმიტი IP+ელფოსტაზეა: სხვა ელფოსტაზე შესვლის მცდელობა ისევ 401-ია, არა 429', t_login_limit_pair)


def t_client_ip():
    import auth
    eq(auth.client_ip('10.0.0.1', '6.6.6.6', 0), '10.0.0.1')                     # პროქსი არ არის: სათაური იგნორირდება
    eq(auth.client_ip('10.0.0.1', '1.2.3.4', 1), '1.2.3.4')
    eq(auth.client_ip('10.0.0.1', '6.6.6.6, 1.2.3.4', 1), '1.2.3.4')            # მარცხენა ნაწილი გაყალბებულია
    eq(auth.client_ip('10.0.0.1', '6.6.6.6, 1.2.3.4, 172.16.0.2', 2), '1.2.3.4')  # ორი სანდო პროქსი
    eq(auth.client_ip('10.0.0.1', '', 1), '10.0.0.1')                            # სათაური არ არის
    eq(auth.client_ip('10.0.0.1', '1.2.3.4', 2), '10.0.0.1')                     # სათაური მოსალოდნელზე მოკლეა
ok('client_ip: გაყალბებულ X-Forwarded-For-ს არ ვენდობით, ვიღებთ სანდო პროქსების რაოდენობით', t_client_ip)


def t_proxy_mode():
    p = 3919; db2 = DB_FILE + '.proxy'
    e2 = {**ENV, 'PORT': str(p), 'DB_FILE': db2, 'TRUST_PROXY': '1', 'TRUST_PROXY_COUNT': '1', 'REQUIRE_EMAIL_VERIFY': '0'}
    s2 = subprocess.Popen([sys.executable, 'server.py'], cwd=HERE, env=e2, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def c2(path, data, xff):
        c = http.client.HTTPConnection('localhost', p, timeout=15)
        c.request('POST', path, json.dumps(data), {'Content-Type': 'application/json', 'X-Requested-With': 'cda', 'X-Forwarded-For': xff})
        r = c.getresponse(); r.read(); return r.status
    try:
        for _ in range(80):
            try:
                http.client.HTTPConnection('localhost', p, timeout=2).request('GET', '/api/config'); break
            except OSError:
                time.sleep(0.1)
        eq(c2('/api/register', {'name': 'მსხვერპლი', 'email': 'victim2@test.ge', 'password': PW, 'terms': True}, '2.2.2.2'), 200)
        eq(c2('/api/register', {'name': 'სუსტი', 'email': 'w3@test.ge', 'password': 'Summer2024!', 'terms': True}, '2.2.2.2'), 400)   # REQUIRE_EMAIL_VERIFY=0: ძველი ნაკადი, პაროლი რეგისტრაციისას
        eq(c2('/api/verify', {'email': 'victim2@test.ge', 'code': '123456', 'password': PW}, '2.2.2.2'), 400)                        # კოდით დადასტურება გამორთულია
        codes = [c2('/api/login', {'email': 'victim2@test.ge', 'password': 'bad'}, f'spoof{i}, 1.1.1.1') for i in range(12)]
        eq(codes[-1], 429)   # მარცხენა მნიშვნელობის შეცვლა ლიმიტს ვერ აშორებს
        eq(c2('/api/login', {'email': 'victim2@test.ge', 'password': PW}, '2.2.2.2'), 200)  # მსხვერპლი სხვა IP-დან ჩვეულებრივად შედის
        eq(c2('/api/login', {'email': 'victim2@test.ge', 'password': PW}, '1.1.1.1'), 429)  # თავდამსხმელის IP დაბლოკილია
    finally:
        s2.terminate(); s2.wait()
        for f in (db2, db2 + '-wal', db2 + '-shm'):
            try: os.remove(f)
            except OSError: pass
ok('ლოგინის ლიმიტი: თავდამსხმელი სხვის ანგარიშს ვერ ბლოკავს, XFF-ის გაყალბება არ მუშაობს', t_proxy_mode)


def t_pw_rules():
    import auth
    for p in ['123456789012345', 'aaaaaaaaaaaaaaa', 'qwertyuiopasdfg', 'zxcvbnmasdfghjk', 'a1b2c3d4', '12345678', 'qwertyui', 'abcd1234', 'Password1!', 'P@ssw0rd', 'Summer2024!', 'Tbilisi2026', 'Qwerty!234',
              'Sunsh1ne!!', '1q2w3e4r5t', '12341234', 'aaaaaaaa', 'Giorgi1990', 'gamarjoba1']:
        assert not auth.strong_pw(p, 'u@x.ge', 'ნინო'), p
    for p in ['Tr0ub4dor&3x-Orbit', 'correct-horse-battery', 'blue-giraffe-77', 'სამი სიტყვა აქ ზის', 'correct horse battery', 'თბილისი-მდინარე-47', 'blue.Giraffe.Tunnel', 'password-correct-horse']:
        assert auth.strong_pw(p, 'u@x.ge', 'ნინო'), p
    assert auth.MIN_PW_LEN == 15
    for p in ['xkqzpwmv', 'Tr0ub4dor&3x', 'Qx7!mN2$pL9&vK']:   # კარგი, მაგრამ 8-14 სიმბოლო: ახლა მოკლეა
        assert not auth.strong_pw(p, 'u@x.ge', 'ნინო'), p
    assert auth.strong_pw('Qx7!mN2$pL9&vK4', 'u@x.ge', 'ნინო')   # ზუსტად 15
    # რეგისტრაციაზე პაროლი არ არსებობს: სისუსტე კოდის გვერდზე მოწმდება, კოდი კი არ იხარჯება
    eq(call('x', '/api/register', {'name': 'ტესტი', 'email': 'w2@test.ge', 'terms': True})['s'], 200); c = mail_code('verify', 'w2@test.ge')
    eq(call('x', '/api/verify', {'email': 'w2@test.ge', 'code': c, 'password': 'Summer2024!'})['s'], 400)
    eq(call('x', '/api/verify', {'email': 'w2@test.ge', 'code': c, 'password': 'Tr0ub4dor&3x-Orbit'})['s'], 200)
ok('პაროლის წესი: მიმდევრობები, სიტყვა+ციფრები, გავრცელებული პაროლები იგდება; ნორმალური გადის', t_pw_rules)


def t_pw_email():
    eq(call('x', '/api/register', {'name': 'ბექა გიორგაძე', 'email': 'bekagio@test.ge', 'terms': True})['s'], 200); c = mail_code('verify', 'bekagio@test.ge')
    eq(call('x', '/api/verify', {'email': 'bekagio@test.ge', 'code': c, 'password': 'bekagio2026'})['s'], 400)
ok('პაროლი, რომელიც ელფოსტის სახელს შეიცავს, იგდება', t_pw_email)


def t_admin_plus():
    st = call('boss', '/api/admin/stats')
    eq(len(st['stages']), 8); eq(len(st['signups']), 8); assert st['new7'] >= 1 and 'completion' in st and st['users'] >= 1
    u = call('boss', '/api/admin/users?q=stu@test&plan=pro'); eq(u['total'], 1); assert u['users'][0]['done'] >= 1 and u['users'][0]['last_login']
    eq(call('boss', '/api/admin/users?q=nobody-here')['total'], 0)
    eq(len(call('boss', '/api/admin/lessons')['lessons']), 28)
    hist = call('boss', '/api/admin/orders?all=1')['orders']; assert hist and hist[0]['status'] == 'approved' and hist[0]['amount'] == 25
    ev = call('boss', '/api/admin/audit')['events']; acts = {e['action'] for e in ev}
    assert {'login', 'admin_plan', 'admin_order_approve', 'login_fail'} <= acts, acts
    r, b = call('boss', '/api/admin/users.csv', raw=True); eq(r.status, 200); assert b.startswith(b'\xef\xbb\xbfid,name') and b'stu@test.ge' in b
    eq(call('stu', '/api/admin/audit')['s'], 403); eq(call('stu', '/api/admin/stats')['s'], 403)
ok('ადმინი: სტატისტიკა, ძებნა, ისტორია, ჟურნალი, CSV', t_admin_plus)


def t_admin_guard():
    boss = next(x for x in call('boss', '/api/admin/users')['users'] if x['email'] == 'boss@test.ge')
    eq(call('boss', '/api/admin/user_delete', {'id': boss['id']})['s'], 400)
    reg('tmp', 'tmp@test.ge'); me = call('tmp', '/api/me')['user']
    eq(call('boss', '/api/admin/user_delete', {'id': me['id']})['s'], 200)
    assert call('tmp', '/api/me')['user'] is None
ok('ადმინი ვერ წაშლის ადმინს; მოსწავლის წაშლა მუშაობს', t_admin_guard)


def t_backup():
    r = call('boss', '/api/admin/backup'); eq(r['s'], 404)  # POST-ს ითხოვს
    r = call('boss', '/api/admin/backup', {}); eq(r['s'], 200)
    p = os.path.join(BACKUP_DIR, r['name']); assert os.path.isfile(p)
    d = sqlite3.connect(p); assert d.execute('SELECT COUNT(*) FROM lessons').fetchone()[0] == 28; d.close()
    eq(call('stu', '/api/admin/backup', {})['s'], 403)
ok('ბაზის სარეზერვო ასლი', t_backup)

def t_verify():
    r = reg('nv', 'nv@test.ge', verify=False); eq(r['s'], 200)
    eq(call('nv', '/api/login', {'email': 'nv@test.ge', 'password': PW})['s'], 401)                              # პაროლი დადასტურებამდე არ არსებობს (შესვლის ლიმიტი IP+ელფოსტაზე 10-ია, ამიტომ ცოტა ცდა)
    wrong = call('nv', '/api/login', {'email': 'nv@test.ge', 'password': 'Wrong-pass-1!'}); eq(wrong['error'], call('nv', '/api/login', {'email': 'nv@test.ge', 'password': PW})['error'])
    assert 'nv' not in jar
    code = mail_code('verify', 'nv@test.ge'); assert code
    d = sqlite3.connect(DB_FILE); rows = d.execute('SELECT hash,salt FROM codes').fetchall(); d.close()
    assert rows and all(code != h and code not in h for h, _ in rows), 'კოდი ბაზაში ჰეშით უნდა ინახებოდეს'
    em = 'nv@test.ge'
    eq(call('x', '/api/verify', {'email': em, 'code': wrong_of(code), 'password': PW})['s'], 400)                 # არასწორი კოდი
    eq(call('x', '/api/verify', {'email': em, 'code': 'abcdef', 'password': PW})['s'], 400)                       # არასწორი ფორმატი
    eq(call('x', '/api/verify', {'email': 'nobody-v@test.ge', 'code': code, 'password': PW})['s'], 400)           # სხვა ელფოსტა: ამ კოდით არ გამოდგება
    e1 = call('x', '/api/verify', {'email': em, 'code': wrong_of(code), 'password': PW}); e2 = call('x', '/api/verify', {'email': 'nobody-v@test.ge', 'code': wrong_of(code), 'password': PW})
    eq(e1, e2)                                                                                                    # არსებულ და არარსებულ ანგარიშზე შეცდომა იდენტურია
    eq(call('x', '/api/verify', {'email': em, 'code': code, 'password': 'Summer2024!'})['s'], 400)                # სუსტი პაროლი: კოდი არ იხარჯება
    eq(call('x', '/api/verify', {'email': em, 'code': code, 'password': 'nv@test.ge'})['s'], 400)                 # პაროლი ელფოსტას შეიცავს
    assert 'nv' not in jar
    v = call('nv', '/api/verify', {'email': em, 'code': code, 'password': PW}); eq(v['s'], 200); assert v['user']['verified'] is True
    assert call('nv', '/api/me')['user']['email'] == em
    eq(call('x', '/api/verify', {'email': em, 'code': code, 'password': PW})['s'], 400)                           # ერთჯერადია
    eq(call('nv', '/api/login', {'email': em, 'password': PW})['s'], 200)                                         # არჩეული პაროლი მუშაობს
    # დაუდასტურებელი სესიის შეზღუდვები (მაგ. დადასტურების მოთხოვნა მოგვიანებით ჩაირთო): ფასიანი წვდომა, კითხვა, დავალება, სერტიფიკატი დაკეტილია
    d = sqlite3.connect(DB_FILE); d.execute("UPDATE users SET email_verified=0, plan='pro', plan_expires=? WHERE email='nv@test.ge'", (int(time.time() * 1000) + 10 ** 10,)); d.commit(); d.close()
    me = call('nv', '/api/me')['user']; assert me['verified'] is False and me['level'] == 0                          # გეგმა ბაზაში თუნდაც Pro იყოს
    eq(call('nv', '/api/orders', {'plan': 'start'})['s'], 403); eq(call('nv', '/api/questions', {'text': 'ა'})['s'], 403)
    L1 = lessons_of('nv')[0]
    eq(call('nv', '/api/questions', {'text': 'ა', 'kind': 'task', 'lesson_id': L1['id']})['s'], 403)
    eq(call('nv', '/api/questions', {'text': 'ა', 'kind': 'capstone'})['s'], 403); eq(call('nv', '/api/certificate')['s'], 403); eq(call('nv', '/api/certificate/status')['s'], 403)
    assert any(l['locked'] for l in lessons_of('nv') if l['stage'] >= 2)                                              # ფასიანი გაკვეთილები დაკეტილია
    uid = me['id']
    eq(call('boss', '/api/admin/plan', {'id': uid, 'plan': 'pro', 'days': 30})['s'], 400)                              # ადმინიც ვერ ანიჭებს გეგმას დაუდასტურებელს
    d = sqlite3.connect(DB_FILE); d.execute("INSERT INTO orders(user_id,plan,status,created) VALUES(?, 'start', 'pending', 1)", (uid,)); oid = d.execute('SELECT MAX(id) FROM orders').fetchone()[0]; d.commit(); d.close()
    eq(call('boss', '/api/admin/order', {'id': oid, 'action': 'approve'})['s'], 400)                                   # განაცხადის დადასტურებაც დაუდასტურებელზე
    d = sqlite3.connect(DB_FILE); d.execute('DELETE FROM orders WHERE id=?', (oid,)); d.commit(); d.close()
    # ასეთი ანგარიშის დადასტურება: ყველა ძველი სესია იშლება, პაროლი ახლით იცვლება (ძველი პაროლი, რომელიც ვინმემ დააყენა, აღარ გამოდგება), ახალი სესია გაიცემა
    old_cookie = jar['nv']; time.sleep(2.2)
    eq(call('x', '/api/verify/resend', {'email': em})['s'], 200); c2 = mail_code('verify', em, n=2); assert c2
    NEWPW = PW2
    v = call('nv', '/api/verify', {'email': em, 'code': c2, 'password': NEWPW}); eq(v['s'], 200)
    jar['oldsess'] = old_cookie; assert call('oldsess', '/api/me')['user'] is None, 'დადასტურებისას ყველა ძველი სესია უნდა წაიშალოს'
    assert jar['nv'] != old_cookie and call('nv', '/api/me')['user']['verified'] is True
    eq(call('x', '/api/login', {'email': em, 'password': PW})['s'], 401); eq(call('x', '/api/login', {'email': em, 'password': NEWPW})['s'], 200)
    d = sqlite3.connect(DB_FILE); eq(d.execute("SELECT COUNT(*) FROM codes WHERE user_id=?", (uid,)).fetchone()[0], 0); d.execute("UPDATE users SET plan='free', plan_expires=NULL WHERE email='nv@test.ge'"); d.commit(); d.close()
    eq(call('nv', '/api/orders', {'plan': 'start'})['s'], 200)
ok('დადასტურება კოდით: პაროლი მხოლოდ დადასტურებისას ჩნდება, სუსტი პაროლი კოდს არ ხარჯავს, კოდი ერთჯერადია, დაუდასტურებელი შეზღუდულია, ძველი სესიები იშლება', t_verify)


def t_code_attempts_expire():
    em = 'nv3@test.ge'; reg('nv3', em, verify=False); code = mail_code('verify', em); w = wrong_of(code)
    for i in range(5):
        eq(call('x', '/api/verify', {'email': em, 'code': w, 'password': PW})['s'], 400)
    eq(call('x', '/api/verify', {'email': em, 'code': code, 'password': PW})['s'], 400)                              # 5 არასწორის შემდეგ სწორი კოდიც აღარ გამოდგება
    d = sqlite3.connect(DB_FILE); r = d.execute("SELECT attempts,expires FROM codes WHERE user_id=(SELECT id FROM users WHERE email=?)", (em,)).fetchone()
    eq(r[0], 5); eq(r[1], 0)
    eq(d.execute("SELECT COUNT(*) FROM audit WHERE action='code_locked'").fetchone()[0] >= 1, True); d.close()
    time.sleep(2.2); eq(call('x', '/api/verify/resend', {'email': em})['s'], 200)
    c2 = mail_code('verify', em, n=2); assert c2
    eq(call('x', '/api/verify', {'email': em, 'code': w if w != c2 else '222222', 'password': PW})['s'], 400)       # ახალ კოდზე მცდელობები ნულიდან იწყება
    # ვადაგასული
    d = sqlite3.connect(DB_FILE); d.execute('UPDATE codes SET expires=1'); d.commit(); d.close()
    eq(call('x', '/api/verify', {'email': em, 'code': c2, 'password': PW})['s'], 400)
    eq(call('nv3', '/api/login', {'email': em, 'password': PW})['s'], 401)
    # 10 წუთიანი ვადა: კოდი 9-10 წუთში იქმნება
    time.sleep(2.2); call('x', '/api/verify/resend', {'email': em}); c3 = mail_code('verify', em, n=3); assert c3
    d = sqlite3.connect(DB_FILE); ex = d.execute("SELECT expires FROM codes WHERE user_id=(SELECT id FROM users WHERE email=?) AND kind='verify'", (em,)).fetchone()[0]; d.close()
    assert 9 * 60_000 < ex - int(time.time() * 1000) <= 10 * 60_000, ex - int(time.time() * 1000)
    eq(call('nv3', '/api/verify', {'email': em, 'code': c3, 'password': PW})['s'], 200)                               # მერე ახალი კოდი ჩვეულებრივად მუშაობს
ok('კოდი: 5 არასწორი მცდელობის შემდეგ იბლოკება (სწორიც არ გამოდგება), ახალი კოდი მცდელობებს ანულებს, ვადაგასული არ მუშაობს, ვადა 10 წუთია', t_code_attempts_expire)


def t_code_parallel_attempts():
    # პარალელური მოთხოვნებით 5 მცდელობაზე მეტი არ გამოდის და კოდი ერთხელ იხარჯება
    import concurrent.futures as cf
    em = 'nv4@test.ge'; reg('nv4', em, verify=False); code = mail_code('verify', em)
    def one(_): return call('x', '/api/verify', {'email': em, 'code': code, 'password': PW})['s']
    with cf.ThreadPoolExecutor(8) as ex: res = list(ex.map(one, range(8)))
    eq(sorted(res), [200] + [400] * 7)
    em2 = 'nv5@test.ge'; reg('nv5', em2, verify=False); c = mail_code('verify', em2); w = wrong_of(c)
    def bad(_): return call('x', '/api/verify', {'email': em2, 'code': w, 'password': PW})['s']
    with cf.ThreadPoolExecutor(8) as ex: list(ex.map(bad, range(8)))
    d = sqlite3.connect(DB_FILE); eq(d.execute("SELECT attempts FROM codes WHERE user_id=(SELECT id FROM users WHERE email=?)", (em2,)).fetchone()[0], 5); d.close()
ok('კოდი: პარალელური მოთხოვნებით ერთხელ იხარჯება და 5 მცდელობაზე მეტი არ გამოდის', t_code_parallel_attempts)


def t_verify_resend_neutral():
    reg('nv2', 'nv2@test.ge', verify=False); c1 = mail_code('verify', 'nv2@test.ge')
    time.sleep(2.2)
    a = call('x', '/api/verify/resend', {'email': 'nv2@test.ge'}); b = call('x', '/api/verify/resend', {'email': 'nobody-resend@test.ge'}); eq(a, b); eq(a['s'], 200)   # ნეიტრალური პასუხი
    c2 = mail_code('verify', 'nv2@test.ge', n=2); assert c2 and c2 != c1; time.sleep(0.5); eq(mail_count('nobody-resend@test.ge'), 0)
    eq(call('x', '/api/verify/resend', {'email': 'boss@test.ge'})['s'], 200); time.sleep(0.5); eq(len(code_mails('boss@test.ge')), 0)     # ადმინს/დადასტურებულს კოდი არ მიდის
    eq(call('x', '/api/verify/resend', {'email': 'stu@test.ge'})['s'], 200); time.sleep(0.5); eq(len([x for x in mail_subjects('stu@test.ge') if 'დადასტურება' in x]), 1)
    eq(call('x', '/api/verify/resend', {'email': 'არა'})['s'], 400)
    eq(call('nv2', '/api/login', {'email': 'nv2@test.ge', 'password': PW})['s'], 401)
    eq(call('x', '/api/verify', {'email': 'stu@test.ge', 'code': '123456', 'password': PW})['s'], 400)                   # დადასტურებულს დადასტურების კოდით პაროლს ვერავინ შეუცვლის
    eq(call('x', '/api/verify', {'email': 'boss@test.ge', 'code': '123456', 'password': PW})['s'], 400)
ok('დადასტურების კოდის ხელახლა გაგზავნა: პასუხი ნეიტრალურია, ადმინს და დადასტურებულს კოდი არ მიდის', t_verify_resend_neutral)


def t_resend_limits():
    em = 'limit@test.ge'
    for path in ('/api/password/forgot', '/api/verify/resend'):
        em = 'limit-' + path.split('/')[-1] + '@test.ge'
        eq(call('x', path, {'email': em})['s'], 200)
        r = call('x', path, {'email': em}); eq(r['s'], 429); assert 0 < r['retry_after'] <= 2, r                   # 60 წამის (ტესტში 2) წესი
        assert call('x', path, {'email': 'other-' + em})['s'] == 200                                              # სხვა ელფოსტა არ ზღუდავს
        for _ in range(4):
            time.sleep(2.2); eq(call('x', path, {'email': em})['s'], 200)                                         # სულ 5 გაგზავნა საათში
        time.sleep(2.2); r = call('x', path, {'email': em}); eq(r['s'], 429); assert 'საათში' in r['error'] and r['retry_after'] > 60, r   # მე-6: საათობრივი ლიმიტი
ok('ხელახლა გაგზავნა: არაუადრეს 60 წამისა და საათში მაქს. 5 (IP+ელფოსტაზე), სხვა ელფოსტა არ იზღუდება', t_resend_limits)


def t_account_hour_cap():
    # ახალ-ახალი IP-ებით კოდის გამოცნობის წინააღმდეგ: ერთი ანგარიშის კოდები საათში 10-მდეა IP-ის მიუხედავად
    em = 'cap@test.ge'; reg('cap', em, verify=False)
    assert mail_code('verify', em)   # კოდი ფონურ ნაკადში იქმნება: ველოდებით წერილს, სანამ ბაზას შევცვლით
    d = sqlite3.connect(DB_FILE); uid = d.execute('SELECT id FROM users WHERE email=?', (em,)).fetchone()[0]
    d.execute("UPDATE codes SET hour_sends=10, hour_start=? WHERE user_id=?", (int(time.time() * 1000), uid)); d.commit()
    before = d.execute('SELECT hash FROM codes WHERE user_id=?', (uid,)).fetchone()[0]
    time.sleep(2.2); eq(call('x', '/api/verify/resend', {'email': em})['s'], 200); time.sleep(0.6)                   # პასუხი ნეიტრალურია
    eq(d.execute('SELECT hash FROM codes WHERE user_id=?', (uid,)).fetchone()[0], before)                           # ახალი კოდი არ შექმნილა
    d.execute("UPDATE codes SET hour_start=1 WHERE user_id=?", (uid,)); d.commit()                                  # საათი გავიდა
    time.sleep(2.2); call('x', '/api/verify/resend', {'email': em}); time.sleep(0.6)
    assert d.execute('SELECT hash FROM codes WHERE user_id=?', (uid,)).fetchone()[0] != before; d.close()
ok('ერთი ანგარიშის კოდები საათში 10-მდეა (IP-ის მიუხედავად), საათის შემდეგ ისევ შეიძლება', t_account_hour_cap)


def t_verify_attempt_limits():
    em = 'pairlim@test.ge'; reg('pl', em, verify=False)
    s = [call('x', '/api/verify', {'email': em, 'code': 'abcdef', 'password': PW})['s'] for _ in range(12)]
    eq(s[:10], [400] * 10); eq(s[10:], [429, 429])
ok('კოდის შეყვანის ლიმიტი IP+ელფოსტაზე: 10 მცდელობა 10 წუთში', t_verify_attempt_limits)


def t_forgot_same():
    a = call('x', '/api/password/forgot', {'email': 'nv@test.ge'}); b = call('x', '/api/password/forgot', {'email': 'nobody-here@test.ge'})
    c = call('x', '/api/password/forgot', {'email': 'boss@test.ge'})
    eq(a, b); eq(a, c); eq(a['s'], 200)                                   # პასუხი ერთნაირია: არსებული / არარსებული / ადმინი
    assert mail_code('reset', 'nv@test.ge'), 'არსებულ ანგარიშს კოდი უნდა მიეწეროს'
    time.sleep(1.0)
    eq(mail_count('nobody-here@test.ge'), 0); eq(len(code_mails('boss@test.ge')), 0)                              # ადმინს და უცნობს აღდგენის წერილი არ მიდის
    assert not re.search(r'\d{6}', ' '.join(mail_subjects('nv@test.ge'))), 'თემა კოდს არ შეიცავს'
    txt = open(LOG, encoding='utf-8').read(); i = txt.rindex('[MAIL -> nv@test.ge] ' + SUBJ['reset']); assert 'თუ ეს შენ არ იყავი, უგულებელყავი' in txt[i:i + 900]
    eq(call('x', '/api/password/forgot', {'email': 'არა'})['s'], 400)
ok('პაროლის აღდგენა: პასუხი ერთნაირია არსებულ, არარსებულ და ადმინის ელფოსტაზე; წერილი (თემა კოდის გარეშე) მხოლოდ არსებულს მიდის', t_forgot_same)


def t_reset():
    em = 'nv@test.ge'; code = mail_code('reset', em)
    NEW = 'Violet-Harbor-52'
    eq(call('x', '/api/password/reset', {'email': em, 'code': code, 'password': 'Summer2024!'})['s'], 400)       # სუსტი პაროლი; კოდი რჩება
    eq(call('x', '/api/password/reset', {'email': em, 'code': wrong_of(code), 'password': NEW})['s'], 400)
    eq(call('x', '/api/password/reset', {'email': 'nobody-here@test.ge', 'code': code, 'password': NEW})['s'], 400)
    eq(call('x', '/api/password/reset', {'email': em, 'code': code})['s'], 400)                                    # პაროლის გარეშე
    eq(call('nv', '/api/login', {'email': em, 'password': PW2})['s'], 200); assert call('nv', '/api/me')['user']
    eq(call('x', '/api/password/reset', {'email': em, 'code': code, 'password': NEW})['s'], 200)
    assert call('nv', '/api/me')['user'] is None, 'ძველი სესიები უნდა გაუქმდეს'
    eq(call('x', '/api/password/reset', {'email': em, 'code': code, 'password': 'Another-Pass-91x'})['s'], 400)   # ერთჯერადია
    eq(call('nv', '/api/login', {'email': em, 'password': PW2})['s'], 401)
    eq(call('nv', '/api/login', {'email': em, 'password': NEW})['s'], 200)
    # reset კოდი დადასტურების ენდპოინტზე არ გამოდგება და პირიქით (სხვადასხვა ტიპის კოდია)
    call('x', '/api/password/forgot', {'email': 'nv2@test.ge'}); tk = mail_code('reset', 'nv2@test.ge')
    eq(call('x', '/api/verify', {'email': 'nv2@test.ge', 'code': tk, 'password': NEW})['s'], 400)
    # დაუდასტურებელი მომხმარებელი აღდგენით ადასტურებს ელფოსტას (კოდი მან მიიღო)
    eq(call('x', '/api/password/reset', {'email': 'nv2@test.ge', 'code': tk, 'password': NEW})['s'], 200)
    eq(call('nv2', '/api/login', {'email': 'nv2@test.ge', 'password': NEW})['s'], 200); assert call('nv2', '/api/me')['user']['verified'] is True
    # ვადაგასული აღდგენის კოდი
    call('x', '/api/password/forgot', {'email': 'stu@test.ge'}); tk = mail_code('reset', 'stu@test.ge')
    d = sqlite3.connect(DB_FILE); d.execute('UPDATE codes SET expires=1'); d.commit(); d.close()
    eq(call('x', '/api/password/reset', {'email': 'stu@test.ge', 'code': tk, 'password': NEW})['s'], 400)
    # 5 არასწორი მცდელობა აღდგენაზეც
    d = sqlite3.connect(DB_FILE); h_stu = d.execute("SELECT hash FROM users WHERE email='stu@test.ge'").fetchone()[0]; d.close()
    time.sleep(2.2); call('x', '/api/password/forgot', {'email': 'stu@test.ge'}); tk = mail_code('reset', 'stu@test.ge', n=2); w = wrong_of(tk)
    for _ in range(5): eq(call('x', '/api/password/reset', {'email': 'stu@test.ge', 'code': w, 'password': NEW})['s'], 400)
    eq(call('x', '/api/password/reset', {'email': 'stu@test.ge', 'code': tk, 'password': NEW})['s'], 400)
    d = sqlite3.connect(DB_FILE); eq(d.execute("SELECT hash FROM users WHERE email='stu@test.ge'").fetchone()[0] == h_stu, True); d.close()   # პაროლი არ შეცვლილა
    # ადმინის პაროლი კოდით არ იცვლება, თუნდაც ბაზაში კოდი ჩაიწეროს
    d = sqlite3.connect(DB_FILE); uid, h_boss = d.execute("SELECT id,hash FROM users WHERE email='boss@test.ge'").fetchone()
    d.execute("INSERT OR REPLACE INTO codes VALUES(?, 'reset', 'ss', ?, ?, 0, 0, 0)", (uid, hmac.new(b'ss', f'{uid}:reset:123456'.encode(), hashlib.sha256).hexdigest(), int(time.time() * 1000) + 600000)); d.commit(); d.close()
    eq(call('x', '/api/password/reset', {'email': 'boss@test.ge', 'code': '123456', 'password': NEW})['s'], 400)
    d = sqlite3.connect(DB_FILE); eq(d.execute("SELECT hash FROM users WHERE email='boss@test.ge'").fetchone()[0] == h_boss, True); d.close()   # ადმინის პაროლი არ შეცვლილა
ok('პაროლის აღდგენა კოდით: ერთჯერადი, სუსტი პაროლი კოდს არ ხარჯავს, 5 მცდელობა, სესიები წყდება, ვადაგასული და ადმინი არ მუშაობს', t_reset)


def t_migration():
    # ძველი (v3) ბაზა: users-ს email_verified არ აქვს. გახსნისას ბექაფი კეთდება, ყველა მომხმარებელი დადასტურებულია, მონაცემები უცვლელია
    old = os.path.join(tempfile.gettempdir(), f'cda-legacy-{int(time.time() * 1000)}.db'); bk = tempfile.mkdtemp(prefix='cda-mig-')
    d = sqlite3.connect(old)
    d.executescript("CREATE TABLE users(id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT NOT NULL, hash TEXT NOT NULL, salt TEXT NOT NULL, role TEXT DEFAULT 'student', plan TEXT DEFAULT 'free', created INTEGER);"
                    "CREATE TABLE progress(user_id INTEGER, lesson_id INTEGER, PRIMARY KEY(user_id,lesson_id));"
                    "CREATE TABLE quiz_results(user_id INTEGER, lesson_id INTEGER, score INTEGER, total INTEGER, PRIMARY KEY(user_id,lesson_id));"
                    "INSERT INTO quiz_results VALUES(1,5,4,5),(1,6,3,5),(1,7,3,4);"
                    "INSERT INTO users(email,name,hash,salt,role) VALUES('old@test.ge','ძველი','h','s','student'),('adm@test.ge','ადმინი','h','s','admin');"
                    "INSERT INTO progress VALUES(1,5),(1,6);PRAGMA user_version=3;")
    d.commit(); d.close()
    env = {**os.environ, 'DB_FILE': old, 'BACKUP_DIR': bk}
    r = subprocess.run([sys.executable, '-c', 'import db; print(db.one("PRAGMA user_version")["user_version"])'], cwd=HERE, env=env, capture_output=True, text=True)
    eq(r.returncode, 0); assert r.stdout.strip().endswith('9'), r.stdout + r.stderr
    d = sqlite3.connect(old)
    eq([x[0] for x in d.execute('SELECT email_verified FROM users ORDER BY id')], [1, 1]); eq(d.execute('SELECT COUNT(*) FROM progress').fetchone()[0], 2)
    eq([tuple(x) for x in d.execute('SELECT email,hash FROM users ORDER BY id')], [('old@test.ge', 'h'), ('adm@test.ge', 'h')])   # არსებული მომხმარებლები შეუხებელია
    assert d.execute("SELECT 1 FROM sqlite_master WHERE name='codes'").fetchone(), 'codes ცხრილი შეიქმნა'
    eq([x[0] for x in d.execute('SELECT passed FROM quiz_results ORDER BY lesson_id')], [1, 0, 1]); d.close()   # 4/5 და 3/4 გავლილია, 3/5 არა
    bks = [f for f in os.listdir(bk) if f.startswith('premigrate-v3-')]; eq(len(bks), 1)
    b = sqlite3.connect(os.path.join(bk, bks[0])); eq(b.execute('PRAGMA user_version').fetchone()[0], 3)
    assert 'email_verified' not in [c[1] for c in b.execute('PRAGMA table_info(users)')], 'ბექაფი სქემის შეცვლამდეა'; b.close()
    # ახალი ბაზა ბექაფს არ აკეთებს
    new = old + '.new'; bk2 = tempfile.mkdtemp(prefix='cda-mig2-')
    subprocess.run([sys.executable, '-c', 'import db'], cwd=HERE, env={**os.environ, 'DB_FILE': new, 'BACKUP_DIR': bk2}, check=True, capture_output=True)
    eq(os.listdir(bk2), [])
    for f in (old, old + '-wal', old + '-shm', new, new + '-wal', new + '-shm'):
        try: os.remove(f)
        except OSError: pass
    shutil.rmtree(bk, ignore_errors=True); shutil.rmtree(bk2, ignore_errors=True)
ok('მიგრაცია: ძველი ბაზა → ბექაფი სქემის შეცვლამდე, ყველა არსებული მომხმარებელი დადასტურებულია, მონაცემები უცვლელია', t_migration)


def t_make_admin_verified():
    d = sqlite3.connect(DB_FILE); eq(d.execute("SELECT email_verified FROM users WHERE email='boss@test.ge'").fetchone()[0], 1)
    reg('pro2', 'pro2@test.ge', verify=False)
    d.execute("UPDATE users SET email_verified=0 WHERE email='pro2@test.ge'"); d.commit()
    subprocess.run([sys.executable, 'make_admin.py', 'pro2@test.ge', PW, 'X'], cwd=HERE, env=ENV, check=True, stdout=subprocess.DEVNULL)
    r = d.execute("SELECT role,email_verified FROM users WHERE email='pro2@test.ge'").fetchone(); d.close()
    eq(tuple(r), ('admin', 1))
ok('make_admin.py ქმნის/ნიშნავს დადასტურებულ ადმინს', t_make_admin_verified)


def t_smtp():
    import socketserver, threading
    got = []

    class H(socketserver.StreamRequestHandler):
        def handle(self):
            w = lambda s: self.wfile.write((s + '\r\n').encode())
            w('220 fake'); data = False; buf = []
            for raw in self.rfile:
                ln = raw.decode('utf-8', 'replace').rstrip('\r\n')
                if data:
                    if ln == '.':
                        data = False; got.append('\n'.join(buf)); w('250 ok')
                    else:
                        buf.append(ln)
                    continue
                cmd = ln.upper()
                if cmd.startswith('EHLO') or cmd.startswith('HELO'): w('250 fake')
                elif cmd.startswith('DATA'): data = True; w('354 go')
                elif cmd.startswith('QUIT'): w('221 bye'); return
                else: w('250 ok')
    srv2 = socketserver.ThreadingTCPServer(('127.0.0.1', 0), H); port = srv2.server_address[1]
    threading.Thread(target=srv2.serve_forever, daemon=True).start()
    env = {**os.environ, 'SMTP_HOST': '127.0.0.1', 'SMTP_PORT': str(port), 'SMTP_SECURITY': 'none', 'SMTP_FROM': 'noreply@cda.test'}
    code = "import mailer;print(mailer.send_now('s@test.ge','CDA: პაროლის აღდგენა','გამარჯობა\\nბმული'))"
    r = subprocess.run([sys.executable, '-c', code], cwd=HERE, env=env, capture_output=True, text=True, timeout=30)
    srv2.shutdown(); eq(r.stdout.strip(), 'True'); eq(len(got), 1)
    assert 'To: s@test.ge' in got[0] and 'From: noreply@cda.test' in got[0] and 'Subject:' in got[0], got[0][:300]
    # სათაურში ახალი ხაზის ჩასმა უარყოფილია და სერვერს არ ეგზავნება
    r = subprocess.run([sys.executable, '-c', "import mailer;print(mailer.send_now('a@b.ge\\nBcc: evil@x.ge','x','y'))"], cwd=HERE, env=env, capture_output=True, text=True, timeout=30)
    eq(r.stdout.strip().splitlines()[-1], 'False'); eq(len(got), 1)
ok('SMTP: წერილი იგზავნება (ყალბ SMTP სერვერზე გატესტილი), სათაურში ახალი ხაზი უარყოფილია', t_smtp)


def fake_smtp(auth='ok', starttls_ext=False):
    """ყალბი SMTP სერვერი (AUTH PLAIN/LOGIN; auth='reject' → 535). აბრუნებს (სერვერი, პორტი, მიღებული წერილები)."""
    import socketserver, threading
    got = []

    class H(socketserver.StreamRequestHandler):
        def handle(self):
            w = lambda s_: self.wfile.write((s_ + '\r\n').encode())
            w('220 fake'); data = False; buf = []
            for raw in self.rfile:
                ln = raw.decode('utf-8', 'replace').rstrip('\r\n')
                if data:
                    if ln == '.': data = False; got.append('\n'.join(buf)); w('250 ok')
                    else: buf.append(ln)
                    continue
                cmd = ln.upper()
                if cmd.startswith('EHLO') or cmd.startswith('HELO'): w('250-fake'); w('250 AUTH PLAIN LOGIN')
                elif cmd.startswith('AUTH'): w('235 ok' if auth == 'ok' else '535 5.7.8 Username and Password not accepted')
                elif cmd.startswith('DATA'): data = True; w('354 go')
                elif cmd.startswith('QUIT'): w('221 bye'); return
                else: w('250 ok')
    srv_ = socketserver.ThreadingTCPServer(('127.0.0.1', 0), H); srv_.daemon_threads = True
    threading.Thread(target=srv_.serve_forever, daemon=True).start()
    return srv_, srv_.server_address[1], got


def run_mail_tool(args=('t@test.ge',), **smtp):
    env = {k: v for k, v in os.environ.items() if not k.startswith('SMTP_')}
    env['CDA_NO_DOTENV'] = '1'; env.update({'SMTP_' + k.upper(): str(v) for k, v in smtp.items()})
    r = subprocess.run([sys.executable, 'tools/test_mail.py', *args], cwd=HERE, env=env, capture_output=True, text=True, encoding='utf-8', timeout=60)
    return r.returncode, r.stdout + r.stderr


def t_test_mail_tool():
    SECRET = 'sekret-pw-9z'
    rc, out = run_mail_tool(); eq(rc, 2); assert 'SMTP_HOST ცარიელია' in out and 'არ იგზავნება' in out, out          # SMTP მორგებული არ არის
    rc, out = run_mail_tool(args=('არა',)); eq(rc, 2)                                                              # არასწორი არგუმენტი
    srv_, port, got = fake_smtp('ok')
    rc, out = run_mail_tool(host='127.0.0.1', port=port, security='none', user='u@x.ge', password=SECRET, **{'from': 'CDA <noreply@x.ge>'})
    eq(rc, 0); assert '✔' in out and SECRET not in out, out; eq(len(got), 1)                                       # წარმატება; პაროლი არ იბეჭდება
    assert 'To: t@test.ge' in got[0] and 'Date:' in got[0] and 'Message-ID:' in got[0], got[0][:400]
    srv_.shutdown()
    srv_, port, got = fake_smtp('reject')
    rc, out = run_mail_tool(host='127.0.0.1', port=port, security='none', user='u@x.ge', password=SECRET)
    eq(rc, 1); assert '[ავტორიზაცია]' in out and 'App password' in out and SECRET not in out, out                   # პაროლის/ავტორიზაციის შეცდომა
    srv_.shutdown()
    srv_, port, got = fake_smtp('ok')
    rc, out = run_mail_tool(host='127.0.0.1', port=port, security='starttls', user='u@x.ge', password=SECRET)
    eq(rc, 1); assert '[უსაფრთხოება]' in out and 'STARTTLS' in out, out                                            # სერვერს STARTTLS არ აქვს
    rc, out = run_mail_tool(host='127.0.0.1', port=port, security='ssl', user='u@x.ge', password=SECRET)
    eq(rc, 1); assert '[უსაფრთხოება]' in out or '[კავშირი]' in out, out                                             # ssl უბრალო სერვერზე
    srv_.shutdown()
    import socket
    sk = socket.socket(); sk.bind(('127.0.0.1', 0)); dead = sk.getsockname()[1]; sk.close()                         # დახურული პორტი
    rc, out = run_mail_tool(host='127.0.0.1', port=dead, security='none')
    eq(rc, 1); assert '[პორტი]' in out, out
    rc, out = run_mail_tool(host='127.0.0.1', port=dead, security='ssl'); eq(rc, 1)
    rc, out = run_mail_tool(host='127.0.0.1', port=587, security='ssl', user='a', password='b')
    assert '⚠' in out and '587' in out, out
    rc, out = run_mail_tool(host='no-such-host.invalid', port=587, security='starttls')
    eq(rc, 1); assert '[მისამართი]' in out or '[ქსელი]' in out, out
    rc, out = run_mail_tool(host='127.0.0.1', port='abc'); eq(rc, 1); assert 'SMTP_PORT' in out, out                    # არასწორი პორტი
ok('tools/test_mail.py: SMTP არ არის / წარმატება / ავტორიზაცია / STARTTLS / ssl / პორტი / ჰოსტი: ნათელი შეტყობინება და გასვლის კოდი, პაროლი არ იბეჭდება', t_test_mail_tool)


def t_startup_and_config():
    txt = open(LOG, encoding='utf-8').read()
    eq(txt.count('SMTP არ არის მორგებული'), 1)                         # გაშვებისას ერთხელ
    c = call('x', '/api/config'); eq((c['requireVerify'], c['codeMinutes'], c['resendSeconds']), (True, 10, 2))
    env = {k: v for k, v in os.environ.items() if not k.startswith('SMTP_')}; env.update(CDA_NO_DOTENV='1', DB_FILE=DB_FILE + '.warn', BACKUP_DIR=BACKUP_DIR)
    r = subprocess.run([sys.executable, '-c', 'import mailer;print(mailer.startup_warning())'], cwd=HERE, env=env, capture_output=True, text=True, encoding='utf-8')
    assert 'არ იგზავნება' in r.stdout, r.stdout
    env.update(SMTP_HOST='h.example', SMTP_PORT='587', SMTP_SECURITY='starttls', SMTP_USER='u', SMTP_PASSWORD='p')
    r = subprocess.run([sys.executable, '-c', 'import mailer;print(mailer.startup_warning())'], cwd=HERE, env=env, capture_output=True, text=True, encoding='utf-8')
    eq(r.stdout.strip(), 'None')                                       # მორგებულ SMTP-ზე გაფრთხილება არ არის
ok('გაშვებისას SMTP-ის გაფრთხილება ერთხელ ჩანს; /api/config იძლევა requireVerify-ს', t_startup_and_config)


def t_envfile():
    import envfile
    txt = '# კომენტარი\nA=1\nexport B="two words"\nC=plain   # comment\nD="has # hash"\nSMTP_FROM="CDA <noreply@x.ge>"\nE=a#b\n bad line\n9X=1\nF=\n﻿G=bom\n'
    pr = envfile.parse(txt)
    eq((pr['A'], pr['B'], pr['C'], pr['D'], pr['SMTP_FROM'], pr['E'], pr['F']), ('1', 'two words', 'plain', 'has # hash', 'CDA <noreply@x.ge>', 'a#b', ''))
    assert '9X' not in pr and 'bad line' not in pr
    f = os.path.join(tempfile.gettempdir(), f'cda-env-{int(time.time() * 1000)}'); open(f, 'w', encoding='utf-8').write('SMTP_HOST=smtp.example.org\nSMTP_PORT=2525\nSMTP_SECURITY=ssl\nSMTP_FROM="CDA <noreply@example.org>"\n')
    e = {'SMTP_PORT': '999'}; new = envfile.load(f, e)
    eq((e['SMTP_HOST'], e['SMTP_PORT'], sorted(new)), ('smtp.example.org', '999', ['SMTP_FROM', 'SMTP_HOST', 'SMTP_SECURITY']))   # რეალური ცვლადი იმარჯვებს
    eq(envfile.load(f, {'CDA_NO_DOTENV': '1'}), []); eq(envfile.load(f + '.missing', {}), [])
    # ინტეგრაცია: მოდულები .env-ს თავისით კითხულობენ (სხვა საქაღალდიდან გაშვებისას)
    env = {k: v for k, v in os.environ.items() if not k.startswith('SMTP_') and k != 'CDA_NO_DOTENV'}; env.update(CDA_ENV_FILE=f, SMTP_PORT='2626')
    r = subprocess.run([sys.executable, '-c', f"import sys; sys.path.insert(0, {HERE!r}); import mailer; print(mailer.HOST, mailer.PORT, mailer.SECURITY, mailer.FROM)"], cwd=tempfile.gettempdir(), env=env, capture_output=True, text=True, encoding='utf-8')
    eq(r.stdout.strip(), 'smtp.example.org 2626 ssl CDA <noreply@example.org>')
    r = subprocess.run([sys.executable, '-c', 'import db; print(db.DB_FILE)'], cwd=HERE, env={**env, 'CDA_ENV_FILE': f}, capture_output=True, text=True)
    os.remove(f)
ok('.env ავტომატურად იტვირთება (დამატებითი პაკეტის გარეშე): ბრჭყალები, კომენტარები, რეალური ცვლადი იმარჯვებს, CDA_NO_DOTENV აჩერებს', t_envfile)


def t_audit_privacy():
    reg('priv', 'priv-user@test.ge')
    call('x', '/api/login', {'email': 'priv-user@test.ge', 'password': 'bad-pass-1'})     # login_fail ჩანაწერი ელფოსტით
    uid = call('priv', '/api/me')['user']['id']
    d = sqlite3.connect(DB_FILE)
    assert d.execute("SELECT COUNT(*) FROM audit WHERE user_id=? OR instr(lower(detail),'priv-user@test.ge')>0", (uid,)).fetchone()[0] >= 2
    eq(call('priv', '/api/account/delete', {'password': PW})['s'], 200)
    eq(d.execute("SELECT COUNT(*) FROM audit WHERE user_id=?", (uid,)).fetchone()[0], 0)
    eq(d.execute("SELECT COUNT(*) FROM audit WHERE instr(lower(detail),'priv-user@test.ge')>0").fetchone()[0], 0)
    eq(d.execute("SELECT COUNT(*) FROM tokens WHERE user_id=?", (uid,)).fetchone()[0], 0); eq(d.execute("SELECT COUNT(*) FROM codes WHERE user_id=?", (uid,)).fetchone()[0], 0); d.close()
ok('ანგარიშის წაშლა: ჟურნალში user_id, IP და ელფოსტა ანონიმიზდება', t_audit_privacy)


def t_audit_retention():
    f = os.path.join(tempfile.gettempdir(), f'cda-aud-{int(time.time() * 1000)}.db'); bk = tempfile.mkdtemp(prefix='cda-aud-')
    code = ("import db,time;now=int(time.time()*1000);D=86400000\n"
            "db.run(\"INSERT INTO audit(action,created) VALUES('old',?)\", now-91*D);db.run(\"INSERT INTO audit(action,created) VALUES('keep',?)\", now-89*D)\n"
            "db.purge_audit(90);print(sorted(r['action'] for r in db.all_('SELECT action FROM audit')))")
    r = subprocess.run([sys.executable, '-c', code], cwd=HERE, env={**os.environ, 'DB_FILE': f, 'BACKUP_DIR': bk}, capture_output=True, text=True, timeout=30)
    eq(r.stdout.strip().splitlines()[-1], "['keep']")
    for x in (f, f + '-wal', f + '-shm'):
        try: os.remove(x)
        except OSError: pass
    shutil.rmtree(bk, ignore_errors=True)
ok('ჟურნალი ვადიანია: 90 დღეზე ძველი ჩანაწერები იშლება', t_audit_retention)


def t_fonts():
    r, b = call('x', '/', raw=True); csp = r.getheader('content-security-policy')
    assert 'googleapis' not in csp and 'gstatic' not in csp and "font-src 'self'" in csp and "style-src 'self';" in csp, csp
    assert b'googleapis' not in b and b'gstatic' not in b, 'index.html-ში Google Fonts არ უნდა იყოს'
    css = open(os.path.join(HERE, 'public', 'css', 'style.css'), encoding='utf-8').read()
    assert 'http' not in ''.join(re.findall(r'url\([^)]*\)', css)), 'CSS-ში გარე url არ უნდა იყოს'
    urls = re.findall(r'@font-face\{[^}]*?url\(\.\./fonts/([^)]+)\)', css); assert len(urls) == 2, urls
    fp = os.path.join(HERE, 'public', 'fonts', '_t.woff2')            # woff2 სწორი MIME-ით ისერვება
    open(fp, 'wb').write(b'wOF2' + b'0' * 40)
    try:
        r, _ = call('x', '/fonts/_t.woff2', raw=True); eq(r.status, 200); eq(r.getheader('content-type'), 'font/woff2')
    finally:
        os.remove(fp)
    for u in urls:
        if not os.path.isfile(os.path.join(HERE, 'public', 'fonts', u)):
            print('  ⚠ შრიფტის ფაილი ჯერ არ არის public/fonts/-ში:', u, '(python3 tools/fetch_fonts.py)')
ok('შრიფტები: Google არ გამოიყენება (CSP, HTML, CSS), woff2 სწორი MIME-ით ისერვება', t_fonts)


def t_md():
    # md() ტესტდება node-ით (თუ დაყენებულია): ბმული მხოლოდ https, სურათი მხოლოდ /img/lessons/-იდან, XSS ვერ გადის
    if not shutil.which('node'):
        print('  ⚠ node არ არის დაყენებული: md()-ის ტესტი გამოტოვებულია'); return
    cases = ['[ტექსტი](https://example.com/a?b=1&c=2)', '[x](javascript:alert(1))', '[x](http://example.com)', '[x](https://a.com/"onmouseover="alert(1))',
             '![სქემა](/img/lessons/dns-resolution.svg)', '![x](/img/lessons/../../x.png)', '![x](/img/other/x.png)', '`[a](https://b.com)` და **მუქი**',
             '<script>alert(1)</script>', '![a"onerror="x](/img/lessons/ok.png)']
    r = subprocess.run(['node', os.path.join(HERE, 'tools', 'mdtest.js'), os.path.join(HERE, 'public', 'js', 'app.js')], input=json.dumps(cases),
                       capture_output=True, text=True, encoding='utf-8', timeout=30)
    eq(r.returncode, 0); o = json.loads(r.stdout)
    assert 'href="https://example.com/a?b=1&amp;c=2" target="_blank" rel="noopener noreferrer"' in o[0]
    assert '<a' not in o[1] and '<a' not in o[2] and '<a' not in o[3] and 'onmouseover=&quot;' in o[3] and 'href="https://a.com/"' not in o[3]
    assert '<img src="/img/lessons/dns-resolution.svg"' in o[4] and '<figcaption>სქემა</figcaption>' in o[4]
    assert '<img' not in o[5] and '<img' not in o[6] and '<a' not in o[7] and '<code>[a](https://b.com)</code>' in o[7]
    assert '<script' not in o[8] and '&lt;script&gt;' in o[8]
    assert 'alt="a&quot;onerror=&quot;x"' in o[9]                       # ბრჭყალები ესკეიპირებულია, ატრიბუტიდან ვერ გამოდის
    assert os.path.isfile(os.path.join(HERE, 'public', 'img', 'lessons', 'dns-resolution.svg'))
    r, b = call('x', '/img/lessons/dns-resolution.svg', raw=True); eq(r.status, 200); assert r.getheader('content-type').startswith('image/svg+xml') and b.startswith(b'<svg')
ok('md(): ბმული მხოლოდ https-ით და noopener-ით, სურათი მხოლოდ /img/lessons/-იდან, XSS ესკეიპირებულია; SVG ისერვება', t_md)


def t_content_validator():
    import copy, validate_content as vc
    errs, warns = vc.validate(COURSE)
    assert not errs, errs[:5]                                          # content.json-ში შეცდომა არ უნდა იყოს
    good = copy.deepcopy(COURSE)
    def bad(fn):
        c = copy.deepcopy(good); fn(c); return vc.validate(c)[0]
    L = lambda c: c[0]['lessons'][0]
    cases = {
        'ქვიზის ინდექსი': lambda c: L(c)['quiz'][0].__setitem__('a', 9),
        'ცარიელი განმარტება': lambda c: L(c)['quiz'][0].__setitem__('e', ' '),
        'ცარიელი კითხვა': lambda c: L(c)['quiz'][0].__setitem__('q', ''),
        'განმეორებული ვარიანტი': lambda c: L(c)['quiz'][0].__setitem__('o', ['ა', 'ა', 'ბ']),
        'ცარიელი content': lambda c: L(c).__setitem__('content', ''),
        'არასწორი minutes': lambda c: L(c).__setitem__('minutes', 0),
        'ცარიელი objectives': lambda c: L(c).__setitem__('objectives', []),
        'http ბმული': lambda c: L(c).__setitem__('content', 'ნახე [აქ](http://example.com)'),
        'javascript ბმული': lambda c: L(c).__setitem__('content', '[x](javascript:alert(1))'),
        'სურათი სხვა გზიდან': lambda c: L(c).__setitem__('content', '![x](https://evil.example/a.png)'),
        'არარსებული სურათი': lambda c: L(c).__setitem__('content', '![x](/img/lessons/not-there.svg)'),
        'დაუხურავი ბლოკი': lambda c: L(c).__setitem__('content', '```\nკოდი'),
        'ეტაპის ნომერი': lambda c: c[1].__setitem__('stage', 7),
        'აკლია ველი': lambda c: L(c).pop('task'),
    }
    for name, fn in cases.items():
        assert bad(fn), f'ვალიდატორმა ვერ დაიჭირა: {name}'
    ok_content = copy.deepcopy(good); L(ok_content)['content'] += '\n\n![DNS](/img/lessons/dns-resolution.svg)\n\nიხილე [RFC](https://www.rfc-editor.org/rfc/rfc1034)'
    assert not vc.validate(ok_content)[0], vc.validate(ok_content)[0]    # არსებული სურათი და https ბმული ვარგა
    code_ok = copy.deepcopy(good); L(code_ok)['content'] += '\n\nგაუშვი `python3 -m http.server --bind 127.0.0.1` და გახსენი `http://127.0.0.1:8000/`.\n\n```\nhttp://127.0.0.1:8000/\n```'
    assert not vc.validate(code_ok)[0], vc.validate(code_ok)[0]          # http:// კოდის ბლოკსა და ინლაინ კოდში ნებადართულია
    bad_http = copy.deepcopy(good); L(bad_http)['content'] += '\n\nნახე [აქ](http://example.com)'
    assert vc.validate(bad_http)[0]                                      # ჩვეულებრივ ბმულში კი არა
    r = subprocess.run([sys.executable, 'validate_content.py'], cwd=HERE, capture_output=True, text=True, encoding='utf-8'); eq(r.returncode, 0)
    r = subprocess.run([sys.executable, 'validate_content.py', '--strict'], cwd=HERE, capture_output=True, text=True, encoding='utf-8')
    print(f'  ინფო: content.json-ზე გაფრთხილება {len(warns)} (ძირითადად ქვიზის ბანკი 10-ზე ნაკლებია), --strict გასვლის კოდი {r.returncode}')
ok('content.json-ის ვალიდატორი: ახლანდელ ფაილზე 0 შეცდომა, ცუდი შიგთავსის 14 ტიპი იჭერს', t_content_validator)


def t_lesson_drafts():
    # დრაფტი გაკვეთილები (content.json-ში ჯერ არ არის) გადიან სტანდარტის შემოწმებას და მათში ჩაწერილი ბრძანებები რეალურად სრულდება
    reg_ = json.load(open(os.path.join(HERE, 'drafts', 'drafts.json'), encoding='utf-8'))
    for f in sorted(reg_):
        r = subprocess.run([sys.executable, 'tools/check_lesson_draft.py', os.path.join('drafts', f)], cwd=HERE, capture_output=True, text=True, encoding='utf-8')
        assert r.returncode == 0, f + '\n' + r.stdout[-900:] + r.stderr[-300:]
        r = subprocess.run([sys.executable, 'tools/verify_lesson_outputs.py', os.path.join('drafts', f)], cwd=HERE, capture_output=True, text=True, encoding='utf-8')
        assert r.returncode == 0, f + '\n' + r.stdout[-900:]
    # საყრდენი რეესტრი ემთხვევა ფაილებს
    eq(sorted(f for f in os.listdir(os.path.join(HERE, 'drafts')) if f.endswith('.json') and f != 'drafts.json'), sorted(reg_))
    print(f'  ინფო: შემოწმებული დრაფტი: {sorted(reg_)}')
ok('დრაფტი გაკვეთილები: სტანდარტის 11 პუნქტი და ჩაწერილი ბრძანებების რეალური გამოსავალი', t_lesson_drafts)


def t_videos_csv():
    import csv as _csv, auth
    rows = list(_csv.DictReader(open(os.path.join(HERE, 'videos.csv'), encoding='utf-8-sig', newline='')))
    eq(len(rows), 28)
    lessons = [(0, s.get('stage', s.get('week')), j + 1, l['title']) for s in COURSE for j, l in enumerate(s['lessons'])]
    lessons = [(i + 1,) + x[1:] for i, x in enumerate(lessons)]
    eq([(int(r['lesson_id']), int(r['stage']), int(r['pos']), r['lesson_title']) for r in rows], lessons)   # id/ეტაპი/პოზიცია/სათაური content.json-ს ემთხვევა
    seen = set()
    for r in rows:
        assert r['status'] in ('გადამოწმებული', 'ვერ ვიპოვე') and r['backup_status'] in ('გადამოწმებული', 'ვერ ვიპოვე')
        for u, st, tt in ((r['primary_url'], r['status'], r['primary_title']), (r['backup_url'], r['backup_status'], r['backup_title'])):
            if st == 'გადამოწმებული':
                assert auth.valid_url(u, allow_empty=False) and re.match(r'https://(www\.)?youtube\.com/(watch\?v=|embed/)[\w-]{11}', u), u
                assert tt.strip() and r['evidence'].strip(), f'სათაური და წყარო სავალდებულოა: {u}'
                assert u not in seen, 'ბმული განმეორდა'; seen.add(u)
            else:
                assert not u, 'ვერ ვიპოვე რიგს ბმული არ უნდა ჰქონდეს'
        if r['status'] != 'გადამოწმებული' or r['backup_status'] != 'გადამოწმებული':
            assert r['search_phrases'].count('|') >= 1, f"{r['lesson_title']}: 2-3 საძიებო ფრაზა სჭირდება"
    assert os.path.isfile(os.path.join(HERE, 'videos.md'))
ok('videos.csv: 28 რიგი ემთხვევა content.json-ს, გადამოწმებულ ბმულებს YouTube-ის ფორმა, სათაური და წყარო აქვს; დანარჩენს საძიებო ფრაზები', t_videos_csv)


def t_import_videos():
    import csv as _csv
    f = os.path.join(tempfile.gettempdir(), f'cda-vid-{int(time.time() * 1000)}.db'); bk = tempfile.mkdtemp(prefix='cda-vid-')
    env = {**os.environ, 'DB_FILE': f, 'BACKUP_DIR': bk}
    run_ = lambda *a: subprocess.run([sys.executable, 'import_videos.py', '--db', f, *a], cwd=HERE, env=env, capture_output=True, text=True, encoding='utf-8')
    q = lambda sql: (lambda c: (c.execute(sql).fetchall(), c.close())[0])(sqlite3.connect(f))
    try:
        r = run_(); eq(r.returncode, 1); assert 'ბაზა ვერ ვიპოვე' in r.stderr or 'ბაზა ვერ ვიპოვე' in r.stdout          # ბაზა არ არსებობს: არაფერს ქმნის
        assert not os.path.exists(f)
        subprocess.run([sys.executable, '-c', 'import db'], cwd=HERE, env=env, check=True, capture_output=True)          # სქემა და გაკვეთილები
        before = q('SELECT id,video_url,video2_url FROM lessons ORDER BY id'); assert all(not x[1] for x in before)
        r = run_(); eq(r.returncode, 0); assert 'საცდელი გაშვება' in r.stdout and '6 გაკვეთილზე' in r.stdout, r.stdout
        eq(q('SELECT id,video_url,video2_url FROM lessons ORDER BY id'), before)                                           # საცდელი გაშვება ბაზას არ ცვლის
        r = run_('--apply'); eq(r.returncode, 0); assert 'ბექაფი:' in r.stdout, r.stdout + r.stderr
        eq(len([x for x in os.listdir(bk) if x.startswith('videos-import-')]), 1)
        row = q("SELECT video_url,video_title,video_channel FROM lessons WHERE week=4 AND pos=1")[0]
        eq(row[0], 'https://www.youtube.com/embed/SBcDGb9l6yo?feature=oembed'); eq(row[2], 'Professor Messer'); assert 'CIA' in row[1]
        eq(q("SELECT video2_url FROM lessons WHERE week=6 AND pos=1")[0][0], 'https://www.youtube.com/watch?v=kqtD5dpn9C8&ab_channel=ProgrammingwithMosh')
        eq(q("SELECT COUNT(*) FROM lessons WHERE video_url<>''")[0][0], 5); eq(q("SELECT COUNT(*) FROM lessons WHERE video2_url<>''")[0][0], 2)
        # ადმინის ჩასმულ ბმულს არ ეხება
        c = sqlite3.connect(f); c.execute("UPDATE lessons SET video_url='https://youtu.be/ADMINLINK01' WHERE week=1 AND pos=1"); c.commit(); c.close()
        r = run_('--apply'); assert 'ადმინის ჩასმული' in r.stdout
        eq(q("SELECT video_url FROM lessons WHERE week=1 AND pos=1")[0][0], 'https://youtu.be/ADMINLINK01')
        # არასწორი ბმულები (http, javascript, ინტერვალი) უარყოფილია
        src = list(_csv.DictReader(open(os.path.join(HERE, 'videos.csv'), encoding='utf-8-sig', newline=''))); bad = os.path.join(bk, 'bad.csv')
        for u, pos in (('http://www.youtube.com/watch?v=aaaaaaaaaaa', 1), ('javascript:alert(1)', 2), ('https://www.youtube.com/watch?v=a b', 3)):
            r0 = dict(src[pos - 1]); r0['primary_url'] = u; r0['status'] = 'გადამოწმებული'; src[pos - 1] = r0
        with open(bad, 'w', encoding='utf-8', newline='') as fh:
            w = _csv.DictWriter(fh, list(src[0])); w.writeheader(); w.writerows(src)
        c = sqlite3.connect(f); c.execute("UPDATE lessons SET video_url=''"); c.commit(); c.close()
        r = run_('--csv', bad, '--apply'); eq(r.stdout.count('ბმული არასწორია'), 3, )
        eq(q("SELECT COUNT(*) FROM lessons WHERE video_url LIKE 'http://%' OR video_url LIKE 'javascript:%' OR video_url LIKE '% %'")[0][0], 0)
    finally:
        for x in (f, f + '-wal', f + '-shm'):
            try: os.remove(x)
            except OSError: pass
        shutil.rmtree(bk, ignore_errors=True)
ok('import_videos.py: საცდელი გაშვება ბაზას არ ცვლის, --apply ბექაფს აკეთებს, https-ის ვალიდაცია, ადმინის ბმულს არ ეხება', t_import_videos)


def t_video_meta_api():
    lid = lessons_of('boss')[1]['id']
    d = call('boss', '/api/admin/lesson', {'id': lid, 'video_url': 'https://www.youtube.com/watch?v=aaaaaaaaaaa', 'pdf_url': '', 'video_title': 'ტესტი', 'video_channel': 'არხი',
                                           'video2_url': 'https://www.youtube.com/watch?v=bbbbbbbbbbb', 'video2_title': 'სათადარიგო'}); eq(d['s'], 200)
    g = call('boss', '/api/lesson/%d' % lid); eq((g['video_title'], g['video_channel'], g['video2_title']), ('ტესტი', 'არხი', 'სათადარიგო'))
    # ბმული შეიცვალა, სათაური არ მოუთითებიათ: ძველი სათაური/არხი სხვა ვიდეოს არ უნდა მიეწეროს
    eq(call('boss', '/api/admin/lesson', {'id': lid, 'video_url': 'https://youtu.be/ccccccccccc', 'pdf_url': ''})['s'], 200)
    eq(call('boss', '/api/admin/lesson', {'id': lid, 'video_url': 'https://youtu.be/ccccccccccc', 'pdf_url': '', 'video2_url': 'https://youtu.be/ddddddddddd'})['s'], 200)
    g0 = call('boss', '/api/lesson/%d' % lid); eq((g0['video2_title'], g0['video2_channel']), ('', '')); eq(g0['video2_url'], 'https://youtu.be/ddddddddddd')   # სათადარიგო შეიცვალა: ძველი სათაური წაიშალა
    eq(call('boss', '/api/admin/lesson', {'id': lid, 'video_url': 'https://youtu.be/ccccccccccc', 'pdf_url': '', 'video2_url': 'https://www.youtube.com/watch?v=bbbbbbbbbbb'})['s'], 200)
    g = call('boss', '/api/lesson/%d' % lid); eq((g['video_title'], g['video_channel']), ('', '')); eq(g['video2_url'], 'https://www.youtube.com/watch?v=bbbbbbbbbbb')
    for bad in ({'video_url': 'http://x.ge/a'}, {'video_url': 'https://a.ge/ b'}, {'video_url': '', 'video2_url': 'javascript:alert(1)'}, {'video_url': '', 'video_title': 'x' * 201}):
        eq(call('boss', '/api/admin/lesson', {'id': lid, 'pdf_url': '', **bad})['s'], 400)
    eq(call('stu', '/api/admin/lesson', {'id': lid, 'video_url': ''})['s'], 403)
    call('boss', '/api/admin/lesson', {'id': lid, 'video_url': '', 'pdf_url': '', 'video2_url': '', 'video_title': '', 'video_channel': '', 'video2_title': '', 'video2_channel': ''})
ok('ვიდეოს მეტამონაცემები: სათაური/არხი/სათადარიგო ბმული ინახება, ბმულის შეცვლისას ძველი სათაური იშლება, არასწორი შეყვანა 400', t_video_meta_api)


def t_admin_legacy_db():
    # რეგრესია: ძველი სქემის ბაზაზე (v3 → მიგრაცია) ადმინის ყველა ენდფოინთი 200-ს აბრუნებს, მონაცემებიც ახალ ველებთან ერთად
    global PORT
    sys.path.insert(0, HERE)
    from auth import hash_pw
    old = os.path.join(tempfile.gettempdir(), f'cda-legacy-adm-{int(time.time() * 1000)}.db'); bk = tempfile.mkdtemp(prefix='cda-adm-bk-')
    d = sqlite3.connect(old)
    d.executescript("CREATE TABLE users(id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT NOT NULL, hash TEXT NOT NULL, salt TEXT NOT NULL, role TEXT DEFAULT 'student', plan TEXT DEFAULT 'free', plan_expires INTEGER, created INTEGER DEFAULT 0, last_login INTEGER);"
                    "CREATE TABLE progress(user_id INTEGER, lesson_id INTEGER, PRIMARY KEY(user_id,lesson_id));"
                    "CREATE TABLE quiz_results(user_id INTEGER, lesson_id INTEGER, score INTEGER, total INTEGER, PRIMARY KEY(user_id,lesson_id));PRAGMA user_version=3;")
    d.execute("INSERT INTO users(email,name,hash,salt,role,created) VALUES('legacy-adm@test.ge','ძველი ადმინი',?,?,'admin',?)", (hash_pw(PW, 'salt1'), 'salt1', int(time.time() * 1000)))
    d.execute("INSERT INTO users(email,name,hash,salt,role,created) VALUES('legacy-st@test.ge','ძველი მოსწავლე','h','s','student',?)", (int(time.time() * 1000),))
    d.execute("INSERT INTO progress VALUES(2,1),(2,2)"); d.execute("INSERT INTO quiz_results VALUES(2,1,4,5)"); d.commit(); d.close()
    env = {**ENV, 'DB_FILE': old, 'BACKUP_DIR': bk, 'PORT': '3918'}
    subprocess.run([sys.executable, '-c', 'import db'], cwd=HERE, env=env, check=True, capture_output=True)   # მიგრაცია
    d = sqlite3.connect(old); now = int(time.time() * 1000)
    d.execute("INSERT INTO orders(user_id,plan,status,created,amount) VALUES(2,'pro','pending',?,50)", (now,))
    d.execute("INSERT INTO questions(user_id,lesson_id,text,created,kind,status) VALUES(2,1,'კითხვა',?,'question','open')", (now,)); d.commit(); d.close()
    lsrv = subprocess.Popen([sys.executable, 'server.py'], cwd=HERE, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    old_port, PORT = PORT, 3918
    try:
        for _ in range(50):
            try:
                http.client.HTTPConnection('localhost', 3918, timeout=2).request('GET', '/api/config'); break
            except OSError:
                time.sleep(0.2)
        eq(call('lg', '/api/login', {'email': 'legacy-adm@test.ge', 'password': PW})['s'], 200)
        for path in ('/api/me', '/api/admin/stats', '/api/admin/users?q=&plan=&page=0', '/api/admin/users.csv', '/api/admin/orders', '/api/admin/orders?all=1',
                     '/api/admin/lessons', '/api/admin/audit', '/api/questions'):
            r, b = call('lg', path, raw=True); assert r.status == 200, (path, r.status, b[:200])
        r, b = call('lg', '/api/admin/backup', {}, raw=True); assert r.status == 200, ('backup', r.status, b[:200])
        st = call('lg', '/api/admin/stats'); eq(st['users'], 1); eq(st['orders'], 1); eq(st['open'], 1)
    finally:
        PORT = old_port; lsrv.terminate(); lsrv.wait()
        for f in (old, old + '-wal', old + '-shm'):
            try: os.remove(f)
            except OSError: pass
        shutil.rmtree(bk, ignore_errors=True)
ok('ადმინი: ძველი სქემის (v3) ბაზაზე ყველა /api/admin/* და /api/questions აბრუნებს 200-ს', t_admin_legacy_db)


# ---------------------------------------------------------------- მრავალი კურსი (courses.py, სქემა v9)
def t_migration_v9():
    # v8 ბაზა (ერთი კურსი): მიგრაცია v9-ზე ბექაფით; lesson id-ები, პროგრესი, ქვიზები, კითხვები, სერტიფიკატი და ადმინის ბმულები უცვლელია; იდემპოტენტურია
    old = os.path.join(tempfile.gettempdir(), f'cda-v8-{int(time.time() * 1000)}.db'); bk = tempfile.mkdtemp(prefix='cda-v9bk-')
    d = sqlite3.connect(old)
    d.executescript(
        "CREATE TABLE users(id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT NOT NULL, hash TEXT NOT NULL, salt TEXT NOT NULL, role TEXT DEFAULT 'student', plan TEXT DEFAULT 'free', created INTEGER);"
        "CREATE TABLE lessons(id INTEGER PRIMARY KEY, week INTEGER, pos INTEGER, title TEXT, summary TEXT, task TEXT, free INTEGER DEFAULT 0, video_url TEXT DEFAULT '', pdf_url TEXT DEFAULT '', content TEXT DEFAULT '', quiz TEXT DEFAULT '[]', bonus TEXT DEFAULT '', objectives TEXT DEFAULT '[]', minutes INTEGER DEFAULT 0, exercises TEXT DEFAULT '[]');"
        "CREATE UNIQUE INDEX i_lessons_wp ON lessons(week,pos);"
        "CREATE TABLE stages(id INTEGER PRIMARY KEY, title TEXT NOT NULL, description TEXT DEFAULT '');"
        "CREATE TABLE progress(user_id INTEGER, lesson_id INTEGER, PRIMARY KEY(user_id,lesson_id));"
        "CREATE TABLE quiz_results(user_id INTEGER, lesson_id INTEGER, score INTEGER, total INTEGER, PRIMARY KEY(user_id,lesson_id));"
        "CREATE TABLE questions(id INTEGER PRIMARY KEY, user_id INTEGER, lesson_id INTEGER, text TEXT, answer TEXT DEFAULT '', created INTEGER);"
        "CREATE TABLE certificates(id TEXT PRIMARY KEY, user_id INTEGER UNIQUE NOT NULL, name TEXT NOT NULL, issued INTEGER NOT NULL, course TEXT NOT NULL);"
        "INSERT INTO users(email,name,hash,salt,role,plan) VALUES('s@test.ge','მოსწავლე','h','s','student','pro'),('gone@test.ge','წაშლილი','h','s','student','free');"
        "INSERT INTO lessons(id,week,pos,title,summary,task,free,video_url) VALUES(101,1,1,'ძველი 1','ს','ტ',1,'https://example.com/v1'),(102,1,2,'ძველი 2','ს','ტ',1,''),(250,3,2,'ძველი 3','ს','ტ',0,'');"
        "INSERT INTO stages VALUES(1,'ძველი ეტაპი 1',''),(3,'ძველი ეტაპი 3','');"
        "INSERT INTO progress VALUES(1,101),(1,250);INSERT INTO quiz_results VALUES(1,101,4,5);"
        "INSERT INTO questions(user_id,lesson_id,text,answer,created) VALUES(1,101,'კითხვა','პასუხი',1);"
        "INSERT INTO certificates VALUES('CDA-AAAAAAAAAAAA',1,'მოსწავლე',1700000000000,'Cybersecurity: Beginner Path'),('CDA-BBBBBBBBBBBB',-2,'','1700000000001','Cybersecurity: Beginner Path');"
        "PRAGMA user_version=8;")
    d.commit(); d.close()
    env = {**os.environ, 'DB_FILE': old, 'BACKUP_DIR': bk}
    for run_n in (1, 2):   # მეორე გაშვება იდემპოტენტურობას ამოწმებს
        r = subprocess.run([sys.executable, '-c', 'import db; print(db.one("PRAGMA user_version")["user_version"])'], cwd=HERE, env=env, capture_output=True, text=True)
        eq(r.returncode, 0); assert r.stdout.strip().endswith('9'), r.stdout + r.stderr
        d = sqlite3.connect(old)
        eq(d.execute('SELECT id,course,week,pos,video_url FROM lessons WHERE id IN (101,102,250) ORDER BY id').fetchall(),
           [(101, 'cybersecurity-beginners', 1, 1, 'https://example.com/v1'), (102, 'cybersecurity-beginners', 1, 2, ''), (250, 'cybersecurity-beginners', 3, 2, '')])   # id-ები და ადმინის ბმული უცვლელია
        eq(d.execute("SELECT COUNT(*) FROM lessons WHERE course='cybersecurity-beginners'").fetchone()[0], 28)   # content.json-ის 28 გაკვეთილი; არსებული (week,pos) განახლდა და ახალი ხაზი არ შეიქმნა
        eq(sorted(x[0] for x in d.execute('SELECT lesson_id FROM progress')), [101, 250])
        eq(d.execute('SELECT lesson_id,score,total,passed FROM quiz_results').fetchall(), [(101, 4, 5, 1)])
        eq(d.execute('SELECT user_id,lesson_id,answer FROM questions').fetchall(), [(1, 101, 'პასუხი')])
        eq(d.execute('SELECT id,user_id,name,course,course_id FROM certificates ORDER BY id').fetchall(),
           [('CDA-AAAAAAAAAAAA', 1, 'მოსწავლე', 'Cybersecurity: Beginner Path', 'cybersecurity-beginners'), ('CDA-BBBBBBBBBBBB', -2, '', 'Cybersecurity: Beginner Path', 'cybersecurity-beginners')])
        eq([c[1] for c in d.execute('PRAGMA table_info(stages)') if c[5]], ['course', 'id'])   # გასაღები (course,id)
        assert d.execute("SELECT 1 FROM sqlite_master WHERE name='i_lessons_cwp'").fetchone() and not d.execute("SELECT 1 FROM sqlite_master WHERE name='i_lessons_wp'").fetchone()
        eq(d.execute("SELECT COUNT(*) FROM stages WHERE course='cybersecurity-beginners'").fetchone()[0], 8)
        d.close()
    bks = [f for f in os.listdir(bk) if f.startswith('premigrate-v8-')]; eq(len(bks), 1)    # ბექაფი მხოლოდ პირველ გაშვებაზე, სქემის შეცვლამდე
    b = sqlite3.connect(os.path.join(bk, bks[0])); assert 'course' not in [c[1] for c in b.execute('PRAGMA table_info(lessons)')]; b.close()
    for f in (old, old + '-wal', old + '-shm'):
        try: os.remove(f)
        except OSError: pass
    shutil.rmtree(bk, ignore_errors=True)
ok('მიგრაცია v8 → v9: ბექაფი, lesson id-ები, პროგრესი, ქვიზები, კითხვები, სერტიფიკატები და ადმინის ბმულები ინახება; განმეორებით გაშვება უსაფრთხოა', t_migration_v9)


def t_multicourse():
    # ორი კურსი დროებით content-ფაილებზე (CDA_EXTRA_COURSES; პროექტში არ იტვირთება): პროგრესი, უფასო ეტაპი, soon-ის დაფარვა, სერტიფიკატი, ადმინის ფილტრი
    global PORT
    sys.path.insert(0, HERE)
    from auth import hash_pw
    tmp = tempfile.mkdtemp(prefix='cda-mc-')
    def lesson(t, quiz=None):
        return {'title': t, 'task': 'დავალება', 'content': f'# {t}\n\nტექსტი.', 'quiz': quiz or [], 'minutes': 10, 'objectives': ['მიზანი']}
    def cf(name, stages):
        p = os.path.join(tmp, name); json.dump(stages, open(p, 'w', encoding='utf-8'), ensure_ascii=False); return p
    f_open = cf('open.json', [{'stage': 1, 'title': 'ა1', 'lessons': [lesson('A1'), lesson('A2')]}, {'stage': 2, 'title': 'ა2', 'lessons': [lesson('A3')]}])
    f_two = cf('two.json', [{'stage': 1, 'title': 'ბ1', 'lessons': [lesson('B1')]}])
    f_soon = cf('soon.json', [{'stage': 1, 'title': 'ს1', 'lessons': [lesson('S1')]}])
    f_bad = os.path.join(tmp, 'bad.json'); open(f_bad, 'w').write('{ არა json')
    f_empty = cf('empty.json', [])
    extra = [{'id': 't-open', 'title': 'Test Open', 'description': 'ა', 'status': 'available', 'content_file': f_open, 'cert_name': 'Test Open Cert'},
             {'id': 't-two', 'title': 'Test Two', 'description': 'ბ', 'status': 'available', 'content_file': f_two},
             {'id': 't-soon', 'title': 'Test Soon', 'description': 'ს', 'status': 'soon', 'content_file': f_soon},
             {'id': 't-bad', 'title': 'Test Bad', 'description': 'x', 'status': 'available', 'content_file': f_bad},
             {'id': 't-empty', 'title': 'Test Empty', 'description': 'x', 'status': 'available', 'content_file': f_empty},
             {'id': 't-missing', 'title': 'Test Missing', 'description': 'x', 'status': 'available', 'content_file': os.path.join(tmp, 'nope.json')}]
    ex = os.path.join(tmp, 'extra.json'); json.dump(extra, open(ex, 'w', encoding='utf-8'), ensure_ascii=False)
    dbf = os.path.join(tmp, 'mc.db'); env = {**ENV, 'DB_FILE': dbf, 'BACKUP_DIR': os.path.join(tmp, 'bk'), 'PORT': '3919', 'CDA_EXTRA_COURSES': ex}
    subprocess.run([sys.executable, 'make_admin.py', 'adm@mc.ge', PW, 'Adm'], cwd=HERE, env=env, check=True, stdout=subprocess.DEVNULL)
    d = sqlite3.connect(dbf)
    for em, nm, plan in (('pro@mc.ge', 'პრო', 'pro'), ('free@mc.ge', 'უფასო', 'free')):
        d.execute("INSERT INTO users(email,name,hash,salt,role,plan,created,email_verified) VALUES(?,?,?,?,'student',?,?,1)", (em, nm, hash_pw(PW, 'salt1'), 'salt1', plan, int(time.time() * 1000)))
    d.commit(); d.close()
    msrv = subprocess.Popen([sys.executable, 'server.py'], cwd=HERE, env=env, stdout=open(os.path.join(tmp, 'log'), 'w'), stderr=subprocess.STDOUT)
    old_port, PORT = PORT, 3919
    try:
        for _ in range(60):
            try:
                http.client.HTTPConnection('localhost', 3919, timeout=2).request('GET', '/api/config'); break
            except OSError:
                time.sleep(0.2)
        for who, em in (('adm', 'adm@mc.ge'), ('pro', 'pro@mc.ge'), ('fr', 'free@mc.ge')):
            eq(call(who, '/api/login', {'email': em, 'password': PW})['s'], 200)
        ids = lambda who, c: {l['title']: l['id'] for l in call(who, f'/api/lessons?course={c}')['lessons']}
        # კურსების სია
        g = {c['id']: c for c in call('guest', '/api/courses')['courses']}
        eq(g['cybersecurity-beginners']['status'], 'available'); eq((g['cybersecurity-beginners']['stages'], g['cybersecurity-beginners']['lessons']), (8, 28))
        eq((g['t-open']['stages'], g['t-open']['lessons'], g['t-open']['minutes']), (2, 3, 30)); eq(g['t-open']['status'], 'available')
        eq(g['t-soon']['status'], 'soon'); assert 'lessons' not in g['t-soon'] and 'has_content' not in g['t-soon']
        for bad in ('t-bad', 't-empty', 't-missing', 'python-developer'):
            eq(g[bad]['status'], 'soon'); assert 'lessons' not in g[bad]   # შიგთავსის გარეშე: გაშვება არ ინგრევა, მოსწავლეს „მალე“ ჩანს
        a = {c['id']: c for c in call('adm', '/api/courses')['courses']}
        eq((a['t-soon']['status'], a['t-soon']['has_content'], a['t-soon']['open'], a['t-soon']['lessons']), ('soon', True, True, 1))
        eq((a['t-bad']['has_content'], a['python-developer']['has_content']), (False, False))
        # გაკვეთილები და უფასო ეტაპი თითო კურსზე
        eq(call('guest', '/api/lessons')['course'], 'cybersecurity-beginners'); eq(len(call('guest', '/api/lessons')['lessons']), 28)   # ძველი ქცევა
        lo = call('guest', '/api/lessons?course=t-open')['lessons']
        eq([(l['title'], l['free'], l['locked']) for l in lo], [('A1', True, False), ('A2', True, False), ('A3', False, True)])
        eq([(l['free'], l['locked']) for l in call('guest', '/api/lessons?course=t-two')['lessons']], [(True, False)])
        eq(call('guest', f"/api/lesson/{ids('guest', 't-open')['A1']}")['s'], 200)
        eq(call('guest', f"/api/lesson/{ids('guest', 't-open')['A3']}")['s'], 403)
        # soon კურსი მოსწავლეს არ ჩანს; უცნობი → 404; ადმინს ჩანს
        sid = ids('adm', 't-soon')['S1']
        for who in ('guest', 'fr', 'pro'):
            eq(call(who, '/api/lessons?course=t-soon')['s'], 404); eq(call(who, f'/api/lesson/{sid}')['s'], 404)
            eq(call(who, '/api/lessons?course=nope')['s'], 404); eq(call(who, '/api/lessons?course=t-bad')['s'], 404)
        eq(call('adm', '/api/lessons?course=t-soon')['s'], 200); eq(call('adm', f'/api/lesson/{sid}')['s'], 200)
        eq(call('pro', '/api/progress', {'lesson_id': sid, 'done': True})['s'], 403)
        eq(call('pro', '/api/questions', {'text': 'x', 'lesson_id': sid})['s'], 200)   # უხილავ გაკვეთილზე მიბმა იგნორირდება
        assert sqlite3.connect(dbf).execute("SELECT lesson_id FROM questions WHERE text='x'").fetchone()[0] is None
        # პროგრესი კურსის მიხედვით
        o = ids('pro', 't-open'); eq(call('pro', '/api/progress', {'lesson_id': o['A1'], 'done': True})['s'], 200)
        eq(call('pro', '/api/lessons?course=t-open')['done'], [o['A1']]); eq(call('pro', '/api/lessons')['done'], [])
        # სერტიფიკატი კურსის მიხედვით
        eq(call('pro', '/api/certificate/status?course=t-open')['eligible'], False)
        eq(call('pro', '/api/certificate?course=t-open')['s'], 403)
        for t in ('A2', 'A3'):
            eq(call('pro', '/api/progress', {'lesson_id': o[t], 'done': True})['s'], 200)
        st = call('pro', '/api/certificate/status?course=t-open'); eq((st['eligible'], st['capstone'], st['done'], st['total']), (True, 'not_required', 3, 3))
        c1 = call('pro', '/api/certificate?course=t-open'); eq(c1['s'], 200); eq((c1['course'], c1['course_id'], c1['lessons'], c1['stages'], c1['minutes']), ('Test Open Cert', 't-open', 3, 2, 30))
        eq(call('pro', '/api/certificate?course=t-open')['id'], c1['id'])    # განმეორებით იგივე სერტიფიკატი
        eq(call('pro', '/api/certificate/status')['issued'], False)           # Beginners-ის სერტიფიკატი ცალკეა და არ გაცემულა
        eq(call('pro', '/api/certificate')['s'], 403)
        eq(call('pro', '/api/progress', {'lesson_id': ids('pro', 't-two')['B1'], 'done': True})['s'], 200)
        c2 = call('pro', '/api/certificate?course=t-two'); eq((c2['s'], c2['course']), (200, 'Test Two')); assert c2['id'] != c1['id']
        eq(call('x', f"/api/cert/{c1['id']}")['course'], 'Test Open Cert'); eq(call('x', f"/api/cert/{c2['id']}")['course'], 'Test Two')
        eq(call('pro', '/api/certificate?course=t-soon')['s'], 404); eq(call('fr', '/api/certificate?course=t-open')['s'], 403)
        eq(call('adm', '/api/certificate?course=nope')['s'], 404)
        # ადმინის ფილტრები
        s_def = call('adm', '/api/admin/stats'); eq((s_def['course'], s_def['lessons'], len(s_def['stages'])), ('cybersecurity-beginners', 28, 8))   # ნაგულისხმევი = Beginners
        s_o = call('adm', '/api/admin/stats?course=t-open'); eq((s_o['lessons'], [x['lessons'] for x in s_o['stages']], [x['done'] for x in s_o['stages']]), (3, [2, 1], [2, 1]))
        eq(call('adm', '/api/admin/stats?course=nope')['s'], 404)
        u_o = {u['email']: u['done'] for u in call('adm', '/api/admin/users?course=t-open')['users']}; eq((u_o['pro@mc.ge'], u_o['free@mc.ge']), (3, 0))
        u_d = {u['email']: u['done'] for u in call('adm', '/api/admin/users')['users']}; eq(u_d['pro@mc.ge'], 0)   # Beginners-ზე პროგრესი არ აქვს
        eq(call('adm', '/api/admin/users?course=t-open')['lessons'], 3)
        eq([l['title'] for l in call('adm', '/api/admin/lessons?course=t-soon')['lessons']], ['S1']); eq(len(call('adm', '/api/admin/lessons')['lessons']), 28)
        q_all = call('adm', '/api/questions')['questions']; q_o = call('adm', '/api/questions?course=t-open')['questions']
        eq(call('pro', '/api/questions', {'text': 'A1-ზე', 'lesson_id': o['A1']})['s'], 200)
        eq([q['text'] for q in call('adm', '/api/questions?course=t-open')['questions'] if q['lesson_id']], ['A1-ზე'])
        eq([q['text'] for q in call('adm', '/api/questions?course=cybersecurity-beginners')['questions'] if q['lesson_id']], [])
        assert call('adm', '/api/questions?course=nope')['s'] == 404
        # პროექტის რეალური სია ტესტის კურსებს არ შეიცავს
        assert not any(c['id'].startswith('t-') for c in __import__('courses').COURSES) or os.environ.get('CDA_EXTRA_COURSES')
    finally:
        PORT = old_port; msrv.terminate(); msrv.wait()
        shutil.rmtree(tmp, ignore_errors=True)
ok('მრავალი კურსი: უფასო ეტაპი თითო კურსზე, პროგრესი და სერტიფიკატი კურსის მიხედვით, soon კურსი მოსწავლეს 404, ადმინს ჩანს, ადმინის ფილტრები, ცუდი ფაილი გაშვებას არ ანგრევს', t_multicourse)


def t_frontend_views():
    # რეგრესია: app.js-ში ყველა გვერდი, რომელზეც ბმული ან views.<სახელი> მიუთითებს, განსაზღვრულია (არადა #/admin ცარიელი რჩებოდა: views.notfound არ არსებობდა)
    src = open(os.path.join(HERE, 'public', 'js', 'app.js'), encoding='utf-8').read()
    body = src[src.index('const views = {'):]
    defined = set(re.findall(r'(?m)^  ([a-z_]+): ', body[:body.index('\n};\n')]))
    used = set(re.findall(r'views\.([a-z_]+)', src)) | set(re.findall(r'href="#/([a-z]+)', src))
    for must in ('home', 'course', 'lesson', 'pricing', 'auth', 'qa', 'account', 'forgot', 'reset', 'confirm', 'resend', 'verify', 'certificate', 'admin', 'notfound', 'terms', 'privacy'):
        assert must in defined, f'views.{must} აკლია'
    missing = sorted(u for u in used if u not in defined and u not in ('login', 'register', 'lesson'))
    assert not missing, f'გვერდები განსაზღვრული არ არის: {missing}'
ok('ფრონტენდი: ყველა გვერდი (admin, notfound, terms, privacy...) განსაზღვრულია views-ში', t_frontend_views)


def t_frontend_catalog():
    # #/ = კატალოგი, #/cybersecurity = ძველი მთავარი; კურსების სია ერთ ადგილას (COURSES)
    src = open(os.path.join(HERE, 'public', 'js', 'app.js'), encoding='utf-8').read()
    body = src[src.index('const views = {'):]
    defined = set(re.findall(r'(?m)^  ([a-z_]+): ', body[:body.index('\n};\n')]))
    assert 'cybersecurity' in defined and 'home' in defined
    home = body[body.index('  home: () => {'):body.index('  cybersecurity: () => {')]
    old = body[body.index('  cybersecurity: () => {'):body.index('  course: () => {')]
    assert 'ისწავლე ციფრული პროფესია ნულიდან' in home and 'S.courses' in home and 'const COURSES' not in src   # კურსები სერვერიდანაა
    assert 'class="chero"' in home and 'class="cr"' in home and 'previewCard()' in home       # ორსვეტიანი პირველი ეკრანი
    pc = src[src.index('const previewCard'):src.index('const views = {')]                    # უფასო გაკვეთილის გადახედვა (ეტაპების სიის ნაცვლად)
    assert 'უფასო გაკვეთილის გადახედვა' in home and 'l.free' in pc and 'l.locked' in pc and 'l.objectives' in pc and '.slice(0, 3)' in pc
    assert 'img\\/lessons' in pc and 'l.minutes' in pc and '#/lesson/${l.id}' in pc and 'უფასო გაკვეთილის ნახვა' in pc and 'class="stl"' not in src
    assert 'id="pick-go"' in home and 'კურსის არჩევა' in home and 'href="#/pick' not in src and 'scrollIntoView' in src   # გადახვევა JS-ით, ჰეშ-როუტერი არ ირღვევა
    assert 'id="pick"' in home and 'აირჩიე კურსი' in home and 'S.courses.map(pickCard)' in home
    assert home.index('${cont}') < home.index('id="pick"') < home.index('როგორ ისწავლი')         # "აირჩიე კურსი": განაგრძე სწავლა-ს შემდეგ, დანარჩენ ბლოკებზე ზემოთ
    assert 'ხელმისაწვდომი კურსი' not in home and 'class="stl"' not in home and 'მომწერე, რა კურსი გინდა' not in home
    pk = src[src.index('const pickCard'):src.index('const previewCard')]
    assert pk.count('<a class="cc pk') == 1 and '#/soon/' in pk and 'ხელმისაწვდომია' in pk and 'გახსნა' in pk and 'ნახვა' in pk and 'პირველი ეტაპი უფასოა' in pk and 'c.stages' in pk and 'hrs(c.minutes)' in pk and 'crsHref(c)' in pk
    assert 'როგორ ისწავლი' in home and all(x in home for x in ('წაიკითხე გაკვეთილი', 'შეასრულე სავარჯიშო', 'ჩააბარე ქვიზი', 'დასვი კითხვა მენტორს'))
    # ნაწილი B: პროგრესის ბლოკი (შესულისთვის), "რას მიიღებ", "მალე" + საკონტაქტო ხაზი, FAQ (5 კითხვა, details/summary)
    assert 'S.user && nx' in home and 'bar(pct())' in home and '#/lesson/${nx.id}' in home and 'განაგრძე სწავლა' in home
    assert 'რას მიიღებ' in home and home.count("['") >= 4 and 'არა აკრედიტებული დოკუმენტი' in home
    assert 'mailto' in src and 'const mailLink' in src
    faq = home[home.index('const faq = ['):home.index('return `<section class="chero">')]
    assert faq.count("['") == 5 and '<details>' in home and '<summary>' in home and 'quizPauseMinutes' in faq and 'quizMaxFails' in faq and 'quizPassPct' in faq
    assert not re.search(r'\b20 წუთ|\b70%', faq)                                  # რიცხვები კონფიგურაციიდანაა და არა ხელით ჩაწერილი
    cfg = call('x', '/api/config')
    assert cfg.get('quizPassPct') == 70 and isinstance(cfg.get('quizMaxFails'), int) and cfg['quizMaxFails'] >= 1 and isinstance(cfg.get('quizPauseMinutes'), int), cfg
    fo = src[src.index('function foot()'):src.index('const planCard')]
    assert 'class="fb"' in fo and 'class="fl"' in fo and 'S.cfg.contact' in fo and '#/pricing' in fo and '#/terms' in fo and '#/privacy' in fo
    assert 'კიბერუსაფრთხოების სისტემური კურსი დამწყებისთვის' in old and 'განაგრძე სწავლა' in old and 'მთელი კურსი' in old
    assert 'კიბერუსაფრთხოების სისტემური კურსი დამწყებისთვის' not in home
    sys.path.insert(0, HERE); import courses as _co                                            # კურსების სია ერთადერთ ადგილას: courses.py
    ids = [c['id'] for c in _co.COURSES]
    assert ids == ['cybersecurity-beginners', 'cybersecurity-pro', 'python-developer', 'web-developer', 'javascript-developer'], ids
    assert [c['status'] for c in _co.COURSES] == ['available', 'soon', 'soon', 'soon', 'soon']
    assert '#/c/' in src and 'crsHref' in src
    assert '<button' not in pk and '<a class="cc pk' in pk                                     # ყველა ბარათი ნამდვილი <a>
    assert 'href="#/">კურსები</a>' in src                                    # მენიუ: "კურსები" → #/
    idx = open(os.path.join(HERE, 'public', 'index.html'), encoding='utf-8').read()
    assert 'href="#/"' in idx and 'კატალოგ' in idx and 'Cybersecurity for Beginners' in idx
    # გვერდი ხელმისაწვდომია სერვერიდან (SPA) და CSP უცვლელია
    r = call('x', '/')
    eq(r['s'], 200)
ok('ფრონტენდი: კატალოგი (#/) და #/cybersecurity (ძველი მთავარი), COURSES სია, გადახედვა, "აირჩიე კურსი"', t_frontend_catalog)


def t_frontend_soon():
    # #/soon/<id>: მხოლოდ COURSES-ის status=soon id-ებისთვის; უცნობი ან available id → "ვერ მოიძებნა"
    src = open(os.path.join(HERE, 'public', 'js', 'app.js'), encoding='utf-8').read()
    body = src[src.index('const views = {'):]
    defined = set(re.findall(r'(?m)^  ([a-z_]+): ', body[:body.index('\n};\n')]))
    assert 'soon' in defined and 'notfound' in defined
    sys.path.insert(0, HERE); import courses as _co
    assert [c['id'] for c in _co.COURSES if c['status'] == 'soon'] == ['cybersecurity-pro', 'python-developer', 'web-developer', 'javascript-developer']
    assert "S.courses.find(c => c.status === 'soon' && c.id === id)" in src                      # available და უცნობი id არ ამოიცნობა
    sv = body[body.index('  soon: id => {'):body.index('  cybersecurity: () => {')]
    assert 'if (!c) return views.notfound()' in sv                                            # უცნობი id → ვერ მოიძებნა გვერდი
    for x in ('ეს კურსი ჯერ მზადდება და მალე გამოქვეყნდება.', '← ყველა კურსი', 'href="#/"', 'დაიწყე Cybersecurity for Beginners', 'href="#/cybersecurity"', 'კითხვა გაქვს? მომწერე:', 'ct ?'):
        assert x in sv, x
    assert '<form' not in sv and '<input' not in sv                                             # ელფოსტების შეგროვება არ არის
    assert "soon: 'კურსი მალე'" in src and "p === 'soon'" in src and "c.title + ' — მალე'" in src   # document.title
    assert "h.startsWith('#/soon')" in src
ok('ფრონტენდი: #/soon/<id> მხოლოდ soon კურსებისთვის, უცნობი id → "ვერ მოიძებნა"', t_frontend_soon)


def t_frontend_multicourse():
    # ფრონტენდის მრავალკურსიანი სტრუქტურა: #/c/<id>, #/course[/<id>], #/cybersecurity ალიასი, კურსის გადართვა, სერტიფიკატი კურსით, ადმინის არჩევა
    src = open(os.path.join(HERE, 'public', 'js', 'app.js'), encoding='utf-8').read()
    body = src[src.index('const views = {'):]
    defined = set(re.findall(r'(?m)^  ([a-z_]+): ', body[:body.index('\n};\n')]))
    assert {'c', 'course', 'cybersecurity', 'soon', 'lesson', 'certificate'} <= defined
    cv = body[body.index('  c: id => {'):body.index('  cybersecurity: () => {')]
    assert 'views.notfound()' in cv and 'S.defCid' in cv and 'views.cybersecurity()' in cv and 'views.course()' in cv     # Beginners: არსებული გვერდი; სხვა კურსი: ზოგადი
    r0 = src[src.index('async function route0()'):src.index('// ---------- ინტერაქტიული კოდის')]
    assert "p === 'c'" in r0 and "p === 'course'" in r0 and 'courseOfLesson' in r0 and "['', 'cybersecurity', 'account']" in r0 and 'S.defCid' in r0
    assert "lessons?course=' + encodeURIComponent" in src and 'async function switchCourse' in src and "api('courses')" in src
    assert "const courseBase = (cid = S.cid) => cid === S.defCid ? '#/course' : '#/course/'" in src and 'courseBase()' in body   # #/course = Beginners, ძველი მისამართები არ გატყდა
    assert "certificate' + cq" in src and "certificate/status' + cq" in src and 'not_required' in src and 'certHref' in src
    assert 'admin/stats?course=' in src and 'admin/lessons?course=' in src and 'course: S.ac' in src and 'id="acs"' in src and all(t in src for t in ('ხელმისაწვდომია', 'მალე (შიგთავსით, მხოლოდ ადმინისთვის)', 'მალე (შიგთავსი არ არის)', 'tools/new_course.py')) and 'S.courses.filter(c => c.has_content)' not in src   # სია ყოველთვის ჩანს, ყველა კურსით
    assert "'questions' + (course && S.user.role === 'admin'" in src                                                    # შეკითხვები: ფილტრი მხოლოდ ადმინის ჩანართში
ok('ფრონტენდი: მრავალკურსიანი როუტინგი (#/c/<id>, #/course/<id>), კურსის გადართვა, სერტიფიკატი კურსით, ადმინის კურსის არჩევა', t_frontend_multicourse)


def t_new_course_tool():
    # tools/new_course.py: ჩანაწერი courses.py-ში (soon), სწორი სტრუქტურის ფაილი, ვალიდაცია გადის; განმეორებით ან არასწორი id → შეცდომა
    tmp = tempfile.mkdtemp(prefix='cda-nc-'); os.makedirs(os.path.join(tmp, 'tools'))
    for f in ('courses.py', 'validate_content.py', 'content.json'):
        shutil.copy(os.path.join(HERE, f), tmp)
    shutil.copy(os.path.join(HERE, 'tools', 'new_course.py'), os.path.join(tmp, 'tools'))
    run = lambda *a: subprocess.run([sys.executable, os.path.join(tmp, 'tools', 'new_course.py'), *a], cwd=tmp, capture_output=True, text=True)
    r = run('data-analyst', 'Data Analyst', 'მონაცემთა ანალიზი ნულიდან.'); eq(r.returncode, 0); assert 'შეცდომა: 0' in r.stdout, r.stdout
    out = subprocess.run([sys.executable, '-c', 'import courses, json; c = courses.get("data-analyst"); print(json.dumps([c["status"], c["content_file"], c["title"], c["description"], len(courses.COURSES)], ensure_ascii=False))'], cwd=tmp, capture_output=True, text=True)
    eq(json.loads(out.stdout), ['soon', 'content-data-analyst.json', 'Data Analyst', 'მონაცემთა ანალიზი ნულიდან.', 6])
    eq(subprocess.run([sys.executable, 'validate_content.py', 'content-data-analyst.json'], cwd=tmp, capture_output=True, text=True).returncode, 0)   # ჩონჩხი ვალიდურია
    eq(run('data-analyst', 'X', 'Y').returncode, 1); eq(run('Bad Id', 'X', 'Y').returncode, 2)
    shutil.rmtree(tmp, ignore_errors=True)
ok('tools/new_course.py: კურსის ჩანაწერი (soon) + ფაილის ჩონჩხი, ვალიდაცია გადის, დუბლიკატი და არასწორი id იგდება', t_new_course_tool)


# ---------------------------------------------------------------- ინტერაქტიული სავარჯიშოები (იხ. public/sandbox/, STYLE_GUIDE.md)
def t_pw_len():
    eq(call('x', '/api/config')['minPw'], 15)
    S14, S15 = 'Qx7!mN2$pL9&vK', 'Qx7!mN2$pL9&vK4'
    # რეგისტრაცია: ჯერ 14 (მოკლეა, კოდი არ იხარჯება), მერე 15 ჰარებიანი უნიკოდი ფრაზა
    em = 'len15@test.ge'
    eq(call('x', '/api/register', {'name': 'სიგრძე', 'email': em, 'terms': True})['s'], 200); c = mail_code('verify', em)
    r = call('x', '/api/verify', {'email': em, 'code': c, 'password': S14}); eq(r['s'], 400); assert '15' in r['error'], r['error']
    PHRASE = 'სამი სიტყვა აქ ზის'
    eq(call('x', '/api/verify', {'email': em, 'code': c, 'password': PHRASE})['s'], 200)
    eq(call('len', '/api/login', {'email': em, 'password': PHRASE})['s'], 200)
    # შეცვლა: 14 არ ვარგა, 15 ვარგა
    r = call('len', '/api/password', {'old': PHRASE, 'next': S14}); eq(r['s'], 400); assert '15' in r['error'], r['error']
    eq(call('len', '/api/password', {'old': PHRASE, 'next': S15})['s'], 200)
    eq(call('x', '/api/login', {'email': em, 'password': S15})['s'], 200)
    # აღდგენა: 14 არ ვარგა და კოდი არ იხარჯება
    time.sleep(2.2); call('x', '/api/password/forgot', {'email': em}); tk = mail_code('reset', em)
    r = call('x', '/api/password/reset', {'email': em, 'code': tk, 'password': S14}); eq(r['s'], 400); assert '15' in r['error'], r['error']
    eq(call('x', '/api/password/reset', {'email': em, 'code': tk, 'password': 'correct horse battery'})['s'], 200)
    # make_admin.py
    p = subprocess.run([sys.executable, 'make_admin.py', 'short-adm@test.ge', S14, 'X'], cwd=HERE, env=ENV, capture_output=True, text=True, encoding='utf-8')
    assert p.returncode != 0 and '15' in (p.stdout + p.stderr), p.stderr
    subprocess.run([sys.executable, 'make_admin.py', 'short-adm@test.ge', S15, 'X'], cwd=HERE, env=ENV, check=True, stdout=subprocess.DEVNULL)
    eq(call('adm15', '/api/login', {'email': 'short-adm@test.ge', 'password': S15})['s'], 200)
    # არსებული მომხმარებელი მოკლე პაროლით ისევ შედის: სიგრძე შესვლისას არ მოწმდება
    from auth import hash_pw
    d = sqlite3.connect(DB_FILE)
    d.execute("INSERT INTO users(email,name,hash,salt,role,created,email_verified) VALUES('legacy8@test.ge','ძველი',?,?,'user',?,1)", (hash_pw('Old8chars', 'saltX'), 'saltX', int(time.time() * 1000)))
    d.commit(); d.close()
    eq(call('leg', '/api/login', {'email': 'legacy8@test.ge', 'password': 'Old8chars'})['s'], 200)
ok('პაროლის მინიმუმი 15: რეგისტრაცია, შეცვლა, აღდგენა, make_admin; არსებული მოკლე პაროლი ისევ მუშაობს; ჰარებიანი უნიკოდი ფრაზა ვარგა', t_pw_len)


def t_sandbox_headers():
    r, _ = call('x', '/', raw=True)
    csp = r.getheader('Content-Security-Policy')
    assert "script-src 'self';" in csp and "style-src 'self';" in csp and "frame-src 'self' https://www.youtube-nocookie.com" in csp and 'unsafe' not in csp, csp
    eq(r.getheader('X-Frame-Options'), 'DENY'); assert "frame-ancestors 'none'" in csp
    r, b = call('x', '/sandbox/editor.html', raw=True)
    c = r.getheader('Content-Security-Policy')
    eq(r.status, 200); assert "default-src 'none'" in c and "worker-src blob:" in c and "frame-ancestors 'self'" in c and 'sandbox allow-scripts' in c and "'unsafe-eval'" not in c and "'unsafe-inline'" not in c, c
    assert 'localhost:3917/vendor/pyodide/' in c and 'connect-src http://localhost:3917/sandbox/pyworker.js' in c, c   # ქსელი მხოლოდ სამ მისამართზე
    assert r.getheader('X-Frame-Options') is None and r.getheader('Cross-Origin-Resource-Policy') == 'cross-origin'
    r, _ = call('x', '/sandbox/preview.html', raw=True)
    c = r.getheader('Content-Security-Policy')
    assert "default-src 'none'" in c and "connect-src" not in c and 'sandbox allow-scripts' in c and 'allow-same-origin' not in c and r.getheader('X-Frame-Options') is None, c
    for f in ('editor.js', 'editor.css', 'pyworker.js', 'runner.py'):
        r, b = call('x', '/sandbox/' + f, raw=True)
        eq(r.status, 200); eq(r.getheader('Cross-Origin-Resource-Policy'), 'cross-origin'); eq(r.getheader('Access-Control-Allow-Origin'), '*')
    assert call('x', '/sandbox/runner.py', raw=True)[0].getheader('Content-Type').startswith('text/plain')
    r, _ = call('x', '/api/config', raw=True)
    assert r.getheader('Access-Control-Allow-Origin') is None and r.getheader('Cross-Origin-Resource-Policy') == 'same-origin'   # სხვა გზებზე CORS არ გაიხსნა
ok('სანდბოქსი: საკუთარი CSP, sandbox, ჰედერები; მთავარი CSP არ შესუსტებულა (frame-src მხოლოდ \'self\'-ით გაიზარდა)', t_sandbox_headers)


def t_exercises_api():
    lj = call('boss', '/api/lessons')
    lid = next(l['id'] for l in lj['lessons'] if (l['stage'], l['pos']) == (6, 1))
    free = next(l['id'] for l in lj['lessons'] if (l['stage'], l['pos']) == (1, 1))
    d = call('boss', f'/api/lesson/{lid}')
    eq(d['s'], 200)
    course = json.load(open(os.path.join(HERE, 'content.json'), encoding='utf-8'))
    expected = {x['id']: x for x in course[5]['lessons'][0]['exercises']}      # რაოდენობას კი არა, სქემას ვამოწმებთ: API ზუსტად content.json-ის სავარჯიშოებს გასცემს
    assert expected, 'ეტაპი 6, გაკვეთილი 1 სავარჯიშოს გარეშეა'
    eq(sorted(x['id'] for x in d['exercises']), sorted(expected))
    for x in d['exercises']:
        eq(x['type'], 'python'); assert 'solution' not in x and x['starter'] and x['checks'] and x['hint']
        s = call('boss', f'/api/lesson/{lid}/exercise/{x["id"]}/solution')
        eq(s['s'], 200); eq(s['solution'], expected[x['id']]['solution'])
        eq(call('x', f'/api/lesson/{lid}/exercise/{x["id"]}/solution')['s'], 403)      # დაკეტილი გაკვეთილის ამოხსნა სტუმარს არ ეძლევა
    eq(call('boss', f'/api/lesson/{lid}/exercise/nope/solution')['s'], 404)
    eq(call('x', f'/api/lesson/{free}')['exercises'], [])
ok('სავარჯიშოები: /api/lesson გასცემს starter/checks-ს solution-ის გარეშე; ამოხსნა ცალკე და წვდომის შემოწმებით', t_exercises_api)


def t_exercises_validator():
    import copy, importlib
    sys.path.insert(0, HERE)
    vc = importlib.import_module('validate_content')
    course = json.load(open(os.path.join(HERE, 'content.json'), encoding='utf-8'))
    e, _ = vc.validate(course)
    assert not e, e
    for x in course[5]['lessons'][0]['exercises']:      # ყოველ სავარჯიშოზე: solution გადის ყველა შემოწმებას, starter — არა (რაოდენობა არ არის დაფიქსირებული)
        assert all(vc._run_checks(x, x['solution'])) and not all(vc._run_checks(x, x['starter'])), x['id']
    n = sum(len(l.get('exercises', [])) for s in course for l in s['lessons'])
    assert n >= 3, n
    def errs(fn):
        c = copy.deepcopy(course); l = c[5]['lessons'][0]; fn(l['exercises'][0], l, c)
        return vc.validate(c)[0]
    assert any('solution ვერ გადის' in x for x in errs(lambda x, l, c: x.update(solution=x['starter'] + '\nprint("x")')))
    assert any('starter უკვე გადის' in x for x in errs(lambda x, l, c: x.update(starter=x['solution'] + '\n# ერთნაირი შედეგი')))
    assert any('უცნობი ველი' in x for x in errs(lambda x, l, c: x.update(extra=1)))
    assert any('განმეორებული id' in x for x in errs(lambda x, l, c: l['exercises'].append(copy.deepcopy(x))))
    assert any('საჭიროა ზუსტად ერთი' in x for x in errs(lambda x, l, c: x['checks'][0].update(expr='1')))
    assert any('type უნდა' in x for x in errs(lambda x, l, c: x.update(type='ruby')))
    assert any('ხილულ შემოწმებას label' in x for x in errs(lambda x, l, c: x['checks'][0].pop('label')))
    assert any('გაშვება ვერ მოხერხდა' in x for x in errs(lambda x, l, c: x.update(solution='while True: pass')))   # უსასრულო ციკლი ტაიმაუტით ჩერდება
    def html_bad(x, l, c):
        h = c[4]['lessons'][0]['exercises'][0]; h['checks'][0]['selector'] = 'div > p'; h['stdin'] = ['a']
    c = copy.deepcopy(course); html_bad(None, None, c)
    r = vc.validate(c)[0]
    assert any('selector' in x for x in r) and any('stdin' in x for x in r), r
    # html: starter ყველა შემოწმებას არ გადის, solution გადის (მინიმალური DOM)
    h = course[4]['lessons'][0]['exercises'][0]
    assert all(vc._run_checks(h, h['solution'])) and not all(vc._run_checks(h, h['starter']))
ok('validate_content: exercises-ის სქემა, solution/starter რეალურ გაშვებაზე (python runner.py-ით, html მინიმალური DOM-ით)', t_exercises_validator)


def t_runner():
    sys.path.insert(0, os.path.join(HERE, 'public', 'sandbox'))
    import runner
    r = runner.run_exercise('print("a")\nx = int(input())\nprint(x)', ['3'], [{'stdout_equals': 'a\n3'}, {'expr': 'x == 3'}, {'stdin': ['4'], 'stdout_equals': 'a\n4'}, {'stdout_contains': 'zzz'}])
    eq(r['results'], [True, True, True, False]); assert not r['err']
    r = runner.run_exercise('x = 1 / 0', [], [{'expr': 'True'}])
    eq(r['err']['type'], 'ZeroDivisionError'); eq(r['err']['line'], 1); eq(r['results'], [False])
    r = runner.run_exercise('input()', [], [])
    eq(r['err']['type'], 'EOFError')
    r = runner.run_exercise('print("x" * 100000)', [], [])
    assert r['cut'] and len(r['out']) <= runner.LIMIT
    r = runner.run_exercise('import sys\nsys.exit(0)\n', [], [{'stdout_equals': ''}])
    assert not r['err'] and r['results'] == [True]
    r = runner.run_exercise('print("a", file=__import__("sys").stderr)', [], [{'stdout_equals': ''}])
    eq(r['results'], [True])   # stderr stdout-ის შემოწმებაში არ ერევა
ok('runner.py: stdout/stdin/expr შემოწმებები, შეცდომის ხაზი, EOFError, გამოსავლის შეკვეცა', t_runner)


def t_fetch_script():
    p = subprocess.run([sys.executable, os.path.join(HERE, 'tools', 'fetch_pyodide.py'), '--check'], capture_output=True, text=True, encoding='utf-8')
    assert 'Traceback' not in p.stderr and p.returncode in (0, 1), p.stderr
    src = open(os.path.join(HERE, 'tools', 'fetch_pyodide.py'), encoding='utf-8').read()
    assert re.search(r"PYODIDE_VERSION = '\d+\.\d+\.\d+'", src)   # ვერსია დაფიქსირებულია
ok('tools/fetch_pyodide.py: დაფიქსირებული ვერსია, --check ქსელის გარეშე სუფთად მუშაობს', t_fetch_script)


def t_project_db_untouched():
    now = (os.stat(PROJECT_DB).st_mtime_ns, os.stat(PROJECT_DB).st_size) if os.path.exists(PROJECT_DB) else None
    assert now == _pdb0, f'ტესტმა პროექტის cda.db შეცვალა: {_pdb0} -> {now}'
ok('დაცვა: პროექტის საქაღალდის cda.db ტესტის დროს არ შეცვლილა (mtime/ზომა)', t_project_db_untouched)


srv.terminate(); srv.wait()
try: os.remove(LOG)
except OSError: pass
shutil.rmtree(BACKUP_DIR, ignore_errors=True)
for f in (DB_FILE, DB_FILE + '-wal', DB_FILE + '-shm'):
    try: os.remove(f)
    except OSError: pass
sys.exit(1 if failed else 0)
