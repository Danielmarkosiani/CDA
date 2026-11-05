#!/usr/bin/env python3
"""Pyodide-ის თვითგანთავსება: python3 tools/fetch_pyodide.py [--version X.Y.Z] [--check]
ჩამოტვირთავს დაფიქსირებული ვერსიის ფაილებს public/vendor/pyodide/-ში (jsDelivr-ის npm სარკიდან), ამოწმებს SHA-256-ს jsDelivr-ის
გამოქვეყნებულ ჰეშებთან და წერს SHA256SUMS.txt-სა და NOTICE.txt-ს (ვერსია, წყარო, ლიცენზიები). ქსელი ამ ბრძანებას სჭირდება ერთხელ;
მერე საიტი ყველაფერს საკუთარი სერვერიდან აძლევს და გარე CDN-ს არ იყენებს. --check ქსელის გარეშე ამოწმებს უკვე ჩამოტვირთულ ფაილებს.
შენიშვნა: ეს სკრიპტი ისეთ გარემოში დაიწერა, სადაც ქსელი არ იყო, ამიტომ პირველად გაუშვი ხელით და ნახე გამოტანა."""
import argparse
import base64
import hashlib
import json
import os
import sys
import urllib.request

PYODIDE_VERSION = '0.27.7'   # ვერსია დაფიქსირებულია; შესაცვლელად --version ან ეს მუდმივა (და შემდეგ გაუშვი სკრიპტი ხელახლა)
HERE = os.path.dirname(os.path.abspath(__file__))
DEST = os.path.join(HERE, '..', 'public', 'vendor', 'pyodide')
FILES = ['pyodide.js', 'pyodide.asm.js', 'pyodide.asm.wasm', 'python_stdlib.zip', 'pyodide-lock.json']   # loadPyodide() მხოლოდ ამ ხუთს ითხოვს (პაკეტების გარეშე)
LICENSE_URL = 'https://raw.githubusercontent.com/pyodide/pyodide/{v}/LICENSE'


def get(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'cda-fetch-pyodide'})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def sha256_hex(b):
    return hashlib.sha256(b).hexdigest()


def check(dest):
    sums = os.path.join(dest, 'SHA256SUMS.txt')
    if not os.path.isfile(sums):
        print('SHA256SUMS.txt არ არის: Pyodide ჩამოტვირთული არ არის (გაუშვი ეს სკრიპტი --check-ის გარეშე).'); return 1
    bad = 0
    for ln in open(sums, encoding='utf-8'):
        h, name = ln.split()
        p = os.path.join(dest, name)
        ok = os.path.isfile(p) and sha256_hex(open(p, 'rb').read()) == h
        print(('✓ ' if ok else '✗ ') + name); bad += not ok
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--version', default=PYODIDE_VERSION)
    ap.add_argument('--check', action='store_true', help='ქსელის გარეშე გადაამოწმე უკვე ჩამოტვირთული ფაილები')
    a = ap.parse_args()
    dest = os.path.realpath(DEST)
    if a.check:
        return check(dest)
    v = a.version
    base = f'https://cdn.jsdelivr.net/npm/pyodide@{v}/'
    print(f'Pyodide {v}: ჰეშების სია jsDelivr-იდან…')
    listing = json.loads(get(f'https://data.jsdelivr.com/v1/packages/npm/pyodide@{v}?structure=flat'))
    want = {f['name'].lstrip('/'): f['hash'] for f in listing.get('files', [])}   # hash = SHA-256, base64
    os.makedirs(dest, exist_ok=True)
    lines = []
    for name in FILES:
        if name not in want:
            print(f'შეცდომა: {name} ვერსია {v}-ის npm პაკეტში ვერ მოიძებნა (ფაილების სია შეიცვალა?)'); return 1
        print(f'  ჩამოტვირთვა: {name}')
        data = get(base + name)
        if base64.b64encode(hashlib.sha256(data).digest()).decode() != want[name]:
            print(f'შეცდომა: {name}-ის SHA-256 არ ემთხვევა jsDelivr-ის ჰეშს; ფაილი არ ინახება'); return 1
        open(os.path.join(dest, name), 'wb').write(data)
        lines.append(f'{sha256_hex(data)}  {name}')
    open(os.path.join(dest, 'SHA256SUMS.txt'), 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
    lic = ''
    try:
        lic = get(LICENSE_URL.format(v=v)).decode('utf-8')
        open(os.path.join(dest, 'LICENSE-pyodide.txt'), 'w', encoding='utf-8').write(lic)
    except Exception as e:  # noqa: BLE001
        print(f'გაფრთხილება: ლიცენზიის ფაილი ვერ ჩამოიტვირთა ({e}); ჩამოტვირთე ხელით: ' + LICENSE_URL.format(v=v))
    open(os.path.join(dest, 'NOTICE.txt'), 'w', encoding='utf-8').write(
        f'Pyodide {v} (https://pyodide.org), ჩამოტვირთულია {base}-დან და გამოიყენება უცვლელად.\n'
        'Pyodide ვრცელდება Mozilla Public License 2.0-ით (იხ. LICENSE-pyodide.txt); მასში შემავალი CPython და სხვა კომპონენტები საკუთარი ლიცენზიებით.\n'
        'SHA-256 ჰეშები: SHA256SUMS.txt. განახლება: python3 tools/fetch_pyodide.py --version X.Y.Z\n')
    print('მზადაა. შემოწმება: python3 tools/fetch_pyodide.py --check'); return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except OSError as e:   # URLError, ტაიმაუტი, ფაილის ჩაწერის შეცდომა
        print(f'შეცდომა: {e}\nქსელი ხელმისაწვდომი უნდა იყოს (cdn.jsdelivr.net, data.jsdelivr.com, raw.githubusercontent.com) და public/vendor/pyodide/ ჩასაწერი.'); sys.exit(1)
