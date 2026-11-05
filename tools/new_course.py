#!/usr/bin/env python3
"""ახალი კურსის შექმნა: ჩანაწერი courses.py-ში (status='soon') + შიგთავსის ფაილის ჩონჩხი სწორი სტრუქტურით.

    python3 tools/new_course.py <id> "<სათაური>" "<აღწერა>" [--file content-<id>.json]

შემდეგი ნაბიჯები (იხ. README, "Adding a new course"):
  1. შეავსე შიგთავსის ფაილი (იგივე ფორმატი, რაც content.json-ს) და გაუშვი: python3 validate_content.py
  2. გაუშვი სერვერი და ადმინით გადახედე: კურსი ჩანს ადმინის კურსების სიაში მარკერით „მალე (მხოლოდ ადმინისთვის)“
  3. მზად რომ იქნება, courses.py-ში შეცვალე status: 'soon' → 'available'
"""
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ID_RE = re.compile(r'[a-z0-9]+(?:-[a-z0-9]+)*')


def skeleton(title):
    return [{'stage': 1, 'title': 'პირველი ეტაპი (შეცვალე)', 'description': '', 'lessons': [{
        'title': 'პირველი გაკვეთილი (შეცვალე)', 'minutes': 10,
        'objectives': ['მიზანი 1 (შეცვალე)', 'მიზანი 2 (შეცვალე)', 'მიზანი 3 (შეცვალე)'],
        'content': f'## {title}\n\nგაკვეთილის ტექსტი (შეცვალე).',
        'task': 'პრაქტიკული დავალება (შეცვალე).', 'bonus': '',
        'quiz': [{'q': 'საკონტროლო კითხვა (შეცვალე)?', 'o': ['სწორი პასუხი', 'არასწორი პასუხი'], 'a': 0, 'e': 'განმარტება (შეცვალე).'}]}]}]


def main(argv):
    args = [a for a in argv if not a.startswith('--')]
    fname = None
    if '--file' in argv:
        i = argv.index('--file')
        fname = argv[i + 1] if i + 1 < len(argv) else None
        args = [a for a in args if a != fname]
    if len(args) != 3 or not ID_RE.fullmatch(args[0]):
        print(__doc__); print('შეცდომა: id უნდა იყოს მცირე ლათინური ასოები/ციფრები და ტირეები (მაგ. python-developer).'); return 2
    cid, title, desc = args
    fname = fname or f'content-{cid}.json'
    cpath = os.path.join(HERE, 'courses.py')
    src = open(cpath, encoding='utf-8').read()
    if re.search(r"'id':\s*'" + re.escape(cid) + r"'", src):
        print(f'შეცდომა: კურსი {cid} უკვე არსებობს courses.py-ში.'); return 1
    fpath = os.path.join(HERE, fname)
    if os.path.exists(fpath):
        print(f'შეცდომა: ფაილი {fname} უკვე არსებობს.'); return 1
    a = src.index('COURSES = [')
    end = src.index('\n]\n', a)   # COURSES სიის დახურვა
    entry = f"\n    {{'id': {cid!r}, 'title': {title!r}, 'status': 'soon', 'content_file': {fname!r},\n     'description': {desc!r}}},"
    with open(fpath, 'w', encoding='utf-8') as f:
        json.dump(skeleton(title), f, ensure_ascii=False, indent=2); f.write('\n')
    open(cpath, 'w', encoding='utf-8').write(src[:end] + entry + src[end:])
    print(f'✓ courses.py: დაემატა {cid} (status=soon); ✓ შიგთავსის ფაილი: {fname}')
    r = subprocess.run([sys.executable, os.path.join(HERE, 'validate_content.py'), fpath], capture_output=True, text=True)
    print(r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr.strip())
    print('შემდეგი: შეავსე ფაილი → python3 validate_content.py → ადმინით გადახედვა → courses.py-ში status=\'available\'.')
    return 0 if r.returncode == 0 else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
