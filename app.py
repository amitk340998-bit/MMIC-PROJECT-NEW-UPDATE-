# app.py
# Main Flask application for the Mahamana Malviya Inter College website
# and its Admin Dashboard. Pure Python (Flask) backend, SQLite database,
# server-rendered HTML templates + vanilla CSS/JS on the frontend.

import os
import uuid
import json
import shutil
import secrets
import smtplib
import random
from email.mime.text import MIMEText
from datetime import datetime, timedelta
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for, session,
    flash, send_from_directory, jsonify, abort, send_file, make_response
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_wtf import CSRFProtect

from database import get_db, init_db, get_settings, set_setting, log_activity, DB_PATH, password_policy_errors

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_ROOT = os.path.join(BASE_DIR, 'static', 'uploads')
BACKUP_DIR = os.path.join(BASE_DIR, 'backups')

app = Flask(__name__)


def _load_or_create_secret_key():
    """Keep the same SECRET_KEY across restarts so sessions/CSRF tokens don't
    randomly invalidate every time the dev server reloads."""
    key_path = os.path.join(BASE_DIR, 'data', '.secret_key')
    os.makedirs(os.path.dirname(key_path), exist_ok=True)
    if os.path.exists(key_path):
        with open(key_path, 'r') as f:
            return f.read().strip()
    key = secrets.token_hex(32)
    with open(key_path, 'w') as f:
        f.write(key)
    return key


app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or _load_or_create_secret_key()
app.config['MAX_CONTENT_LENGTH'] = 8 * 1024 * 1024  # 8MB max upload
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=2)
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['WTF_CSRF_TIME_LIMIT'] = None  # tokens don't expire mid-session

csrf = CSRFProtect(app)

ALLOWED_IMAGE_EXT = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
ALLOWED_DOC_EXT = {'pdf'}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def allowed_file(filename, allowed_ext):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_ext


def save_upload(file_storage, subfolder, allowed_ext):
    """Saves an uploaded file with a random-safe name. Returns the stored
    filename, or None if there was no valid file to save."""
    if not file_storage or file_storage.filename == '':
        return None
    if not allowed_file(file_storage.filename, allowed_ext):
        raise ValueError(f"File type not allowed. Allowed: {', '.join(allowed_ext)}")
    ext = file_storage.filename.rsplit('.', 1)[1].lower()
    safe_name = f"{uuid.uuid4().hex}.{ext}"
    folder = os.path.join(UPLOAD_ROOT, subfolder)
    os.makedirs(folder, exist_ok=True)
    file_storage.save(os.path.join(folder, safe_name))
    return safe_name


def delete_upload(subfolder, filename):
    if not filename:
        return
    path = os.path.join(UPLOAD_ROOT, subfolder, filename)
    if os.path.exists(path):
        os.remove(path)


IDLE_TIMEOUT_MINUTES = 30


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin_login', next=request.path))

        # Idle session timeout — log the user out if they've been inactive too long
        last_activity = session.get('last_activity')
        if last_activity:
            try:
                last_dt = datetime.fromisoformat(last_activity)
                if datetime.now() - last_dt > timedelta(minutes=IDLE_TIMEOUT_MINUTES):
                    session.clear()
                    flash('You were logged out due to inactivity. Please log in again.', 'error')
                    return redirect(url_for('admin_login'))
            except ValueError:
                pass
        session['last_activity'] = datetime.now().isoformat()

        # Account may have been disabled after this session started — re-check every request
        conn = get_db()
        acct = conn.execute('SELECT status FROM admins WHERE id = ?', (session.get('admin_id'),)).fetchone()
        conn.close()
        if not acct or acct['status'] != 'active':
            session.clear()
            flash('This account has been disabled. Contact your Super Admin.', 'error')
            return redirect(url_for('admin_login'))

        return f(*args, **kwargs)
    return wrapper


def staff_required(f):
    """Full CMS access — Super Admin and Admin roles only (blocks Teacher accounts)."""
    @wraps(f)
    @login_required
    def wrapper(*args, **kwargs):
        if session.get('admin_role') not in ('super_admin', 'admin'):
            flash('Your account does not have access to that section.', 'error')
            return redirect(url_for('admin_teacher_home'))
        return f(*args, **kwargs)
    return wrapper


def super_admin_required(f):
    """Super Admin only — user management, roles, security settings."""
    @wraps(f)
    @login_required
    def wrapper(*args, **kwargs):
        if session.get('admin_role') != 'super_admin':
            flash('Only a Super Admin can access that page.', 'error')
            return redirect(url_for('admin_dashboard'))
        return f(*args, **kwargs)
    return wrapper


def current_admin():
    return session.get('admin_username', 'admin')


def current_admin_role():
    return session.get('admin_role', 'admin')


def generate_otp():
    return ''.join(random.choices('0123456789', k=6))


def log(action, details=''):
    log_activity(current_admin(), action, details)


def send_email(to_email, subject, body):
    """Sends a plain-text email using the SMTP settings saved in the admin panel.
    Returns (success: bool, message: str)."""
    settings = get_settings()
    host = settings.get('smtp_host', '').strip()
    port = settings.get('smtp_port', '').strip()
    username = settings.get('smtp_username', '').strip()
    password = settings.get('smtp_password', '').strip()
    from_name = settings.get('smtp_from_name', '').strip() or 'School Admin'

    if not (host and port and username and password):
        return False, 'Email is not set up yet. Go to Admin → Email Settings and add your SMTP details first.'

    try:
        msg = MIMEText(body, 'plain', 'utf-8')
        msg['Subject'] = subject
        msg['From'] = f'{from_name} <{username}>'
        msg['To'] = to_email

        with smtplib.SMTP(host, int(port), timeout=15) as server:
            server.starttls()
            server.login(username, password)
            server.sendmail(username, [to_email], msg.as_string())
        return True, 'Email sent successfully.'
    except Exception as e:
        return False, f'Could not send email: {e}'


def notify_super_admins(title, message, link=None):
    """Puts a notification in front of every Super Admin account (in-app notification,
    plus an email if that Super Admin has an email address on file). Never include a
    plaintext password in `message` — passwords are always hashed and are never shown
    to anyone, including Super Admin, once set."""
    conn = get_db()
    supers = conn.execute("SELECT id, email FROM admins WHERE role = 'super_admin'").fetchall()
    for s in supers:
        conn.execute(
            'INSERT INTO notifications (admin_id, title, message, link) VALUES (?, ?, ?, ?)',
            (s['id'], title, message, link)
        )
    conn.commit()
    conn.close()
    for s in supers:
        if s['email']:
            send_email(s['email'], title, message)


# ---------------------------------------------------------------------------
# PUBLIC ROUTES
# ---------------------------------------------------------------------------

@app.route('/')
def home():
    conn = get_db()
    settings = get_settings()
    sections = {row['section_key']: dict(row) for row in conn.execute(
        'SELECT * FROM sections ORDER BY display_order').fetchall()}
    hero_slides = conn.execute(
        'SELECT * FROM hero_slides WHERE active = 1 ORDER BY display_order').fetchall()
    teachers = conn.execute(
        'SELECT * FROM teachers WHERE active = 1 ORDER BY display_order').fetchall()
    sports = conn.execute(
        'SELECT * FROM sports WHERE active = 1 ORDER BY display_order').fetchall()
    alumni = conn.execute(
        'SELECT * FROM alumni WHERE active = 1 ORDER BY display_order').fetchall()
    results_rows = conn.execute('SELECT * FROM results').fetchall()
    results = {r['result_key']: dict(r) for r in results_rows}
    gallery = conn.execute(
        'SELECT * FROM gallery ORDER BY display_order DESC, created_at DESC LIMIT 12').fetchall()
    notices = conn.execute(
        'SELECT * FROM notices WHERE active = 1 ORDER BY published_date DESC LIMIT 10').fetchall()
    conn.close()
    return render_template(
        'index.html',
        settings=settings, sections=sections, hero_slides=hero_slides,
        teachers=teachers, sports=sports, alumni=alumni, results=results, gallery=gallery, notices=notices
    )


@app.route('/notices/download/<int:notice_id>')
def download_notice(notice_id):
    conn = get_db()
    notice = conn.execute('SELECT * FROM notices WHERE id = ?', (notice_id,)).fetchone()
    conn.close()
    if not notice:
        abort(404)
    folder = os.path.join(UPLOAD_ROOT, 'notices')
    return send_from_directory(folder, notice['file'], as_attachment=True,
                                download_name=f"{notice['title']}.pdf")


@app.route('/notices/view/<int:notice_id>')
def view_notice(notice_id):
    """Opens the uploaded notice file inline in the browser (preview), instead of forcing a download."""
    conn = get_db()
    notice = conn.execute('SELECT * FROM notices WHERE id = ?', (notice_id,)).fetchone()
    conn.close()
    if not notice:
        abort(404)
    folder = os.path.join(UPLOAD_ROOT, 'notices')
    return send_from_directory(folder, notice['file'], as_attachment=False)


@app.route('/admission/submit', methods=['POST'])
def submit_admission():
    student_name = request.form.get('student_name', '').strip()
    class_applying = request.form.get('class_applying', '').strip()
    dob = request.form.get('dob', '').strip()
    parent_name = request.form.get('parent_name', '').strip()
    mobile = request.form.get('mobile', '').strip()
    email = request.form.get('email', '').strip()
    previous_school = request.form.get('previous_school', '').strip()

    errors = []
    if len(student_name) < 2:
        errors.append('Please enter a valid student name.')
    if not class_applying:
        errors.append('Please select a class.')
    if len(parent_name) < 2:
        errors.append('Please enter a valid parent/guardian name.')
    if len(mobile) < 7:
        errors.append('Please enter a valid mobile number.')

    if errors:
        flash(' '.join(errors), 'error')
        return redirect(url_for('home', _anchor='admissions'))

    conn = get_db()
    conn.execute(
        '''INSERT INTO admissions (student_name, class_applying, dob, parent_name, mobile, email, previous_school)
           VALUES (?, ?, ?, ?, ?, ?, ?)''',
        (student_name, class_applying, dob, parent_name, mobile, email, previous_school)
    )
    conn.execute(
        '''INSERT INTO notifications (admin_id, title, message, link)
           VALUES (NULL, ?, ?, ?)''',
        ('New admission request', f'{student_name} applied for class {class_applying}.', '/admin/teacher/admissions')
    )
    conn.commit()
    conn.close()
    flash('Admission form submitted successfully! We will contact you soon.', 'success')
    return redirect(url_for('home', _anchor='admissions'))


@app.route('/complaint/submit', methods=['POST'])
def submit_complaint():
    student_name = request.form.get('student_name', '').strip()
    class_name = request.form.get('class_name', '').strip()
    mobile = request.form.get('mobile', '').strip()
    email = request.form.get('email', '').strip()
    subject = request.form.get('subject', '').strip()
    description = request.form.get('description', '').strip()

    errors = []
    if len(student_name) < 2:
        errors.append('Please enter a valid student name.')
    if len(mobile) < 7:
        errors.append('Please enter a valid mobile number.')
    if len(subject) < 3:
        errors.append('Please enter a subject.')
    if len(description) < 5:
        errors.append('Please describe your complaint.')

    if errors:
        flash(' '.join(errors), 'error')
        return redirect(url_for('home', _anchor='complaints'))

    attachment = None
    file = request.files.get('attachment')
    if file and file.filename:
        try:
            attachment = save_upload(file, 'complaints', ALLOWED_IMAGE_EXT | ALLOWED_DOC_EXT)
        except ValueError as e:
            flash(str(e), 'error')
            return redirect(url_for('home', _anchor='complaints'))

    code = f"CMP-{datetime.now().strftime('%y%m%d')}-{uuid.uuid4().hex[:5].upper()}"

    conn = get_db()
    conn.execute(
        '''INSERT INTO complaints (complaint_code, student_name, class_name, mobile, email, subject, description, attachment)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
        (code, student_name, class_name, mobile, email, subject, description, attachment)
    )
    conn.commit()
    conn.close()
    flash(f'Complaint submitted! Your complaint ID is {code}. Please save this for reference.', 'success')
    return redirect(url_for('home', _anchor='complaints'))


@app.route('/contact/submit', methods=['POST'])
def submit_contact():
    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip()
    message = request.form.get('message', '').strip()

    errors = []
    if len(name) < 2:
        errors.append('Please enter your name.')
    if len(message) < 5:
        errors.append('Please enter a message.')

    if errors:
        flash(' '.join(errors), 'error')
        return redirect(url_for('home', _anchor='contact'))

    conn = get_db()
    conn.execute(
        'INSERT INTO contact_messages (name, email, message) VALUES (?, ?, ?)',
        (name, email, message)
    )
    conn.commit()
    conn.close()
    flash('Message sent successfully! We will get back to you soon.', 'success')
    return redirect(url_for('home', _anchor='contact'))


# ---------------------------------------------------------------------------
# ADMIN: AUTH
# ---------------------------------------------------------------------------

def get_device_id():
    """Returns the device-identifier token for this browser, generating one if it doesn't
    exist yet. This is a long-lived, HttpOnly, randomly-generated cookie value — it is what
    makes device-specific lockout possible (a login attempt is tied to THIS browser/device,
    not just the account)."""
    token = request.cookies.get('device_id')
    if not token or len(token) < 32:
        token = secrets.token_hex(24)
    return token


def set_device_cookie(response):
    existing = request.cookies.get('device_id')
    if not existing or len(existing) < 32:
        response.set_cookie('device_id', get_device_id(), max_age=60 * 60 * 24 * 365,
                             httponly=True, samesite='Lax')
    return response


@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    DEVICE_LOCKOUT_THRESHOLD = 5
    DEVICE_LOCKOUT_MINUTES = 15
    # Safety-net threshold: catches an attacker who keeps clearing cookies / switching
    # devices specifically to dodge the per-device lockout above. This is intentionally a
    # much higher bar than the per-device one, and only trips after sustained abuse spread
    # across many devices/sources — a normal user on a second device will never reach it.
    GLOBAL_SAFETY_THRESHOLD = 20
    GLOBAL_SAFETY_MINUTES = 60

    device_id = get_device_id()
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr) or 'unknown'

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        conn = get_db()
        admin = conn.execute('SELECT * FROM admins WHERE username = ?', (username,)).fetchone()

        device_row = None
        if admin:
            device_row = conn.execute(
                'SELECT * FROM login_lockouts WHERE admin_id = ? AND device_id = ?',
                (admin['id'], device_id)).fetchone()

        # 1) Is THIS device currently locked out? (device-specific — does not affect other devices)
        if device_row and device_row['locked_until']:
            try:
                locked_until = datetime.fromisoformat(device_row['locked_until'])
                if datetime.now() < locked_until:
                    mins_left = int((locked_until - datetime.now()).total_seconds() // 60) + 1
                    flash(f'Too many failed attempts from this device. Try again in {mins_left} minute(s).', 'error')
                    conn.close()
                    log_activity(username or '(unknown)', 'Login blocked',
                                 f'Device locked out — attempt during lockout (device_id ending …{device_id[-6:]})')
                    resp = make_response(render_template('admin/login.html', settings=get_settings()))
                    return set_device_cookie(resp)
            except ValueError:
                pass

        # 2) Global safety-net lock? (only trips after excessive failures spread across many devices)
        if admin and admin['locked_until']:
            try:
                global_locked_until = datetime.fromisoformat(admin['locked_until'])
                if datetime.now() < global_locked_until:
                    mins_left = int((global_locked_until - datetime.now()).total_seconds() // 60) + 1
                    flash(f'Too many failed attempts on this account. Try again in {mins_left} minute(s).', 'error')
                    conn.close()
                    resp = make_response(render_template('admin/login.html', settings=get_settings()))
                    return set_device_cookie(resp)
            except ValueError:
                pass

        if admin and admin['status'] != 'active':
            flash('This account has been disabled. Contact your Super Admin.', 'error')
            conn.close()
            resp = make_response(render_template('admin/login.html', settings=get_settings()))
            return set_device_cookie(resp)

        if admin and check_password_hash(admin['password_hash'], password):
            # Successful login — clear THIS device's failed-attempt record only.
            # Other devices' existing lockouts are left exactly as they are (requirement: a
            # success on Device B must never lift a lockout that's active on Device A).
            conn.execute('DELETE FROM login_lockouts WHERE admin_id = ? AND device_id = ?',
                         (admin['id'], device_id))
            # A verified correct password is strong proof of legitimate access, so it's safe
            # to also clear the account-wide safety-net counter (an attacker without the
            # password can never trigger this branch, so this can't be abused to "reset" abuse).
            conn.execute('UPDATE admins SET failed_attempts = 0, locked_until = NULL, last_login = ? WHERE id = ?',
                         (datetime.now().isoformat(), admin['id']))
            conn.commit()
            conn.close()

            session.permanent = True
            session['admin_logged_in'] = True
            session['admin_username'] = admin['username']
            session['admin_id'] = admin['id']
            session['admin_role'] = admin['role'] or 'admin'
            session['last_activity'] = datetime.now().isoformat()
            log_activity(admin['username'], 'Login', f'Successful login (device …{device_id[-6:]}, ip {client_ip})')

            if admin['must_change_password']:
                flash('For security, please set a new password before continuing.', 'success')
                resp = make_response(redirect(url_for('admin_account_settings')))
                return set_device_cookie(resp)

            if session['admin_role'] == 'teacher':
                resp = make_response(redirect(url_for('admin_teacher_home')))
                return set_device_cookie(resp)
            next_url = request.args.get('next') or url_for('admin_dashboard')
            resp = make_response(redirect(next_url))
            return set_device_cookie(resp)
        else:
            if admin:
                lockout_log_msg = None
                safety_log_msg = None

                # --- Device-specific counter ---
                if device_row:
                    dev_attempts = (device_row['failed_attempts'] or 0) + 1
                    if dev_attempts >= DEVICE_LOCKOUT_THRESHOLD:
                        dev_locked_until = (datetime.now() + timedelta(minutes=DEVICE_LOCKOUT_MINUTES)).isoformat()
                        conn.execute(
                            'UPDATE login_lockouts SET failed_attempts = ?, locked_until = ?, ip_address = ?, last_attempt_at = ? WHERE id = ?',
                            (dev_attempts, dev_locked_until, client_ip, datetime.now().isoformat(), device_row['id']))
                        flash(f'Too many failed attempts from this device. Locked for {DEVICE_LOCKOUT_MINUTES} minutes.', 'error')
                        lockout_log_msg = f'{dev_attempts} failed attempts from device …{device_id[-6:]} (ip {client_ip})'
                    else:
                        conn.execute(
                            'UPDATE login_lockouts SET failed_attempts = ?, ip_address = ?, last_attempt_at = ? WHERE id = ?',
                            (dev_attempts, client_ip, datetime.now().isoformat(), device_row['id']))
                        flash('Invalid username or password.', 'error')
                else:
                    conn.execute(
                        'INSERT INTO login_lockouts (admin_id, device_id, ip_address, failed_attempts, last_attempt_at) VALUES (?, ?, ?, 1, ?)',
                        (admin['id'], device_id, client_ip, datetime.now().isoformat()))
                    flash('Invalid username or password.', 'error')

                # --- Global safety-net counter (spread across all devices for this account) ---
                global_attempts = (admin['failed_attempts'] or 0) + 1
                if global_attempts >= GLOBAL_SAFETY_THRESHOLD:
                    global_locked_until = (datetime.now() + timedelta(minutes=GLOBAL_SAFETY_MINUTES)).isoformat()
                    conn.execute('UPDATE admins SET failed_attempts = ?, locked_until = ? WHERE id = ?',
                                 (global_attempts, global_locked_until, admin['id']))
                    safety_log_msg = (f'{global_attempts} failed attempts across multiple devices/sources — '
                                       f'account locked for {GLOBAL_SAFETY_MINUTES} minutes as an anti-bypass measure')
                    flash(f'Too many failed attempts on this account from multiple sources. '
                          f'Locked for {GLOBAL_SAFETY_MINUTES} minutes.', 'error')
                else:
                    conn.execute('UPDATE admins SET failed_attempts = ? WHERE id = ?', (global_attempts, admin['id']))
                conn.commit()
                conn.close()
                # Log AFTER commit+close — log_activity() opens its own DB connection, and
                # calling it while this connection still has an uncommitted transaction open
                # causes a "database is locked" error (SQLite locks the whole file per writer).
                if lockout_log_msg:
                    log_activity(username, 'Device locked out', lockout_log_msg)
                if safety_log_msg:
                    log_activity(username, 'Account locked (safety net)', safety_log_msg)
            else:
                flash('Invalid username or password.', 'error')
                conn.close()

    resp = make_response(render_template('admin/login.html', settings=get_settings()))
    return set_device_cookie(resp)


@app.route('/admin/logout')
def admin_logout():
    if session.get('admin_username'):
        log_activity(session['admin_username'], 'Logout', '')
    session.clear()
    return redirect(url_for('admin_login'))


@app.route('/admin/forgot-password', methods=['GET', 'POST'])
def admin_forgot_password():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        conn = get_db()
        admin = conn.execute('SELECT * FROM admins WHERE username = ?', (username,)).fetchone()

        # Always show the same message whether or not the account exists (avoid leaking who has accounts)
        generic_msg = 'If that account exists and has an email on file, a reset code has been sent to it.'

        if admin and admin['email']:
            code = generate_otp()
            expires = (datetime.now() + timedelta(minutes=15)).isoformat()
            conn.execute('INSERT INTO otp_codes (admin_id, code, purpose, expires_at) VALUES (?, ?, ?, ?)',
                         (admin['id'], code, 'password_reset', expires))
            conn.commit()
            send_email(admin['email'], 'Password reset code',
                       f'Your password reset code is: {code}\n\nThis code expires in 15 minutes. '
                       f'If you did not request this, you can safely ignore this email.')
        conn.close()
        flash(generic_msg, 'success')
        return redirect(url_for('admin_reset_password', username=username))

    return render_template('admin/forgot_password.html')


@app.route('/admin/reset-password', methods=['GET', 'POST'])
def admin_reset_password():
    username = request.values.get('username', '').strip()

    if request.method == 'POST':
        code = request.form.get('otp', '').strip()
        new = request.form.get('new_password', '')
        confirm = request.form.get('confirm_password', '')

        conn = get_db()
        admin = conn.execute('SELECT * FROM admins WHERE username = ?', (username,)).fetchone()
        if not admin:
            flash('Invalid request.', 'error')
            conn.close()
            return redirect(url_for('admin_forgot_password'))

        row = conn.execute(
            '''SELECT * FROM otp_codes WHERE admin_id = ? AND purpose = 'password_reset'
               AND used = 0 ORDER BY id DESC LIMIT 1''', (admin['id'],)).fetchone()

        policy_errors = password_policy_errors(new)

        if not row or row['code'] != code:
            flash('Incorrect reset code.', 'error')
        elif datetime.now() > datetime.fromisoformat(row['expires_at']):
            flash('That code has expired. Please request a new one.', 'error')
        elif policy_errors:
            flash('Password is too weak: ' + '; '.join(policy_errors), 'error')
        elif new != confirm:
            flash('Passwords do not match.', 'error')
        else:
            conn.execute('UPDATE admins SET password_hash = ?, failed_attempts = 0, locked_until = NULL WHERE id = ?',
                         (generate_password_hash(new), admin['id']))
            conn.execute('UPDATE otp_codes SET used = 1 WHERE id = ?', (row['id'],))
            conn.commit()
            conn.close()
            log_activity(admin['username'], 'Password reset', 'Reset via forgot-password flow')
            if admin['email']:
                send_email(admin['email'], 'Your password was reset',
                           'Your account password was just reset. If this was not you, contact your Super Admin immediately.')
            flash('Password reset successfully. You can now log in.', 'success')
            return redirect(url_for('admin_login'))
        conn.close()

    return render_template('admin/reset_password.html', username=username)



@app.route('/admin/change-password', methods=['POST'])
@login_required
def change_password():
    """Legacy endpoint kept so any old bookmark/link still works — redirect to the new Account Settings page."""
    return redirect(url_for('admin_account_settings'))


# ---------------------------------------------------------------------------
# ADMIN: ACCOUNT SETTINGS — password change (with policy), email change (with OTP)
# ---------------------------------------------------------------------------

@app.route('/admin/account')
@login_required
def admin_account_settings():
    conn = get_db()
    admin = conn.execute('SELECT * FROM admins WHERE id = ?', (session['admin_id'],)).fetchone()
    conn.close()
    return render_template('admin/account_settings.html', admin=admin)


@app.route('/admin/account/change-password', methods=['POST'])
@login_required
def admin_account_change_password():
    current = request.form.get('current_password', '')
    new = request.form.get('new_password', '')
    confirm = request.form.get('confirm_password', '')

    conn = get_db()
    admin = conn.execute('SELECT * FROM admins WHERE id = ?', (session['admin_id'],)).fetchone()

    policy_errors = password_policy_errors(new)

    if not admin or not check_password_hash(admin['password_hash'], current):
        flash('Current password is incorrect.', 'error')
    elif policy_errors:
        flash('Password is too weak: ' + '; '.join(policy_errors), 'error')
    elif new != confirm:
        flash('New password and confirmation do not match.', 'error')
    else:
        conn.execute('UPDATE admins SET password_hash = ?, must_change_password = 0 WHERE id = ?',
                     (generate_password_hash(new), admin['id']))
        conn.commit()
        log('Changed own password', '')
        flash('Password updated successfully.', 'success')
        # Notify every Super Admin — but NEVER include the actual new password anywhere.
        # Passwords are hashed and are not retrievable/viewable by anyone, including Super Admin.
        if admin['role'] != 'super_admin':
            notify_super_admins(
                'Password changed',
                f"The account \"{admin['username']}\" ({admin['role'].replace('_',' ').title()}) just changed its own password.",
                link=url_for('admin_team')
            )
    conn.close()
    return redirect(url_for('admin_account_settings'))


@app.route('/admin/account/change-username', methods=['POST'])
@login_required
def admin_account_change_username():
    """Any logged-in account (Super Admin, Admin, Teacher) can change ONLY its own username.
    There is no route anywhere that lets one account change another account's username or
    password except the Super Admin's own Manage Team tools — a Normal Admin can never reach
    or modify the Super Admin's account through this page, because it always acts on the
    currently logged-in account's own id (session['admin_id']), never an id supplied by the form."""
    new_username = request.form.get('new_username', '').strip()
    current_password = request.form.get('confirm_password_for_username', '')

    conn = get_db()
    admin = conn.execute('SELECT * FROM admins WHERE id = ?', (session['admin_id'],)).fetchone()
    taken = conn.execute('SELECT 1 FROM admins WHERE username = ? AND id != ?',
                          (new_username, session['admin_id'])).fetchone()

    if not admin or not check_password_hash(admin['password_hash'], current_password):
        flash('Your current password is incorrect.', 'error')
    elif not new_username or len(new_username) < 3:
        flash('New username must be at least 3 characters.', 'error')
    elif taken:
        flash('That username is already taken by another account.', 'error')
    elif new_username == admin['username']:
        flash('That is already your username.', 'error')
    else:
        old_username = admin['username']
        conn.execute('UPDATE admins SET username = ? WHERE id = ?', (new_username, admin['id']))
        conn.commit()
        session['admin_username'] = new_username
        log(f'Changed own username from "{old_username}" to "{new_username}"', '')
        flash(f'Username changed to "{new_username}". Use this for your next login.', 'success')
        if admin['role'] != 'super_admin':
            notify_super_admins(
                'Username changed',
                f'The account "{old_username}" ({admin["role"].replace("_"," ").title()}) '
                f'changed its username to "{new_username}".',
                link=url_for('admin_team')
            )
    conn.close()
    return redirect(url_for('admin_account_settings'))


# ---------------------------------------------------------------------------
# ADMIN: DASHBOARD
# ---------------------------------------------------------------------------

@app.route('/admin/')
@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    if session.get('admin_role') == 'teacher':
        return redirect(url_for('admin_teacher_home'))
    conn = get_db()
    stats = {
        'admissions': conn.execute('SELECT COUNT(*) c FROM admissions').fetchone()['c'],
        'complaints': conn.execute('SELECT COUNT(*) c FROM complaints').fetchone()['c'],
        'pending_complaints': conn.execute("SELECT COUNT(*) c FROM complaints WHERE status='Pending'").fetchone()['c'],
        'contacts': conn.execute('SELECT COUNT(*) c FROM contact_messages').fetchone()['c'],
        'gallery': conn.execute('SELECT COUNT(*) c FROM gallery').fetchone()['c'],
        'notices': conn.execute('SELECT COUNT(*) c FROM notices').fetchone()['c'],
        'teachers': conn.execute('SELECT COUNT(*) c FROM teachers').fetchone()['c'],
    }
    recent_admissions = conn.execute(
        'SELECT * FROM admissions ORDER BY created_at DESC LIMIT 5').fetchall()
    recent_complaints = conn.execute(
        'SELECT * FROM complaints ORDER BY created_at DESC LIMIT 5').fetchall()
    recent_activity = conn.execute(
        'SELECT * FROM activity_log ORDER BY created_at DESC LIMIT 8').fetchall()
    my_notifications = []
    if session.get('admin_role') == 'super_admin':
        my_notifications = conn.execute(
            'SELECT * FROM notifications WHERE admin_id = ? ORDER BY created_at DESC LIMIT 10',
            (session['admin_id'],)).fetchall()
    conn.close()
    return render_template('admin/dashboard.html', stats=stats,
                            recent_admissions=recent_admissions,
                            recent_complaints=recent_complaints,
                            recent_activity=recent_activity,
                            my_notifications=my_notifications)


# ---------------------------------------------------------------------------
# WEBSITE CUSTOMIZATION — Hero, Content, Branding, Fonts, Sections, Teachers.
# Lives under its own URL prefix (/mmic-customizer/), separate from the
# day-to-day Admin Dashboard, but uses the SAME Super Admin login/session —
# there is no separate hidden account. Enforced by @super_admin_required
# on every route below (server-side authorization, not just a hidden link).
# ---------------------------------------------------------------------------

@app.route('/mmic-customizer/')
@super_admin_required
def customizer_home():
    return render_template('admin/customizer_home.html')


# ---------------------------------------------------------------------------
# ADMIN: HERO BANNER MANAGEMENT
# ---------------------------------------------------------------------------

@app.route('/mmic-customizer/hero')
@super_admin_required
def admin_hero():
    conn = get_db()
    slides = conn.execute('SELECT * FROM hero_slides ORDER BY display_order').fetchall()
    conn.close()
    return render_template('admin/hero.html', slides=slides, settings=get_settings())


@app.route('/mmic-customizer/hero/text-save', methods=['POST'])
@super_admin_required
def admin_hero_text_save():
    set_setting('hero_eyebrow', request.form.get('hero_eyebrow', '').strip())
    set_setting('hero_tagline', request.form.get('hero_tagline', '').strip())
    log('Updated hero eyebrow/tagline text')
    flash('Hero text updated.', 'success')
    return redirect(url_for('admin_hero'))


@app.route('/mmic-customizer/hero/add', methods=['POST'])
@super_admin_required
def admin_hero_add():
    title = request.form.get('title', '').strip()
    subtitle = request.form.get('subtitle', '').strip()
    button_text = request.form.get('button_text', '').strip()
    button_link = request.form.get('button_link', '').strip()

    if not title:
        flash('Title is required.', 'error')
        return redirect(url_for('admin_hero'))

    image = None
    file = request.files.get('image')
    try:
        image = save_upload(file, 'hero', ALLOWED_IMAGE_EXT)
    except ValueError as e:
        flash(str(e), 'error')
        return redirect(url_for('admin_hero'))

    conn = get_db()
    max_order = conn.execute('SELECT COALESCE(MAX(display_order), 0) m FROM hero_slides').fetchone()['m']
    conn.execute(
        '''INSERT INTO hero_slides (title, subtitle, image, button_text, button_link, display_order)
           VALUES (?, ?, ?, ?, ?, ?)''',
        (title, subtitle, image, button_text, button_link, max_order + 1)
    )
    conn.commit()
    conn.close()
    log('Added hero slide', title)
    flash('Hero slide added.', 'success')
    return redirect(url_for('admin_hero'))


@app.route('/mmic-customizer/hero/toggle/<int:slide_id>', methods=['POST'])
@super_admin_required
def admin_hero_toggle(slide_id):
    conn = get_db()
    slide = conn.execute('SELECT * FROM hero_slides WHERE id = ?', (slide_id,)).fetchone()
    if slide:
        conn.execute('UPDATE hero_slides SET active = ? WHERE id = ?',
                      (0 if slide['active'] else 1, slide_id))
        conn.commit()
        log('Toggled hero slide', slide['title'])
    conn.close()
    return redirect(url_for('admin_hero'))


@app.route('/mmic-customizer/hero/delete/<int:slide_id>', methods=['POST'])
@super_admin_required
def admin_hero_delete(slide_id):
    conn = get_db()
    slide = conn.execute('SELECT * FROM hero_slides WHERE id = ?', (slide_id,)).fetchone()
    if slide:
        delete_upload('hero', slide['image'])
        conn.execute('DELETE FROM hero_slides WHERE id = ?', (slide_id,))
        conn.commit()
        log('Deleted hero slide', slide['title'])
    conn.close()
    flash('Hero slide deleted.', 'success')
    return redirect(url_for('admin_hero'))


# ---------------------------------------------------------------------------
# ADMIN: GALLERY MANAGEMENT
# ---------------------------------------------------------------------------

@app.route('/admin/gallery')
@staff_required
def admin_gallery():
    search = request.args.get('search', '').strip()
    conn = get_db()
    if search:
        photos = conn.execute(
            'SELECT * FROM gallery WHERE caption LIKE ? ORDER BY created_at DESC',
            (f'%{search}%',)
        ).fetchall()
    else:
        photos = conn.execute('SELECT * FROM gallery ORDER BY created_at DESC').fetchall()
    conn.close()
    return render_template('admin/gallery.html', photos=photos, search=search)


@app.route('/admin/gallery/upload', methods=['POST'])
@staff_required
def admin_gallery_upload():
    caption = request.form.get('caption', '').strip()
    category = request.form.get('category', '').strip()
    file = request.files.get('photo')

    try:
        filename = save_upload(file, 'gallery', ALLOWED_IMAGE_EXT)
    except ValueError as e:
        flash(str(e), 'error')
        return redirect(url_for('admin_gallery'))

    if not filename:
        flash('Please choose a photo to upload.', 'error')
        return redirect(url_for('admin_gallery'))

    conn = get_db()
    conn.execute('INSERT INTO gallery (filename, caption, category) VALUES (?, ?, ?)',
                 (filename, caption, category))
    conn.commit()
    conn.close()
    log('Uploaded gallery photo', caption or filename)
    flash('Photo uploaded successfully.', 'success')
    return redirect(url_for('admin_gallery'))


@app.route('/admin/gallery/edit/<int:photo_id>', methods=['POST'])
@staff_required
def admin_gallery_edit(photo_id):
    caption = request.form.get('caption', '').strip()
    category = request.form.get('category', '').strip()
    conn = get_db()
    conn.execute('UPDATE gallery SET caption = ?, category = ? WHERE id = ?',
                 (caption, category, photo_id))
    conn.commit()
    conn.close()
    log('Edited gallery photo', caption)
    flash('Photo updated.', 'success')
    return redirect(url_for('admin_gallery'))


@app.route('/admin/gallery/delete/<int:photo_id>', methods=['POST'])
@staff_required
def admin_gallery_delete(photo_id):
    conn = get_db()
    photo = conn.execute('SELECT * FROM gallery WHERE id = ?', (photo_id,)).fetchone()
    if photo:
        delete_upload('gallery', photo['filename'])
        conn.execute('DELETE FROM gallery WHERE id = ?', (photo_id,))
        conn.commit()
        log('Deleted gallery photo', photo['caption'] or photo['filename'])
    conn.close()
    flash('Photo deleted.', 'success')
    return redirect(url_for('admin_gallery'))


# ---------------------------------------------------------------------------
# ADMIN: NOTICES & CIRCULARS (PDF)
# ---------------------------------------------------------------------------

@app.route('/admin/notices')
@staff_required
def admin_notices():
    search = request.args.get('search', '').strip()
    conn = get_db()
    if search:
        notices = conn.execute(
            'SELECT * FROM notices WHERE title LIKE ? ORDER BY published_date DESC',
            (f'%{search}%',)
        ).fetchall()
    else:
        notices = conn.execute('SELECT * FROM notices ORDER BY published_date DESC').fetchall()
    conn.close()
    return render_template('admin/notices.html', notices=notices, search=search)


@app.route('/admin/notices/upload', methods=['POST'])
@staff_required
def admin_notices_upload():
    title = request.form.get('title', '').strip()
    category = request.form.get('category', 'Notice').strip()
    file = request.files.get('file')

    if not title:
        flash('Title is required.', 'error')
        return redirect(url_for('admin_notices'))

    try:
        filename = save_upload(file, 'notices', ALLOWED_DOC_EXT)
    except ValueError as e:
        flash(str(e), 'error')
        return redirect(url_for('admin_notices'))

    if not filename:
        flash('Please choose a PDF file to upload.', 'error')
        return redirect(url_for('admin_notices'))

    conn = get_db()
    conn.execute('INSERT INTO notices (title, category, file) VALUES (?, ?, ?)',
                 (title, category, filename))
    conn.commit()
    conn.close()
    log('Uploaded notice/circular', title)
    flash('Notice uploaded successfully.', 'success')
    return redirect(url_for('admin_notices'))


@app.route('/admin/notices/toggle/<int:notice_id>', methods=['POST'])
@staff_required
def admin_notices_toggle(notice_id):
    conn = get_db()
    notice = conn.execute('SELECT * FROM notices WHERE id = ?', (notice_id,)).fetchone()
    if notice:
        conn.execute('UPDATE notices SET active = ? WHERE id = ?',
                      (0 if notice['active'] else 1, notice_id))
        conn.commit()
        log('Toggled notice', notice['title'])
    conn.close()
    return redirect(url_for('admin_notices'))


@app.route('/admin/notices/delete/<int:notice_id>', methods=['POST'])
@staff_required
def admin_notices_delete(notice_id):
    conn = get_db()
    notice = conn.execute('SELECT * FROM notices WHERE id = ?', (notice_id,)).fetchone()
    if notice:
        delete_upload('notices', notice['file'])
        conn.execute('DELETE FROM notices WHERE id = ?', (notice_id,))
        conn.commit()
        log('Deleted notice', notice['title'])
    conn.close()
    flash('Notice deleted.', 'success')
    return redirect(url_for('admin_notices'))


# ---------------------------------------------------------------------------
# ADMIN: TEACHERS & STAFF (day-to-day — Admin and Super Admin both manage this)
# ---------------------------------------------------------------------------

@app.route('/admin/teachers')
@staff_required
def admin_teachers():
    search = request.args.get('search', '').strip()
    conn = get_db()
    if search:
        teachers = conn.execute(
            'SELECT * FROM teachers WHERE name LIKE ? OR subject LIKE ? ORDER BY display_order',
            (f'%{search}%', f'%{search}%')
        ).fetchall()
    else:
        teachers = conn.execute('SELECT * FROM teachers ORDER BY display_order').fetchall()
    conn.close()
    return render_template('admin/teachers.html', teachers=teachers, search=search)


@app.route('/admin/teachers/add', methods=['POST'])
@staff_required
def admin_teachers_add():
    name = request.form.get('name', '').strip()
    role = request.form.get('role', '').strip()
    subject = request.form.get('subject', '').strip()
    mobile_number = request.form.get('mobile_number', '').strip()
    bio = request.form.get('bio', '').strip()

    if not name:
        flash('Name is required.', 'error')
        return redirect(url_for('admin_teachers'))

    try:
        photo = save_upload(request.files.get('photo'), 'teachers', ALLOWED_IMAGE_EXT)
    except ValueError as e:
        flash(str(e), 'error')
        return redirect(url_for('admin_teachers'))

    conn = get_db()
    max_order = conn.execute('SELECT COALESCE(MAX(display_order), 0) m FROM teachers').fetchone()['m']
    conn.execute(
        '''INSERT INTO teachers (name, role, subject, mobile_number, bio, photo, display_order)
           VALUES (?, ?, ?, ?, ?, ?, ?)''',
        (name, role, subject, mobile_number, bio, photo, max_order + 1)
    )
    conn.commit()
    conn.close()
    log('Added teacher', name)
    flash('Teacher added successfully.', 'success')
    return redirect(url_for('admin_teachers'))


@app.route('/admin/teachers/edit/<int:teacher_id>', methods=['POST'])
@staff_required
def admin_teachers_edit(teacher_id):
    name = request.form.get('name', '').strip()
    role = request.form.get('role', '').strip()
    subject = request.form.get('subject', '').strip()
    mobile_number = request.form.get('mobile_number', '').strip()
    bio = request.form.get('bio', '').strip()

    conn = get_db()
    teacher = conn.execute('SELECT * FROM teachers WHERE id = ?', (teacher_id,)).fetchone()
    if not teacher:
        conn.close()
        abort(404)

    photo = teacher['photo']
    file = request.files.get('photo')
    if file and file.filename:
        try:
            new_photo = save_upload(file, 'teachers', ALLOWED_IMAGE_EXT)
            if new_photo:
                delete_upload('teachers', teacher['photo'])
                photo = new_photo
        except ValueError as e:
            flash(str(e), 'error')
            conn.close()
            return redirect(url_for('admin_teachers'))

    conn.execute(
        'UPDATE teachers SET name=?, role=?, subject=?, mobile_number=?, bio=?, photo=? WHERE id=?',
        (name, role, subject, mobile_number, bio, photo, teacher_id)
    )
    conn.commit()
    conn.close()
    log('Edited teacher', name)
    flash('Teacher updated.', 'success')
    return redirect(url_for('admin_teachers'))


@app.route('/admin/teachers/delete/<int:teacher_id>', methods=['POST'])
@staff_required
def admin_teachers_delete(teacher_id):
    conn = get_db()
    teacher = conn.execute('SELECT * FROM teachers WHERE id = ?', (teacher_id,)).fetchone()
    if teacher:
        delete_upload('teachers', teacher['photo'])
        conn.execute('DELETE FROM teachers WHERE id = ?', (teacher_id,))
        conn.commit()
        log('Deleted teacher', teacher['name'])
    conn.close()
    flash('Teacher removed.', 'success')
    return redirect(url_for('admin_teachers'))


# ---------------------------------------------------------------------------
# ADMIN: SPORTS (day-to-day — Admin and Super Admin both manage this)
# ---------------------------------------------------------------------------

@app.route('/admin/sports')
@staff_required
def admin_sports():
    conn = get_db()
    sports = conn.execute('SELECT * FROM sports ORDER BY display_order').fetchall()
    conn.close()
    return render_template('admin/sports.html', sports=sports)


@app.route('/admin/sports/add', methods=['POST'])
@staff_required
def admin_sports_add():
    name = request.form.get('name', '').strip()
    description = request.form.get('description', '').strip()

    if not name:
        flash('Name is required.', 'error')
        return redirect(url_for('admin_sports'))

    try:
        image = save_upload(request.files.get('image'), 'sports', ALLOWED_IMAGE_EXT)
    except ValueError as e:
        flash(str(e), 'error')
        return redirect(url_for('admin_sports'))

    conn = get_db()
    max_order = conn.execute('SELECT COALESCE(MAX(display_order), 0) m FROM sports').fetchone()['m']
    conn.execute(
        'INSERT INTO sports (name, description, image, display_order) VALUES (?, ?, ?, ?)',
        (name, description, image, max_order + 1)
    )
    conn.commit()
    conn.close()
    log('Added sport', name)
    flash('Sport added successfully.', 'success')
    return redirect(url_for('admin_sports'))


@app.route('/admin/sports/edit/<int:sport_id>', methods=['POST'])
@staff_required
def admin_sports_edit(sport_id):
    name = request.form.get('name', '').strip()
    description = request.form.get('description', '').strip()

    conn = get_db()
    sport = conn.execute('SELECT * FROM sports WHERE id = ?', (sport_id,)).fetchone()
    if not sport:
        conn.close()
        abort(404)

    image = sport['image']
    file = request.files.get('image')
    if file and file.filename:
        try:
            new_image = save_upload(file, 'sports', ALLOWED_IMAGE_EXT)
            if new_image:
                delete_upload('sports', sport['image'])
                image = new_image
        except ValueError as e:
            flash(str(e), 'error')
            conn.close()
            return redirect(url_for('admin_sports'))

    conn.execute('UPDATE sports SET name=?, description=?, image=? WHERE id=?',
                 (name, description, image, sport_id))
    conn.commit()
    conn.close()
    log('Edited sport', name)
    flash('Sport updated.', 'success')
    return redirect(url_for('admin_sports'))


@app.route('/admin/sports/delete/<int:sport_id>', methods=['POST'])
@staff_required
def admin_sports_delete(sport_id):
    conn = get_db()
    sport = conn.execute('SELECT * FROM sports WHERE id = ?', (sport_id,)).fetchone()
    if sport:
        delete_upload('sports', sport['image'])
        conn.execute('DELETE FROM sports WHERE id = ?', (sport_id,))
        conn.commit()
        log('Deleted sport', sport['name'])
    conn.close()
    flash('Sport removed.', 'success')
    return redirect(url_for('admin_sports'))


# ---------------------------------------------------------------------------
# ADMIN: OLD STUDENTS / ALUMNI (day-to-day — Admin and Super Admin both manage this)
# ---------------------------------------------------------------------------

@app.route('/admin/alumni')
@staff_required
def admin_alumni():
    conn = get_db()
    alumni = conn.execute('SELECT * FROM alumni ORDER BY display_order').fetchall()
    conn.close()
    return render_template('admin/alumni.html', alumni=alumni)


@app.route('/admin/alumni/add', methods=['POST'])
@staff_required
def admin_alumni_add():
    name = request.form.get('name', '').strip()
    note = request.form.get('note', '').strip()

    if not name:
        flash('Name is required.', 'error')
        return redirect(url_for('admin_alumni'))

    try:
        photo = save_upload(request.files.get('photo'), 'alumni', ALLOWED_IMAGE_EXT)
    except ValueError as e:
        flash(str(e), 'error')
        return redirect(url_for('admin_alumni'))

    conn = get_db()
    max_order = conn.execute('SELECT COALESCE(MAX(display_order), 0) m FROM alumni').fetchone()['m']
    conn.execute(
        'INSERT INTO alumni (name, note, photo, display_order) VALUES (?, ?, ?, ?)',
        (name, note, photo, max_order + 1)
    )
    conn.commit()
    conn.close()
    log('Added alumni', name)
    flash('Alumni added successfully.', 'success')
    return redirect(url_for('admin_alumni'))


@app.route('/admin/alumni/edit/<int:alumni_id>', methods=['POST'])
@staff_required
def admin_alumni_edit(alumni_id):
    name = request.form.get('name', '').strip()
    note = request.form.get('note', '').strip()

    conn = get_db()
    person = conn.execute('SELECT * FROM alumni WHERE id = ?', (alumni_id,)).fetchone()
    if not person:
        conn.close()
        abort(404)

    photo = person['photo']
    file = request.files.get('photo')
    if file and file.filename:
        try:
            new_photo = save_upload(file, 'alumni', ALLOWED_IMAGE_EXT)
            if new_photo:
                delete_upload('alumni', person['photo'])
                photo = new_photo
        except ValueError as e:
            flash(str(e), 'error')
            conn.close()
            return redirect(url_for('admin_alumni'))

    conn.execute('UPDATE alumni SET name=?, note=?, photo=? WHERE id=?',
                 (name, note, photo, alumni_id))
    conn.commit()
    conn.close()
    log('Edited alumni', name)
    flash('Alumni updated.', 'success')
    return redirect(url_for('admin_alumni'))


@app.route('/admin/alumni/delete/<int:alumni_id>', methods=['POST'])
@staff_required
def admin_alumni_delete(alumni_id):
    conn = get_db()
    person = conn.execute('SELECT * FROM alumni WHERE id = ?', (alumni_id,)).fetchone()
    if person:
        delete_upload('alumni', person['photo'])
        conn.execute('DELETE FROM alumni WHERE id = ?', (alumni_id,))
        conn.commit()
        log('Deleted alumni', person['name'])
    conn.close()
    flash('Alumni removed.', 'success')
    return redirect(url_for('admin_alumni'))


# ---------------------------------------------------------------------------
# ADMIN: RESULT (10th / 12th) — one image + one note per category
# ---------------------------------------------------------------------------

@app.route('/admin/results')
@staff_required
def admin_results():
    conn = get_db()
    rows = {r['result_key']: r for r in conn.execute('SELECT * FROM results').fetchall()}
    conn.close()
    return render_template('admin/results.html', rows=rows)


@app.route('/admin/results/save/<result_key>', methods=['POST'])
@staff_required
def admin_results_save(result_key):
    if result_key not in ('class10', 'class12'):
        abort(404)

    note = request.form.get('note', '').strip()
    conn = get_db()
    existing = conn.execute('SELECT * FROM results WHERE result_key = ?', (result_key,)).fetchone()

    try:
        new_image = save_upload(request.files.get('image'), 'results', ALLOWED_IMAGE_EXT)
    except ValueError as e:
        flash(str(e), 'error')
        conn.close()
        return redirect(url_for('admin_results'))

    if new_image:
        # Only one image per category is ever kept — remove the old one first.
        if existing and existing['image']:
            delete_upload('results', existing['image'])
        conn.execute('UPDATE results SET image = ?, note = ?, updated_at = ? WHERE result_key = ?',
                     (new_image, note, datetime.now().isoformat(), result_key))
    else:
        conn.execute('UPDATE results SET note = ?, updated_at = ? WHERE result_key = ?',
                     (note, datetime.now().isoformat(), result_key))
    conn.commit()
    conn.close()
    log('Updated result', result_key)
    flash('Result updated successfully.', 'success')
    return redirect(url_for('admin_results'))


# ---------------------------------------------------------------------------
# ADMIN: SITE CONTENT (About / Principal / Admission info / Contact info)
# ---------------------------------------------------------------------------

@app.route('/mmic-customizer/content')
@super_admin_required
def admin_content():
    settings = get_settings()
    return render_template('admin/content.html', settings=settings)


@app.route('/mmic-customizer/content/save', methods=['POST'])
@super_admin_required
def admin_content_save():
    fields = [
        'site_title', 'site_motto', 'about_heading', 'about_text',
        'established_year', 'board', 'classes_offered', 'medium',
        'total_students', 'board_result', 'faculty_count', 'school_location_short',
        'principal_name', 'principal_bio',
        'admission_info',
        'contact_address', 'contact_phone', 'contact_email', 'contact_hours',
    ]
    for field in fields:
        if field in request.form:
            set_setting(field, request.form.get(field, '').strip())

    # Checkbox toggles (absent from form data entirely when unchecked)
    set_setting('site_title_bold', '1' if request.form.get('site_title_bold') == '1' else '0')

    # Optional principal photo replace
    file = request.files.get('principal_photo')
    if file and file.filename:
        try:
            filename = save_upload(file, 'branding', ALLOWED_IMAGE_EXT)
            if filename:
                set_setting('principal_photo', filename)
        except ValueError as e:
            flash(str(e), 'error')
            return redirect(url_for('admin_content'))

    log('Updated site content/text sections', '')
    flash('Content updated successfully.', 'success')
    return redirect(url_for('admin_content'))


# ---------------------------------------------------------------------------
# ADMIN: LOGO & FAVICON
# ---------------------------------------------------------------------------

@app.route('/mmic-customizer/branding')
@super_admin_required
def admin_branding():
    settings = get_settings()
    return render_template('admin/branding.html', settings=settings)


# ---------------------------------------------------------------------------
# ADMIN: FONT & TYPOGRAPHY MANAGEMENT
# ---------------------------------------------------------------------------

@app.route('/mmic-customizer/fonts')
@super_admin_required
def admin_fonts():
    return render_template('admin/fonts.html', settings=get_settings())


@app.route('/mmic-customizer/fonts/save', methods=['POST'])
@super_admin_required
def admin_fonts_save():
    for key in ['font_family', 'font_size_base', 'font_weight_base', 'text_color', 'line_height', 'letter_spacing']:
        set_setting(key, request.form.get(key, '').strip())
    log('Updated site typography settings')
    flash('Font settings saved.', 'success')
    return redirect(url_for('admin_fonts'))


# ---------------------------------------------------------------------------
# ADMIN: EMAIL (SMTP) SETTINGS — needed so contact-form replies actually send
# ---------------------------------------------------------------------------

@app.route('/admin/email-settings')
@super_admin_required
def admin_email_settings():
    return render_template('admin/email_settings.html', settings=get_settings())


@app.route('/admin/email-settings/save', methods=['POST'])
@super_admin_required
def admin_email_settings_save():
    for key in ['smtp_host', 'smtp_port', 'smtp_username', 'smtp_from_name']:
        set_setting(key, request.form.get(key, '').strip())
    new_password = request.form.get('smtp_password', '').strip()
    if new_password:
        set_setting('smtp_password', new_password)
    log('Updated email (SMTP) settings')
    flash('Email settings saved.', 'success')
    return redirect(url_for('admin_email_settings'))


@app.route('/admin/email-settings/test', methods=['POST'])
@super_admin_required
def admin_email_settings_test():
    test_to = request.form.get('test_email', '').strip()
    if not test_to:
        flash('Enter an email address to send the test to.', 'error')
        return redirect(url_for('admin_email_settings'))
    ok, info = send_email(test_to, 'Test email from your school website',
                           'This is a test email to confirm your SMTP settings are working correctly.')
    flash(info if not ok else 'Test email sent successfully — check the inbox.', 'success' if ok else 'error')
    return redirect(url_for('admin_email_settings'))


@app.route('/mmic-customizer/branding/save', methods=['POST'])
@super_admin_required
def admin_branding_save():
    logo_file = request.files.get('logo')
    favicon_file = request.files.get('favicon')
    founder_file = request.files.get('founder_photo')

    try:
        logo = save_upload(logo_file, 'branding', ALLOWED_IMAGE_EXT)
        if logo:
            set_setting('logo_path', logo)
        favicon = save_upload(favicon_file, 'branding', ALLOWED_IMAGE_EXT)
        if favicon:
            set_setting('favicon_path', favicon)
        founder = save_upload(founder_file, 'branding', ALLOWED_IMAGE_EXT)
        if founder:
            set_setting('founder_photo', founder)
    except ValueError as e:
        flash(str(e), 'error')
        return redirect(url_for('admin_branding'))

    log('Updated logo/favicon/founder photo', '')
    flash('Branding updated successfully.', 'success')
    return redirect(url_for('admin_branding'))


# ---------------------------------------------------------------------------
# ADMIN: HOMEPAGE SECTION ENABLE/DISABLE
# ---------------------------------------------------------------------------

@app.route('/mmic-customizer/sections')
@super_admin_required
def admin_sections():
    conn = get_db()
    sections = conn.execute('SELECT * FROM sections ORDER BY display_order').fetchall()
    conn.close()
    return render_template('admin/sections.html', sections=sections)


@app.route('/mmic-customizer/sections/toggle/<key>', methods=['POST'])
@super_admin_required
def admin_sections_toggle(key):
    conn = get_db()
    section = conn.execute('SELECT * FROM sections WHERE section_key = ?', (key,)).fetchone()
    if section:
        conn.execute('UPDATE sections SET enabled = ? WHERE section_key = ?',
                      (0 if section['enabled'] else 1, key))
        conn.commit()
        log('Toggled homepage section', section['label'])
    conn.close()
    return redirect(url_for('admin_sections'))


# ---------------------------------------------------------------------------
# ADMIN: ADMISSIONS (submitted applications)
# ---------------------------------------------------------------------------

@app.route('/admin/admissions')
@staff_required
def admin_admissions():
    search = request.args.get('search', '').strip()
    class_filter = request.args.get('class_filter', '').strip()
    conn = get_db()
    query = 'SELECT * FROM admissions WHERE 1=1'
    params = []
    if search:
        query += ' AND (student_name LIKE ? OR parent_name LIKE ? OR mobile LIKE ?)'
        params += [f'%{search}%', f'%{search}%', f'%{search}%']
    if class_filter:
        query += ' AND class_applying = ?'
        params.append(class_filter)
    query += ' ORDER BY created_at DESC'
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return render_template('admin/admissions.html', rows=rows, search=search, class_filter=class_filter)


@app.route('/admin/admissions/status/<int:app_id>', methods=['POST'])
@staff_required
def admin_admissions_status(app_id):
    status = request.form.get('status', 'New')
    reply = request.form.get('admin_reply', '').strip()
    conn = get_db()
    row = conn.execute('SELECT * FROM admissions WHERE id = ?', (app_id,)).fetchone()
    prev_reply = row['admin_reply'] if row else ''
    conn.execute('UPDATE admissions SET status = ?, admin_reply = ? WHERE id = ?',
                 (status, reply, app_id))
    conn.commit()
    conn.close()
    log('Updated admission status', f'#{app_id} -> {status}')

    if reply and reply != prev_reply and row and row['email']:
        settings = get_settings()
        subject = f"Update on your Entrance Examination Admission Form — {settings.get('site_title', 'MMIC')}"
        body = (
            f"Dear {row['parent_name']},\n\n"
            f"Regarding the admission form submitted for {row['student_name']} "
            f"(Class {row['class_applying']}), current status: {status}.\n\n"
            f"{reply}\n\n"
            f"— {settings.get('site_title', 'Mahamana Malviya Inter College')}\n"
        )
        ok, info = send_email(row['email'], subject, body)
        if ok:
            flash('Status updated and message emailed to the applicant.', 'success')
        else:
            flash(f'Status saved, but the email could not be sent: {info}', 'error')
    else:
        flash('Status updated.', 'success')

    return redirect(url_for('admin_admissions'))


@app.route('/admin/admissions/delete/<int:app_id>', methods=['POST'])
@staff_required
def admin_admissions_delete(app_id):
    conn = get_db()
    conn.execute('DELETE FROM admissions WHERE id = ?', (app_id,))
    conn.commit()
    conn.close()
    log('Deleted admission record', f'#{app_id}')
    flash('Record deleted.', 'success')
    return redirect(url_for('admin_admissions'))


@app.route('/admin/admissions/export')
@staff_required
def admin_admissions_export():
    import csv
    import io
    conn = get_db()
    rows = conn.execute('SELECT * FROM admissions ORDER BY created_at DESC').fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    if rows:
        writer.writerow(rows[0].keys())
        for row in rows:
            writer.writerow(list(row))
    mem = io.BytesIO(output.getvalue().encode('utf-8'))
    log('Exported admissions CSV', '')
    return send_file(mem, mimetype='text/csv', as_attachment=True, download_name='admissions.csv')


# ---------------------------------------------------------------------------
# ADMIN: COMPLAINTS
# ---------------------------------------------------------------------------

@app.route('/admin/complaints')
@staff_required
def admin_complaints():
    search = request.args.get('search', '').strip()
    status_filter = request.args.get('status_filter', '').strip()
    conn = get_db()
    query = 'SELECT * FROM complaints WHERE 1=1'
    params = []
    if search:
        query += ' AND (student_name LIKE ? OR complaint_code LIKE ? OR subject LIKE ?)'
        params += [f'%{search}%', f'%{search}%', f'%{search}%']
    if status_filter:
        query += ' AND status = ?'
        params.append(status_filter)
    query += ' ORDER BY created_at DESC'
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return render_template('admin/complaints.html', rows=rows, search=search, status_filter=status_filter)


@app.route('/admin/complaints/update/<int:c_id>', methods=['POST'])
@staff_required
def admin_complaints_update(c_id):
    status = request.form.get('status', 'Pending')
    reply = request.form.get('admin_reply', '').strip()
    conn = get_db()
    row = conn.execute('SELECT * FROM complaints WHERE id = ?', (c_id,)).fetchone()
    prev_reply = row['admin_reply'] if row else ''
    conn.execute('UPDATE complaints SET status = ?, admin_reply = ? WHERE id = ?',
                 (status, reply, c_id))
    conn.commit()
    conn.close()
    log('Updated complaint', f'#{c_id} -> {status}')

    if reply and reply != prev_reply and row and row['email']:
        settings = get_settings()
        subject = f"Update on your complaint ({row['complaint_code']}) — {settings.get('site_title', 'MMIC')}"
        body = (
            f"Dear {row['student_name']},\n\n"
            f"Regarding your complaint ({row['complaint_code']}, status: {status}):\n\n"
            f"{reply}\n\n"
            f"— {settings.get('site_title', 'Mahamana Malviya Inter College')}\n"
        )
        ok, info = send_email(row['email'], subject, body)
        if ok:
            flash('Complaint updated and reply emailed to the sender.', 'success')
        else:
            flash(f'Complaint saved, but the email could not be sent: {info}', 'error')
    else:
        flash('Complaint updated.', 'success')

    return redirect(url_for('admin_complaints'))


@app.route('/admin/complaints/delete/<int:c_id>', methods=['POST'])
@staff_required
def admin_complaints_delete(c_id):
    conn = get_db()
    complaint = conn.execute('SELECT * FROM complaints WHERE id = ?', (c_id,)).fetchone()
    if complaint:
        delete_upload('complaints', complaint['attachment'])
        conn.execute('DELETE FROM complaints WHERE id = ?', (c_id,))
        conn.commit()
        log('Deleted complaint', complaint['complaint_code'])
    conn.close()
    flash('Complaint deleted.', 'success')
    return redirect(url_for('admin_complaints'))


@app.route('/admin/complaints/export')
@staff_required
def admin_complaints_export():
    import csv
    import io
    conn = get_db()
    rows = conn.execute('SELECT * FROM complaints ORDER BY created_at DESC').fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    if rows:
        writer.writerow(rows[0].keys())
        for row in rows:
            writer.writerow(list(row))
    mem = io.BytesIO(output.getvalue().encode('utf-8'))
    log('Exported complaints CSV', '')
    return send_file(mem, mimetype='text/csv', as_attachment=True, download_name='complaints.csv')


# ---------------------------------------------------------------------------
# ADMIN: CONTACT MESSAGES
# ---------------------------------------------------------------------------

@app.route('/admin/contact-messages')
@staff_required
def admin_contact_messages():
    search = request.args.get('search', '').strip()
    conn = get_db()
    if search:
        rows = conn.execute(
            'SELECT * FROM contact_messages WHERE name LIKE ? OR email LIKE ? OR message LIKE ? ORDER BY created_at DESC',
            (f'%{search}%', f'%{search}%', f'%{search}%')
        ).fetchall()
    else:
        rows = conn.execute('SELECT * FROM contact_messages ORDER BY created_at DESC').fetchall()
    conn.close()
    return render_template('admin/contact_messages.html', rows=rows, search=search)


@app.route('/admin/contact-messages/update/<int:m_id>', methods=['POST'])
@staff_required
def admin_contact_messages_update(m_id):
    status = request.form.get('status', 'New')
    reply = request.form.get('admin_reply', '').strip()
    conn = get_db()
    row = conn.execute('SELECT * FROM contact_messages WHERE id = ?', (m_id,)).fetchone()
    prev_reply = row['admin_reply'] if row else ''
    conn.execute('UPDATE contact_messages SET status = ?, admin_reply = ? WHERE id = ?',
                 (status, reply, m_id))
    conn.commit()
    conn.close()
    log('Updated contact message', f'#{m_id}')

    # Only send an email if there's a reply text, it changed from before, and we have their email
    if reply and reply != prev_reply and row and row['email']:
        settings = get_settings()
        subject = f"Reply from {settings.get('site_title', 'MMIC')} — regarding your message"
        body = (
            f"Dear {row['name']},\n\n"
            f"Thank you for contacting us. Here is our reply:\n\n"
            f"{reply}\n\n"
            f"— {settings.get('site_title', 'Mahamana Malviya Inter College')}\n"
        )
        ok, info = send_email(row['email'], subject, body)
        if ok:
            flash('Message updated and reply emailed to the sender.', 'success')
        else:
            flash(f'Message saved, but the email could not be sent: {info}', 'error')
    else:
        flash('Message updated.', 'success')

    return redirect(url_for('admin_contact_messages'))


@app.route('/admin/contact-messages/delete/<int:m_id>', methods=['POST'])
@staff_required
def admin_contact_messages_delete(m_id):
    conn = get_db()
    conn.execute('DELETE FROM contact_messages WHERE id = ?', (m_id,))
    conn.commit()
    conn.close()
    log('Deleted contact message', f'#{m_id}')
    flash('Message deleted.', 'success')
    return redirect(url_for('admin_contact_messages'))


# ---------------------------------------------------------------------------
# ADMIN: ACTIVITY LOG
# ---------------------------------------------------------------------------

@app.route('/admin/activity-log')
@super_admin_required
def admin_activity_log():
    conn = get_db()
    rows = conn.execute('SELECT * FROM activity_log ORDER BY created_at DESC LIMIT 200').fetchall()
    conn.close()
    return render_template('admin/activity_log.html', rows=rows)


# ---------------------------------------------------------------------------
# ADMIN: BACKUP & RESTORE
# ---------------------------------------------------------------------------

@app.route('/admin/backup')
@super_admin_required
def admin_backup():
    backups = []
    if os.path.exists(BACKUP_DIR):
        backups = sorted(os.listdir(BACKUP_DIR), reverse=True)
    return render_template('admin/backup.html', backups=backups)


@app.route('/admin/backup/create', methods=['POST'])
@super_admin_required
def admin_backup_create():
    os.makedirs(BACKUP_DIR, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_name = f'backup_{timestamp}.db'
    shutil.copy2(DB_PATH, os.path.join(BACKUP_DIR, backup_name))
    log('Created backup', backup_name)
    flash(f'Backup created: {backup_name}', 'success')
    return redirect(url_for('admin_backup'))


@app.route('/admin/backup/download/<filename>')
@super_admin_required
def admin_backup_download(filename):
    safe_name = secure_filename(filename)
    return send_from_directory(BACKUP_DIR, safe_name, as_attachment=True)


@app.route('/admin/backup/restore', methods=['POST'])
@super_admin_required
def admin_backup_restore():
    file = request.files.get('backup_file')
    if not file or not file.filename.endswith('.db'):
        flash('Please choose a valid .db backup file.', 'error')
        return redirect(url_for('admin_backup'))

    # Save a safety copy of the current DB before overwriting
    os.makedirs(BACKUP_DIR, exist_ok=True)
    safety_name = f'before_restore_{datetime.now().strftime("%Y%m%d_%H%M%S")}.db'
    shutil.copy2(DB_PATH, os.path.join(BACKUP_DIR, safety_name))

    file.save(DB_PATH)
    log('Restored database from backup', file.filename)
    flash('Database restored successfully. Please log in again.', 'success')
    session.clear()
    return redirect(url_for('admin_login'))


@app.route('/admin/backup/delete/<filename>', methods=['POST'])
@super_admin_required
def admin_backup_delete(filename):
    safe_name = secure_filename(filename)
    path = os.path.join(BACKUP_DIR, safe_name)
    if os.path.exists(path):
        os.remove(path)
        log('Deleted backup file', safe_name)
    flash('Backup file deleted.', 'success')
    return redirect(url_for('admin_backup'))


# ---------------------------------------------------------------------------
# SUPER ADMIN: MANAGE TEAM (accounts, roles, permissions)
# ---------------------------------------------------------------------------



@app.route('/admin/team')
@super_admin_required
def admin_team():
    conn = get_db()
    rows = conn.execute('SELECT * FROM admins ORDER BY (role = "super_admin") DESC, username').fetchall()
    conn.close()
    return render_template('admin/team.html', rows=rows)


@app.route('/admin/team/create', methods=['POST'])
@super_admin_required
def admin_team_create():
    username = request.form.get('username', '').strip()
    email = request.form.get('email', '').strip()
    role = request.form.get('role', 'teacher')
    custom_password = request.form.get('custom_password', '').strip()
    if role not in ('super_admin', 'admin', 'teacher'):
        role = 'teacher'

    conn = get_db()
    existing = conn.execute('SELECT 1 FROM admins WHERE username = ?', (username,)).fetchone()
    policy_errors = password_policy_errors(custom_password) if custom_password else []

    if not username or len(username) < 3:
        flash('Username must be at least 3 characters.', 'error')
    elif existing:
        flash('That username is already taken.', 'error')
    elif custom_password and policy_errors:
        flash('Password is too weak: ' + '; '.join(policy_errors), 'error')
    elif not custom_password and (not email or '@' not in email):
        flash('Enter a valid email address (to send login details), or set a password yourself instead.', 'error')
    else:
        use_password = custom_password if custom_password else secrets.token_urlsafe(9)
        must_change = 0 if custom_password else 1
        conn.execute(
            '''INSERT INTO admins (username, email, password_hash, role, status, must_change_password)
               VALUES (?, ?, ?, ?, 'active', ?)''',
            (username, email or None, generate_password_hash(use_password), role, must_change)
        )
        conn.commit()
        log('Created new account', f'{username} ({role})')

        if custom_password:
            flash(f'Account "{username}" created with the password you set. Share it with them directly.', 'success')
        else:
            ok, info = send_email(email, 'Your school website admin account',
                                   f'An account has been created for you.\n\n'
                                   f'Username: {username}\nTemporary password: {use_password}\n\n'
                                   f'Log in and you will be asked to set your own password right away.')
            if ok:
                flash(f'Account created for {username}. Login details were emailed to {email}.', 'success')
            else:
                flash(f'Account created for {username}. Could not email the login details ({info}) — '
                      f'share this temporary password yourself: {use_password}', 'error')
    conn.close()
    return redirect(url_for('admin_team'))


@app.route('/admin/team/<int:admin_id>/toggle', methods=['POST'])
@super_admin_required
def admin_team_toggle(admin_id):
    if admin_id == session.get('admin_id'):
        flash('You cannot disable your own account.', 'error')
        return redirect(url_for('admin_team'))
    conn = get_db()
    row = conn.execute('SELECT * FROM admins WHERE id = ?', (admin_id,)).fetchone()
    if row:
        new_status = 'disabled' if row['status'] == 'active' else 'active'
        conn.execute('UPDATE admins SET status = ? WHERE id = ?', (new_status, admin_id))
        conn.commit()
        log('Changed account status', f"{row['username']} -> {new_status}")
        flash(f"{row['username']} is now {new_status}.", 'success')
    conn.close()
    return redirect(url_for('admin_team'))


@app.route('/admin/team/<int:admin_id>/role', methods=['POST'])
@super_admin_required
def admin_team_role(admin_id):
    new_role = request.form.get('role', 'teacher')
    if new_role not in ('super_admin', 'admin', 'teacher'):
        new_role = 'teacher'
    if admin_id == session.get('admin_id') and new_role != 'super_admin':
        flash('You cannot remove your own Super Admin role.', 'error')
        return redirect(url_for('admin_team'))
    conn = get_db()
    row = conn.execute('SELECT username FROM admins WHERE id = ?', (admin_id,)).fetchone()
    conn.execute('UPDATE admins SET role = ? WHERE id = ?', (new_role, admin_id))
    conn.commit()
    conn.close()
    if row:
        log('Changed account role', f"{row['username']} -> {new_role}")
        flash(f"{row['username']}'s role is now {new_role.replace('_',' ').title()}.", 'success')
    return redirect(url_for('admin_team'))


@app.route('/admin/team/<int:admin_id>/delete', methods=['POST'])
@super_admin_required
def admin_team_delete(admin_id):
    if admin_id == session.get('admin_id'):
        flash('You cannot delete your own account.', 'error')
        return redirect(url_for('admin_team'))
    conn = get_db()
    row = conn.execute('SELECT username FROM admins WHERE id = ?', (admin_id,)).fetchone()
    conn.execute('DELETE FROM admins WHERE id = ?', (admin_id,))
    conn.commit()
    conn.close()
    if row:
        log('Deleted account', row['username'])
        flash(f"{row['username']}'s account was deleted.", 'success')
    return redirect(url_for('admin_team'))


@app.route('/admin/team/<int:admin_id>/set-password', methods=['POST'])
@super_admin_required
def admin_team_set_password(admin_id):
    """Lets the Super Admin directly set a password for ANY account (including their own),
    no email/OTP required — since the Super Admin already has full trusted control."""
    new_password = request.form.get('new_password', '').strip()
    policy_errors = password_policy_errors(new_password)

    conn = get_db()
    row = conn.execute('SELECT username FROM admins WHERE id = ?', (admin_id,)).fetchone()

    if not row:
        flash('Account not found.', 'error')
    elif policy_errors:
        flash('Password is too weak: ' + '; '.join(policy_errors), 'error')
    else:
        conn.execute('UPDATE admins SET password_hash = ?, must_change_password = 0 WHERE id = ?',
                     (generate_password_hash(new_password), admin_id))
        conn.commit()
        log('Set password for account', row['username'])
        flash(f"Password for \"{row['username']}\" updated.", 'success')
    conn.close()
    return redirect(url_for('admin_team'))


# ---------------------------------------------------------------------------
# TEACHER AREA — limited access: notifications, admission requests (view-only), notices
# ---------------------------------------------------------------------------

@app.route('/admin/teacher')
@login_required
def admin_teacher_home():
    conn = get_db()
    notifications = conn.execute(
        '''SELECT * FROM notifications WHERE admin_id IS NULL OR admin_id = ?
           ORDER BY created_at DESC LIMIT 20''', (session['admin_id'],)).fetchall()
    recent_admissions = conn.execute(
        'SELECT * FROM admissions ORDER BY created_at DESC LIMIT 10').fetchall()
    conn.close()
    return render_template('admin/teacher_home.html', notifications=notifications, recent_admissions=recent_admissions)


@app.route('/admin/teacher/admissions')
@login_required
def admin_teacher_admissions():
    conn = get_db()
    rows = conn.execute('SELECT * FROM admissions ORDER BY created_at DESC').fetchall()
    conn.close()
    return render_template('admin/teacher_admissions.html', rows=rows)


@app.route('/admin/teacher/notices')
@login_required
def admin_teacher_notices():
    conn = get_db()
    rows = conn.execute('SELECT * FROM notices ORDER BY published_date DESC').fetchall()
    conn.close()
    return render_template('admin/teacher_notices.html', rows=rows)


@app.route('/admin/notifications/mark-read/<int:n_id>', methods=['POST'])
@login_required
def admin_notification_mark_read(n_id):
    conn = get_db()
    conn.execute('UPDATE notifications SET is_read = 1 WHERE id = ?', (n_id,))
    conn.commit()
    conn.close()
    return redirect(request.referrer or url_for('admin_teacher_home'))


if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)
