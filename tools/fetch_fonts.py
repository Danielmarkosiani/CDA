#!/usr/bin/env python3
"""ჩამოტვირთავს თვითგანთავსებულ შრიფტებს public/fonts/-ში (მხოლოდ სტანდარტული ბიბლიოთეკა). გაუშვი ინტერნეტიან მანქანაზე:
    python3 tools/fetch_fonts.py
ფაილებს ამოწმებს (woff2 სიგნატურა 'wOF2', მინიმალური ზომა). წარუმატებლობისას კოდი 1-ია და ბოლოს ჩამოწერს, რა აკლია.
წყარო: Fontsource (jsDelivr). შრიფტები ორივე SIL Open Font License 1.1-ითაა: ლიცენზიის ტექსტებიც უნდა ინახებოდეს public/fonts/-ში."""
import os
import sys
import urllib.request

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'public', 'fonts')
V = '5.3.0'
FILES = {
    'inter-latin-wght-normal.woff2': [f'https://cdn.jsdelivr.net/fontsource/fonts/inter:vf@{V}/latin-wght-normal.woff2'],
    'noto-sans-georgian-georgian-wght-normal.woff2': [
        f'https://cdn.jsdelivr.net/fontsource/fonts/noto-sans-georgian:vf@{V}/georgian-wght-normal.woff2',
        'https://cdn.jsdelivr.net/fontsource/fonts/noto-sans-georgian:vf@latest/georgian-wght-normal.woff2'],
}
LICENSES = {  # ლიცენზიები საუკეთესო მცდელობით; თუ ვერ ჩამოტვირთა, ხელით ჩაწერე (იხ. public/fonts/README.txt)
    'OFL-Inter.txt': ['https://cdn.jsdelivr.net/npm/@fontsource-variable/inter/LICENSE'],
    'OFL-NotoSansGeorgian.txt': ['https://cdn.jsdelivr.net/npm/@fontsource-variable/noto-sans-georgian/LICENSE'],
}


def get(urls):
    last = None
    for u in urls:
        try:
            with urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'cda-fetch-fonts'}), timeout=30) as r:
                return u, r.read()
        except Exception as e:  # noqa: BLE001
            last = f'{u}: {e}'
    raise RuntimeError(last)


os.makedirs(OUT, exist_ok=True)
missing = []
for name, urls in FILES.items():
    try:
        u, data = get(urls)
        if data[:4] != b'wOF2' or len(data) < 5000:
            raise RuntimeError(f'{u}: არ ჰგავს woff2 ფაილს ({len(data)} ბაიტი)')
        open(os.path.join(OUT, name), 'wb').write(data)
        print('OK ', name, len(data), 'ბაიტი  <-', u)
    except Exception as e:  # noqa: BLE001
        missing.append(name); print('ERR', name, e)
for name, urls in LICENSES.items():
    try:
        u, data = get(urls)
        if b'Open Font License' not in data:
            raise RuntimeError('ლიცენზიის ტექსტი არ არის')
        open(os.path.join(OUT, name), 'wb').write(data); print('OK ', name)
    except Exception as e:  # noqa: BLE001
        print('WARN ლიცენზია ვერ ჩამოვიტვირთე:', name, e)
if missing:
    print('\nვერ ჩამოიტვირთა:', ', '.join(missing), '\nჩამოტვირთე ხელით: https://fontsource.org/fonts/inter და https://fontsource.org/fonts/noto-sans-georgian (Download)')
    sys.exit(1)
