# database.py
# Handles the SQLite database: connecting, creating tables on first run,
# and seeding sensible default content so the site isn't empty when the
# admin logs in for the very first time.

import sqlite3
import os
import re
import secrets
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'data', 'mmic.db')
SCHEMA_PATH = os.path.join(BASE_DIR, 'schema.sql')

DEFAULT_SECTIONS = [
    ('hero', 'Hero Banner', 1, 1),
    ('about', 'About School', 1, 2),
    ('principal', 'Principal', 1, 3),
    ('teachers', 'Teachers & Staff', 1, 4),
    ('gallery', 'Gallery', 1, 5),
    ('notices', 'Notices & Circulars', 1, 6),
    ('admissions', 'Entrance Examination Admission Form', 1, 7),
    ('complaints', 'Complaint / Feedback', 1, 8),
    ('contact', 'Contact Us', 1, 9),
    ('alumni', 'Old Students (Alumni)', 1, 10),
    ('sports', 'Sports', 1, 11),
    ('result', 'Result', 1, 12),
]

DEFAULT_SETTINGS = {
    'site_title': 'Mahamana Malviya Inter College',
    'site_motto': 'Gyanam Param Balam',
    'logo_path': '',
    'favicon_path': '',
    'founder_photo': '',
    'hero_eyebrow': 'In the spirit of Mahamana',
    'hero_tagline': 'Where every student is shaped into a lamp that lights another.',
    'font_family': "'Segoe UI', system-ui, sans-serif",
    'font_size_base': '16',
    'font_weight_base': '400',
    'text_color': '',
    'line_height': '1.6',
    'letter_spacing': '0',
    'smtp_host': 'smtp.gmail.com',
    'smtp_port': '587',
    'smtp_username': '',
    'smtp_password': '',
    'smtp_from_name': 'Mahamana Malviya Inter College',
    'about_heading': 'About the College',
    'about_text': (
        'Mahamana Malviya Inter College was founded to make quality education '
        'accessible to the students of Varanasi and the surrounding region, in '
        'keeping with the vision of Pandit Madan Mohan Malaviya — the belief '
        'that education is the strongest tool for building character and nation.'
    ),
    'established_year': '1968',
    'board': 'UP Board',
    'classes_offered': 'VI - XII',
    'medium': 'Hindi / English',
    'total_students': '3,600+',
    'board_result': '90%+ Pass Rate',
    'faculty_count': '85+',
    'school_location_short': 'Bachchhaon, Varanasi',
    'principal_name': 'Dr. Chandramani Singh',
    'principal_bio': (
        'Dr. Chandramani Singh is a native of Kolna village in Mirzapur district, '
        'Uttar Pradesh. He completed his B.Sc., M.Sc., and Ph.D. from Agra '
        'University. He began his teaching career in 1992 as a Lecturer in '
        'Agriculture at Sardar Patel Inter College, Kolna, Mirzapur, and was '
        'appointed Principal of Mahamana Malviya Inter College, Bachhawn, '
        'Varanasi, on 22 February 2000.'
    ),
    'principal_photo': '',
    'site_title_bold': '0',
    'admission_info': (
        '1. Collect the admission form from the school office or download it here.\n'
        '2. Submit documents: birth certificate, transfer certificate, photographs.\n'
        '3. A short interaction with the class teacher for Class III and above.\n'
        '4. Complete the admission fee to confirm your seat.'
    ),
    'contact_address': 'Mahamana Malviya Inter College, Bachchhaon, Varanasi, Uttar Pradesh, India',
    'contact_phone': '+91 95546 95694',
    'contact_email': 'r21871928@gmail.com',
    'contact_hours': 'Monday - Saturday, 8:00 AM - 2:00 PM',
}


def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    conn.execute('PRAGMA busy_timeout = 8000')
    return conn


def init_db(default_admin_user='MMIC', default_admin_pass='AmitKumarMMIC@12345'):
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_db()
    with open(SCHEMA_PATH, 'r', encoding='utf-8') as f:
        conn.executescript(f.read())

    # --- Migration: add any new admins columns if this is an older database file ---
    existing_cols = [r['name'] for r in conn.execute('PRAGMA table_info(admins)').fetchall()]
    migrations = {
        'email': "ALTER TABLE admins ADD COLUMN email TEXT",
        'role': "ALTER TABLE admins ADD COLUMN role TEXT DEFAULT 'admin'",
        'status': "ALTER TABLE admins ADD COLUMN status TEXT DEFAULT 'active'",
        'permissions': "ALTER TABLE admins ADD COLUMN permissions TEXT DEFAULT ''",
        'failed_attempts': "ALTER TABLE admins ADD COLUMN failed_attempts INTEGER DEFAULT 0",
        'locked_until': "ALTER TABLE admins ADD COLUMN locked_until TEXT",
        'last_login': "ALTER TABLE admins ADD COLUMN last_login TEXT",
        'must_change_password': "ALTER TABLE admins ADD COLUMN must_change_password INTEGER DEFAULT 0",
    }
    for col, ddl in migrations.items():
        if col not in existing_cols:
            conn.execute(ddl)

    # Migration: add mobile_number to teachers table for existing databases
    teacher_cols = [r['name'] for r in conn.execute('PRAGMA table_info(teachers)').fetchall()]
    if 'mobile_number' not in teacher_cols:
        conn.execute("ALTER TABLE teachers ADD COLUMN mobile_number TEXT")

    # Seed default admin if none exists
    existing = conn.execute('SELECT COUNT(*) AS c FROM admins').fetchone()['c']
    if existing == 0:
        conn.execute(
            'INSERT INTO admins (username, password_hash, role, status) VALUES (?, ?, ?, ?)',
            (default_admin_user, generate_password_hash(default_admin_pass), 'super_admin', 'active')
        )
        print('================================================')
        print(' Default admin account created:')
        print(f'   username: {default_admin_user}')
        print(f'   password: {default_admin_pass}')
        print(' Role: Super Admin')
        print(' Please change this password from the dashboard')
        print(' before using the site with real data.')
        print('================================================')

        # Also seed a default Normal Admin account (day-to-day access only —
        # no Website Customizer, no Manage Team, nothing Super-Admin-related).
        default_normal_admin_pass = 'Admin@12345'
        conn.execute(
            'INSERT INTO admins (username, password_hash, role, status) VALUES (?, ?, ?, ?)',
            ('ADMIN', generate_password_hash(default_normal_admin_pass), 'admin', 'active')
        )
        print('================================================')
        print(' Default Normal Admin account created:')
        print('   username: ADMIN')
        print(f'   password: {default_normal_admin_pass}')
        print(' Role: Normal Admin (day-to-day only — no customization access)')
        print(' Change this from Manage Team > Set Password after logging in as Super Admin.')
        print('================================================')
    else:
        # Make sure at least one pre-existing account (from before roles existed) is a super_admin
        any_super = conn.execute("SELECT COUNT(*) AS c FROM admins WHERE role = 'super_admin'").fetchone()['c']
        if any_super == 0:
            conn.execute("UPDATE admins SET role = 'super_admin' WHERE id = (SELECT MIN(id) FROM admins)")
        conn.execute("UPDATE admins SET role = 'admin' WHERE role IS NULL OR role = ''")
        conn.execute("UPDATE admins SET status = 'active' WHERE status IS NULL OR status = ''")

        # One-time safe upgrade: if the MMIC account still has the OLD default password ('MMIC'),
        # move it to the new default. This never touches an account where the password was
        # already changed by the person using it.
        mmic_row = conn.execute("SELECT * FROM admins WHERE username = ?", (default_admin_user,)).fetchone()
        if mmic_row and check_password_hash(mmic_row['password_hash'], 'MMIC'):
            conn.execute("UPDATE admins SET password_hash = ? WHERE id = ?",
                         (generate_password_hash(default_admin_pass), mmic_row['id']))
            print('================================================')
            print(f' Security update: the default password for "{default_admin_user}" was')
            print(f' upgraded from the old default to the new default: {default_admin_pass}')
            print(' Please change it from Account Settings after logging in.')
            print('================================================')

    # Seed default sections if empty
    existing_sections = conn.execute('SELECT COUNT(*) AS c FROM sections').fetchone()['c']
    if existing_sections == 0:
        conn.executemany(
            'INSERT INTO sections (section_key, label, enabled, display_order) VALUES (?, ?, ?, ?)',
            DEFAULT_SECTIONS
        )
    else:
        # Migration: add any NEW default sections (e.g. sports, alumni) that didn't exist
        # in an older database, without touching existing sections' enabled/order state.
        existing_keys = {r['section_key'] for r in conn.execute('SELECT section_key FROM sections').fetchall()}
        for key, label, enabled, order in DEFAULT_SECTIONS:
            if key not in existing_keys:
                conn.execute(
                    'INSERT INTO sections (section_key, label, enabled, display_order) VALUES (?, ?, ?, ?)',
                    (key, label, enabled, order)
                )
        # One-time reorder: move Old Students / Sports to the end of the homepage
        # (after Contact), matching the new required section order. This only moves
        # their POSITION — it never changes whether they're enabled or their content.
        reorder_map = {'alumni': 10, 'sports': 11, 'result': 12}
        for key, order in reorder_map.items():
            conn.execute('UPDATE sections SET display_order = ? WHERE section_key = ?', (order, key))

        # Remove the old, now-discontinued "Entrance Examination Admission" duplicate
        # section — the original Admissions form was renamed to take over that role,
        # so this separate section/toggle no longer applies.
        conn.execute("DELETE FROM sections WHERE section_key = 'entrance_exam'")
        # Fully retire the old duplicate applications table too, if an earlier run
        # of this project already created it on this machine.
        conn.execute("DROP TABLE IF EXISTS entrance_applications")

    # One-time safe upgrade: if "Classes Offered" is still at the old default ("I - XII"),
    # move it to the new default ("VI - XII") — this school only admits from Class 6 upward.
    # Never touches it if a Super Admin has already customized this field to something else.
    classes_row = conn.execute("SELECT value FROM settings WHERE key = 'classes_offered'").fetchone()
    if classes_row and classes_row['value'] == 'I - XII':
        conn.execute("UPDATE settings SET value = 'VI - XII' WHERE key = 'classes_offered'")

    # Seed the two Result categories if they don't exist yet
    for rkey, rlabel in [('class10', '10th Result'), ('class12', '12th Result')]:
        exists = conn.execute('SELECT 1 FROM results WHERE result_key = ?', (rkey,)).fetchone()
        if not exists:
            conn.execute('INSERT INTO results (result_key, label) VALUES (?, ?)', (rkey, rlabel))

    # Seed default settings if not present (only fill in missing keys)
    for key, value in DEFAULT_SETTINGS.items():
        row = conn.execute('SELECT 1 FROM settings WHERE key = ?', (key,)).fetchone()
        if not row:
            conn.execute('INSERT INTO settings (key, value) VALUES (?, ?)', (key, value))

    conn.commit()
    conn.close()


def get_settings():
    conn = get_db()
    rows = conn.execute('SELECT key, value FROM settings').fetchall()
    conn.close()
    return {row['key']: row['value'] for row in rows}


def password_policy_errors(password):
    """Returns a list of human-readable problems with a password, or [] if it's strong enough."""
    errs = []
    if not password or len(password) < 8:
        errs.append('At least 8 characters')
    if not re.search(r'[a-z]', password or ''):
        errs.append('At least one lowercase letter')
    if not re.search(r'[A-Z]', password or ''):
        errs.append('At least one uppercase letter')
    if not re.search(r'[0-9]', password or ''):
        errs.append('At least one number')
    if not re.search(r'[^A-Za-z0-9]', password or ''):
        errs.append('At least one special character (e.g. ! @ # $ %)')
    return errs


def set_setting(key, value):
    conn = get_db()
    conn.execute(
        'INSERT INTO settings (key, value) VALUES (?, ?) '
        'ON CONFLICT(key) DO UPDATE SET value = excluded.value',
        (key, value)
    )
    conn.commit()
    conn.close()


def log_activity(admin_username, action, details=''):
    conn = get_db()
    conn.execute(
        'INSERT INTO activity_log (admin_username, action, details) VALUES (?, ?, ?)',
        (admin_username, action, details)
    )
    conn.commit()
    conn.close()
