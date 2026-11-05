#!/usr/bin/env python3
"""ამოწმებს გაკვეთილის დრაფტში ჩაწერილ ბრძანებებს და გამოსავალს ამ მანქანაზე გაშვებით.
ყველა "$ ბრძანება" + შემდეგი ხაზები ```-ბლოკში გადაგვყავს და ვადარებთ რეალურ შედეგს.
გაშვება: python3 tools/verify_lesson_outputs.py drafts/stage2-lesson1.json
ბრძანებებს, რომლებიც ქსელს ან კონკრეტულ სისტემას ითხოვენ, ვხდით SKIP-ად და ვწერთ მიზეზს."""
import json
import re
import subprocess
import sys

lesson = json.load(open(sys.argv[1], encoding='utf-8'))
text = lesson['content']
blocks = re.findall(r'```\n(.*?)```', text, re.S)
bad = 0
for b in blocks:
    lines = b.rstrip('\n').split('\n')
    i = 0
    while i < len(lines):
        if lines[i].startswith('$ '):
            cmd = lines[i][2:]
            exp = []
            i += 1
            while i < len(lines) and not lines[i].startswith('$ '):
                exp.append(lines[i]); i += 1
            if not cmd.startswith('python3 ') and sys.platform != 'linux':   # Linux-ის ბრძანებები მხოლოდ Linux-ზე მოწმდება
                print('SKIP', cmd[:80], '(არა Linux)'); continue
            if 'gethostbyname' in cmd:   # ქსელის გარეშე სანდოა მხოლოდ ბოლო ხაზი
                r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                got = r.stderr.strip().split('\n')[-1]
            else:
                r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                got = r.stdout.rstrip('\n')
            want = '\n'.join(exp)
            same = got.split() == want.split()   # ჰორიზონტალური ინტერვალების განსხვავება არ ითვლება
            print(('OK  ' if same else 'FAIL'), cmd[:90], '\n     მოსალოდნელი:', want, '\n     რეალური:    ', got)
            bad += not same
        else:
            i += 1
print('\nგადამოწმებული ბრძანება/გამოსავლის წყვილები გაიარა' if not bad else f'\nშეუსაბამობა: {bad}')
sys.exit(1 if bad else 0)
