# Installation & Localhost Setup Guide

## 1. Requirements
- Python 3.10+ (tested on 3.12–3.14)
- Windows, macOS, or Linux
- No internet connection needed to run the site itself (only for the first `pip install`)

## 2. Extract the project
Unzip the project. You should see a folder that directly contains `app.py`, `requirements.txt`, `templates/`, `static/`, etc. Open **that exact folder** in VS Code — not a parent folder.

## 3. Install dependencies
Open a terminal inside that folder and run:

```
pip install -r requirements.txt
```

If `pip` isn't recognized, try `py -m pip install -r requirements.txt` (Windows) or `pip3 install -r requirements.txt` (Mac/Linux).

## 4. Run the app
```
python app.py
```

You should see:
```
Default admin account created:
   username: MMIC
   password: MMIC
   Role: Super Admin
* Running on http://127.0.0.1:5000
```

Keep this terminal window open — closing it stops the website.

## 5. Open the site
- Public website: http://127.0.0.1:5000
- Admin login: http://127.0.0.1:5000/admin/login (or click "Admin Login" on the homepage)

Log in with `MMIC` / `MMIC`, then immediately:
1. Go to **Account Settings** and set a strong new password.
2. Go to **Manage Team** → add your real email to your account (via Account Settings → Change Email) so password-reset and security emails work.
3. Go to **Email Settings** and configure SMTP (see `SMTP_GUIDE.md`).

## 6. Stopping / restarting
- Stop: press `Ctrl+C` in the terminal, or just close it.
- Restart later: open the folder in VS Code again, open a terminal (`Ctrl+` `` ` ``), run `python app.py` again. No need to `pip install` again unless you deleted the folder.

## 7. Where your data lives
Everything (accounts, pages, uploads' metadata, admissions, etc.) is stored in one file:
```
data/mmic.db
```
Uploaded images/PDFs live under `static/uploads/`. Back these up regularly — see `BACKUP_RESTORE_GUIDE.md`.

## 8. Common issues
| Problem | Fix |
|---|---|
| `Could not open requirements file` | You're in the wrong folder — `cd` into the folder that has `app.py` in it. |
| `python: command not found` | Install Python from python.org and make sure "Add to PATH" was checked during install. |
| Port 5000 already in use | Edit the last line of `app.py` and change `port=5000` to `port=5050` (or any free port). |
| Forgot the admin password | Use "Forgot password?" on the login page (requires Email Settings to be configured first). |
