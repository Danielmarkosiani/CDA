#!/usr/bin/env python3
"""videos.csv და videos.md აგება. მონაცემები ქვემოთაა: ყოველი ბმული, რომელიც 'გადამოწმებული'-ა, სიტყვასიტყვით ნანახია
საძიებო შედეგებში ან გახსნილ გვერდზე (წყარო სვეტ 'evidence'-ში). YouTube ID არსად არის გამოცნობილი ან შედგენილი."""
import csv
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import json
course = json.load(open(os.path.join(HERE, 'content.json'), encoding='utf-8'))
LESSONS = []
n = 0
for s in course:
    st = s.get('stage', s.get('week'))
    for j, l in enumerate(s['lessons'], 1):
        n += 1; LESSONS.append((n, st, j, l['title']))

NF = 'ვერ ვიპოვე'
OK = 'გადამოწმებული'
CC = 'Crash Course'
PL = '&list=PL8dPuuaLjXtNlUrzyH5r6jN9ulIgZBpdo'
V = {  # (stage,pos) -> dict
 (1, 1): dict(
   primary_url='https://www.youtube.com/embed/FZGugFqdr60', primary_title='The Central Processing Unit (CPU): Crash Course Computer Science #7', channel=CC, language='ინგლისური', duration='11:38 (videohighlight-ის სია; PBS-ის გვერდზე 11:15)', status=OK,
   why='პროცესორის მუშაობა (fetch-decode-execute) ნაბიჯ-ნაბიჯ და ანიმაციით, დამწყებისთვის გასაგები, არამარკეტინგული.',
   backup_url='https://www.youtube.com/watch?v=fpnE6UAfbtU' + PL + '&index=7', backup_title='Registers and RAM: Crash Course Computer Science #6', backup_channel=CC, backup_duration='12:17', backup_status=OK,
   evidence='ძირითადი: ბმული embed სახით სიტყვასიტყვით ჩანს გახსნილ გვერდზე videohighlight.com/v/FZGugFqdr60 (სათაური, აღწერა, ეპიზოდი #7). სათადარიგო: ბმული სიტყვასიტყვით ჩანს UC Denver-ის PDF-ში (clas.ucdenver.edu, Crash Course annotations); სათაური/ხანგრძლივობა videohighlight-ის playlist-იდან (იგივე ID).',
   notes='ვიდეო 2017 წლისაა, მაგრამ თემა (CPU-ს აგებულება) არ ძველდება.', phrases=''),
 (1, 2): dict(
   primary_url='https://www.youtube.com/watch?v=26QPDBe-NB8', primary_title='Operating Systems: Crash Course Computer Science #18', channel=CC, language='ინგლისური', duration='13:36', status=OK,
   why='ოპერაციული სისტემის როლი, მეხსიერების დაცვა, Unix/Linux-ისა და Windows-ის ფესვები: სწორად ქმნის საფუძველს ეტაპი 3-ისთვის.',
   backup_url='', backup_title='', backup_channel='', backup_duration='', backup_status=NF,
   evidence='ბმული სიტყვასიტყვით ჩანს გახსნილ გვერდზე videohighlight.com/v/26QPDBe-NB8 (როგორც youtube.com/embed/..., ისე youtube.com/watch?v=...). ხანგრძლივობა: playlist-ის გვერდი.',
   notes='2017 წლის ვიდეოა; Windows 10/macOS OS X ეპოქა.', phrases='operating system explained for beginners kernel processes memory | Computerphile operating system | ოპერაციული სისტემა რა არის ქართულად'),
 (1, 3): dict(
   primary_url='https://www.youtube.com/watch?v=TQCr9RV7twk' + PL + '&index=20', primary_title='Memory & Storage: Crash Course Computer Science #19', channel=CC, language='ინგლისური', duration='12:17', status=OK,
   why='მონაცემთა შენახვის ტიპები (RAM, დისკი, SSD) და მათი განსხვავება: გაკვეთილის „მონაცემთა შენახვა“ ნაწილს ფარავს.',
   backup_url='', backup_title='', backup_channel='', backup_duration='', backup_status=NF,
   evidence='ბმული სიტყვასიტყვით ჩანს UC Denver-ის PDF-ში (ხაზი გატეხილია PDF-ის გვერდზე, ბმული ერთია); სათაური და ხანგრძლივობა videohighlight-ის playlist-იდან (იგივე ID).',
   notes='ფაილური სისტემების ნაწილისთვის უკეთესი იქნება „Files & File Systems: Crash Course Computer Science #20“ (12:03). მისი ID videohighlight-ზე ჩანს (KN8YgJnShPM), მაგრამ YouTube-ის ბმული ვერ ვნახე, ამიტომ არ ჩამიწერია: ხელით გადაამოწმე.', phrases='file systems explained NTFS ext4 FAT beginners | Crash Course Computer Science Files & File Systems'),
 (2, 1): dict(
   primary_url='https://www.youtube.com/embed/mxpLTv9Gd3k?feature=oembed', primary_title='What is DNS | Domain Name System | Explained', channel='Hostinger Academy', language='ინგლისური', duration='ვერ დადგინდა', status=OK,
   why='DNS-ის როლი და სერვერების როლები მარტივად; ჩანაწერის თავისებურებებზე არ ჩერდება.',
   backup_url='', backup_title='', backup_channel='', backup_duration='', backup_status=NF,
   evidence='ბმული სიტყვასიტყვით ჩანს hostinger.com-ის გვერდის ჩაშენებულ iframe-ში (სათაური iframe-ის title-იდან; ტექსტი: „In this video, you will learn how DNS works and the role of each DNS server“).',
   notes='ყურადღება: ეს ჰოსტინგ-კომპანიის არხია, შეიძლება მარკეტინგული შინაარსი ჰქონდეს; ხანგრძლივობა არ ვიცი. უკეთესი კანდიდატები, რომელთა YouTube-ის ბმული ვერ ვნახე: Computerphile „How DNS Works“ (8 წთ, 2020-07-09; ID uOfonONtIuk ჩანს TheTVDB-სა და yt.d0.cx-ზე) და Professor Messer „An Overview of DNS – N10-009 – 3.4“ (16:54). ორივე ხელით გადაამოწმე.', phrases='Computerphile How DNS Works | Professor Messer An Overview of DNS N10-009 3.4 | DNS explained beginners'),
 (4, 1): dict(
   primary_url='https://www.youtube.com/embed/SBcDGb9l6yo?feature=oembed', primary_title='The CIA Triad - CompTIA Security+ SY0-701 - 1.2', channel='Professor Messer', language='ინგლისური', duration='5:17', status=OK,
   why='კონფიდენციალურობა, მთლიანობა და ხელმისაწვდომობა მოკლედ და მაგალითებით (ჰეში, ციფრული ხელმოწერა, ხარვეზების ატანა). ავტორი ცნობილი სასერტიფიკაციო ტრენერია.',
   backup_url='', backup_title='', backup_channel='', backup_duration='', backup_status=NF,
   evidence='ბმული სიტყვასიტყვით ჩანს ავტორის ოფიციალურ გვერდზე professormesser.com (iframe და og:video მეტა), ხანგრძლივობა: og:video:duration 317 წმ; გამოქვეყნება 2023-11-01.',
   notes='სასერტიფიკაციო (Security+) კონტექსტია, მაგრამ ეს ეპიზოდი ზოგადია.', phrases='CIA triad explained confidentiality integrity availability | Computerphile CIA triad | კონფიდენციალურობა მთლიანობა ხელმისაწვდომობა'),
 (6, 1): dict(
   primary_url='', primary_title='', channel='', language='', duration='', status=NF, why='',
   backup_url='https://www.youtube.com/watch?v=kqtD5dpn9C8&ab_channel=ProgrammingwithMosh', backup_title='Python for Beginners - Learn Python in 1 Hour', backup_channel='Programming with Mosh', backup_duration='≈1:00:00', backup_status=OK,
   evidence='ბმული სიტყვასიტყვით ჩანს git.hpc.odu.edu-ის დოკუმენტში (ხაზი „Mosh\'s Python for Beginners - Learn Python in 1 Hour“, Length: 1 hr); არხი ბმულის ab_channel პარამეტრიდან.',
   notes='ზღვარს (5–40 წთ) სცდება, ამიტომ მხოლოდ სათადარიგოდ. გრძელი ალტერნატივა freeCodeCamp-ის „Learn Python - Full Course for Beginners“ (≈4:26): https://www.youtube.com/watch?v=rfscVS0vtbw ჩანს freecodecamp.org-ის RSS-ში. Crash Course #12 (Programming Basics) ID l26oaHV7D40 ჩანს videohighlight-ზე, YouTube-ის ბმული ვერ ვნახე.',
   phrases='Python variables and if else for beginners 10 minutes | Corey Schafer Python variables | Python conditionals if elif else tutorial'),
}
SEARCH = {
 (2, 2): 'How HTTP works for beginners | HTTPS TLS explained Computerphile | network ports and protocols Professor Messer',
 (2, 3): 'router switch access point explained for beginners | WPA2 WPA3 Wi-Fi security explained | ქსელის მოწყობილობები როუტერი სვიჩი',
 (3, 1): 'Linux terminal commands for beginners | NetworkChuck Linux for hackers | Linux command line basics ls cd cat',
 (3, 2): 'Linux file permissions chmod explained | rwx permissions explained beginners | chmod chown tutorial',
 (3, 3): 'Linux processes ps top kill explained | journalctl and /var/log explained | apt package manager basics',
 (4, 2): 'Professor Messer authentication factors multifactor | password manager explained for beginners | how 2FA TOTP works',
 (4, 3): 'risk assessment cybersecurity for beginners | defense in depth explained | Professor Messer risk management',
 (5, 1): 'how the web works browser server HTTP request | what happens when you type a URL | Crash Course Computer Science The World Wide Web',
 (5, 2): 'OWASP Top 10 explained for beginners | XSS and SQL injection explained | web security basics',
 (5, 3): 'cookies and sessions explained authentication | session vs token authentication | how login works web',
 (6, 2): 'Python for loop while loop tutorial beginners | Python functions tutorial Corey Schafer | Crash Course Computer Science Programming Basics',
 (6, 3): 'Python read write files tutorial | Python with open file handling | Python pathlib basics',
 (6, 4): 'Python lists and strings tutorial | Python parse log file | Python split strip string methods',
 (6, 5): 'Python venv pip tutorial | Python virtual environments explained Corey Schafer | pip install requirements.txt',
 (6, 6): 'hashing explained sha256 file integrity | Python hashlib tutorial | Computerphile hashing',
 (6, 7): 'Python log analyzer project | Python parse auth.log failed logins | Python mini project beginners',
 (7, 1): 'OSINT verifying sources fact checking | reverse image search verification beginners | how to verify information online',
 (7, 2): 'digital footprint privacy explained | what is OSINT digital footprint | online privacy basics',
 (7, 3): 'OSINT methodology and ethics for beginners | OSINT framework introduction | OSINT legal ethical limits',
 (8, 1): 'cybersecurity portfolio project ideas beginners | how to plan a technical project | writing project documentation',
 (8, 2): 'how to present a technical project | presenting a cybersecurity project | technical presentation tips',
 (8, 3): 'cybersecurity career path beginners roadmap | how to start a cybersecurity career entry level | კიბერუსაფრთხოების კარიერა ქართულად',
}
COLS = ['lesson_id', 'stage', 'pos', 'lesson_title', 'primary_url', 'backup_url', 'language', 'channel', 'duration', 'why', 'status',
        'primary_title', 'backup_title', 'backup_channel', 'backup_duration', 'backup_status', 'search_phrases', 'notes', 'evidence']
rows = []
for lid, st, pos, title in LESSONS:
    v = V.get((st, pos))
    if v is None:
        v = dict(primary_url='', primary_title='', channel='', language='', duration='', status=NF, why='', backup_url='', backup_title='', backup_channel='',
                 backup_duration='', backup_status=NF, evidence='', notes='ორივე ვიდეო ვერ ვიპოვე: ვერცერთი კანდიდატი YouTube-ის სიტყვასიტყვითი ბმულით ვერ დავადასტურე.', phrases=SEARCH[(st, pos)])
    rows.append({'lesson_id': lid, 'stage': st, 'pos': pos, 'lesson_title': title, 'primary_url': v['primary_url'], 'backup_url': v['backup_url'], 'language': v['language'],
                 'channel': v['channel'], 'duration': v['duration'], 'why': v['why'], 'status': v['status'], 'primary_title': v['primary_title'], 'backup_title': v['backup_title'],
                 'backup_channel': v['backup_channel'], 'backup_duration': v['backup_duration'], 'backup_status': v['backup_status'], 'search_phrases': v['phrases'],
                 'notes': v['notes'], 'evidence': v['evidence']})
with open(os.path.join(HERE, 'videos.csv'), 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.DictWriter(f, COLS); w.writeheader(); w.writerows(rows)

ver = [r for r in rows if r['status'] == OK or r['backup_status'] == OK]
md = ['# ვიდეოები გაკვეთილებისთვის (ფაზა 4)', '',
      'წყარო: `videos.csv` (იგივე მონაცემი). ბაზაში **არაფერი ჩაწერილა**: ჯერ შენ გადაამოწმე, მერე გაუშვი `python3 import_videos.py` (იხ. README).', '',
      '## როგორ მოვძებნე და რას ნიშნავს „გადამოწმებული“', '',
      '- ბმული ჩავწერე **მხოლოდ** მაშინ, თუ YouTube-ის ბმული (`youtube.com/watch?v=…` ან `youtube.com/embed/…`) სიტყვასიტყვით ვნახე საძიებო შედეგში ან გახსნილ გვერდზე. YouTube ID არსად გამომიცნია და არც ბმული შემიდგენია. სვეტი `evidence` ამბობს, რომელ გვერდზე ვნახე.',
      '- „გადამოწმებული“ ნიშნავს: ბმული არსებობს და სათაური/აღწერა თემას ემთხვევა. **ვიდეო არ გამიხედავს.** ანუ შინაარსის ხარისხს, სიზუსტეს და არქიტექტურას ვერ ვადასტურებ: ეს შენი გადახედვაა.',
      '- ქართულენოვანი ვიდეო ვეძებე (1 ძიება: „ქართულად კიბერუსაფრთხოება დამწყებთათვის ... DNS“): შედეგი არ მოიტანა. ქართულ ვიდეოებზე მიზანმიმართული ძიება ვერ ჩავატარე.',
      '- ხანგრძლივობა მხოლოდ იქ წერია, სადაც გვერდზე ვნახე. სხვაგან „ვერ დადგინდა“.',
      f'- შედეგი: ძირითადი ვიდეო გადამოწმებულია {sum(1 for r in rows if r["status"] == OK)}/28 გაკვეთილზე, სათადარიგო {sum(1 for r in rows if r["backup_status"] == OK)}/28-ზე. დანარჩენზე ვწერ „ვერ ვიპოვე“ და საძიებო ფრაზებს.', '',
      '## გადამოწმებული ბმულები', '',
      '| id | ეტაპი.პოზ. | გაკვეთილი | ძირითადი | სათადარიგო | ენა | არხი | ხანგრძლივობა | რატომ |', '|---|---|---|---|---|---|---|---|---|']
for r in ver:
    p = f'[{r["primary_title"]}]({r["primary_url"]})' if r['primary_url'] else 'ვერ ვიპოვე'
    b = f'[{r["backup_title"]}]({r["backup_url"]}) ({r["backup_duration"]})' if r['backup_url'] else 'ვერ ვიპოვე'
    md.append(f'| {r["lesson_id"]} | {r["stage"]}.{r["pos"]} | {r["lesson_title"]} | {p} | {b} | {r["language"]} | {r["channel"] or r["backup_channel"]} | {r["duration"] or "-"} | {r["why"] or "-"} |')
md += ['', '### დეტალები და გაფრთხილებები', '']
for r in ver:
    md.append(f'- **{r["stage"]}.{r["pos"]} {r["lesson_title"]}**: {r["notes"]} _წყარო: {r["evidence"]}_')
md += ['', '## „ვერ ვიპოვე“: ხელით საძიებოდ (ბმული ადმინის პანელში ჩასვი)', '', '| id | ეტაპი.პოზ. | გაკვეთილი | რა მაკლია | საძიებო ფრაზები (2–3) |', '|---|---|---|---|---|']
for r in rows:
    miss = []
    if r['status'] != OK: miss.append('ძირითადი')
    if r['backup_status'] != OK: miss.append('სათადარიგო')
    if miss:
        md.append(f'| {r["lesson_id"]} | {r["stage"]}.{r["pos"]} | {r["lesson_title"]} | {" და ".join(miss)} | {r["search_phrases"].replace("|", "·") or "-"} |')
md += ['', '## ბაზაში ჩასაწერად', '', 'ნაბიჯები README-შია („ვიდეოების იმპორტი“). მოკლედ: გადაამოწმე `videos.csv`, `python3 import_videos.py` (საცდელი გაშვება, ბაზას არ ცვლის), მერე `python3 import_videos.py --apply`.']
open(os.path.join(HERE, 'videos.md'), 'w', encoding='utf-8').write('\n'.join(md) + '\n')
print('rows', len(rows), 'primary ok', sum(1 for r in rows if r['status'] == OK), 'backup ok', sum(1 for r in rows if r['backup_status'] == OK))
