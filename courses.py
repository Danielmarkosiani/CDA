# კურსების სია: ერთადერთი წყარო (კოდში). ფრონტენდი კურსებს იღებს GET /api/courses-იდან.
# ველები: id, title, description, status ('available' | 'soon'), content_file (შიგთავსის JSON; იგივე ფორმატი, რაც content.json-ს),
#         cert_name (სახელი სერტიფიკატზე; ნაგულისხმევი: title), capstone (True: სერტიფიკატისთვის დადასტურებული შემაჯამებელი პროექტი).
# status='soon' კურსს მოსწავლე ხედავს მხოლოდ როგორც „მალე“; ადმინი ხსნის ყველა კურსს, რომელსაც გაკვეთილები აქვს.
# ახალი კურსის დამატება: tools/new_course.py ან README-ის განყოფილება „Adding a new course“.
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_COURSE = 'cybersecurity-beginners'

COURSES = [
    {'id': 'cybersecurity-beginners', 'title': 'Cybersecurity for Beginners', 'status': 'available', 'content_file': 'content.json',
     'description': 'სისტემური კურსი დამწყებისთვის: კომპიუტერი, ქსელები, Linux, უსაფრთხოების პრინციპები, ვებტექნოლოგიები, Python და OSINT. გაკვეთილები, ქვიზები, პრაქტიკული დავალებები და მენტორი.',
     'cert_name': 'Cybersecurity: Beginner Path', 'capstone': True},
    {'id': 'cybersecurity-pro', 'title': 'Cybersecurity Pro', 'status': 'soon', 'content_file': None,
     'description': 'გაღრმავებული კურსი Beginner Path-ის კურსდამთავრებულებისთვის.'},
    {'id': 'python-developer', 'title': 'Python Developer', 'status': 'soon', 'content_file': None,
     'description': 'პროგრამირება Python-ზე: საფუძვლებიდან რეალურ პროექტებამდე.'},
    {'id': 'web-developer', 'title': 'Web Developer', 'status': 'soon', 'content_file': None,
     'description': 'HTML, CSS და ვებ-გვერდების აწყობა ნულიდან.'},
    {'id': 'javascript-developer', 'title': 'JavaScript Developer', 'status': 'soon', 'content_file': None,
     'description': 'JavaScript: ინტერაქტიული ვებ-აპლიკაციების შექმნა.'},
]

# ტესტებისა და ინსტალაციისთვის: CDA_EXTRA_COURSES=<json-ფაილი> (კურსების მასივი ზემოთ აღწერილი ველებით) ამატებს ან ანაცვლებს ჩანაწერებს id-ით.
# ეს გზა პროექტში არსებულ სიას არ ცვლის: ცვლადის გარეშე მხოლოდ COURSES მუშაობს.
_extra = os.environ.get('CDA_EXTRA_COURSES')
if _extra:
    with open(_extra, encoding='utf-8') as _f:
        for _c in json.load(_f):
            COURSES[:] = [c for c in COURSES if c['id'] != _c['id']] + [_c]


def get(cid):
    return next((c for c in COURSES if c['id'] == cid), None)


def content_path(c):
    f = c.get('content_file')
    return None if not f else (f if os.path.isabs(f) else os.path.join(HERE, f))


def cert_name(c):
    return c.get('cert_name') or c['title']
