#!/usr/bin/env python3
"""კურსების შიგთავსის ვალიდატორი.   python3 validate_content.py [--strict] [ფაილი]
ფაილის გარეშე ამოწმებს courses.py-ში აღწერილ ყველა კურსის content_file-ს (content.json და სხვა); ფაილით — მხოლოდ მას.
შეცდომა (ERROR): ფაილი ვერ ჩაიტვირთება სწორად (გატეხილი სტრუქტურა, ქვიზის ინდექსი, ცარიელი ველი, არასწორი ბმული/სურათი).
გაფრთხილება (WARN): ხარისხის ნიშნები (ქვიზის ბანკი 10-ზე ნაკლებია, პასუხები ერთ ვარიანტზეა გადახრილი...). --strict-ზე გაფრთხილებაც შეცდომაა.
გასვლის კოდი 1-ია შეცდომის (ან --strict-ზე გაფრთხილების) შემთხვევაში."""
import json
import os
import re
import subprocess
import sys
import tempfile
from html.parser import HTMLParser

HERE = os.path.dirname(os.path.abspath(__file__))
IMG_DIR = os.path.join(HERE, 'public', 'img', 'lessons')
LINK = re.compile(r'(?<!!)\[([^\]]*)\]\(([^)\s]*)\)')
IMAGE = re.compile(r'!\[([^\]]*)\]\(([^)\s]*)\)')
IMG_OK = re.compile(r'/img/lessons/([A-Za-z0-9_][\w.-]*\.(?:svg|png|jpe?g|webp))')
BARE_URL = re.compile(r'(?<![\](])\bhttp://\S+')
LESSON_KEYS = ('title', 'minutes', 'objectives', 'content', 'task', 'bonus', 'quiz')
RUNNER = os.path.join(HERE, 'public', 'sandbox', 'runner.py')   # იგივე ძრავა, რომელიც ბრაუზერში Pyodide-ზე მუშაობს
EX_KEYS = {'id', 'type', 'title', 'instructions', 'starter', 'checks', 'hint', 'solution', 'stdin'}
EX_TEXT = ('title', 'instructions', 'starter', 'hint', 'solution')
EX_ID = re.compile(r'[a-z0-9][a-z0-9-]{0,39}')
PY_CHECK_KEYS = {'label', 'hidden', 'stdin', 'stdout_equals', 'stdout_contains', 'expr'}
HTML_CHECK_KEYS = {'label', 'hidden', 'selector', 'min', 'text_contains', 'attr', 'attr_startswith'}
SELECTOR = re.compile(r'([a-z][a-z0-9]*)(?:\[([a-z-]+)(?:\^=\"([^\"]*)\")?\])?')   # მხოლოდ ეს ფორმებია, რომ validate-მა HTML-ზეც გადაამოწმოს: tag, tag[attr], tag[attr^="x"]
RUN_TIMEOUT = 10


def _strip_code(text):
    """კოდის ბლოკები და `ინლაინ კოდი` ბმულების შემოწმებას არ ექვემდებარება (მაგ. http://127.0.0.1:8000 ადგილობრივი სერვერის მაგალითია)."""
    text = re.sub(r'```.*?```', '', text, flags=re.S)
    return re.sub(r'`[^`\n]*`', '', text)


def _text_checks(where, field, text, err, warn):
    if text.count('```') % 2:
        err(f'{where}: {field}: ``` ბლოკი დაუხურავია')
    text = _strip_code(text)
    for alt, src in IMAGE.findall(text):
        m = IMG_OK.fullmatch(src)
        if not m:
            err(f'{where}: {field}: სურათი უნდა იყოს /img/lessons/<ფაილი>.svg|png|jpg|webp, ნაპოვნია: {src!r}')
        elif not os.path.isfile(os.path.join(IMG_DIR, m.group(1))):
            err(f'{where}: {field}: სურათის ფაილი არ არსებობს: public/img/lessons/{m.group(1)}')
        if not alt.strip():
            warn(f'{where}: {field}: სურათს წარწერა (alt) არ აქვს: {src}')
    for txt, url in LINK.findall(text):
        if not url.startswith('https://'):
            err(f'{where}: {field}: ბმული უნდა იწყებოდეს https://-ით: {url!r}')
        elif not txt.strip():
            err(f'{where}: {field}: ბმულს ტექსტი არ აქვს: {url}')
    for u in BARE_URL.findall(text):
        err(f'{where}: {field}: http:// ბმული დაუშვებელია: {u}')
    if re.search(r'<\s*/?\s*(script|iframe|img|a|style)\b', text, re.I):
        warn(f'{where}: {field}: ტექსტში HTML ტეგია; ის ესკეიპირდება და ტექსტად გამოჩნდება')
    fence = False
    for i, ln in enumerate(text.split('\n'), 1):
        if ln.startswith('```'):
            fence = not fence
        if not fence and (re.match(r'#{1}\s', ln) or re.match(r'#{4,}\s', ln)):
            warn(f'{where}: {field}: ხაზი {i}: მხარდაჭერილია მხოლოდ ## და ### სათაურები')


class _Dom(HTMLParser):
    """მინიმალური DOM: ელემენტი = [tag, attrs, ტექსტი]; ტექსტი ჩაითვლება ყველა წინაპარ ელემენტშიც (როგორც textContent)."""
    def __init__(self):
        super().__init__(); self.els, self.stack = [], []

    def handle_starttag(self, tag, attrs):
        e = [tag, dict(attrs), '']; self.els.append(e)
        if tag not in ('br', 'img', 'hr', 'meta', 'link', 'input'):
            self.stack.append(e)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]; break

    def handle_data(self, data):
        for e in self.stack:
            e[2] += data


def _html_check(dom, c):
    m = SELECTOR.fullmatch(c['selector'])
    tag, at, pre = m.groups()
    els = [e for e in dom.els if e[0] == tag and (at is None or at in e[1]) and (pre is None or (e[1].get(at) or '').startswith(pre))]
    ok = len(els) >= c.get('min', 1)
    if ok and c.get('text_contains'):
        ok = any(c['text_contains'] in e[2] for e in els)
    if ok and c.get('attr'):
        ok = any(e[1].get(c['attr']) is not None and ((e[1][c['attr']] or '').startswith(c['attr_startswith']) if c.get('attr_startswith') else (e[1][c['attr']] or '').strip() != '') for e in els)
    return ok


def _run_checks(x, code):
    """აბრუნებს [bool] თითო check-ზე. python: runner.py ცალკე პროცესში (დროის ლიმიტით); html: მინიმალური DOM."""
    if x['type'] == 'html':
        dom = _Dom(); dom.feed(code); dom.close()
        return [_html_check(dom, c) for c in x['checks']]
    with tempfile.TemporaryDirectory(prefix='cda-ex-') as td:   # სავარჯიშო ფაილსაც ქმნის: დროებით საქაღალდეში გავუშვათ, რეპოში ნაგავი არ დარჩეს
        p = subprocess.run([sys.executable, RUNNER], input=json.dumps({'code': code, 'stdin': x.get('stdin', []), 'checks': x['checks']}),
                           capture_output=True, text=True, encoding='utf-8', timeout=RUN_TIMEOUT, cwd=td)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip()[-300:])
    return json.loads(p.stdout)['results']


def _exercise_checks(w, l, err, warn, run=True):
    exs = l.get('exercises')
    if exs is None:
        return
    if not isinstance(exs, list) or not exs:
        err(f'{w}: exercises უნდა იყოს არაცარიელი სია (ან საერთოდ არ იყოს)'); return
    seen = set()
    for n, x in enumerate(exs, 1):
        xw = f'{w}, სავარჯიშო {n}'
        if not isinstance(x, dict):
            err(f'{xw}: ობიექტი უნდა იყოს'); continue
        for k in sorted(set(x) - EX_KEYS):
            err(f'{xw}: უცნობი ველი {k!r}')
        for k in EX_TEXT:
            if not isinstance(x.get(k), str) or not x[k].strip():
                err(f'{xw}: ცარიელი ან აკლია {k}')
        if not isinstance(x.get('id'), str) or not EX_ID.fullmatch(x['id']):
            err(f'{xw}: id უნდა შეესაბამებოდეს [a-z0-9-]{{1,40}}-ს')
        elif x['id'] in seen:
            err(f'{xw}: განმეორებული id {x["id"]!r}')
        else:
            seen.add(x['id'])
        typ = x.get('type')
        if typ not in ('python', 'html'):
            err(f'{xw}: type უნდა იყოს python ან html'); continue
        for k in ('starter', 'solution'):
            if isinstance(x.get(k), str) and len(x[k]) > 6000:
                err(f'{xw}: {k} 6000 სიმბოლოზე გრძელია')
        if isinstance(x.get('title'), str) and len(x['title']) > 120:
            err(f'{xw}: title 120 სიმბოლოზე გრძელია')
        if isinstance(x.get('starter'), str) and x.get('starter') == x.get('solution'):
            err(f'{xw}: starter და solution ერთნაირია')
        for k in ('instructions', 'hint'):
            if isinstance(x.get(k), str):
                _text_checks(xw, k, x[k], err, warn)
        st = x.get('stdin')
        if st is not None and (typ != 'python' or not isinstance(st, list) or not all(isinstance(i, str) for i in st)):
            err(f'{xw}: stdin მხოლოდ python-ზეა და უნდა იყოს ტექსტების სია')
        cs = x.get('checks')
        if not isinstance(cs, list) or not 1 <= len(cs) <= 12:
            err(f'{xw}: checks უნდა იყოს 1-12 ელემენტის სია'); continue
        bad = False
        for ci, c in enumerate(cs, 1):
            cw = f'{xw}, შემოწმება {ci}'
            if not isinstance(c, dict):
                err(f'{cw}: ობიექტი უნდა იყოს'); bad = True; continue
            allowed = PY_CHECK_KEYS if typ == 'python' else HTML_CHECK_KEYS
            for k in sorted(set(c) - allowed):
                err(f'{cw}: ველი {k!r} {typ}-ის შემოწმებაში დაუშვებელია'); bad = True
            if c.get('hidden') is not None and not isinstance(c['hidden'], bool):
                err(f'{cw}: hidden უნდა იყოს true/false'); bad = True
            if not c.get('hidden') and (not isinstance(c.get('label'), str) or not c['label'].strip()):
                err(f'{cw}: ხილულ შემოწმებას label სჭირდება'); bad = True
            if typ == 'python':
                kinds = [k for k in ('stdout_equals', 'stdout_contains', 'expr') if k in c]
                if len(kinds) != 1 or not isinstance(c[kinds[0]], str) or not c[kinds[0]].strip():
                    err(f'{cw}: საჭიროა ზუსტად ერთი არაცარიელი: stdout_equals | stdout_contains | expr'); bad = True
                if 'stdin' in c and (not isinstance(c['stdin'], list) or not all(isinstance(i, str) for i in c['stdin'])):
                    err(f'{cw}: stdin უნდა იყოს ტექსტების სია'); bad = True
            else:
                if not isinstance(c.get('selector'), str) or not SELECTOR.fullmatch(c['selector']):
                    err(f'{cw}: selector უნდა იყოს tag, tag[attr] ან tag[attr^="x"] (რომ ვალიდატორმაც გადაამოწმოს)'); bad = True
                if 'min' in c and (not isinstance(c['min'], int) or isinstance(c['min'], bool) or not 1 <= c['min'] <= 20):
                    err(f'{cw}: min უნდა იყოს 1-20'); bad = True
                if 'attr_startswith' in c and 'attr' not in c:
                    err(f'{cw}: attr_startswith-ს attr სჭირდება'); bad = True
                for k in ('text_contains', 'attr', 'attr_startswith'):
                    if k in c and (not isinstance(c[k], str) or not c[k]):
                        err(f'{cw}: {k} უნდა იყოს არაცარიელი ტექსტი'); bad = True
        if bad or not run or not isinstance(x.get('starter'), str) or not isinstance(x.get('solution'), str):
            continue
        try:   # ნამდვილი გაშვება: solution ყველა შემოწმებას გადის, starter კი ყველას არ გადის
            sol, sta = _run_checks(x, x['solution']), _run_checks(x, x['starter'])
        except (RuntimeError, subprocess.TimeoutExpired, ValueError, OSError) as e:
            err(f'{xw}: კოდის გაშვება ვერ მოხერხდა ({type(e).__name__}: {e})'); continue
        for ci, ok in enumerate(sol, 1):
            if not ok:
                err(f'{xw}: solution ვერ გადის შემოწმებას {ci}')
        if all(sta):
            err(f'{xw}: starter უკვე გადის ყველა შემოწმებას (სავარჯიშო უკვე ამოხსნილია)')


def validate(course, strict_bank=10):
    errors, warnings = [], []
    err, warn = errors.append, warnings.append
    if not isinstance(course, list) or not course:
        return ['content.json უნდა იყოს არაცარიელი სია'], []
    seen_stages = []
    for si, s in enumerate(course):
        if not isinstance(s, dict):
            err(f'ეტაპი #{si + 1}: ობიექტი უნდა იყოს'); continue
        n = s.get('stage', s.get('week'))
        where = f'ეტაპი {n}'
        if not isinstance(n, int) or isinstance(n, bool) or n < 1:
            err(f'ეტაპი #{si + 1}: stage უნდა იყოს დადებითი მთელი რიცხვი'); continue
        if n in seen_stages:
            err(f'{where}: განმეორებული ეტაპის ნომერი')
        seen_stages.append(n)
        if not str(s.get('title', '')).strip():
            err(f'{where}: ცარიელი title')
        lessons = s.get('lessons')
        if not isinstance(lessons, list) or not lessons:
            err(f'{where}: lessons უნდა იყოს არაცარიელი სია'); continue
        titles = set()
        for li, l in enumerate(lessons, 1):
            w = f'{where}, გაკვეთილი {li}'
            if not isinstance(l, dict):
                err(f'{w}: ობიექტი უნდა იყოს'); continue
            for k in LESSON_KEYS:
                if k not in l:
                    err(f'{w}: აკლია ველი {k!r}')
            title = str(l.get('title', '')).strip()
            if not title:
                err(f'{w}: ცარიელი title')
            elif title in titles:
                err(f'{w}: განმეორებული სათაური: {title}')
            titles.add(title)
            w = f'{w} ({title[:40]})'
            m = l.get('minutes')
            if not isinstance(m, int) or isinstance(m, bool) or not 1 <= m <= 600:
                err(f'{w}: minutes უნდა იყოს მთელი რიცხვი 1-600')
            obj = l.get('objectives')
            if not isinstance(obj, list) or not obj or not all(isinstance(x, str) and x.strip() for x in obj):
                err(f'{w}: objectives უნდა იყოს არაცარიელი ტექსტების სია')
            elif not 3 <= len(obj) <= 4:
                warn(f'{w}: მიზნების რაოდენობაა {len(obj)} (რეკომენდაცია: 3-4)')
            for k in ('content', 'task'):
                if not isinstance(l.get(k), str) or not l[k].strip():
                    err(f'{w}: ცარიელი {k}')
            if not isinstance(l.get('bonus', ''), str):
                err(f'{w}: bonus ტექსტი უნდა იყოს')
            for k in ('content', 'task', 'bonus'):
                if isinstance(l.get(k), str):
                    _text_checks(w, k, l[k], err, warn)
            _exercise_checks(w, l, err, warn)
            quiz = l.get('quiz')
            if not isinstance(quiz, list) or not quiz:
                err(f'{w}: quiz უნდა იყოს არაცარიელი სია'); continue
            if len(quiz) < strict_bank:
                warn(f'{w}: ქვიზის ბანკში {len(quiz)} კითხვაა (რეკომენდაცია: 10-12)')
            qs, correct = set(), []
            for qi, q in enumerate(quiz, 1):
                qw = f'{w}, კითხვა {qi}'
                if not isinstance(q, dict):
                    err(f'{qw}: ობიექტი უნდა იყოს'); continue
                if not isinstance(q.get('q'), str) or not q['q'].strip():
                    err(f'{qw}: ცარიელი კითხვა (q)')
                elif q['q'] in qs:
                    err(f'{qw}: განმეორებული კითხვა')
                qs.add(q.get('q'))
                o = q.get('o')
                if not isinstance(o, list) or not 2 <= len(o) <= 6 or not all(isinstance(x, str) and x.strip() for x in o):
                    err(f'{qw}: o უნდა იყოს 2-6 არაცარიელი ვარიანტი'); continue
                if len(set(x.strip() for x in o)) != len(o):
                    err(f'{qw}: განმეორებული პასუხის ვარიანტები')
                a = q.get('a')
                if not isinstance(a, int) or isinstance(a, bool) or not 0 <= a < len(o):
                    err(f'{qw}: a უნდა იყოს ინდექსი 0..{len(o) - 1}, ნაპოვნია {a!r}')
                else:
                    correct.append(a)
                if not isinstance(q.get('e'), str) or not q['e'].strip():
                    err(f'{qw}: ცარიელი განმარტება (e)')
                for fld in ('q', 'e'):
                    if isinstance(q.get(fld), str):
                        _text_checks(qw, fld, q[fld], err, warn)
            if len(correct) >= 10:
                top = max(correct.count(i) for i in set(correct))
                if top / len(correct) > 0.4:
                    warn(f'{w}: სწორი პასუხები არათანაბრადაა გადანაწილებული ({top}/{len(correct)} ერთსა და იმავე ვარიანტზე)')
    if sorted(seen_stages) != list(range(1, len(seen_stages) + 1)):
        err(f'ეტაპის ნომრები უნდა იყოს 1..{len(seen_stages)} უჭრელად, ნაპოვნია {sorted(seen_stages)}')
    return errors, warnings


def _check_file(path, label=''):
    """აბრუნებს (გაკვეთილების რაოდენობა, შეცდომები, გაფრთხილებები) ერთი ფაილისთვის; ფაილის ჩატვირთვის შეცდომა = ერთი ERROR."""
    try:
        with open(path, encoding='utf-8') as f:
            course = json.load(f)
    except (OSError, ValueError) as e:
        return 0, [f'ფაილი ვერ ჩაიტვირთა: {e}'], []
    errors, warnings = validate(course)
    n = sum(len(s.get('lessons', [])) for s in course if isinstance(s, dict)) if isinstance(course, list) else 0
    return n, errors, warnings


def main(argv):
    strict = '--strict' in argv
    paths = [a for a in argv if not a.startswith('--')]
    if paths:   # კონკრეტული ფაილი (ძველი ქცევა)
        targets = [('', paths[0], 'available')]
    else:       # courses.py-ის ყველა კურსის content_file
        sys.path.insert(0, HERE)
        import courses
        targets = []
        for c in courses.COURSES:
            p = courses.content_path(c)
            if not p:
                print(f"INFO  კურსი {c['id']}: content_file არ აქვს (შიგთავსის გარეშე, status={c['status']})"); continue
            targets.append((c['id'], p, c['status']))
    tot_n = tot_e = tot_w = 0
    for cid, path, status in targets:
        pre = f'[{cid}] ' if cid else ''
        if cid and not os.path.exists(path):   # ფაილი არ არსებობს: კურსი შიგთავსის გარეშეა; available სტატუსზე ეს შეცდომაა (მოსწავლეს „მალე“ ეჩვენება)
            print(('ERROR ' if status == 'available' else 'INFO  ') + f'{pre}ფაილი არ არსებობს: {path}')
            tot_e += status == 'available'; continue
        n, errors, warnings = _check_file(path)
        for e in errors:
            print('ERROR', pre + e)
        for w in warnings:
            print('WARN ', pre + w)
        if cid:
            print(f'{pre}გაკვეთილი: {n}, შეცდომა: {len(errors)}, გაფრთხილება: {len(warnings)}')
        tot_n += n; tot_e += len(errors); tot_w += len(warnings)
    print(f'გაკვეთილი: {tot_n}, შეცდომა: {tot_e}, გაფრთხილება: {tot_w}')
    return 1 if tot_e or (strict and tot_w) else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
