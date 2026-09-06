# Mahamana Malviya Inter College — Website + Admin CMS (Python/Flask)

A complete school website with a secure, role-based Admin system:
- **Super Admin** — full control: the separate **Website Customization CMS** (design, branding, fonts,
  homepage sections, teachers, gallery), Manage Team, Email Settings, Activity Log, Backup & Restore.
- **Admin** — day-to-day operations only: Admissions, Complaints, Contact Messages, Notices.
- **Teacher** — a separate limited portal: Notifications, Admission Requests (view-only), Notices.

Everything runs on **one shared Flask backend and one shared database** — the public website and every
admin area read and write the same data, so changes appear instantly, with no duplication.

**More guides:**
- [`INSTALL_GUIDE.md`](INSTALL_GUIDE.md) — step-by-step localhost setup
- [`SMTP_GUIDE.md`](SMTP_GUIDE.md) — email configuration (Gmail App Passwords, etc.)
- [`BACKUP_RESTORE_GUIDE.md`](BACKUP_RESTORE_GUIDE.md) — backing up and restoring your data
- [`TESTING_CHECKLIST.md`](TESTING_CHECKLIST.md) — full checklist to verify everything works after changes

Built with **only HTML, CSS, JavaScript, and Python** (Flask — a lightweight
Python library, not a separate language) as requested. No Node.js, no PHP.

---

## 1. Requirements

- [Python 3.9 or newer](https://www.python.org/downloads/) installed on your
  computer. During installation on Windows, **tick "Add Python to PATH"**.

That's it — no database server to install. The project uses SQLite, which is
a single file and is built into Python.

---

## 2. How to run it (step by step)

1. Extract the project zip folder anywhere on your computer, e.g. Desktop.
2. Open a terminal / Command Prompt in that folder:
   - **Windows:** open the folder in File Explorer, click the address bar,
     type `cmd`, and press Enter.
   - **VS Code:** open the folder (`File → Open Folder`), then
     `Terminal → New Terminal`.
3. Install Flask (only needed once):
   ```
   pip install -r requirements.txt
   ```
4. Start the website:
   ```
   python app.py
   ```
5. You'll see:
   ```
   Default admin account created:
      username: MMIC
      password: MMIC
   * Running on http://127.0.0.1:5000
   ```
6. Open your browser and go to: **http://127.0.0.1:5000**
7. Click **Admin Login** (top-right of the navbar), then log in with:
   - Username: `MMIC`
   - Password: `MMIC`

**Important:** keep the terminal window open while you use the site — closing
it stops the server. To start it again later, just run `python app.py` again
from the project folder.

**Change the default password** as soon as possible from
**Admin Dashboard → change password** (top of the sidebar) — `MMIC/MMIC` is
easy to guess and should not be used with real student data.

---

## 3. Folder structure

```
mmic-python/
├── app.py                   All website + admin logic (Flask routes)
├── database.py               Creates the database tables and default data
├── schema.sql                 The database table definitions (SQL)
├── requirements.txt            The two Python libraries this needs
├── data/
│   └── mmic.db                  The database file (created automatically)
├── backups/                      Downloadable backup .db files go here
├── static/
│   ├── css/
│   │   ├── style.css               Public website styling
│   │   └── admin.css                Admin dashboard styling
│   ├── js/
│   │   └── admin.js                  Admin dashboard interactivity (rich
│   │                                   text editor, image preview, confirm
│   │                                   dialogs, notifications)
│   └── uploads/
│       ├── hero/                       Hero banner images
│       ├── gallery/                     Gallery photos
│       ├── notices/                      Notice/circular PDFs
│       ├── teachers/                      Staff photos
│       └── branding/                       Logo, favicon, principal photo
└── templates/
    ├── index.html                Public homepage (the one page visitors see)
    └── admin/
        ├── base.html                Shared sidebar + layout for all admin pages
        ├── login.html                 Admin login page
        ├── dashboard.html               Stats + charts overview
        ├── hero.html                     Hero banner management
        ├── gallery.html                    Gallery management
        ├── notices.html                     Notices/circulars management
        ├── teachers.html                      Staff management
        ├── content.html                        About/Principal/Admissions/
        │                                         Contact text editing
        ├── branding.html                          Logo/favicon/school name
        ├── sections.html                           Show/hide homepage sections
        ├── admissions.html                          View admission form
        │                                             submissions
        ├── complaints.html                            View & reply to
        │                                                complaints
        ├── contact_messages.html                       View & reply to
        │                                                 Contact Us messages
        ├── activity_log.html                             Who changed what,
        │                                                   and when
        └── backup.html                                     Create/download/
                                                              restore backups
```

---

## 4. How the pieces fit together

### HTML structure
- `templates/index.html` is the **only** public-facing page. It's built with
  Jinja2 (Flask's templating language — still plain HTML with `{{ }}` and
  `{% %}` placeholders that Python fills in). Every section (Hero, About,
  Gallery, Notices, Admissions, Contact, etc.) reads its content from the
  database instead of being hardcoded, so editing it in the Admin Dashboard
  changes the live page immediately, with no code edits.
- `templates/admin/base.html` holds the shared sidebar and page frame; every
  other `admin/*.html` file "extends" it (`{% extends "admin/base.html" %}`)
  and only defines its own middle content — so the whole dashboard looks and
  behaves consistently.

### CSS structure
- `static/css/style.css` — styles the **public website only** (navy/gold
  theme, hero banner, cards, forms, responsive layout).
- `static/css/admin.css` — styles the **admin dashboard only** (sidebar,
  stat cards, data tables, modals, badges, buttons). Kept separate on
  purpose so editing one never accidentally breaks the other.

### JavaScript structure
- `static/js/admin.js` is loaded on every admin page and provides:
  - the rich text editor (bold/italic/lists/links toolbar using the
    browser's built-in `execCommand`, no external library),
  - image preview before you click Upload,
  - "Are you sure?" confirmation before any delete,
  - success/error toast notifications,
  - simple client-side search/filter on data tables.
- The public site's JavaScript (translation switcher etc., if present) lives
  inline inside `templates/index.html`.

### Python backend structure (`app.py`)
Routes are grouped into clear sections (search for these comments inside
`app.py`):
1. **Helpers** — file upload validation/saving, login-required decorator,
   activity logging.
2. **Public routes** — the homepage (`/`), and the three public form
   submission endpoints (`/admission/submit`, `/complaint/submit`,
   `/contact/submit`).
3. **Admin auth** — `/admin/login`, `/admin/logout`, change password.
4. **Admin management routes** — one clear group per feature: Hero,
   Gallery, Notices, Teachers, Content/Text, Branding, Sections,
   Admissions, Complaints, Contact Messages, Activity Log, Backup/Restore.

Every admin route (except the login page itself) is protected by
`@login_required` — a small function that checks you're actually logged in
before allowing access, and sends you to the login page otherwise.

### Database (`schema.sql` / `database.py`)
- `schema.sql` defines every table: `admins`, `settings` (all editable text
  like About/Admissions/Contact info + branding, stored as simple key-value
  pairs), `hero_slides`, `gallery`, `notices`, `teachers`, `sections`
  (show/hide toggles), `admissions`, `complaints`, `contact_messages`, and
  `activity_log`.
- `database.py` creates these tables the first time you run the app, and
  seeds a default admin account plus sensible starting content so the site
  isn't empty on first run.

---

## 5. Step-by-step: using each Admin Dashboard page

After logging in, the left sidebar takes you to every section:

1. **Dashboard** — quick stats (admissions, complaints, messages) and recent
   activity at a glance.
2. **Hero Banner** — add/edit/delete homepage banner slides (heading,
   subtext, button, background image). Turn a slide on/off without deleting
   it.
3. **Gallery** — upload photos with a caption; delete anytime. Photos appear
   on the public Gallery section in the order you set.
4. **Notices & Circulars** — upload a PDF with a title and description;
   visitors can view/download it from the public site. Toggle
   published/unpublished.
5. **Teachers & Staff** — add/edit/delete staff cards (name, role, subject,
   bio, photo).
6. **Content / Text Sections** — edit About text, Principal bio, Admission
   info, Contact info, and general site settings — all from simple forms,
   no code.
7. **Branding** — upload logo and favicon, set school name and motto.
8. **Sections** — a simple on/off switch for every homepage section (Hero,
   About, Gallery, Notices, etc.) if you want to temporarily hide one.
9. **Admissions** — view every submitted admission form, change its status,
   delete, or export to CSV.
10. **Complaints** — view submitted complaints (with their auto-generated
    Complaint ID and any attachment), reply, change status
    (Pending/In Progress/Resolved), delete, or export.
11. **Contact Messages** — view and reply to messages from the public
    Contact Us form.
12. **Activity Log** — a running history of every change made from the
    dashboard (who did what, and when) — useful for accountability if more
    than one person has admin access.
13. **Backup & Restore** — create a downloadable backup of the entire
    database at any time; restore from a previously downloaded backup file
    if something goes wrong.

---

## 6. Security features already included

- Passwords are hashed with Werkzeug's `generate_password_hash` — never
  stored in plain text.
- Sessions are signed and expire automatically after 2 hours of inactivity.
- Every admin page checks you're logged in before showing anything.
- All form inputs are validated on the server.
- File uploads are restricted by type (only images for photos, only PDFs for
  notices) and by size (8MB max).
- Uploaded files get randomly generated filenames, so an attacker can't
  guess or overwrite another file.

**Before deploying this on the public internet** (rather than just your own
computer), please also:
- Set a real `SECRET_KEY` (currently auto-generated on each run — fine for
  local use, but set a fixed one via an environment variable for a real
  deployment so logins don't get invalidated on every restart).
- Turn off debug mode: in `app.py`, change `debug=True` to `debug=False` in
  the very last line before deploying for real.
- Serve it over HTTPS via a proper web server (e.g. behind Nginx), not the
  built-in development server.
- Take regular backups using the Backup page.

---

## 7. Adding your own background images

You mentioned you'll provide background images separately. Once you have
them:
- **Hero banner images** — upload directly from **Admin → Hero Banner →
  Add Slide**, no code needed.
- **Logo / favicon** — upload from **Admin → Branding**.
- **Login page background** — if you'd like a specific photo behind the
  Admin Login form itself (like the college gate photo used before), send
  it over and it can be wired in the same way, or you can manually place the
  file in `static/uploads/branding/` and reference it in
  `templates/admin/login.html`.

---

## 8. If something goes wrong

- **"pip is not recognized"** — Python wasn't added to PATH during install.
  Reinstall Python and tick "Add Python to PATH", or use `py -m pip install
  -r requirements.txt` instead.
- **"Address already in use"** — another program (or a previous run of this
  app) is already using port 5000. Close the other terminal window, or
  change `port=5000` to `port=5050` in the last line of `app.py`.
- **Changes don't show on the public site** — make sure you clicked "Save"
  and check the Activity Log to confirm the change was recorded.
- Any other error — copy the exact error text from the terminal and share
  it; it usually points straight to the fix.
