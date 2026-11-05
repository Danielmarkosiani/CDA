#!/usr/bin/env python3
"""SMTP-ის შემოწმება .env-ის (ან გარემოს ცვლადების) პარამეტრებით.

    python3 tools/test_mail.py მისამართი@example.com

ცდის ერთ სატესტო წერილს გაგზავნას და ნათლად ამბობს, რა არ მუშაობს: პაროლი/მომხმარებელი, პორტი, ავტორიზაცია, TLS.
გასვლის კოდი: 0 = გაიგზავნა, 1 = SMTP-მ ვერ გააგზავნა, 2 = SMTP მორგებული არ არის ან არგუმენტი არასწორია.
პაროლს არასოდეს ბეჭდავს. წარმატება ნიშნავს, რომ SMTP სერვერმა წერილი მიიღო; სპამში ხვდება თუ არა, ამას ვერ ამოწმებს: ჩაუხედე ყუთს და სპამის საქაღალდეს.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))   # პროექტის საქაღალდე: envfile და mailer იქაა

import envfile  # noqa: E402  (.env-ს ტვირთავს იმპორტისას)
import mailer  # noqa: E402


def main(argv):
    if len(argv) != 2 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', argv[1]):
        print('გამოყენება: python3 tools/test_mail.py მისამართი@example.com')
        return 2
    to = argv[1]
    print('.env:', ('ნაპოვნია და ჩაიტვირთა (' + ', '.join(sorted(envfile.LOADED)) + ')') if envfile.LOADED
          else ('ფაილი არ არის ან ყველა ცვლადი უკვე გარემოშია: ' + envfile.PATH))
    if not mailer.configured():
        print('\n✘ SMTP_HOST ცარიელია: წერილები არ იგზავნება, მხოლოდ კონსოლში იბეჭდება.\n'
              '  შეავსე SMTP_HOST, SMTP_PORT, SMTP_SECURITY, SMTP_USER, SMTP_PASSWORD, SMTP_FROM .env-ში (იხ. .env.example და DEPLOY.md, ნაწილი 4).')
        return 2
    print(f'სერვერი: {mailer.HOST}:{mailer.PORT}, უსაფრთხოება: {mailer.SECURITY}, მომხმარებელი: {mailer.USER or "(არ არის)"}, '
          f'პაროლი: {"მითითებულია" if mailer.PASSWORD else "არ არის"}, გამგზავნი: {mailer.FROM}')
    problems = mailer.config_problems()
    for pr in problems:
        print('⚠', pr)
    print(f'ვცდილობ გაგზავნას: {to} ...')
    ok, err = mailer.deliver(to, 'CDA: SMTP-ის ტესტი', 'ეს სატესტო წერილია CDA-ს tools/test_mail.py-დან.\nთუ ეს მიიღე, SMTP სწორად არის მორგებული.\n')
    if ok:
        print(f'\n✔ სერვერმა წერილი მიიღო. ჩაუხედე {to}-ს შემომავალსა და სპამს. თუ არ მოვიდა, პრობლემა უკვე პროვაიდერისა ან დომენის ავთენტიფიკაციაშია (SPF/DKIM).')
        return 0
    cat, text = mailer.describe_error(err)
    print(f'\n✘ ვერ გაიგზავნა [{cat}]: {text}')
    print(f'  ტექნიკური დეტალი: {type(err).__name__}: {err}')
    return 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
