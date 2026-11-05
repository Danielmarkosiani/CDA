# .env ფაილის ჩატვირთვა დამატებითი პაკეტის გარეშე. იმპორტისას ავტომატურად სრულდება (db.py, mailer.py და server.py ამას პირველად იმპორტავენ).
#   - ფაილი: .env პროექტის საქაღალდეში (არა მიმდინარე საქაღალდეში)
#   - რეალური გარემოს ცვლადი ყოველთვის იმარჯვებს: .env არსებულ ცვლადს არ გადაწერს (systemd EnvironmentFile და `export` უცვლელად მუშაობს)
#   - გამორთვა: CDA_NO_DOTENV=1 (ტესტები); სხვა ფაილი: CDA_ENV_FILE=/გზა/.env
#   - ფორმატი: KEY=VALUE; # ხაზები უგულებელყოფილია; მნიშვნელობა შეიძლება იყოს "ბრჭყალებში"; ბოლოში კომენტარი (ინტერვალი + #) მხოლოდ ბრჭყალების გარეშე მნიშვნელობაზე
import os

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.environ.get('CDA_ENV_FILE') or os.path.join(HERE, '.env')   # CDA_ENV_FILE: სხვა გზა (ტესტები)
LOADED = []   # რომელი ცვლადები ჩაიტვირთა .env-იდან (მნიშვნელობის გარეშე: პაროლი არსად იბეჭდება)


def parse(text):
    out = {}
    for raw in text.splitlines():
        ln = raw.strip()
        if not ln or ln.startswith('#') or '=' not in ln:
            continue
        if ln.startswith('export '):
            ln = ln[7:].lstrip()
        k, v = ln.split('=', 1)
        k, v = k.strip(), v.strip()
        if not k or not (k[0].isalpha() or k[0] == '_') or not all(c.isalnum() or c == '_' for c in k):
            continue
        if len(v) >= 2 and v[0] == v[-1] and v[0] in '"\'':
            v = v[1:-1]
        else:
            for i, ch in enumerate(v):          # ბრჭყალების გარეშე: ინტერვალით დაწყებული # კომენტარია
                if ch == '#' and i > 0 and v[i - 1] in ' \t':
                    v = v[:i].rstrip()
                    break
        out[k] = v
    return out


def load(path=PATH, environ=os.environ):
    if environ.get('CDA_NO_DOTENV') == '1':
        return []
    try:
        with open(path, encoding='utf-8-sig') as f:
            data = parse(f.read())
    except OSError:
        return []
    new = []
    for k, v in data.items():
        if k not in environ:
            environ[k] = v
            new.append(k)
    return new


if not LOADED:
    LOADED.extend(load())
