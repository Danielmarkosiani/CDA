# ელფოსტის გაგზავნა (smtplib). SMTP_HOST-ის გარეშე წერილი კონსოლში იბეჭდება: ლოკალური ტესტირებისთვის.
#   SMTP_HOST, SMTP_PORT (587), SMTP_USER, SMTP_PASSWORD, SMTP_FROM, SMTP_SECURITY=starttls|ssl|none (starttls)
# პარამეტრები იკითხება .env-იდან (envfile.py) ან გარემოს ცვლადებიდან. შემოწმება: python3 tools/test_mail.py მისამართი@...
import envfile  # noqa: F401  (.env-ის ჩატვირთვა სხვა ცვლადების წაკითხვამდე)
import os
import smtplib
import socket
import ssl
import sys
import threading
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

HOST = os.environ.get('SMTP_HOST', '').strip()
SECURITY = (os.environ.get('SMTP_SECURITY') or 'starttls').strip().lower()
try:
    PORT = int(os.environ.get('SMTP_PORT') or (465 if SECURITY == 'ssl' else 587))
except ValueError:
    PORT = -1   # არასწორი მნიშვნელობა: describe_error() ამას ცალკე იტყვის
USER = os.environ.get('SMTP_USER', '')
PASSWORD = os.environ.get('SMTP_PASSWORD', '')
FROM = os.environ.get('SMTP_FROM') or USER or 'noreply@localhost'


def configured():
    return bool(HOST)


def config_problems():
    """პარამეტრების აშკარა შეცდომები გაგზავნამდე (სია ქართულად; ცარიელია, თუ ყველაფერი რიგზეა ან SMTP არ არის ჩართული)."""
    if not HOST:
        return []
    out = []
    if PORT <= 0 or PORT > 65535:
        out.append('SMTP_PORT არასწორია (უნდა იყოს რიცხვი, მაგ. 587 ან 465).')
    if SECURITY not in ('starttls', 'ssl', 'none'):
        out.append(f'SMTP_SECURITY="{SECURITY}" უცნობია: დასაშვებია starttls, ssl ან none.')
    if SECURITY == 'ssl' and PORT == 587:
        out.append('SMTP_SECURITY=ssl და პორტი 587 ერთმანეთს არ ესადაგება: ssl-ს ჩვეულებრივ 465 უხდება, starttls-ს 587.')
    if SECURITY == 'starttls' and PORT == 465:
        out.append('SMTP_SECURITY=starttls და პორტი 465 ერთმანეთს არ ესადაგება: 465 ჩვეულებრივ ssl-ია, starttls-ს 587 უხდება.')
    if bool(USER) != bool(PASSWORD):
        out.append('SMTP_USER და SMTP_PASSWORD ან ორივე უნდა იყოს მითითებული, ან არც ერთი.')
    if SECURITY == 'none' and USER:
        out.append('SMTP_SECURITY=none: პაროლი დაუშიფრავად გაიგზავნება. ეს მხოლოდ ლოკალური ტესტისთვის გამოდგება.')
    return out


def describe_error(e):
    """გაგზავნის შეცდომის ახსნა ქართულად: რა მოხდა და რა უნდა შეამოწმო. აბრუნებს (კატეგორია, ტექსტი)."""
    if isinstance(e, smtplib.SMTPAuthenticationError):
        return 'ავტორიზაცია', (f'სერვერმა უარყო SMTP_USER/SMTP_PASSWORD (კოდი {e.smtp_code}). შეამოწმე მომხმარებელი და პაროლი. '
                               'Gmail-ზე ჩვეულებრივი პაროლი არ გამოდგება: საჭიროა App password (იხ. DEPLOY.md, ნაწილი 4).')
    if isinstance(e, smtplib.SMTPNotSupportedError):
        return 'უსაფრთხოება', ('სერვერი არ მხარს უჭერს მოთხოვნილ რეჟიმს (STARTTLS ან ავტორიზაცია). სცადე SMTP_SECURITY=ssl და პორტი 465, '
                               'ან შეამოწმე, რომ პორტი 587 STARTTLS-ს გულისხმობს.')
    if isinstance(e, smtplib.SMTPSenderRefused):
        return 'გამგზავნი', f'სერვერმა უარყო გამგზავნის მისამართი SMTP_FROM (კოდი {e.smtp_code}). პროვაიდერები ხშირად მხოლოდ საკუთარ ან დადასტურებულ მისამართს უშვებენ.'
    if isinstance(e, smtplib.SMTPRecipientsRefused):
        return 'მიმღები', 'სერვერმა უარყო მიმღების მისამართი. შეამოწმე, რომ ელფოსტა სწორად არის დაწერილი.'
    if isinstance(e, smtplib.SMTPResponseException):
        return 'სერვერის პასუხი', f'სერვერმა დააბრუნა შეცდომა {e.smtp_code}: {e.smtp_error!r}'
    if isinstance(e, smtplib.SMTPServerDisconnected):
        return 'კავშირი', ('სერვერმა კავშირი გაწყვიტა. ხშირი მიზეზი: პორტი და SMTP_SECURITY არ ესადაგება ერთმანეთს '
                           '(587 ↔ starttls, 465 ↔ ssl) ან პროვაიდერი ბლოკავს ამ კავშირს.')
    if isinstance(e, ssl.SSLCertVerificationError):
        return 'სერტიფიკატი', 'სერვერის სერტიფიკატი ვერ დადასტურდა: შეამოწმე SMTP_HOST (უნდა ემთხვეოდეს სერტიფიკატის სახელს).'
    if isinstance(e, ssl.SSLError):
        return 'უსაფრთხოება', ('TLS-ის დამყარება ვერ მოხერხდა: ალბათ პორტი და SMTP_SECURITY არ ესადაგება ერთმანეთს '
                               '(587 ↔ starttls, 465 ↔ ssl).')
    if isinstance(e, socket.gaierror):
        return 'მისამართი', 'SMTP_HOST ვერ მოიძებნა (DNS). შეამოწმე, რომ სახელი სწორად არის დაწერილი.'
    if isinstance(e, (socket.timeout, TimeoutError)):
        return 'პორტი', 'სერვერმა დროზე არ უპასუხა. შეამოწმე SMTP_PORT, ინტერნეტი და ფაიერვოლი (ზოგ ჰოსტინგზე გამავალი SMTP დაბლოკილია).'
    if isinstance(e, ConnectionRefusedError):
        return 'პორტი', 'კავშირი უარყოფილია: ამ პორტზე SMTP არ უსმენს. შეამოწმე SMTP_PORT და SMTP_HOST.'
    if isinstance(e, OSError):
        return 'ქსელი', f'ქსელის შეცდომა: {e}'
    return 'სხვა', f'{type(e).__name__}: {e}'


def deliver(to, subject, text):
    """აბრუნებს (True, None) ან (False, გამონაკლისი). შეცდომას არ აგდებს."""
    try:
        m = EmailMessage()  # სათაურებში ახალი ხაზის ჩასმას ბიბლიოთეკა თვითონ კრძალავს
        m['From'], m['To'], m['Subject'] = FROM, to, subject
        m['Date'] = formatdate(localtime=True)
        m['Message-ID'] = make_msgid(domain=(FROM.rsplit('@', 1)[-1].strip(' >') or 'localhost'))
        m.set_content(text)
        ctx = ssl.create_default_context()
        if SECURITY == 'ssl':
            s = smtplib.SMTP_SSL(HOST, PORT, timeout=15, context=ctx)
        else:
            s = smtplib.SMTP(HOST, PORT, timeout=15)
        with s:
            if SECURITY == 'starttls':
                s.starttls(context=ctx)
            if USER:
                s.login(USER, PASSWORD)
            s.send_message(m)
        return True, None
    except Exception as e:  # noqa: BLE001
        return False, e


def send_now(to, subject, text):
    """აბრუნებს True-ს წარმატებისას. შეცდომას არ აგდებს: სერვერი წერილის გამო არ უნდა გაითიშოს."""
    if not HOST:
        print(f'[MAIL -> {to}] {subject}\n{text}\n[/MAIL]', flush=True)  # SMTP არ არის: კონსოლში
        return True
    ok, e = deliver(to, subject, text)
    if not ok:
        print('mail error:', type(e).__name__, e, '|', describe_error(e)[1], file=sys.stderr, flush=True)
    return ok


def send(to, subject, text):
    """ფონურ ნაკადში: მოთხოვნის პასუხის დრო არ არის დამოკიდებული SMTP-ზე (და არც იმაზე, არსებობს თუ არა ანგარიში)."""
    threading.Thread(target=send_now, args=(to, subject, text), daemon=True).start()


def startup_warning():
    """გაშვებისას ერთხელ: ცხადად ეუბნება ადმინისტრატორს, რომ წერილები არ იგზავნება (ან პარამეტრები საეჭვოა)."""
    if not HOST:
        return ('⚠⚠⚠ SMTP არ არის მორგებული (SMTP_HOST ცარიელია): წერილები, მათ შორის დადასტურებისა და პაროლის აღდგენის კოდები, '
                'არ იგზავნება და მხოლოდ ამ კონსოლში იბეჭდება. მოსწავლეები ვერ დაადასტურებენ ელფოსტას. '
                'მორგება: .env-ში SMTP_* (იხ. .env.example და DEPLOY.md), შემოწმება: python3 tools/test_mail.py შენი@მისამართი')
    probs = config_problems()
    return ('⚠ SMTP პარამეტრები საეჭვოა: ' + ' '.join(probs) + ' შემოწმება: python3 tools/test_mail.py შენი@მისამართი') if probs else None
