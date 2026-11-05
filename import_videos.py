#!/usr/bin/env python3
"""videos.csv -> ბაზა (lessons.video_url / video_title / video_channel / video2_*).

    python3 import_videos.py            # საცდელი გაშვება: მხოლოდ გიჩვენებს, რას ჩაწერს. ბაზას არ ცვლის
    python3 import_videos.py --apply    # ჩაწერს (ჯერ ბაზის ბექაფს აკეთებს BACKUP_DIR-ში)
    python3 import_videos.py --csv ფაილი.csv --db გზა/cda.db --overwrite

წესები:
- იმპორტდება მხოლოდ რიგები, სადაც status (ძირითადი) ან backup_status (სათადარიგო) = «გადამოწმებული».
- ბმული გადის იგივე ვალიდაციას, რასაც ადმინის API (auth.valid_url): მხოლოდ https://, ინტერვალების გარეშე, მაქს. 500 სიმბოლო.
- გაკვეთილი ეძებება (ეტაპი, პოზიცია)-ით და არა id-ით: ეს სანდოა ძველ ბაზებზეც.
- ადმინის პანელში ხელით ჩასმულ ბმულს არ გადაწერს (თუ არ მიუთითე --overwrite).
- სქემა უნდა იყოს განახლებული (სერვერი ერთხელ უნდა გაშვებულიყო), თორემ სკრიპტი გაჩერდება და ბაზას არ შეეხება."""
import argparse
import csv
import os
import sqlite3
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from auth import valid_url  # noqa: E402  (გვერდითი ეფექტების გარეშე მოდული)

OK = 'გადამოწმებული'
NEED = ('video_title', 'video_channel', 'video2_url', 'video2_title', 'video2_channel')


def plan(rows, con, overwrite):
    """აბრუნებს (ჩასაწერი ცვლილებები, გამოტოვებული მიზეზებით)."""
    cols = {r[1] for r in con.execute('PRAGMA table_info(lessons)')}
    missing = [c for c in NEED if c not in cols]
    if missing:
        sys.exit('ბაზას ახალი სვეტები აკლია: ' + ', '.join(missing) + '\nგაუშვი სერვერი ერთხელ (ან: python3 -c "import db"), სქემა თავისით განახლდება და ბექაფიც შეიქმნება. მერე გაიმეორე.')
    changes, skipped = [], []
    for r in rows:
        try:
            stage, pos = int(r['stage']), int(r['pos'])
        except (ValueError, KeyError):
            skipped.append((r.get('lesson_title', '?'), 'stage/pos არასწორია')); continue
        les = con.execute('SELECT id,video_url,video2_url FROM lessons WHERE course=? AND week=? AND pos=?', ('cybersecurity-beginners', stage, pos)).fetchone()
        tag = f'{stage}.{pos} {r["lesson_title"]}'
        if not les:
            skipped.append((tag, 'ასეთი გაკვეთილი ბაზაში არ არის')); continue
        upd = {}
        for kind, url_k, title_k, chan_k, st_k, db_url, db_cols in (
                ('ძირითადი', 'primary_url', 'primary_title', 'channel', 'status', les[1], ('video_url', 'video_title', 'video_channel')),
                ('სათადარიგო', 'backup_url', 'backup_title', 'backup_channel', 'backup_status', les[2], ('video2_url', 'video2_title', 'video2_channel'))):
            url = (r.get(url_k) or '').strip()
            if r.get(st_k) != OK or not url:
                continue
            if not valid_url(url, allow_empty=False):
                skipped.append((tag, f'{kind}: ბმული არასწორია (მხოლოდ https://): {url[:60]}')); continue
            if db_url and not overwrite and db_url != url:
                skipped.append((tag, f'{kind}: ბაზაში უკვე სხვა ბმულია (ადმინის ჩასმული?), გამოტოვებულია; გადასაწერად --overwrite')); continue
            title, chan = (r.get(title_k) or '').strip()[:200], (r.get(chan_k) or '').strip()[:200]
            upd.update({db_cols[0]: url, db_cols[1]: title, db_cols[2]: chan})
        if upd:
            changes.append((les[0], tag, upd))
    return changes, skipped


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--csv', default=os.path.join(HERE, 'videos.csv'))
    ap.add_argument('--db', default=os.environ.get('DB_FILE') or os.path.join(HERE, 'cda.db'))
    ap.add_argument('--apply', action='store_true', help='ბაზაში ჩაწერა (ნაგულისხმევად მხოლოდ საცდელი გაშვებაა)')
    ap.add_argument('--overwrite', action='store_true', help='არსებული ბმულის გადაწერა')
    a = ap.parse_args(argv)
    if not os.path.isfile(a.db):
        sys.exit(f'ბაზა ვერ ვიპოვე: {a.db}')
    with open(a.csv, encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f))
    try:
        con = sqlite3.connect(f'file:{os.path.abspath(a.db)}?mode=ro', uri=True) if not a.apply else sqlite3.connect(a.db, timeout=10)
        con.execute('SELECT 1 FROM lessons LIMIT 1')
    except sqlite3.Error:
        con = sqlite3.connect(a.db, timeout=10)
    changes, skipped = plan(rows, con, a.overwrite)
    print(('ჩაიწერება' if a.apply else 'საცდელი გაშვება: ჩაიწერებოდა') + f' {len(changes)} გაკვეთილზე:')
    for lid, tag, upd in changes:
        print(f'  + {tag}: ' + ', '.join(k for k in upd if k.endswith('url')))
    for tag, why in skipped:
        print(f'  - გამოტოვებულია {tag}: {why}')
    if not a.apply:
        print('\nბაზა არ შეცვლილა. ჩასაწერად დაამატე --apply')
        return 0
    if not changes:
        print('ჩასაწერი არაფერია.'); return 0
    bdir = os.environ.get('BACKUP_DIR') or os.path.join(os.path.dirname(os.path.abspath(a.db)), 'backups')
    os.makedirs(bdir, exist_ok=True)
    bpath = os.path.join(bdir, time.strftime('videos-import-%Y%m%d-%H%M%S.db'))
    dst = sqlite3.connect(bpath)
    con.backup(dst); dst.close()
    os.chmod(bpath, 0o600)
    print('ბექაფი:', bpath)
    with con:
        for lid, tag, upd in changes:
            con.execute(f'UPDATE lessons SET {",".join(k + "=?" for k in upd)} WHERE id=?', (*upd.values(), lid))
    print('მზადაა.')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
