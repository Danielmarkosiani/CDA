# CDA: Cyber & Digital Academy

Flask + SQLite (Python's built-in `sqlite3`). The frontend is plain HTML/CSS/JS, so there is no build step.

The interface language is Georgian. Course content lives in `content.json`.

## Running

    pip install -r requirements.txt
    ADMIN_EMAIL=you@example.com python3 server.py

Open http://localhost:3000 and register with exactly that email: you become the admin.
To promote an existing account instead, run `python3 make_admin.py email password`.
Production: `gunicorn -w 1 --threads 8 -b 127.0.0.1:3000 server:app`

**Using an existing `cda.db`:** drop it into the new project folder. The schema upgrades itself (new columns, tables and indexes), and students and their progress are kept. Progress on old lessons carries over to the new material automatically.

### Environment variables

| Variable | Purpose |
|---|---|
| `PORT` | Port (3000) |
| `DB_FILE` | Database file (defaults to `cda.db` in the project folder) |
| `BACKUP_DIR` | Backup folder (defaults to `backups/` next to the database) |
| `AUTO_BACKUP=0` | Disables the automatic daily backup (on by default, the last 14 are kept) |
| `ALLOWED_HOSTS` | Comma-separated domains (`academy.ge,www.academy.ge`); requests with any other Host are rejected |
| `PAY_INFO` | Payment details shown to a student after they submit a plan request |
| `CONTACT` | Contact line shown in the footer |
| `MENTOR_NAME` | Your name, shown in the mentor block |
| `TRUST_PROXY=1` | Set when the site runs behind nginx or Cloudflare |
| `SECURE_COOKIE=1` | Adds the Secure flag to the cookie (turned on automatically over HTTPS) |

## Project structure

- `server.py`: API, security, static files
- `db.py`: database, migrations, backups, course loading
- `content.json`: **the course material** (8 stages, 28 lessons; the database is refreshed on restart, and video/PDF links entered by the admin are not overwritten)
- `plans.py`: **plans and prices**
- `public/`: the frontend (`index.html`, `css/style.css`, `js/app.js`, `js/theme.js`, `img/`)
- `test_api.py`: tests (25 checks): `python3 test_api.py`

### Design and fonts

The whole site uses **Inter**, except code, which is monospaced. Inter has no Georgian glyphs, so Georgian text falls back to **Noto Sans Georgian** automatically (both load from Google Fonts in `index.html`). The font stack and all colors are variables at the top of `public/css/style.css`:

- `--sans`: font stack (`--serif` is an alias of it, kept so older rules still work)
- `--mono`: font for code
- `--bg`, `--card`, `--ink`, `--ln`: background, cards, text, borders
- `--pri`, `--btn`, `--btnh`, `--onbtn`, `--link`: accent color, buttons, button text, links

There are two blocks: `:root` (light theme) and `:root[data-theme=dark]` (dark theme). The theme toggle is in the top navigation.

### content.json format

Each stage has `stage` (number), `title`, `description` and `lessons`. Each lesson has `title`, `minutes`, `objectives` (list), `content`, `task`, `bonus` and `quiz` (`q` = question, `o` = options, `a` = index of the correct answer starting at 0, `e` = explanation).

Supported markup in text: `## heading`, `### subheading`, `- list`, `1. numbered list`, `> note`, `| table |`, `**bold**`, `` `code` ``, and fenced code blocks.

**Adding a new lesson:** append it at the end of its stage and do not reorder existing ones, because student progress is tied to a lesson's position. In the database the column `week` is a historical name and holds the stage number.

## Security

- Passwords: scrypt with a salt; weak passwords and passwords containing the email name are rejected
- Session tokens are stored in the database as **hashes**; at most 10 sessions per user; changing the password ends the other sessions
- CSRF: cookie `SameSite=Lax`, Origin/Referer checks, and the API only accepts JSON requests that carry the `X-Requested-With: cda` header
- CSP without inline scripts or styles, `object-src 'none'`, `upgrade-insecure-requests` (on HTTPS), HSTS, COOP/CORP, `nosniff`, `X-Frame-Options`
- Rate limits on login, registration, password change and account deletion; `ALLOWED_HOSTS` protects against Host spoofing
- **Audit log:** logins, failed logins (with IP), password changes and every admin action (Admin panel: "Log")
- An admin cannot change another admin's password or delete an admin; the CSV export is protected against Excel formula injection
- The database file and backups use `600` permissions; account deletion is an atomic transaction
- Files starting with `.` and everything outside `public/` are not served

## Admin panel

- **Overview:** students, paying users, revenue, new and active users, average progress and quiz score, a signups chart, progress per stage, and a database backup button
- **Requests:** pending plan requests and history (who, when, how much)
- **Students:** search, plan filter, pagination, progress, last login, plan assignment, password reset, deletion, CSV export
- **Questions and tasks:** filter (unanswered / tasks / all) and answer editing
- **Materials:** the video and PDF link of every lesson in one table
- **Log:** security and admin events

## Before going public

- **HTTPS is required** (Caddy, or nginx + Let's Encrypt). Set `ALLOWED_HOSTS` and `TRUST_PROXY=1`.
- Automatic backups are stored in `backups/`: copy them elsewhere from time to time (the 3-2-1 rule).
- The terms and privacy pages (`#/terms`, `#/privacy`) are templates: have a lawyer review them.
- There is no email password recovery: the "Password" button in the admin panel generates a temporary password.
- Do not publish the test `cda.db` (admin@gmail.com): start with a fresh database.
