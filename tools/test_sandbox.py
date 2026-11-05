#!/usr/bin/env python3
"""სანდბოქსის ბრაუზერული ტესტი: python3 tools/test_sandbox.py   (საჭიროა: pip install playwright && playwright install chromium)
რეალური Pyodide-ის გარეშე: პროექტის დროებით ასლში public/vendor/pyodide/ იცვლება პატარა ჩანაცვლებით (stub), რომელიც ამ ფაილებს ბაძავს:
pyodide.js (loadPyodide), runPython, globals.get('run_json'). ამით მოწმდება ყველაფერი, რაც Pyodide-ზე არ არის დამოკიდებული:
CSP და ჰედერები, sandbox="allow-scripts" (გაუმჭვირვალე წარმოშობა), Blob-Worker-ის შექმნა ასეთი გვერდიდან, importScripts /vendor/-იდან,
5-წამიანი ლიმიტი და Worker-ის გადატვირთვა, postMessage, localStorage-ში შენახვა, Reset, html-ის ნახვა და შემოწმებები, ქსელის დაბლოკვა.
რეალური Python-ის შესრულება აქ არ მოწმდება (იხ. README: Pyodide-ის ხელით შემოწმება)."""
import json, os, shutil, subprocess, sys, tempfile, time, http.client

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print('⚠ playwright არ არის დაყენებული: ბრაუზერული ტესტი გამოტოვებულია'); sys.exit(0)

PORT, PW = 3918, 'Tr0ub4dor&3x-Orbit'
STUB_JS = r"""
async function loadPyodide(o) {
  const g = { run_json: null };
  const api = { runPython(src) { api.src = src; g.run_json = Object.assign((code, stdin, checks) => {
      if (code.indexOf('LOOP') >= 0) { for (;;) {} }
      const n = JSON.parse(checks).length;
      return JSON.stringify({ out: 'stub:' + code + '|fetch:' + typeof self.fetch + '|xhr:' + typeof self.XMLHttpRequest, cut: false, err: null, results: Array(n).fill(true) });
    }, { destroy() {} }); }, globals: { get(k) { return g[k]; } } };
  return api;
}
"""
fails = 0
LOGS = []


def check(name, cond, extra=''):
    global fails
    print(('✓ ' if cond else '✗ ') + name + (f'  {extra}' if (extra and not cond) else ''))
    fails += not cond


def main():
    tmp = tempfile.mkdtemp(prefix='cda-sbx-')
    proj = os.path.join(tmp, 'p')
    shutil.copytree(HERE, proj, ignore=shutil.ignore_patterns('.git', '__pycache__', '*.db', 'drafts', 'backups', '.env'))
    vd = os.path.join(proj, 'public', 'vendor', 'pyodide')
    os.makedirs(vd, exist_ok=True)
    open(os.path.join(vd, 'pyodide.js'), 'w').write(STUB_JS)
    env = {**os.environ, 'PORT': str(PORT), 'DB_FILE': os.path.join(tmp, 't.db'), 'BACKUP_DIR': os.path.join(tmp, 'bk'), 'CDA_NO_DOTENV': '1', 'LOGIN_IP_LIMIT': '1000'}
    env.pop('ADMIN_EMAIL', None)
    subprocess.run([sys.executable, 'make_admin.py', 'boss@test.ge', PW, 'Boss'], cwd=proj, env=env, check=True, stdout=subprocess.DEVNULL)
    srv = subprocess.Popen([sys.executable, 'server.py'], cwd=proj, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(80):
            try:
                c = http.client.HTTPConnection('localhost', PORT, timeout=3); c.request('GET', '/api/config'); c.getresponse().read(); break
            except OSError:
                time.sleep(0.1)
        run(f'http://localhost:{PORT}', env['DB_FILE'])
    finally:
        srv.terminate(); srv.wait(); shutil.rmtree(tmp, ignore_errors=True)


def frame_of(page, part, timeout=8000):
    end = time.time() + timeout / 1000
    while time.time() < end:
        for f in page.frames:
            if part in f.url:
                return f
        page.wait_for_timeout(100)
    print('  frames:', [f.url for f in page.frames]); print('  console:', LOGS[-8:])
    raise AssertionError('iframe not found: ' + part)


def until(frame, expr, timeout=8000):
    """wait_for_function eval()-ს იყენებს და sandbox-ის CSP მას (სწორად) კრძალავს; ამიტომ ვიყენებთ evaluate-ის პოლინგს."""
    end = time.time() + timeout / 1000
    while time.time() < end:
        try:
            if frame.evaluate(expr):
                return
        except Exception:  # noqa: BLE001  (გვერდი ახლა იტვირთება)
            pass
        time.sleep(0.1)
    raise AssertionError('timeout: ' + expr)


def run(base, DBF):
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={'width': 1100, 'height': 900})
        page = ctx.new_page()
        logs = LOGS
        page.on('console', lambda m: logs.append(m.text))
        page.on('response', lambda r: logs.append(f'{r.status} {r.url}') if r.status >= 400 or 'preview' in r.url else None)
        page.goto(base + '/')
        r = page.evaluate("""async (pw) => { const r = await fetch('/api/login', {method:'POST', headers:{'Content-Type':'application/json','X-Requested-With':'cda'}, body: JSON.stringify({email:'boss@test.ge', password: pw})}); return r.status; }""", PW)
        check('ადმინით შესვლა', r == 200)
        page.reload()   # ფრონტენდის მდგომარეობა შესვლის შემდეგ თავიდან იტვირთება
        ids = page.evaluate("""async () => { const d = await (await fetch('/api/lessons')).json(); const f = (s, p) => d.lessons.find(l => l.stage === s && l.pos === p).id; return {py1: f(6, 1), py2: f(6, 2), html: f(5, 1)}; }""")

        # ---- ჰედერები
        hr = ctx.request.get(base + '/')
        csp = hr.headers.get('content-security-policy', '')
        check('მთავარი CSP: script-src/style-src უცვლელია, frame-src მხოლოდ \'self\'-ით გაიზარდა', "script-src 'self';" in csp and "style-src 'self';" in csp and "frame-src 'self' https://www.youtube-nocookie.com" in csp and 'unsafe' not in csp, csp)
        eh = ctx.request.get(base + '/sandbox/editor.html').headers
        check('editor.html: საკუთარი CSP, XFO არ არის, frame-ancestors self', "default-src 'none'" in eh['content-security-policy'] and 'frame-ancestors \'self\'' in eh['content-security-policy'] and 'x-frame-options' not in eh and eh['cross-origin-resource-policy'] == 'cross-origin')
        ph = ctx.request.get(base + '/sandbox/preview.html').headers
        check('preview.html: connect/frame/form აკრძალულია (default-src none), XFO არ არის', "default-src 'none'" in ph['content-security-policy'] and 'connect-src' not in ph['content-security-policy'] and 'sandbox allow-scripts' in ph['content-security-policy'] and 'x-frame-options' not in ph)
        check('მთავარ გვერდზე X-Frame-Options DENY რჩება', hr.headers.get('x-frame-options') == 'DENY')

        # ---- python სავარჯიშო (stub)
        page.goto(f"{base}/#/lesson/{ids['py1']}"); page.reload()
        page.wait_for_selector('.exs .ex [data-open]')
        page.click('.exs .ex [data-open]')
        ef = frame_of(page, '/sandbox/editor.html')
        until(ef, "document.getElementById('status').textContent.indexOf('მზადაა') === 0", 15000)
        check('Python-ის Worker (Blob) გაიშვა გაუმჭვირვალე წარმოშობის iframe-დან და stub-ი ჩაიტვირთა', not ef.is_disabled('#run'))
        check('iframe-ის წარმოშობა გაუმჭვირვალეა (origin "null")', ef.evaluate('window.origin') == 'null')
        check('iframe-ში localStorage მიუწვდომელია', ef.evaluate("(() => { try { localStorage.getItem('x'); return false; } catch (e) { return true; } })()"))
        check('iframe-იდან საიტის API წაუკითხავია (CSP/CORS)', ef.evaluate("fetch('/api/me').then(() => 'open', () => 'blocked')") == 'blocked')
        check('iframe-იდან სხვა მისამართზე fetch დაბლოკილია', ef.evaluate("fetch('https://example.com/').then(() => 'open', () => 'blocked')") == 'blocked')
        ef.click('#run')
        until(ef, "document.getElementById('out').textContent.indexOf('stub:') === 0", 8000)
        outt = ef.inner_text('#out')
        check('Run: შედეგი ჩანს, Worker-ში fetch/XMLHttpRequest გათიშულია', 'fetch:undefined' in outt and 'xhr:undefined' in outt, outt)
        check('შემოწმებების ✓ სია ჩანს', 'ყველა შემოწმება გავიდა' in ef.inner_text('#res') and ef.inner_text('#res').count('✓') == 6)
        check('დამალულ შემოწმებას წარწერა არ აქვს', 'დამალული შემოწმება 1' in ef.inner_text('#res') and '18' not in ef.inner_text('#res'))
        ef.fill('#code', 'while True: pass  # LOOP')
        t0 = time.time(); ef.click('#run')
        until(ef, "document.getElementById('out').textContent.indexOf('5 წამზე') >= 0", 10000)
        dt = time.time() - t0
        check('უსასრულო ციკლი ~5 წამში შეჩერდა და მოსწავლეს ეცნობა', 4.5 < dt < 7.5, f'{dt:.1f}s')
        until(ef, "document.getElementById('status').textContent.indexOf('მზადაა') === 0", 15000)
        ef.fill('#code', 'print(1)'); ef.click('#run')
        until(ef, "document.getElementById('out').textContent.indexOf('stub:print(1)') === 0", 8000)
        check('Worker დროის ლიმიტის შემდეგ ახლიდან ჩაირთო და Run ისევ მუშაობს', True)
        # შენახვა
        ef.fill('#code', 'name = "x"'); page.wait_for_timeout(700)
        saved = page.evaluate(f"localStorage.getItem('cda-ex:{ids['py1']}:vars-conditions')")
        check('ნამუშევარი localStorage-ში მშობელ გვერდზე შეინახა', saved == 'name = "x"', saved)
        page.reload(); page.wait_for_selector('.exs .ex [data-open]'); page.click('.exs .ex [data-open]')
        ef = frame_of(page, '/sandbox/editor.html')
        until(ef, "document.getElementById('code').value.length > 0", 8000)
        check('გვერდის განახლების შემდეგ შენახული კოდი აღდგა', ef.input_value('#code') == 'name = "x"')
        ef.click('#reset'); check('Reset პირველ დაჭერაზე ადასტურებას ითხოვს', 'დარწმუნებული' in ef.inner_text('#reset') and ef.input_value('#code') == 'name = "x"')
        ef.click('#reset'); page.wait_for_timeout(300)
        check('Reset მეორე დაჭერაზე starter-ს აბრუნებს და შენახულს შლის', ef.input_value('#code').startswith('name = input()') and page.evaluate(f"localStorage.getItem('cda-ex:{ids['py1']}:vars-conditions')") is None)
        # Tab / Escape
        ef.fill('#code', 'if x:'); ef.focus('#code'); ef.press('#code', 'End'); ef.press('#code', 'Enter')
        check('Enter ორწერტილის შემდეგ 4 ცარიელს ამატებს', ef.input_value('#code') == 'if x:\n    ')
        ef.press('#code', 'Tab'); check('Tab 4 ცარიელს სვამს', ef.input_value('#code').endswith('        '))
        ef.press('#code', 'Escape'); ef.press('#code', 'Tab')
        check('Escape-ის შემდეგ Tab ფოკუსს ტოვებს textarea-დან', ef.evaluate("document.activeElement.id") != 'code')
        # ამოხსნა
        page.click('.exs .ex [data-sol]'); page.wait_for_selector('.exs .ex .exsol:not([hidden])')
        check('ამოხსნა მხოლოდ ღილაკზე იტვირთება', 'if age < 0:' in page.inner_text('.exs .ex .exsol'))
        lj = json.loads(page.evaluate(f"fetch('/api/lesson/{ids['py1']}').then(r => r.text())"))
        check('/api/lesson-ის პასუხში solution არ არის', all('solution' not in x for x in lj['exercises']) and 'if age < 0:' not in json.dumps(lj, ensure_ascii=False))
        # მუქი თემა გადაეცემა iframe-ს
        page.evaluate("document.documentElement.setAttribute('data-theme','dark')"); page.wait_for_timeout(300)
        check('თემის ცვლილება iframe-ს გადაეცემა', ef.evaluate("document.documentElement.getAttribute('data-theme')") == 'dark')
        # მობილური სიგანე: ერთ სვეტად
        page.set_viewport_size({'width': 380, 'height': 800}); page.wait_for_timeout(400)
        check('ვიწრო ეკრანზე რედაქტორი ერთ სვეტადაა და ჰორიზონტალურად არ სკროლდება', ef.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1"))
        page.set_viewport_size({'width': 1100, 'height': 900})

        # ---- html სავარჯიშო
        page.goto(f"{base}/#/lesson/{ids['html']}"); page.reload()
        page.wait_for_selector('.exs .ex [data-open]'); page.click('.exs .ex [data-open]')
        ef = frame_of(page, '/sandbox/editor.html')
        until(ef, "document.getElementById('status').textContent.indexOf('მზადაა') === 0")
        try:
            pf = frame_of(page, '/sandbox/preview.html')
        except AssertionError:
            print('  frames:', [f.url for f in page.frames]); print('  console:', logs[-6:]); raise
        ef.click('#run'); ef.wait_for_selector('#res:not([hidden])', timeout=8000)
        check('html starter ყველა შემოწმებას არ გადის (1/3)', '1/3' in ef.inner_text('#res'), ef.inner_text('#res'))
        sol = '<h1>x</h1><p>y</p><a href="https://example.com">z</a>'
        ef.fill('#code', sol); ef.click('#run')
        until(ef, "document.getElementById('res').textContent.indexOf('ყველა შემოწმება გავიდა') >= 0", 8000)
        check('html solution ყველა შემოწმებას გადის', True)
        probe = ('<h1>x</h1><script>document.body.setAttribute("data-ran","1");'
                 'try{parent.document.title;document.body.setAttribute("data-parent","reachable")}catch(e){document.body.setAttribute("data-parent","isolated")}'
                 'fetch("/api/me").then(function(){document.body.setAttribute("data-net","open")},function(){document.body.setAttribute("data-net","blocked")});</script>')
        ef.fill('#code', probe); page.wait_for_timeout(1800)
        pf = frame_of(page, '/sandbox/preview.html')
        until(pf, "document.body && document.body.getAttribute('data-net')", 8000)
        check('მოსწავლის ინლაინ სკრიპტი preview-ში სრულდება', pf.evaluate("document.body.getAttribute('data-ran')") == '1')
        check('preview მშობელს ვერ წვდება (გაუმჭვირვალე წარმოშობა)', pf.evaluate("document.body.getAttribute('data-parent')") == 'isolated')
        check('preview-დან ქსელი დაბლოკილია (CSP connect-src ← default-src none)', pf.evaluate("document.body.getAttribute('data-net')") == 'blocked')
        check('preview-ის origin "null"', pf.evaluate('window.origin') == 'null')

        # ---- ვიდეოს განლაგება გაკვეთილის გვერდზე (ღია/მუქი თემა; 375, 768 და 1920 სიგანე)
        import sqlite3
        db = sqlite3.connect(DBF)
        db.execute("UPDATE lessons SET video_url='https://youtu.be/ABCDEFGHIJK', video_title='სატესტო ვიდეო', video_channel='სატესტო არხი', video2_url='https://example.com/backup', video2_title='სათადარიგო' WHERE id=?", (ids['py1'],))
        db.commit(); db.close()
        page.goto(f"{base}/#/lesson/{ids['py1']}"); page.reload(); page.wait_for_selector('.player iframe')
        for theme in ('light', 'dark'):
            page.evaluate("t => document.documentElement.setAttribute('data-theme', t)", theme)
            for w in (375, 768, 1920):
                page.set_viewport_size({'width': w, 'height': 900}); page.wait_for_timeout(250)
                m = page.evaluate("""() => { const r = e => { const b = document.querySelector(e).getBoundingClientRect(); return {x: b.x, w: b.width, h: b.height}; };
                    const p = r('.player'), pr = r('.prose'), cap = [...document.querySelectorAll('.vcap')].map(e => e.getBoundingClientRect());
                    return {p, pr, caps: cap.map(c => ({x: c.x, w: c.width, top: c.top})), ptop: document.querySelector('.player').getBoundingClientRect().bottom,
                            sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth}; }""")
                tag = f'{theme} {w}px'
                check(f'ვიდეო ≤ 720px და ეკრანს არ სცდება ({tag})', m['p']['w'] <= 720.5 and m['p']['x'] + m['p']['w'] <= w + 0.5, str(m['p']))
                check(f'ვიდეო 16:9 ({tag})', abs(m['p']['w'] / m['p']['h'] - 16 / 9) < 0.02, str(m['p']))
                check(f'ვიდეო და წარწერები ტექსტის სვეტთან გასწორებულია და ეკრანს არ სცდება ({tag})', abs(m['p']['x'] - m['pr']['x']) < 1.5 and all(abs(c['x'] - m['pr']['x']) < 1.5 and c['x'] + c['w'] <= w + 0.5 for c in m['caps']), f"{m['p']} {m['pr']} {m['caps']}")
                if w >= 768:
                    check(f'ფართო ეკრანზე ვიდეო ზუსტად 720 სიგანისაა ({tag})', w < 1000 or abs(m['p']['w'] - 720) < 1, str(m['p']))
                check(f'სათაური/არხი და სათადარიგო ბმული ვიდეოს ქვეშაა ({tag})', len(m['caps']) == 2 and all(c['top'] >= m['ptop'] - 1 and c['w'] <= 721 for c in m['caps']), str(m['caps']))
        page.set_viewport_size({'width': 1100, 'height': 900})
        b.close()
    print('\nკონსოლის ტექსტები (CSP-ის დაბლოკვები მოსალოდნელია):', len(logs))
    return 0


if __name__ == '__main__':
    main()
    sys.exit(1 if fails else 0)
