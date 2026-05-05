import random
import re
import string
from datetime import datetime, timedelta
from functools import wraps

from flask import (Blueprint, current_app, flash, redirect,
                   render_template, request, session, url_for)
from flask_mail import Message
from werkzeug.security import check_password_hash, generate_password_hash

from app.db import get_db

auth_bp = Blueprint('auth', __name__)


# ─── Decorators ──────────────────────────────────────────────────────────────

def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to continue.', 'warning')
            return redirect(url_for('auth.login'))
        return view(*args, **kwargs)
    return wrapped_view


# ─── Helpers ─────────────────────────────────────────────────────────────────

def generate_otp(length=6):
    return ''.join(random.choices(string.digits, k=length))


def is_valid_email(email):
    return re.match(r'^[\w\.-]+@[\w\.-]+\.\w{2,}$', email)


def is_strong_password(password):
    return (
        len(password) >= 6
        and any(c.isdigit() for c in password)
        and any(c.isalpha() for c in password)
    )


def send_email(to, subject, html_body):
    from app import mail
    msg = Message(
        subject=subject,
        sender=current_app.config['MAIL_FROM'],
        recipients=[to],
        html=html_body
    )
    mail.send(msg)


# ─── Email Templates ─────────────────────────────────────────────────────────

def welcome_email_html(name):
    return f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:auto;
                border:1px solid #e0e0e0;border-radius:8px;overflow:hidden;">
      <div style="background:#1a1a2e;padding:30px;text-align:center;">
        <h1 style="color:#e94560;margin:0;">Seamless News Scraper</h1>
      </div>
      <div style="padding:30px;">
        <h2 style="color:#1a1a2e;">Welcome, {name}! 🎉</h2>
        <p style="color:#555;line-height:1.6;">
          Your <strong>Seamless News Scraper</strong> account has been
          created successfully. You can now log in and start scraping
          the news that matters to you.
        </p>
        <p style="color:#555;">Happy scraping!</p>
        <p style="color:#888;font-size:12px;margin-top:40px;
                  border-top:1px solid #eee;padding-top:15px;">
          If you did not create this account, please ignore this email.
        </p>
      </div>
    </div>
    """


def otp_email_html(name, otp, purpose='login'):
    action = 'log in to' if purpose == 'login' else 'reset the password for'
    return f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:auto;
                border:1px solid #e0e0e0;border-radius:8px;overflow:hidden;">
      <div style="background:#1a1a2e;padding:30px;text-align:center;">
        <h1 style="color:#e94560;margin:0;">Seamless News Scraper</h1>
      </div>
      <div style="padding:30px;">
        <h2 style="color:#1a1a2e;">Hi {name},</h2>
        <p style="color:#555;line-height:1.6;">
          Use the OTP below to {action} your Seamless News Scraper account.
          This code is valid for <strong>10 minutes</strong>.
        </p>
        <div style="background:#f4f4f4;border-radius:8px;padding:20px;
                    text-align:center;margin:20px 0;">
          <span style="font-size:36px;font-weight:bold;letter-spacing:8px;
                       color:#e94560;">{otp}</span>
        </div>
        <p style="color:#888;font-size:12px;">
          If you did not request this OTP, please ignore this email.
        </p>
      </div>
    </div>
    """


# ─── Signup ──────────────────────────────────────────────────────────────────

@auth_bp.route('/signup', methods=['GET', 'POST'])
def signup():
    if 'user_id' in session:
        return redirect(url_for('main.home'))

    if request.method == 'POST':
        name     = request.form.get('name', '').strip()
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        errors = []
        if not name:
            errors.append('Name is required.')
        if not email or not is_valid_email(email):
            errors.append('Enter a valid email address.')
        if not is_strong_password(password):
            errors.append('Password must be at least 6 characters and contain both letters and digits.')

        if errors:
            # Tagged 'signup-danger' so it only shows on the signup page
            flash(' | '.join(errors), 'signup-danger')
            return render_template('auth/signup.html')

        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
        if cursor.fetchone():
            cursor.close()
            flash('An account with this email already exists.', 'signup-danger')
            return render_template('auth/signup.html')

        hashed = generate_password_hash(password)
        cursor.execute(
            "INSERT INTO users (name, email, password) VALUES (%s, %s, %s)",
            (name, email, hashed)
        )
        db.commit()
        cursor.close()

        try:
            send_email(email, 'Welcome to Seamless News Scraper!', welcome_email_html(name))
        except Exception as e:
            print(f"[MAIL ERROR] {e}")

        # Tagged 'success' — login page allows 'success' through so user sees this
        flash('Account created! A confirmation email has been sent. Please log in.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/signup.html')


# ─── Login – Step 1: credentials ─────────────────────────────────────────────

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('main.home'))

    if request.method == 'POST':
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        if not email or not password:
            flash('Please enter both email and password.', 'login-danger')
            return render_template('auth/login.html')

        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()
        cursor.close()

        if not user or not check_password_hash(user['password'], password):
            flash('Invalid email or password.', 'login-danger')
            return render_template('auth/login.html')

        otp    = generate_otp()
        expiry = (datetime.utcnow() + timedelta(minutes=10)).isoformat()

        session['otp_login'] = {
            'user_id': user['id'],
            'name':    user['name'],
            'email':   user['email'],
            'otp':     otp,
            'expiry':  expiry,
        }

        try:
            send_email(user['email'], 'Your Seamless Login OTP',
                       otp_email_html(user['name'], otp, 'login'))
        except Exception as e:
            print(f"[MAIL ERROR] {e}")
            flash('Could not send OTP. Please try again.', 'login-danger')
            session.pop('otp_login', None)
            return render_template('auth/login.html')

        flash(f"OTP sent to {user['email']}. Check your inbox.", 'info')
        return redirect(url_for('auth.verify_login_otp'))

    return render_template('auth/login.html')


# ─── Login – Step 2: OTP entry ───────────────────────────────────────────────

@auth_bp.route('/verify-otp', methods=['GET', 'POST'])
def verify_login_otp():
    otp_data = session.get('otp_login')
    if not otp_data:
        flash('Session expired. Please log in again.', 'login-warning')
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        entered = request.form.get('otp', '').strip()

        if datetime.utcnow() > datetime.fromisoformat(otp_data['expiry']):
            session.pop('otp_login', None)
            flash('OTP has expired. Please log in again.', 'login-danger')
            return redirect(url_for('auth.login'))

        if entered != otp_data['otp']:
            flash('Incorrect OTP. Please try again.', 'danger')
            return render_template('auth/verify_otp.html',
                                   purpose='login',
                                   email=otp_data['email'])

        user_id    = otp_data['user_id']
        user_name  = otp_data['name']
        user_email = otp_data['email']

        session.clear()
        session['user_id']    = user_id
        session['user_name']  = user_name
        session['user_email'] = user_email
        session.permanent     = True

        flash(f"Welcome back, {user_name}!", 'success')
        return redirect(url_for('main.home'))

    return render_template('auth/verify_otp.html',
                           purpose='login',
                           email=otp_data['email'])


# ─── Forgot Password – Step 1: enter email ───────────────────────────────────

@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()

        if not is_valid_email(email):
            flash('Enter a valid email address.', 'danger')
            return render_template('auth/forgot_password.html')

        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT id, name FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()
        cursor.close()

        if user:
            otp    = generate_otp()
            expiry = (datetime.utcnow() + timedelta(minutes=10)).isoformat()
            session['otp_reset'] = {
                'user_id': user['id'],
                'name':    user['name'],
                'email':   email,
                'otp':     otp,
                'expiry':  expiry,
            }
            try:
                send_email(email, 'Password Reset OTP – Seamless',
                           otp_email_html(user['name'], otp, 'reset'))
            except Exception as e:
                print(f"[MAIL ERROR] {e}")
                flash('Could not send OTP. Please try again.', 'danger')
                session.pop('otp_reset', None)
                return render_template('auth/forgot_password.html')

        flash('If that email is registered, a reset OTP has been sent.', 'info')
        return redirect(url_for('auth.verify_reset_otp'))

    return render_template('auth/forgot_password.html')


# ─── Forgot Password – Step 2: verify OTP ────────────────────────────────────

@auth_bp.route('/verify-reset-otp', methods=['GET', 'POST'])
def verify_reset_otp():
    otp_data = session.get('otp_reset')
    if not otp_data:
        flash('Session expired. Please start again.', 'warning')
        return redirect(url_for('auth.forgot_password'))

    if request.method == 'POST':
        entered = request.form.get('otp', '').strip()

        if datetime.utcnow() > datetime.fromisoformat(otp_data['expiry']):
            session.pop('otp_reset', None)
            flash('OTP expired. Please try again.', 'danger')
            return redirect(url_for('auth.forgot_password'))

        if entered != otp_data['otp']:
            flash('Incorrect OTP. Please try again.', 'danger')
            return render_template('auth/verify_otp.html',
                                   purpose='reset',
                                   email=otp_data['email'])

        session['reset_verified'] = True
        return redirect(url_for('auth.reset_password'))

    return render_template('auth/verify_otp.html',
                           purpose='reset',
                           email=otp_data['email'])


# ─── Forgot Password – Step 3: new password ──────────────────────────────────

@auth_bp.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    if not session.get('reset_verified') or not session.get('otp_reset'):
        flash('Unauthorized. Please restart the reset flow.', 'danger')
        return redirect(url_for('auth.forgot_password'))

    if request.method == 'POST':
        new_password = request.form.get('password', '')
        confirm      = request.form.get('confirm_password', '')

        if new_password != confirm:
            flash('Passwords do not match.', 'danger')
            return render_template('auth/reset_password.html')

        if not is_strong_password(new_password):
            flash('Password must be at least 6 characters with letters and digits.', 'danger')
            return render_template('auth/reset_password.html')

        otp_data = session['otp_reset']
        hashed   = generate_password_hash(new_password)

        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            "UPDATE users SET password = %s WHERE id = %s",
            (hashed, otp_data['user_id'])
        )
        db.commit()
        cursor.close()

        session.pop('otp_reset', None)
        session.pop('reset_verified', None)
        flash('Password reset successfully. Please log in.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/reset_password.html')


# ─── Resend OTP ───────────────────────────────────────────────────────────────

@auth_bp.route('/resend-otp/<purpose>')
def resend_otp(purpose):
    if purpose == 'login':
        session_key   = 'otp_login'
        email_subject = 'Your Seamless Login OTP'
        redirect_to   = 'auth.verify_login_otp'
    elif purpose == 'reset':
        session_key   = 'otp_reset'
        email_subject = 'Password Reset OTP – Seamless'
        redirect_to   = 'auth.verify_reset_otp'
    else:
        return redirect(url_for('auth.login'))

    otp_data = session.get(session_key)
    if not otp_data:
        flash('Session expired. Please start again.', 'warning')
        return redirect(url_for('auth.login'))

    new_otp            = generate_otp()
    otp_data['otp']    = new_otp
    otp_data['expiry'] = (datetime.utcnow() + timedelta(minutes=10)).isoformat()
    session[session_key] = otp_data

    try:
        send_email(otp_data['email'], email_subject,
                   otp_email_html(otp_data['name'], new_otp, purpose))
        flash('A new OTP has been sent to your email.', 'info')
    except Exception as e:
        print(f"[MAIL ERROR] {e}")
        flash('Failed to resend OTP. Please try again.', 'danger')

    return redirect(url_for(redirect_to))


# ─── Logout ───────────────────────────────────────────────────────────────────

@auth_bp.route('/logout')
@login_required
def logout():
    session.clear()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('main.index'))