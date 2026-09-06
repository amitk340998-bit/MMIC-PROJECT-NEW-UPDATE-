-- schema.sql
-- Full database schema for the Mahamana Malviya Inter College website
-- and its Admin Dashboard (CMS). SQLite database.

CREATE TABLE IF NOT EXISTS admins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    email TEXT,
    password_hash TEXT NOT NULL,
    role TEXT DEFAULT 'admin',              -- 'super_admin' | 'admin' | 'teacher'
    status TEXT DEFAULT 'active',           -- 'active' | 'disabled'
    permissions TEXT DEFAULT '',            -- comma-separated extra permission keys (for future fine-tuning)
    failed_attempts INTEGER DEFAULT 0,
    locked_until TEXT,
    last_login TEXT,
    must_change_password INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);

-- One-time codes for email-change verification and password reset
CREATE TABLE IF NOT EXISTS otp_codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_id INTEGER NOT NULL,
    code TEXT NOT NULL,
    purpose TEXT NOT NULL,          -- 'email_change_old' | 'email_change_new' | 'password_reset'
    target_email TEXT,              -- for email_change_new: the email being verified
    expires_at TEXT NOT NULL,
    used INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);

-- Device-specific login lockout tracking. Each row represents one (account, browser/device)
-- pair. A device is identified by a random token stored in a long-lived cookie on that
-- browser — this is NOT the same as an IP address, since IPs are shared/change. The IP is
-- also recorded here for audit/monitoring, but is never used as the sole lockout key.
CREATE TABLE IF NOT EXISTS login_lockouts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_id INTEGER NOT NULL,
    device_id TEXT NOT NULL,
    ip_address TEXT,
    failed_attempts INTEGER DEFAULT 0,
    locked_until TEXT,
    last_attempt_at TEXT DEFAULT (datetime('now')),
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(admin_id, device_id)
);

-- Notifications for teachers/admins (e.g. "New admission request received")
CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_id INTEGER,               -- NULL = visible to all teachers
    title TEXT NOT NULL,
    message TEXT,
    link TEXT,
    is_read INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);

-- Generic key/value store for simple site-wide text fields:
-- site title, motto, about paragraphs, contact info, logo/favicon paths,
-- principal bio, etc. Anything that's "one value, one field" lives here so
-- new text fields can be added later without new tables.
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

-- Hero banner (Home page top section) — supports multiple slides
CREATE TABLE IF NOT EXISTS hero_slides (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    subtitle TEXT,
    image TEXT,
    button_text TEXT,
    button_link TEXT,
    display_order INTEGER DEFAULT 0,
    active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now'))
);

-- Gallery photos
CREATE TABLE IF NOT EXISTS gallery (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    caption TEXT,
    category TEXT,
    display_order INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);

-- Notices & Circulars (PDF uploads)
CREATE TABLE IF NOT EXISTS notices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    category TEXT DEFAULT 'Notice',
    file TEXT NOT NULL,
    published_date TEXT DEFAULT (datetime('now')),
    active INTEGER DEFAULT 1
);

-- Teachers / Staff
CREATE TABLE IF NOT EXISTS teachers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    role TEXT,
    subject TEXT,
    mobile_number TEXT,
    bio TEXT,
    photo TEXT,
    display_order INTEGER DEFAULT 0,
    active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    image TEXT,
    display_order INTEGER DEFAULT 0,
    active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS alumni (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    note TEXT,
    photo TEXT,
    display_order INTEGER DEFAULT 0,
    active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now'))
);

-- Homepage sections that can be shown/hidden
CREATE TABLE IF NOT EXISTS sections (
    section_key TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    enabled INTEGER DEFAULT 1,
    display_order INTEGER DEFAULT 0
);

-- Admission applications submitted by visitors
CREATE TABLE IF NOT EXISTS admissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_name TEXT NOT NULL,
    class_applying TEXT NOT NULL,
    dob TEXT,
    parent_name TEXT NOT NULL,
    mobile TEXT NOT NULL,
    email TEXT,
    previous_school TEXT,
    status TEXT DEFAULT 'New',
    admin_reply TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

-- Result categories (10th / 12th) — one image + one note each, admin-managed
CREATE TABLE IF NOT EXISTS results (
    result_key TEXT PRIMARY KEY,            -- 'class10' | 'class12'
    label TEXT NOT NULL,
    image TEXT,
    note TEXT,
    updated_at TEXT DEFAULT (datetime('now'))
);

-- Complaints / feedback submitted by visitors
CREATE TABLE IF NOT EXISTS complaints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    complaint_code TEXT UNIQUE NOT NULL,
    student_name TEXT NOT NULL,
    class_name TEXT,
    mobile TEXT NOT NULL,
    email TEXT,
    subject TEXT NOT NULL,
    description TEXT NOT NULL,
    attachment TEXT,
    status TEXT DEFAULT 'Pending',
    admin_reply TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

-- Contact form messages
CREATE TABLE IF NOT EXISTS contact_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT,
    message TEXT NOT NULL,
    admin_reply TEXT,
    status TEXT DEFAULT 'New',
    created_at TEXT DEFAULT (datetime('now'))
);

-- Every admin action, for the Activity Log screen
CREATE TABLE IF NOT EXISTS activity_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_username TEXT,
    action TEXT NOT NULL,
    details TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
