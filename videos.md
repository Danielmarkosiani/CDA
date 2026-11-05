# ვიდეოები გაკვეთილებისთვის (ფაზა 4)

წყარო: `videos.csv` (იგივე მონაცემი). ბაზაში **არაფერი ჩაწერილა**: ჯერ შენ გადაამოწმე, მერე გაუშვი `python3 import_videos.py` (იხ. README).

## როგორ მოვძებნე და რას ნიშნავს „გადამოწმებული“

- ბმული ჩავწერე **მხოლოდ** მაშინ, თუ YouTube-ის ბმული (`youtube.com/watch?v=…` ან `youtube.com/embed/…`) სიტყვასიტყვით ვნახე საძიებო შედეგში ან გახსნილ გვერდზე. YouTube ID არსად გამომიცნია და არც ბმული შემიდგენია. სვეტი `evidence` ამბობს, რომელ გვერდზე ვნახე.
- „გადამოწმებული“ ნიშნავს: ბმული არსებობს და სათაური/აღწერა თემას ემთხვევა. **ვიდეო არ გამიხედავს.** ანუ შინაარსის ხარისხს, სიზუსტეს და არქიტექტურას ვერ ვადასტურებ: ეს შენი გადახედვაა.
- ქართულენოვანი ვიდეო ვეძებე (1 ძიება: „ქართულად კიბერუსაფრთხოება დამწყებთათვის ... DNS“): შედეგი არ მოიტანა. ქართულ ვიდეოებზე მიზანმიმართული ძიება ვერ ჩავატარე.
- ხანგრძლივობა მხოლოდ იქ წერია, სადაც გვერდზე ვნახე. სხვაგან „ვერ დადგინდა“.
- შედეგი: ძირითადი ვიდეო გადამოწმებულია 5/28 გაკვეთილზე, სათადარიგო 2/28-ზე. დანარჩენზე ვწერ „ვერ ვიპოვე“ და საძიებო ფრაზებს.

## გადამოწმებული ბმულები

| id | ეტაპი.პოზ. | გაკვეთილი | ძირითადი | სათადარიგო | ენა | არხი | ხანგრძლივობა | რატომ |
|---|---|---|---|---|---|---|---|---|
| 1 | 1.1 | როგორ მუშაობს კომპიუტერი | [The Central Processing Unit (CPU): Crash Course Computer Science #7](https://www.youtube.com/embed/FZGugFqdr60) | [Registers and RAM: Crash Course Computer Science #6](https://www.youtube.com/watch?v=fpnE6UAfbtU&list=PL8dPuuaLjXtNlUrzyH5r6jN9ulIgZBpdo&index=7) (12:17) | ინგლისური | Crash Course | 11:38 (videohighlight-ის სია; PBS-ის გვერდზე 11:15) | პროცესორის მუშაობა (fetch-decode-execute) ნაბიჯ-ნაბიჯ და ანიმაციით, დამწყებისთვის გასაგები, არამარკეტინგული. |
| 2 | 1.2 | ოპერაციული სისტემები | [Operating Systems: Crash Course Computer Science #18](https://www.youtube.com/watch?v=26QPDBe-NB8) | ვერ ვიპოვე | ინგლისური | Crash Course | 13:36 | ოპერაციული სისტემის როლი, მეხსიერების დაცვა, Unix/Linux-ისა და Windows-ის ფესვები: სწორად ქმნის საფუძველს ეტაპი 3-ისთვის. |
| 3 | 1.3 | ფაილური სისტემები და მონაცემთა შენახვა | [Memory & Storage: Crash Course Computer Science #19](https://www.youtube.com/watch?v=TQCr9RV7twk&list=PL8dPuuaLjXtNlUrzyH5r6jN9ulIgZBpdo&index=20) | ვერ ვიპოვე | ინგლისური | Crash Course | 12:17 | მონაცემთა შენახვის ტიპები (RAM, დისკი, SSD) და მათი განსხვავება: გაკვეთილის „მონაცემთა შენახვა“ ნაწილს ფარავს. |
| 4 | 2.1 | IP მისამართები და DNS | [What is DNS | Domain Name System | Explained](https://www.youtube.com/embed/mxpLTv9Gd3k?feature=oembed) | ვერ ვიპოვე | ინგლისური | Hostinger Academy | ვერ დადგინდა | DNS-ის როლი და სერვერების როლები მარტივად; ჩანაწერის თავისებურებებზე არ ჩერდება. |
| 10 | 4.1 | CIA სამეული და საფრთხეები | [The CIA Triad - CompTIA Security+ SY0-701 - 1.2](https://www.youtube.com/embed/SBcDGb9l6yo?feature=oembed) | ვერ ვიპოვე | ინგლისური | Professor Messer | 5:17 | კონფიდენციალურობა, მთლიანობა და ხელმისაწვდომობა მოკლედ და მაგალითებით (ჰეში, ციფრული ხელმოწერა, ხარვეზების ატანა). ავტორი ცნობილი სასერტიფიკაციო ტრენერია. |
| 16 | 6.1 | ცვლადები და პირობები | ვერ ვიპოვე | [Python for Beginners - Learn Python in 1 Hour](https://www.youtube.com/watch?v=kqtD5dpn9C8&ab_channel=ProgrammingwithMosh) (≈1:00:00) |  | Programming with Mosh | - | - |

### დეტალები და გაფრთხილებები

- **1.1 როგორ მუშაობს კომპიუტერი**: ვიდეო 2017 წლისაა, მაგრამ თემა (CPU-ს აგებულება) არ ძველდება. _წყარო: ძირითადი: ბმული embed სახით სიტყვასიტყვით ჩანს გახსნილ გვერდზე videohighlight.com/v/FZGugFqdr60 (სათაური, აღწერა, ეპიზოდი #7). სათადარიგო: ბმული სიტყვასიტყვით ჩანს UC Denver-ის PDF-ში (clas.ucdenver.edu, Crash Course annotations); სათაური/ხანგრძლივობა videohighlight-ის playlist-იდან (იგივე ID)._
- **1.2 ოპერაციული სისტემები**: 2017 წლის ვიდეოა; Windows 10/macOS OS X ეპოქა. _წყარო: ბმული სიტყვასიტყვით ჩანს გახსნილ გვერდზე videohighlight.com/v/26QPDBe-NB8 (როგორც youtube.com/embed/..., ისე youtube.com/watch?v=...). ხანგრძლივობა: playlist-ის გვერდი._
- **1.3 ფაილური სისტემები და მონაცემთა შენახვა**: ფაილური სისტემების ნაწილისთვის უკეთესი იქნება „Files & File Systems: Crash Course Computer Science #20“ (12:03). მისი ID videohighlight-ზე ჩანს (KN8YgJnShPM), მაგრამ YouTube-ის ბმული ვერ ვნახე, ამიტომ არ ჩამიწერია: ხელით გადაამოწმე. _წყარო: ბმული სიტყვასიტყვით ჩანს UC Denver-ის PDF-ში (ხაზი გატეხილია PDF-ის გვერდზე, ბმული ერთია); სათაური და ხანგრძლივობა videohighlight-ის playlist-იდან (იგივე ID)._
- **2.1 IP მისამართები და DNS**: ყურადღება: ეს ჰოსტინგ-კომპანიის არხია, შეიძლება მარკეტინგული შინაარსი ჰქონდეს; ხანგრძლივობა არ ვიცი. უკეთესი კანდიდატები, რომელთა YouTube-ის ბმული ვერ ვნახე: Computerphile „How DNS Works“ (8 წთ, 2020-07-09; ID uOfonONtIuk ჩანს TheTVDB-სა და yt.d0.cx-ზე) და Professor Messer „An Overview of DNS – N10-009 – 3.4“ (16:54). ორივე ხელით გადაამოწმე. _წყარო: ბმული სიტყვასიტყვით ჩანს hostinger.com-ის გვერდის ჩაშენებულ iframe-ში (სათაური iframe-ის title-იდან; ტექსტი: „In this video, you will learn how DNS works and the role of each DNS server“)._
- **4.1 CIA სამეული და საფრთხეები**: სასერტიფიკაციო (Security+) კონტექსტია, მაგრამ ეს ეპიზოდი ზოგადია. _წყარო: ბმული სიტყვასიტყვით ჩანს ავტორის ოფიციალურ გვერდზე professormesser.com (iframe და og:video მეტა), ხანგრძლივობა: og:video:duration 317 წმ; გამოქვეყნება 2023-11-01._
- **6.1 ცვლადები და პირობები**: ზღვარს (5–40 წთ) სცდება, ამიტომ მხოლოდ სათადარიგოდ. გრძელი ალტერნატივა freeCodeCamp-ის „Learn Python - Full Course for Beginners“ (≈4:26): https://www.youtube.com/watch?v=rfscVS0vtbw ჩანს freecodecamp.org-ის RSS-ში. Crash Course #12 (Programming Basics) ID l26oaHV7D40 ჩანს videohighlight-ზე, YouTube-ის ბმული ვერ ვნახე. _წყარო: ბმული სიტყვასიტყვით ჩანს git.hpc.odu.edu-ის დოკუმენტში (ხაზი „Mosh's Python for Beginners - Learn Python in 1 Hour“, Length: 1 hr); არხი ბმულის ab_channel პარამეტრიდან._

## „ვერ ვიპოვე“: ხელით საძიებოდ (ბმული ადმინის პანელში ჩასვი)

| id | ეტაპი.პოზ. | გაკვეთილი | რა მაკლია | საძიებო ფრაზები (2–3) |
|---|---|---|---|---|
| 2 | 1.2 | ოპერაციული სისტემები | სათადარიგო | operating system explained for beginners kernel processes memory · Computerphile operating system · ოპერაციული სისტემა რა არის ქართულად |
| 3 | 1.3 | ფაილური სისტემები და მონაცემთა შენახვა | სათადარიგო | file systems explained NTFS ext4 FAT beginners · Crash Course Computer Science Files & File Systems |
| 4 | 2.1 | IP მისამართები და DNS | სათადარიგო | Computerphile How DNS Works · Professor Messer An Overview of DNS N10-009 3.4 · DNS explained beginners |
| 5 | 2.2 | HTTP/HTTPS და პორტები | ძირითადი და სათადარიგო | How HTTP works for beginners · HTTPS TLS explained Computerphile · network ports and protocols Professor Messer |
| 6 | 2.3 | ქსელის მოწყობილობები და უსაფრთხო Wi‑Fi | ძირითადი და სათადარიგო | router switch access point explained for beginners · WPA2 WPA3 Wi-Fi security explained · ქსელის მოწყობილობები როუტერი სვიჩი |
| 7 | 3.1 | ტერმინალის ბრძანებები | ძირითადი და სათადარიგო | Linux terminal commands for beginners · NetworkChuck Linux for hackers · Linux command line basics ls cd cat |
| 8 | 3.2 | ფაილების უფლებები | ძირითადი და სათადარიგო | Linux file permissions chmod explained · rwx permissions explained beginners · chmod chown tutorial |
| 9 | 3.3 | პროცესები, ლოგები და პაკეტები | ძირითადი და სათადარიგო | Linux processes ps top kill explained · journalctl and /var/log explained · apt package manager basics |
| 10 | 4.1 | CIA სამეული და საფრთხეები | სათადარიგო | CIA triad explained confidentiality integrity availability · Computerphile CIA triad · კონფიდენციალურობა მთლიანობა ხელმისაწვდომობა |
| 11 | 4.2 | პაროლები და ორფაქტორიანი დაცვა | ძირითადი და სათადარიგო | Professor Messer authentication factors multifactor · password manager explained for beginners · how 2FA TOTP works |
| 12 | 4.3 | რისკის შეფასება და ფენოვანი დაცვა | ძირითადი და სათადარიგო | risk assessment cybersecurity for beginners · defense in depth explained · Professor Messer risk management |
| 13 | 5.1 | ბრაუზერი და სერვერი | ძირითადი და სათადარიგო | how the web works browser server HTTP request · what happens when you type a URL · Crash Course Computer Science The World Wide Web |
| 14 | 5.2 | ვებ უსაფრთხოების შესავალი | ძირითადი და სათადარიგო | OWASP Top 10 explained for beginners · XSS and SQL injection explained · web security basics |
| 15 | 5.3 | ავტორიზაცია, სესიები და cookie | ძირითადი და სათადარიგო | cookies and sessions explained authentication · session vs token authentication · how login works web |
| 16 | 6.1 | ცვლადები და პირობები | ძირითადი | Python variables and if else for beginners 10 minutes · Corey Schafer Python variables · Python conditionals if elif else tutorial |
| 17 | 6.2 | ციკლები და ფუნქციები | ძირითადი და სათადარიგო | Python for loop while loop tutorial beginners · Python functions tutorial Corey Schafer · Crash Course Computer Science Programming Basics |
| 18 | 6.3 | ფაილები და უსაფრთხოების სკრიპტები | ძირითადი და სათადარიგო | Python read write files tutorial · Python with open file handling · Python pathlib basics |
| 19 | 6.4 | სიები, სტრიქონები და ლოგების დამუშავება | ძირითადი და სათადარიგო | Python lists and strings tutorial · Python parse log file · Python split strip string methods |
| 20 | 6.5 | მოდულები, pip და ვირტუალური გარემო | ძირითადი და სათადარიგო | Python venv pip tutorial · Python virtual environments explained Corey Schafer · pip install requirements.txt |
| 21 | 6.6 | ჰეშები და ფაილის მთლიანობა | ძირითადი და სათადარიგო | hashing explained sha256 file integrity · Python hashlib tutorial · Computerphile hashing |
| 22 | 6.7 | მინი-პროექტი: ლოგების ანალიზატორი | ძირითადი და სათადარიგო | Python log analyzer project · Python parse auth.log failed logins · Python mini project beginners |
| 23 | 7.1 | ინფორმაციის გადამოწმება | ძირითადი და სათადარიგო | OSINT verifying sources fact checking · reverse image search verification beginners · how to verify information online |
| 24 | 7.2 | ციფრული კვალი და კონფიდენციალურობა | ძირითადი და სათადარიგო | digital footprint privacy explained · what is OSINT digital footprint · online privacy basics |
| 25 | 7.3 | OSINT-ის მეთოდოლოგია და ეთიკა | ძირითადი და სათადარიგო | OSINT methodology and ethics for beginners · OSINT framework introduction · OSINT legal ethical limits |
| 26 | 8.1 | პროექტის დაგეგმვა | ძირითადი და სათადარიგო | cybersecurity portfolio project ideas beginners · how to plan a technical project · writing project documentation |
| 27 | 8.2 | პროექტის წარდგენა | ძირითადი და სათადარიგო | how to present a technical project · presenting a cybersecurity project · technical presentation tips |
| 28 | 8.3 | კარიერა და სწავლის გაგრძელება | ძირითადი და სათადარიგო | cybersecurity career path beginners roadmap · how to start a cybersecurity career entry level · კიბერუსაფრთხოების კარიერა ქართულად |

## ბაზაში ჩასაწერად

ნაბიჯები README-შია („ვიდეოების იმპორტი“). მოკლედ: გადაამოწმე `videos.csv`, `python3 import_videos.py` (საცდელი გაშვება, ბაზას არ ცვლის), მერე `python3 import_videos.py --apply`.
