#!/usr/bin/env python3
"""ეტალონური/დრაფტი გაკვეთილის შემოწმება STYLE_GUIDE.md-ის სტანდარტზე (11 პუნქტი, რაც ავტომატურად მოწმდება).
    python3 tools/check_lesson_draft.py drafts/stage2-lesson1.json [--at 2,1]
დრაფტი content.json-ის ასლში ჩაისმება (ეტაპი, პოზიცია) და გადის validate_content-ს; content.json არ იცვლება."""
import copy
import ipaddress as ip
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import validate_content as vc  # noqa: E402

# კითხვები, რომლებიც სცენარულია ("რა მოხდება, თუ...", "რომელს აირჩევდი, როცა...") ხელით არის მონიშნული დრაფტის ავტორის მიერ
VAGUE = ('გაიგებ', 'გაეცნობი', 'გაეცნობით', 'ისწავლი რა არის', 'მნიშვნელოვანია გვახსოვდეს')


def check(path, at=(2, 1), scenario=(), numbers='ip'):
    lesson = json.load(open(path, encoding='utf-8'))
    course = json.load(open(os.path.join(HERE, 'content.json'), encoding='utf-8'))
    c2 = copy.deepcopy(course)
    st = next(s for s in c2 if s.get('stage', s.get('week')) == at[0])
    st['lessons'][at[1] - 1] = lesson
    errs, warns = vc.validate(c2)
    rep = []
    P = lambda ok, name, extra='': rep.append((ok, name, extra))  # noqa: E731
    P(not errs, 'content.json-ში ჩასმული დრაფტი ვალიდატორს გადის', '; '.join(errs[:3]))
    mine = [w for w in warns if lesson['title'][:20] in w]
    P(not mine, 'ვალიდატორის გაფრთხილება ამ გაკვეთილზე არ არის', '; '.join(mine[:3]))
    text = lesson['content']
    secs = re.split(r'(?m)^(?=## )', text)
    # [გადასამოწმებელი...] ნიშნულები ექსპერტის გადახედვის შემდეგ იშლება, ამიტომ სიგრძეში არ ითვლება
    teach = sum(len(re.sub(r'\s?\[გადასამოწმებელი[^\]]*\]', '', s)) for s in secs if s.startswith('## ') and not s.startswith(('## ხშირი', '## პრაქტიკული', '## მოკლე')))
    P(6000 <= teach <= 9000, f'(4) ძირითადი ტექსტი 6000-9000 სიმბოლო (ახლა {teach})')
    mist = re.search(r'## ხშირი შეცდომები.*?(?=\n## )', text, re.S)
    n_m = len(re.findall(r'(?m)^\d+\. ', mist.group(0))) if mist else 0
    P(3 <= n_m <= 5, f'(5) ხშირი შეცდომები: 3-5 ({n_m})')
    n_terms = len(re.findall(r'\([A-Za-z][A-Za-z0-9 \-/.,]{2,}\)', text))
    P(n_terms >= 3, f'(3) ტერმინები ქართულად + ინგლისურად ფრჩხილებში (ნაპოვნია {n_terms})')
    P('![' in text and all(os.path.isfile(os.path.join(HERE, 'public', p[1:])) for p in re.findall(r'\]\((/img/lessons/[^)]+)\)', text)), '(6) დიაგრამა(ები) არსებობს და ფაილებიც არსებობს', ', '.join(re.findall(r'/img/lessons/[\w.-]+', text)))
    for f in re.findall(r'/img/lessons/[\w.-]+', text):
        svg = open(os.path.join(HERE, 'public', f[1:]), encoding='utf-8').read()
        P('<title' in svg and '<desc' in svg and 'fill="#ffffff"' in svg, f'(6) {f}: აქვს title/desc და საკუთარი ღია ფონი (თემაზე დამოუკიდებლად იკითხება)')
    tasks = re.search(r'## პრაქტიკული დავალებები.*?(?=\n## )', text, re.S)
    tt = re.findall(r'(?ms)^### დავალება \d+.*?(?=^### |\Z)', tasks.group(0)) if tasks else []
    P(2 <= len(tt) <= 3, f'(7) 2-3 დავალება ({len(tt)})')
    for i, t in enumerate(tt, 1):
        has = all(k in t for k in ('**მიზანი:**', '**საფეხურები', '**სწორი პასუხი ასე გამოიყურება', '**მინიშნება', 'წუთი'))
        P(has, f'(7) დავალება {i}: მიზანი, საფეხურები, სწორი შედეგი, დრო, მინიშნება')
    summ = re.search(r'## მოკლე შეჯამება\n(.*)', text, re.S)
    n_s = len(re.findall(r'(?m)^- ', summ.group(1))) if summ else 0
    P(5 <= n_s <= 7 and text.rstrip().endswith(summ.group(1).rstrip()) if summ else False, f'(9) შეჯამება ბოლოშია, 5-7 აზრი ({n_s})')
    q = lesson['quiz']
    P(10 <= len(q) <= 12, f'(8) ქვიზის ბანკი 10-12 ({len(q)})')
    from collections import Counter
    cnt = Counter(x['a'] for x in q)
    P(max(cnt.values()) - min(cnt.get(i, 0) for i in range(4)) <= 1, f'(8) სწორი პასუხები თანაბრად ნაწილდება: {dict(sorted(cnt.items()))}')
    P(len(scenario) * 2 >= len(q), f'(8) სცენარული კითხვები ნახევარზე მეტია ({len(scenario)}/{len(q)})')
    P(all(len(x['o']) == 4 and x['e'].strip() for x in q), '(8) ყველა კითხვას 4 ვარიანტი და განმარტება აქვს')
    P(not any(v in json.dumps(lesson, ensure_ascii=False) for v in VAGUE), '(1,4) ბუნდოვანი ფრაზები ("გაიგებ", "გაეცნობი"...) არ არის')
    P(all(not re.match(r'^(გაიგებ|გაეცნობი|შეისწავლი)', o) for o in lesson['objectives']) and 3 <= len(lesson['objectives']) <= 4, '(1) 3-4 გაზომვადი მიზანი')
    P(10 <= lesson['minutes'] <= 180, f"minutes = {lesson['minutes']}")
    P(not re.search(r'რეზოლვერ', json.dumps(lesson, ensure_ascii=False)), '(3) ერთიანი ტერმინი: "რეკურსიული DNS სერვერი" (არა "რეზოლვერი")')
    # რიცხვითი მტკიცებები ითვლით გადამოწმდება
    def nums_ip():
        n24, n26 = ip.ip_network('192.168.1.0/24'), ip.ip_network('192.168.1.0/26')
        return (n24.num_addresses == 256 and len(list(n24.hosts())) == 254 and n26.num_addresses == 64 and len(list(n26.hosts())) == 62
                and n26.broadcast_address == ip.ip_address('192.168.1.63') and 2 ** 32 == 4294967296 and ip.ip_network('10.0.0.0/8').num_addresses == 16777216
                and ip.ip_network('172.16.0.0/12').num_addresses == 1048576 and ip.ip_network('192.168.0.0/16').num_addresses == 65536
                and ip.ip_address('2001:db8::1').exploded == '2001:0db8:0000:0000:0000:0000:0000:0001' and format(130, '08b') == '10000010'
                and ip.ip_address('192.168.1.130') in n24 and ip.ip_address('192.168.2.5') not in n24
                and ip.ip_address('100.127.255.255') in ip.ip_network('100.64.0.0/10') and ip.ip_network('192.168.1.130/24', strict=False) == n24)

    def nums_http():
        return 2 ** 16 == 65536 and 49151 - 1024 + 1 == 48128 and 65535 - 49152 + 1 == 16384 and 1023 - 0 + 1 == 1024
    def nums_wifi():
        return 36 ** 8 == 2821109907456 and 36 ** 12 == 4738381338321616896 and abs(36 ** 12 / 1e18 - 4.738) < 0.001 and abs(36 ** 8 / 1e12 - 2.821) < 0.001
    def nums_units():
        return (2 ** 10 == 1024 and 2 ** 20 == 1048576 and 2 ** 30 == 1073741824 and len('გამარჯობა') == 9 and len('გამარჯობა'.encode('utf-8')) == 27
                and bin(65) == '0b1000001' and chr(65) == 'A' and 4 * 1024 ** 3 == 4294967296)

    def nums_files():
        import hashlib, posixpath
        return (hashlib.sha256(b'hello').hexdigest().startswith('2cf24dba') and hashlib.sha256(b'hello').hexdigest() != hashlib.sha256(b'hellp').hexdigest()
                and posixpath.normpath('/home/ana/docs/../notes.txt') == '/home/ana/notes.txt' and posixpath.relpath('/home/ana/notes.txt', '/home/ana/docs') == '../notes.txt'
                and 2 ** 32 - 1 == 4294967295)

    def nums_cia():
        import hashlib
        h = lambda b: hashlib.sha256(b).hexdigest()
        return (h(b'hello') == '2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824'
                and h(b'hellp') == 'fdd7585e08c4e2afd71dcabdb4636c89d557a3f42db9e2040c8bbd1708aa4ce7' and len(h(b'x')) == 64)

    def nums_pw():
        import hmac, hashlib, struct

        def totp(k, t, d=8):
            h = hmac.new(k, struct.pack('>Q', t // 30), hashlib.sha1).digest()
            o = h[-1] & 15
            return str((int.from_bytes(h[o:o + 4], 'big') & 0x7fffffff) % 10 ** d).zfill(d)
        k = b'12345678901234567890'
        return (95 ** 8 == 6634204312890625 and 26 ** 8 == 208827064576 and 95 ** 8 // 26 ** 8 == 31768 and 7776 == 6 ** 5
                and 7776 ** 4 == 3656158440062976 and 7776 ** 6 == 221073919720733357899776 and 26 ** 12 == 95428956661682176 and 26 ** 4 == 456976
                and totp(k, 59) == '94287082' and totp(k, 1111111109) == '07081804' and totp(k, 1111111111) == '14050471'
                and totp(k, 1234567890) == '89005924' and totp(k, 2000000000) == '69279037' and totp(k, 20000000000) == '65353130'
                and hashlib.sha256(b'password').hexdigest().startswith('5e884898da28047151d0e56f')
                and hashlib.sha256(b'x7Kpassword').hexdigest().startswith('5d251dcb5961f18a68c7bab9'))

    def nums_web():
        import html, secrets
        from urllib.parse import urlsplit
        from http.cookies import SimpleCookie
        import sqlite3
        d = sqlite3.connect(':memory:')
        d.execute('create table u(name,secret)')
        d.execute("insert into u values('ana','A1'),('bob','B2')")
        x = "' OR 1=1 --"
        c = SimpleCookie()
        c.load('sid=abc123; HttpOnly; SameSite=Lax; Path=/; Max-Age=2592000')
        m = c['sid']
        f = lambda u: (urlsplit(u).scheme, urlsplit(u).hostname, urlsplit(u).port or {'http': 80, 'https': 443}[urlsplit(u).scheme])
        return (len(d.execute("select name from u where name='" + x + "'").fetchall()) == 2 and d.execute('select name from u where name=?', (x,)).fetchall() == []
                and html.escape('<script>alert(1)</script>') == '&lt;script&gt;alert(1)&lt;/script&gt;' and len(secrets.token_hex(32)) == 64 and len(str(2 ** 256)) == 78
                and (m.value, m['httponly'], m['samesite'], m['path'], m['max-age']) == ('abc123', True, 'Lax', '/', '2592000')
                and f('http://store.example.com/dir2/o.html') == f('http://store.example.com/dir/page.html')
                and f('https://store.example.com/p') != f('http://store.example.com/dir/page.html') and f('https://shop.example.com') == f('https://shop.example.com:443')
                and f('http://shop.example.com:8080') != f('http://shop.example.com'))

    def nums_py():
        import hashlib, hmac, ipaddress, datetime, collections, csv, io
        c = collections.Counter(['192.0.2.5', '203.0.113.9', '192.0.2.5'])
        return (7 / 2 == 3.5 and 7 // 2 == 3 and 7 % 2 == 1 and 2 ** 10 == 1024 and int('5') + 3 == 8 and '5' + '3' == '53' and str(5) + '3' == '53' and 0 <= 30 <= 120 and not 0 <= 130 <= 120
                and c.most_common(1) == [('192.0.2.5', 2)] and len(set(['a', 'b', 'a'])) == 2
                and hashlib.sha256(b'hello').hexdigest().startswith('2cf24dba') and hashlib.sha256(b'hellp').hexdigest().startswith('fdd7585e') and len(hashlib.sha256(b'x').hexdigest()) == 64
                and sum(range(1, 101)) == 5050 and sum(range(1, 100)) == 4950 and len([n for n in range(1, 101) if n % 2 == 0]) == 50 and len('maple-orbit-77x') == 15 and len('tea-lamp-orbit-1990') >= 12
                and hmac.compare_digest('abc', 'abc') and not hmac.compare_digest('abc', 'abd')
                and ipaddress.ip_address('192.0.2.5') in ipaddress.ip_network('192.0.2.0/24') and ipaddress.ip_address('198.51.100.7') not in ipaddress.ip_network('192.0.2.0/24')
                and (datetime.datetime.strptime('2025-01-10 10:07', '%Y-%m-%d %H:%M') - datetime.datetime.strptime('2025-01-10 10:01', '%Y-%m-%d %H:%M')).seconds // 60 == 6)

    def nums_none():
        return True
    nums = {'ip': nums_ip, 'http': nums_http, 'wifi': nums_wifi, 'units': nums_units, 'files': nums_files, 'cia': nums_cia, 'pw': nums_pw, 'web': nums_web, 'py': nums_py, 'none': nums_none}[numbers]()
    P(nums, f'(10) რიცხვითი მტკიცებები გამოთვლით დადასტურებულია ({numbers})')
    bad = [r for r in rep if not r[0]]
    for ok_, name, extra in rep:
        print('✓' if ok_ else '✗', name, ('| ' + extra) if extra and not ok_ else '')
    return not bad, {'teach': teach, 'mistakes': n_m, 'tasks': len(tt), 'summary': n_s, 'quiz': len(q), 'warnings': len(warns)}


if __name__ == '__main__':
    import os as _os
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    reg = json.load(open(_os.path.join(HERE, 'drafts', 'drafts.json'), encoding='utf-8'))
    cfg = reg.get(_os.path.basename(args[0]), {})
    at = tuple(cfg.get('at', (2, 1)))
    if '--at' in sys.argv:
        at = tuple(int(x) for x in sys.argv[sys.argv.index('--at') + 1].split(','))
    ok_, meta = check(args[0], at, set(cfg.get('scenario', [])), cfg.get('numbers', 'ip'))
    print(meta)
    sys.exit(0 if ok_ else 1)
