# სავარჯიშოს გამშვები: ერთი და იგივე კოდი მუშაობს მოსწავლის ბრაუზერში (Pyodide, Web Worker) და validate_content.py-ში (ჩვეულებრივი Python).
# სერვერზე ეს ფაილი არასოდეს სრულდება: server.py მას მხოლოდ სტატიკურ ფაილად აბრუნებს.
# შემოწმების სახეობები (checks): stdout_equals | stdout_contains | expr; არასავალდებულო: stdin (ხაზების სია input()-ისთვის), hidden.
import builtins
import json
import sys
import traceback

LIMIT = 20000          # გამოსავლის მაქსიმალური სიგრძე (სიმბოლო): უსასრულო print-ის დროს მეხსიერება არ გაივსოს
FILE = '<კოდი>'


class _State:
    def __init__(self):
        self.disp, self.cap, self.size, self.cut = [], [], 0, False

    def emit(self, text, to_cap):
        text = str(text)
        if self.size >= LIMIT:
            self.cut = True
            return
        text = text[:LIMIT - self.size]
        self.size += len(text)
        self.disp.append(text)
        if to_cap:
            self.cap.append(text)


class _Out:
    def __init__(self, st, to_cap):
        self.st, self.to_cap = st, to_cap

    def write(self, x):
        self.st.emit(x, self.to_cap)
        return len(str(x))

    def flush(self):
        pass

    def isatty(self):
        return False


class _Sink:
    def write(self, x):
        return len(str(x))

    def flush(self):
        pass


def _error(e):
    frames = [f for f in traceback.extract_tb(e.__traceback__) if f.filename == FILE]
    line = frames[-1].lineno if frames else getattr(e, 'lineno', None)
    msg = ''.join(traceback.format_exception_only(type(e), e)).strip()
    return {'type': type(e).__name__, 'msg': msg, 'line': line, 'tb': ''.join(traceback.format_list(frames)).rstrip()}


def _one(code, stdin, exprs):
    """კოდი ერთხელ სრულდება ახალ სახელთა სივრცეში; exprs გამოითვლება იმავე სივრცეში. აბრუნებს (st, err, [bool])."""
    st, lines, err, res = _State(), list(stdin), None, []
    real = (sys.stdout, sys.stderr, builtins.input)

    def fake_input(prompt=''):
        st.emit(prompt, False)
        if not lines:
            raise EOFError('EOF when reading a line')
        s = lines.pop(0)
        st.emit(s + '\n', False)
        return s

    ns = {'__name__': '__main__'}
    sys.stdout, sys.stderr = _Out(st, True), _Out(st, False)
    builtins.input = fake_input
    try:
        try:
            exec(compile(code, FILE, 'exec'), ns)
        except SystemExit:
            pass
        except BaseException as e:  # noqa: BLE001
            err = _error(e)
        sys.stdout = sys.stderr = _Sink()   # expr-ის გამოთვლისას print-ები არავის აჩვენოთ
        for ex in exprs:
            try:
                res.append(err is None and bool(eval(ex, ns)))
            except BaseException:  # noqa: BLE001
                res.append(False)
    finally:
        sys.stdout, sys.stderr, builtins.input = real
    return st, err, res


def _lines(t):
    return '\n'.join(x.rstrip() for x in t.replace('\r\n', '\n').rstrip().split('\n'))


def run_exercise(code, stdin, checks):
    """code: ტექსტი; stdin: ხაზების სია (ხილული გაშვებისთვის); checks: სავარჯიშოს შემოწმებები.
    აბრუნებს {'out': ტექსტი, 'cut': bool, 'err': None|{...}, 'results': [bool]} (results ემთხვევა checks-ის რიგს)."""
    groups = {}   # stdin-ის ვარიანტი → [check-ის ინდექსები]
    for i, c in enumerate(checks):
        groups.setdefault(json.dumps(c.get('stdin', stdin), ensure_ascii=False), []).append(i)
    base_key = json.dumps(stdin, ensure_ascii=False)
    groups.setdefault(base_key, [])
    results = [False] * len(checks)
    shown = None
    for key, idxs in sorted(groups.items(), key=lambda kv: kv[0] != base_key):   # ხილული გაშვება პირველია
        exprs = [checks[i]['expr'] for i in idxs if 'expr' in checks[i]]
        st, err, ex_res = _one(code, json.loads(key), exprs)
        out = ''.join(st.cap)
        it = iter(ex_res)
        for i in idxs:
            c = checks[i]
            if 'expr' in c:
                results[i] = next(it)
            elif 'stdout_equals' in c:
                results[i] = err is None and _lines(out) == _lines(c['stdout_equals'])
            elif 'stdout_contains' in c:
                results[i] = c['stdout_contains'] in out
        if shown is None:
            shown = {'out': ''.join(st.disp), 'cut': st.cut, 'err': err}
    return {**shown, 'results': results}


def run_json(code, stdin_json, checks_json):
    """Pyodide-დან გამოსაძახებელი: ყველაფერი JSON ტექსტია."""
    return json.dumps(run_exercise(code, json.loads(stdin_json), json.loads(checks_json)), ensure_ascii=False)


if __name__ == '__main__' and sys.platform != 'emscripten':   # CLI validate_content.py-სთვის: JSON stdin-ზე {code, stdin, checks}
    d = json.load(sys.stdin)
    print(run_json(d['code'], json.dumps(d.get('stdin', [])), json.dumps(d.get('checks', []))))
