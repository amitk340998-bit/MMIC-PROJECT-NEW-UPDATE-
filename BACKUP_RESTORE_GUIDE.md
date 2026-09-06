# Backup & Restore Guide

Your entire website's data (accounts, pages, settings, admissions, complaints, messages) lives in one
SQLite file: `data/mmic.db`. Uploaded photos/PDFs live separately in `static/uploads/`.

## Creating a backup (Super Admin only)
1. Log in as a **Super Admin**.
2. Go to **Backup & Restore** (in the Super Admin section of the sidebar).
3. Click **Create Backup Now**. A timestamped copy of the database (e.g. `backup_20260809_143000.db`)
   is saved in the `backups/` folder.
4. Click **Download** next to any backup to save a copy to your own computer (recommended — don't rely
   only on the copy sitting on the same machine).

**How often?** Weekly is reasonable for a low-traffic school site; do it right before any big change
(e.g. before a bulk data import, before restoring, before upgrading the code).

## Restoring a backup (Super Admin only)
1. Go to **Backup & Restore**.
2. Under **Restore from Backup File**, choose a `.db` file (either one you downloaded earlier, or any
   valid backup of this same database).
3. Click **Restore**. The site automatically saves a safety copy of whatever database was active
   *before* the restore (named `before_restore_<timestamp>.db`), so a mistaken restore is itself
   reversible.
4. You'll be logged out automatically after a restore — log back in with whatever credentials existed
   in the restored backup.

⚠️ **Restoring replaces everything** — accounts, settings, uploads' database records — with what's in
that backup file. Anything created after that backup was taken will be lost from the database (uploaded
files themselves in `static/uploads/` are not touched, only the database records referencing them).

## Manual backup (outside the website)
You can also just copy these two things with the site stopped:
```
data/mmic.db
static/uploads/   (whole folder)
```
Paste them back into a fresh copy of the project folder to fully restore, including files.

## Moving to a new computer
1. Copy the whole project folder, including `data/` and `static/uploads/`.
2. On the new machine, follow `INSTALL_GUIDE.md` from step 3 (skip step "Default admin account created"
   messaging if `data/mmic.db` already exists — your existing accounts will just work).
