# CDA: Cyber & Digital Academy

Flask + SQLite (Python's built-in `sqlite3`). The frontend is plain HTML/CSS/JS, so there is no build step.

The interface language is Georgian. Course content lives in `content.json`.

## Current state (2026-11-04)

`content.json` holds all 8 stages (28 lessons, 12-question quiz banks); stages 6.1-6.7 each carry 2 python exercises, stages 7 and 8 have none. `validate_content.py`: 0 errors, 0 warnings. Open points:

- **Stage 7 (OSINT) needs an expert review before it is opened to the public** (`EXPERT_REVIEW.md`, section "ეტაპი 7"). It is already in `content.json`, and the code has no switch to hide a stage. Its ethical framing (own data or public organisations only; no looking up or doxxing of a specific private person) must not be weakened.
- Lessons still contain `[გადასამოწმებელი]` markers where a claim has no source yet; they stay until an expert reviews them (stages 4-8, see `EXPERT_REVIEW.md`).
- The certificate is the **academy's own course-completion document, not accredited**, and does not replace a state-recognised qualification.
- Never exercised for real: SMTP, Pyodide in a browser, the site's look in a browser, mobile layout (see `HANDOFF.md` §5-6). The lesson videos have not been watched by anyone.

## Pages and the course catalog

- `#/` is the **course catalog** (`views.home`): two-column first screen. Left: title, subtitle, "კურსის არჩევა" (scrolls to the course grid with `scrollIntoView`, no `href="#..."`; signed-in users get "განაგრძე სწავლა" → `#/course`) and "გეგმები და ფასები". Right: a **free-lesson preview** (stage 1 lesson 1 from `content.json`: number and minutes, first `/img/lessons/` diagram, first 3 objectives, button to the lesson; hidden if that lesson is not free for guests, and each missing field just disappears). Then (signed in only) "განაგრძე სწავლა", **"აირჩიე კურსი"** (every course from `GET /api/courses` as an equal-size clickable `<a>` card: available → `#/c/<id>`, soon → `#/soon/<id>`), "როგორ ისწავლი", "რას მიიღებ", an FAQ (quiz numbers from `/api/config`) and the footer. The stage list lives only on `#/cybersecurity`.
- `#/soon/<id>` ("coming soon" page) exists only for courses with `status: 'soon'` in `courses.py`; an unknown or available id shows the normal "გვერდი ვერ მოიძებნა" page. It shows the title, description, a short note, buttons to `#/` and `#/cybersecurity`, and a `CONTACT` line (hidden when empty). No forms, no e-mail collection.
- `#/cybersecurity` is the former home page of the Cybersecurity course (hero, stage list, metrics, plans, FAQ); its buttons behave as before (`#/course` = the full stage list with progress, `#/lesson/<id>`, `#/pricing`, `#/register`).
- Other pages are unchanged (`#/course`, `#/lesson/...`, `#/pricing`, `#/login`, `#/register`, `#/account`, `#/qa`, `#/admin`, ...). `index.html` meta/og descriptions describe the whole academy.
- **Multiple courses.** `courses.py` is the single list of courses (id, title, description, status `available`|`soon`, `content_file`, optional `cert_name`, `capstone`). The frontend gets it from `GET /api/courses`. Routes: `#/c/<id>` (course page; `#/cybersecurity` is the same page for `cybersecurity-beginners`), `#/course[/<id>]` (learning view; `#/course` = Beginners), `#/lesson/<id>` (lesson ids are global, the course is found automatically), `#/certificate[/<id>]`, `#/soon/<id>`. Plans cover every available course; the first stage of every course is free.
- A `soon` course is hidden from students and guests (its lessons answer 404); admins see and open any course that has lessons, marked "მალე (მხოლოდ ადმინისთვის)", and the admin panel has a course selector (overview, learners' progress, questions, materials follow it; orders, audit log, users and plans stay global).

**Adding a new course.**

1. `python3 tools/new_course.py <id> "<Title>" "<description>"` adds the entry to `courses.py` with `status: 'soon'` and creates `content-<id>.json` (same format as `content.json`, one placeholder lesson that passes validation).
2. Fill the file, then `python3 validate_content.py` (it checks every course file listed in `courses.py`). A missing, empty or broken file just leaves the course without content; the server still starts.
3. Start the server and preview as admin (the course shows in the course selector and at `#/c/<id>`).
4. When ready, change `status` to `'available'` in `courses.py`. Done: the catalog card, `#/c/<id>`, progress, quizzes and certificates work with no other code. (A certificate is issued when every lesson of the course is done; set `capstone: True` on the course to also require an approved final project.)

Known limits: the plan is global (covers all courses) and there is no per-course price; the home "continue learning" block, the account progress and the Q&A page use the default course (`cybersecurity-beginners`); the final project (`kind='capstone'` question) is not tied to a course.

## Running

    pip install -r requirements.txt
    python3 make_admin.py you@example.com 'a-strong-password' 'Your name'
    python3 server.py

Open http://localhost:3000 and log in with that email. **An admin can only be created or promoted with `make_admin.py`** (it works directly on the database, also for an existing account). Nobody becomes an admin by registering, whatever email they use.
Production: `gunicorn -w 1 --threads 8 -b 127.0.0.1:3000 server:app`

**Using an existing `cda.db`:** drop it into the new project folder. The schema upgrades itself (new columns, tables and indexes), and students and their progress are kept. Progress on old lessons carries over to the new material automatically.

### Environment variables

Settings are read from `.env` automatically (`envfile.py`; real environment variables win; `CDA_NO_DOTENV=1` disables it). Full annotated list: `.env.example`. Deployment steps: **`DEPLOY.md`**.

| Variable | Purpose |
|---|---|
| `PORT` | Port (3000) |
| `BASE_URL` | Public address used in email links (`https://academy.ge`) |
| `DB_FILE` / `BACKUP_DIR` | Database file / backup folder (default: `cda.db` in the project folder / `backups/` next to the database) |
| `AUTO_BACKUP=0` | Disables the automatic daily backup (on by default, the last 14 are kept) |
| `ALLOWED_HOSTS` | Comma-separated domains; requests with any other Host are rejected |
| `TRUST_PROXY=1`, `TRUST_PROXY_COUNT` | Behind nginx/Caddy/Cloudflare: number of trusted proxies (default 1). The client IP is taken from the **end** of `X-Forwarded-For` |
| `SECURE_COOKIE=1` | Secure flag on the cookie (also automatic over HTTPS, or `X-Forwarded-Proto` when `TRUST_PROXY=1`) |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_SECURITY`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` | Email (verification and reset codes). Without `SMTP_HOST` emails are printed to the console and the server prints a warning at startup. Check with `python3 tools/test_mail.py you@example.com` |
| `CODE_RESEND_SECONDS`, `CODE_IP_SENDS_PER_HOUR`, `CODE_VERIFY_IP_LIMIT` | Code limits: minimum gap before a new code (60), codes sent per IP per hour (30), code submissions per IP per 10 minutes (30) |
| `REQUIRE_EMAIL_VERIFY=0` | Turns off the email verification requirement (on by default) |
| `AUDIT_DAYS` | How long the security log is kept (90) |
| `LOGIN_IP_LIMIT`, `LOGIN_PAIR_LIMIT`, `REGISTER_LIMIT` | Rate limits per 10 minutes (30 / 10 per IP+email / 10) |
| `MENTOR_EMAIL` | Where new questions/tasks are emailed (comma-separated). Default: all admin accounts |
| `QUIZ_MAX_FAILS`, `QUIZ_PAUSE_MINUTES` | After every 3rd failed attempt on a lesson the answers and explanations are shown and the quiz pauses for 20 minutes; the next attempt uses new questions when the bank is big enough |
| `PAY_INFO`, `CONTACT`, `MENTOR_NAME` | Texts shown on the site |

## Project structure

- `server.py`: API, security, static files
- `auth.py`: password hashing, password strength rules, client IP from proxy headers (no side effects, safe to import)
- `mailer.py`: email sending (SMTP or console), error explanations
- `envfile.py`: loads `.env` without extra packages
- `tools/test_mail.py`: checks the SMTP settings and explains the error
- `common_passwords.txt`: list of common passwords (hand-compiled and small; replace or extend it, e.g. with SecLists `10k-most-common.txt`)
- `EXPERT_REVIEW.md`: claims in the lessons that could not be confirmed by a source (expert to review); `SOURCES.md`: sources per lesson
- `validate_content.py`: checks `content.json` (run `python3 validate_content.py`, `--strict` also fails on warnings); it is part of the tests
- `db.py`: database, migrations (automatic backup before a schema change), backups, course loading
- `tools/fetch_fonts.py`: downloads the self-hosted fonts into `public/fonts/`
- `content.json`: **the course material** (8 stages, 28 lessons; the database is refreshed on restart, and video/PDF links entered by the admin are not overwritten)
- `plans.py`: **plans and prices**
- `public/`: the frontend (`index.html`, `css/style.css`, `js/app.js`, `js/theme.js`, `img/`)
- `test_api.py`: tests: `python3 test_api.py`

### Design and fonts

The whole site uses **Inter**, except code, which is monospaced. Inter has no Georgian glyphs, so Georgian text falls back to **Noto Sans Georgian** automatically. Both fonts are **self-hosted** in `public/fonts/` (run `python3 tools/fetch_fonts.py`; see `public/fonts/README.txt`). No request goes to Google. The font stack and all colors are variables at the top of `public/css/style.css`:

- `--sans`: font stack (`--serif` is an alias of it, kept so older rules still work)
- `--mono`: font for code
- `--bg`, `--card`, `--ink`, `--ln`: background, cards, text, borders
- `--pri`, `--btn`, `--btnh`, `--onbtn`, `--link`: accent color, buttons, button text, links

There are two blocks: `:root` (light theme) and `:root[data-theme=dark]` (dark theme). The theme toggle is in the top navigation.

### content.json format

Each stage has `stage` (number), `title`, `description` and `lessons`. Each lesson has `title`, `minutes`, `objectives` (list), `content`, `task`, `bonus` and `quiz` (`q` = question, `o` = options, `a` = index of the correct answer starting at 0, `e` = explanation).

Supported markup in text: `## heading`, `### subheading`, `- list`, `1. numbered list`, `> note`, `| table |`, `**bold**`, `` `code` ``, fenced code blocks, links `[text](https://...)` (https only, open in a new tab with `noopener noreferrer`) and images on their own line `![caption](/img/lessons/file.svg)` (only files from `public/img/lessons/`; svg, png, jpg, webp).

**Quiz bank:** `quiz` is a bank (aim for 10-12 questions per lesson). Each attempt draws 5 random questions with shuffled options; correct answers and explanations are revealed after a pass (70%) or after every 3rd failed attempt (then a 20 minute pause). A lesson can be marked done only after passing its quiz (the server enforces this; lessons already marked done before this rule stay done).

**Diagrams:** SVG files are shown with `<img>`, so they cannot use the page's fonts or theme. The ones in `public/img/lessons/` carry their own light background and use a system font stack; Georgian text needs a system font that has Georgian glyphs.

**Adding a new lesson:** append it at the end of its stage and do not reorder existing ones, because student progress is tied to a lesson's position. In the database the column `week` is a historical name and holds the stage number.

## Interactive code exercises

A lesson in `content.json` may have an optional `exercises` list (schema: STYLE_GUIDE.md, "როგორ იწერება სავარჯიშო"). The lesson page shows a button; only when the student presses it, an editor iframe is created (code on the left, output on the right, Run and Reset). Two types: `python` (runs in the student's browser with Pyodide inside a Web Worker; nothing runs on the server) and `html` (live preview).

**Files.** `public/sandbox/`: `editor.html/.css/.js` (the editor, no libraries), `preview.html` (html preview), `pyworker.js` (Worker), `runner.py` (runs the code and the checks; the same file is used by `validate_content.py` in real Python). `public/vendor/pyodide/` holds Pyodide itself.

**Setup (once, needs network):** `python3 tools/fetch_pyodide.py` downloads the pinned Pyodide version into `public/vendor/pyodide/`, verifies SHA-256 against jsDelivr's published hashes and writes `SHA256SUMS.txt` and `NOTICE.txt` (MPL-2.0, see `LICENSE-pyodide.txt`). `--check` re-verifies offline. Until it is run, python exercises open and tell the student that the environment could not load. Nothing is loaded from any CDN at runtime, and Pyodide loads only after the student opens an exercise.

**Security design.**
- The main site CSP is unchanged except `frame-src` gained `'self'` (the editor is a page of our own origin; X-Frame-Options stays `DENY` everywhere else).
- The editor is a separate page, `/sandbox/editor.html`, with its own CSP header, embedded as `<iframe sandbox="allow-scripts">` (no `allow-same-origin`): it has an opaque origin, so no cookies, no localStorage, no site API. It talks to the lesson page only through `postMessage` (the lesson page accepts messages only from iframes it created and does the localStorage saving itself).
- Both iframes are loaded by ordinary URL (`src`) with their own headers, never `srcdoc`/`blob:` documents, because whether those inherit the parent's CSP varies by browser and by case; a document loaded by URL is governed only by its own header, so the design does not depend on it. (A `blob:` URL is used only for the Worker script, because an opaque-origin page cannot start a Worker from a URL; that Worker's own CSP is the editor's.)
- Python code can reach no network: the editor CSP allows `connect-src` only for `/sandbox/pyworker.js`, `/sandbox/runner.py` and `/vendor/pyodide/`; in addition, `fetch`, `XMLHttpRequest`, `WebSocket` and friends are removed in the Worker after Pyodide loads (second layer only).
- html preview (`preview.html`): CSP `default-src 'none'` with inline script/style allowed, so the student's own `<script>`/`<style>` work but nothing external, no network, no forms, no frames, and `sandbox allow-scripts` as a CSP directive (opaque origin even if someone frames the page elsewhere).
- `/sandbox/*` and `/vendor/*` are public static files served with `Cross-Origin-Resource-Policy: cross-origin` and `Access-Control-Allow-Origin: *`, which an opaque-origin page needs; no other path got CORS.
- Python limit: 5 seconds per Run (all checks included); after that the Worker is terminated, the student is told, and the environment reloads. Output is cut at 20,000 characters. `input()` never reads the keyboard: the exercise supplies values (`stdin` field); when they run out the student gets an `EOFError` explanation.

**Checks are learning feedback only.** They show ✓/✗ per check (hidden checks show no label) but are never sent to the server and are not connected to lesson completion, quiz results or the certificate. They cannot be: the code and the checks run in the student's browser, and the exercise data (including hidden checks) is delivered to the browser. Only `solution` is kept out of the lesson JSON and fetched on demand (`/api/lesson/<id>/exercise/<exid>/solution`), which hides it from casual viewing, not from a determined student.

**Known limits.** An endless loop in a *html* exercise's own JavaScript can freeze that browser tab (it cannot be killed like the Worker); memory-hungry Python is limited only by the browser; stdlib modules that Pyodide ships as separate packages (e.g. `ssl`, `sqlite3`) are not loaded. Student work is saved in the browser's localStorage per lesson and exercise (`cda-ex:<lesson id>:<exercise id>`).

**Tests.** `validate_content.py` checks the schema and, for every python exercise, really runs `solution` (must pass all checks) and `starter` (must fail at least one) with `public/sandbox/runner.py`, 10 s timeout; for html exercises a minimal DOM does the same. `test_api.py` covers headers, the solution endpoint and the validator. `tools/test_sandbox.py` (Playwright + Chromium) drives the real lesson page against a *stub* Pyodide and checks isolation, CSP, the 5-second limit and Worker restart, saving/Reset, Tab/Escape and the html preview. **Not covered anywhere: real Pyodide in a real browser** (manual check: run `tools/fetch_pyodide.py`, open the exercises of lessons 6.1 and 6.2, press Run on the starter, then on the solution from "ამოხსნის ჩვენება", and try `while True: pass`).

## Lesson videos

Each lesson can have a main video and a backup video. The lesson page shows the video, and under it the title and channel (if known), plus a link to the backup video. The admin panel ("Materials" tab and the editor on the lesson page) edits the video link, title, channel, backup link and PDF; changing a link without changing its title/channel clears the old title/channel so they never describe another video. The API (`POST /api/admin/lesson`) also accepts `video_title`, `video_channel`, `video2_url`, `video2_title`, `video2_channel`.

- `videos.csv` / `videos.md`: the researched list. Only rows marked "გადამოწმებული" (verified) are imported; the link was seen verbatim in a search result or an opened page (column `evidence`). Nobody has watched the videos: a person should review them first.
- `python3 import_videos.py` is a dry run and does not change the database. `python3 import_videos.py --apply` writes after making a backup (`videos-import-….db` in `BACKUP_DIR`). Links are validated like in the admin API (https only). A link an admin already entered is not overwritten unless `--overwrite`. Lessons are matched by (stage, position), not by id.
- The database schema must be current (start the server once). Rebuild the files after editing the data in `tools/build_videos.py`.

## Security

- Admins exist only through `make_admin.py`; registering never gives a role
- Passwords: scrypt with a salt; **new passwords must be at least 15 characters** (`MIN_PW_LEN` in `auth.py`, applied to registration, reset, change and `make_admin.py`; max 200). No character-type rules; spaces and Unicode are fine, so a phrase works. This follows NIST SP 800-63B-4 for password-only sign-in. Existing users are not affected: login does not check length, and the rule applies only when a password is chosen or changed. Rejected: common passwords (`common_passwords.txt`), sequences (`12345678`, `a1b2c3d4`, keyboard rows), repeats, "word + digits/symbols" (`Summer2024!`, also with leet-speak), and anything containing the email name
- **Email codes (verification and password reset):** a 6-digit code (`secrets`), stored only as a salted HMAC hash, valid 10 minutes, single use, locked after 5 wrong attempts (the check runs in one transaction, so parallel requests cannot get more tries). The email subject never contains the code. Sending: at least 60 seconds apart and at most 5 per hour per IP+email, 30 per hour per IP, and at most 10 codes per hour per account whatever the IP (limits the guessing surface for an attacker who rotates IPs; trade-off: an attacker can keep a victim from getting a fresh code for up to an hour). Limit counters are in memory (`gunicorn -w 1`).
- **Registration (verification on):** name + email → code by email → on the code page the user chooses the password (normal strength rules) → the account is verified and logged in. Until then the account has **no password** (the registration request cannot set one), so registering somebody else's email gives the registrant nothing. Verification ends every existing session and issues a new one. The answer to registration is the same for a new and an existing email; an existing verified owner gets an "account already exists" email (throttled). An unverified account cannot log in (same error as a wrong password) and is blocked from plans, mentor questions, task submission and certificates. `POST /api/verify` (`email`, `code`, `password`) and `POST /api/verify/resend` (`email`, neutral answer). Existing verified users are not touched; a legacy unverified account with an old password gets a new password when verified. With `REQUIRE_EMAIL_VERIFY=0` the old flow remains (password at registration, auto login, 409 for an existing email).
- Password reset by code: `POST /api/password/forgot` (`email`) then `POST /api/password/reset` (`email`, `code`, `password`). The "forgot" answer is identical for existing, unknown and admin addresses. Using the code ends all sessions; a weak password is rejected without spending the code (and without counting against the attempt limits). Admin passwords are not resettable by email (use `make_admin.py`; it also deletes pending codes).
- Certificates need all lessons done **and** a mentor-approved final project (kind `capstone`, approved in Admin > Questions and tasks). The number is random (`CDA-` + 12 hex), stored in the database, and the date and name are fixed when it is issued. Public check: `#/verify/CDA-XXXXXXXXXXXX` (shows only name, date, course). Deleting an account keeps the certificate number, date and course but removes the owner's name (the public check shows "verified certificate" without a name); order records stay anonymized (user id 0; amount, plan and date remain), pending requests are deleted
- Session tokens are stored in the database as **hashes**; at most 10 sessions per user; changing the password ends the other sessions
- Client IP: only the trusted proxy count (`TRUST_PROXY_COUNT`) is used; the left part of `X-Forwarded-For` is ignored. Login limits are per IP and per IP+email, so nobody can lock another person out of their account
- CSRF: cookie `SameSite=Lax`, Origin/Referer checks, and the API only accepts JSON requests that carry the `X-Requested-With: cda` header
- CSP without inline scripts or styles and without third-party fonts (`style-src 'self'`, `font-src 'self'`), `object-src 'none'`, `upgrade-insecure-requests` (on HTTPS), HSTS, COOP/CORP, `nosniff`, `X-Frame-Options`
- **Audit log:** logins, failed logins (with IP), password changes/resets and every admin action (Admin panel: "Log"). Kept 90 days; on account deletion the user id, IP and email are removed from it
- An admin cannot change another admin's password or delete an admin; the CSV export is protected against Excel formula injection
- The database file and backups use `600` permissions; account deletion is an atomic transaction
- Before any schema change a backup `premigrate-v<N>-….db` is written (never rotated away)
- Files starting with `.` and everything outside `public/` are not served

## Admin panel

- **Overview:** students, paying users, revenue, new and active users, average progress and quiz score, a signups chart, progress per stage, and a database backup button
- **Requests:** pending plan requests and history (who, when, how much)
- **Students:** search, plan filter, pagination, progress, last login, plan assignment, password reset, deletion, CSV export
- **Questions and tasks:** filter (unanswered / tasks / all), answer editing and an approve button for tasks and final projects (the student gets an email)
- **Materials:** the video and PDF link of every lesson in one table
- **Log:** security and admin events

## Before going public

Follow **`DEPLOY.md`** (HTTPS, proxy settings, SMTP, backups, checklist). In short:

- Start with a fresh database (do not publish your development `cda.db`; it contains your account).
- Test the whole email cycle (register, code, choose password, password reset) with real SMTP, starting with `python3 tools/test_mail.py`.
- Copy `backups/` elsewhere from time to time (the 3-2-1 rule) and test a restore once.
- The terms and privacy pages (`#/terms`, `#/privacy`) are templates: have a lawyer review them.
