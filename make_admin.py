# ადმინის შექმნა/დანიშვნა პირდაპირ ბაზაში:
#   python3 make_admin.py ელფოსტა პაროლი [სახელი]
# თუ ანგარიში უკვე არსებობს, ის ადმინი გახდება და პაროლი შეიცვლება.
import re
import secrets
import sys
import time

import db
from auth import MIN_PW_LEN, hash_pw, strong_pw

args = sys.argv[1:]
email = args[0] if len(args) > 0 else ''
password = args[1] if len(args) > 1 else ''
name = args[2] if len(args) > 2 else 'მენტორი'
if not email or not re.fullmatch(r'\S+@\S+\.\S+', email) or not strong_pw(password, email, name):
    sys.exit(f'გამოყენება: python3 make_admin.py ელფოსტა პაროლი [სახელი]\nპაროლი: მინ. {MIN_PW_LEN} სიმბოლო (ჰარებიანი ფრაზაც ვარგა), არა გავრცელებული და არ უნდა შეიცავდეს ელფოსტის სახელს.')
e, salt = email.strip().lower(), secrets.token_hex(16)
h = hash_pw(password, salt)
if db.one('SELECT 1 FROM users WHERE email=?', e):
    db.run("UPDATE users SET role='admin',hash=?,salt=?,email_verified=1 WHERE email=?", h, salt, e)
    db.run('DELETE FROM sessions WHERE user_id=(SELECT id FROM users WHERE email=?)', e)
    db.run('DELETE FROM codes WHERE user_id=(SELECT id FROM users WHERE email=?)', e)   # გაგზავნილი დადასტურების/აღდგენის კოდები აღარ გამოდგება
    db.audit(None, 'make_admin', e, 'cli')
    print(f'ანგარიში {e} ახლა ადმინია, პაროლი შეცვლილია.')
else:
    db.run("INSERT INTO users(email,name,hash,salt,role,created,email_verified) VALUES(?,?,?,?,'admin',?,1)", e, name[:60], h, salt, int(time.time() * 1000))
    db.audit(None, 'make_admin', e, 'cli')
    print(f'ადმინი შეიქმნა: {e}')
