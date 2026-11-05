# პაროლები და ტოკენები: გვერდითი ეფექტების გარეშე (არ ხსნის ბაზას, არ იწყებს ნაკადებს),
# რომ make_admin.py-მ და ტესტებმა უსაფრთხოდ შეძლონ იმპორტი.
import hashlib
import hmac
import re

import os

HERE = os.path.dirname(os.path.abspath(__file__))


def _load_common():
    s = set()
    try:
        with open(os.path.join(HERE, 'common_passwords.txt'), encoding='utf-8') as f:
            for ln in f:
                ln = ln.strip().lower()
                if ln and not ln.startswith('#'):
                    s.add(ln)
    except OSError:
        pass
    return s


COMMON_PW = _load_common()
_LEETS = [str.maketrans({'@': 'a', '4': 'a', '0': 'o', '1': one, '3': 'e', '$': 's', '5': 's', '7': 't', '!': one}) for one in ('l', 'i')]


def _in_common(t):
    return t in COMMON_PW or any(t.translate(m) in COMMON_PW for m in _LEETS)
_ROWS = ['qwertyuiop', 'asdfghjkl', 'zxcvbnm', '1234567890', 'abcdefghijklmnopqrstuvwxyz']


def _has_run(s, n=5):
    """ეძებს n+ ზედიზედ სიმბოლოს: კლავიატურის რიგი, ანბანი ან ციფრები, პირდაპირ ან უკუღმა,
    ასევე ორი ერთმანეთში გადახლართული მიმდევრობა (a1b2c3d4)."""
    def runs(t):
        for row in _ROWS:
            for r in (row, row[::-1]):
                for k in range(len(r) - n + 1):
                    if r[k:k + n] in t:
                        return True
        return False
    if runs(s):
        return True
    return len(s) >= 2 * n - 1 and (runs(s[0::2]) or runs(s[1::2])) and (runs(s[0::2]) and runs(s[1::2]))


_EDGE = re.compile(r'^[^a-z\u10d0-\u10ff]+|[^a-z\u10d0-\u10ff]+$')


def hash_pw(pw, salt):
    # Node-ის crypto.scryptSync(pw, salt, 64)-თან თავსებადია (salt გამოიყენება როგორც ტექსტი)
    return hashlib.scrypt(pw.encode(), salt=salt.encode(), n=16384, r=8, p=1, dklen=64, maxmem=64 * 1024 * 1024).hex()


def th(token):
    return hashlib.sha256(token.encode()).hexdigest()


def same(a, b):
    return hmac.compare_digest(a.encode(), b.encode())


def weak_reason(p):
    """None თუ პაროლი ზოგადად კარგია; სხვა შემთხვევაში მიზეზის კოდი (ტესტებისთვის და ლოგისთვის)."""
    low = p.lower()
    if _in_common(low):
        return 'common'
    if len(set(low)) < 4:
        return 'few_chars'
    if re.fullmatch(r'(.{1,4}?)\1+.{0,3}', low):
        return 'repeat'            # abababab, 12341234
    if _has_run(low, 5) and len(re.sub(r'[a-z0-9]', '', low)) == 0:
        return 'sequence'          # 12345678, qwertyui, a1b2c3d4, abcdefgh1
    core = _EDGE.sub('', low)                      # სიტყვა ციფრებისა და სიმბოლოების გარეშე დასაწყისსა და ბოლოში
    if core and len(low) - len(core) <= 6 and len(core) <= 12 and _in_common(core):
        return 'word_plus_digits'                  # Summer2024!, Password1!, Qwerty!234, paroli123
    return None


# ახალი პაროლის მინიმალური სიგრძე (სიმბოლო, არა ბაიტი: უნიკოდი და ჰარები დაშვებულია). სიმბოლოების ტიპების მოთხოვნა არ არსებობს; ზედა ზღვარი 200 ტექსტის ბოროტად გამოყენებისგან იცავს.
# წესი ეყრდნობა NIST SP 800-63B-4-ს (იხ. SOURCES.md). არსებულ მომხმარებლებს ეს არ ეხება: ლოგინზე სიგრძე არ მოწმდება.
MIN_PW_LEN = 15


def strong_pw(p, email='', name=''):
    if not (isinstance(p, str) and MIN_PW_LEN <= len(p) <= 200) or weak_reason(p):
        return False
    low, local = p.lower(), (email or '').split('@')[0].lower()
    if low == (email or '').lower() or (len(local) >= 4 and local in low):
        return False  # პაროლი არ უნდა შეიცავდეს ელფოსტის სახელს
    return not (len(name or '') >= 4 and low == name.strip().lower())


def client_ip(remote, xff, proxies):
    """კლიენტის IP. proxies = სანდო საპროქსო სერვერების რაოდენობა აპლიკაციის წინ.
    ყოველი სანდო პროქსი X-Forwarded-For-ს ბოლოში უმატებს მისთვის პირდაპირ დაკავშირებულ მისამართს,
    ამიტომ ნამდვილი კლიენტი ბოლოდან proxies-ურ ელემენტშია. მარცხენა ელემენტებს კლიენტი თვითონ წერს და არ უნდა ვენდოთ.
    თუ სათაური მოსალოდნელზე მოკლეა (პროქსის გვერდის ავლა ან არასწორი რაოდენობა), ვიყენებთ პირდაპირ მისამართს."""
    if proxies <= 0:
        return remote or '?'
    parts = [p.strip() for p in (xff or '').split(',') if p.strip()]
    if len(parts) >= proxies:
        return parts[-proxies][:64]
    return remote or '?'


def valid_url(s, allow_empty=True):
    """მასალის ბმულის ვალიდაცია (ადმინის API და import_videos.py ერთსა და იმავეს იყენებს):
    მხოლოდ https://, მაქს. 500 სიმბოლო, ინტერვალისა და მართვის სიმბოლოების გარეშე, ჰოსტი სავალდებულოა."""
    if not isinstance(s, str) or len(s) > 500:
        return False
    s = s.strip()
    if s == '':
        return allow_empty
    from urllib.parse import urlsplit
    if not s.startswith('https://') or re.search(r'[\s\x00-\x1f\x7f"\'<>\\]', s):
        return False
    try:
        return bool(urlsplit(s).hostname)
    except ValueError:
        return False
