from datetime import date, timedelta

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from werkzeug.security import generate_password_hash

from app.db import get_db
from app.permissions import (
    APP_TABS,
    ROLES,
    admin_required,
    default_permission_for,
    get_effective_permission,
    log_activity,
    normalize_role,
)

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def _bool_from_form(name):
    return 1 if request.form.get(name) else 0


def _fetch_user(user_id):
    db = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT id, name, email, role, is_active, created_at, updated_at, last_login FROM users WHERE id=%s",
            (user_id,),
        )
        return cursor.fetchone()
    finally:
        cursor.close()


@admin_bp.route("/")
@admin_required
def index():
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/dashboard")
@admin_required
def dashboard():
    db = get_db()
    cursor = db.cursor(dictionary=True)
    stats = {
        "total_users": 0,
        "admins": 0,
        "editors": 0,
        "basic_users": 0,
        "active_users": 0,
        "inactive_users": 0,
        "published_news": 0,
        "pending_news": 0,
        "sources": 0,
        "today_operations": 0,
    }
    recent_logs = []

    try:
        cursor.execute("SELECT COUNT(*) AS cnt FROM users")
        stats["total_users"] = cursor.fetchone()["cnt"]
        cursor.execute("SELECT COUNT(*) AS cnt FROM users WHERE role='admin'")
        stats["admins"] = cursor.fetchone()["cnt"]
        cursor.execute("SELECT COUNT(*) AS cnt FROM users WHERE role='editor'")
        stats["editors"] = cursor.fetchone()["cnt"]
        cursor.execute("SELECT COUNT(*) AS cnt FROM users WHERE role='user'")
        stats["basic_users"] = cursor.fetchone()["cnt"]
        cursor.execute("SELECT COUNT(*) AS cnt FROM users WHERE is_active=1")
        stats["active_users"] = cursor.fetchone()["cnt"]
        cursor.execute("SELECT COUNT(*) AS cnt FROM users WHERE is_active=0")
        stats["inactive_users"] = cursor.fetchone()["cnt"]
        cursor.execute("SELECT COUNT(*) AS cnt FROM published_news")
        stats["published_news"] = cursor.fetchone()["cnt"]
        cursor.execute("SELECT COUNT(*) AS cnt FROM non_published_news WHERE published=0")
        stats["pending_news"] = cursor.fetchone()["cnt"]
        cursor.execute("SELECT COUNT(*) AS cnt FROM websites")
        stats["sources"] = cursor.fetchone()["cnt"]
        cursor.execute("SELECT COUNT(*) AS cnt FROM activity_logs WHERE DATE(created_at)=CURDATE()")
        stats["today_operations"] = cursor.fetchone()["cnt"]

        cursor.execute(
            """
            SELECT l.*, u.name AS user_name, u.email AS user_email
            FROM activity_logs l
            LEFT JOIN users u ON u.id = l.user_id
            ORDER BY l.created_at DESC
            LIMIT 8
            """
        )
        recent_logs = cursor.fetchall()
    except Exception as exc:
        flash(f"Unable to load admin dashboard completely: {exc}", "warning")
    finally:
        cursor.close()

    return render_template("admin/dashboard.html", stats=stats, recent_logs=recent_logs)


@admin_bp.route("/users")
@admin_required
def users():
    search = request.args.get("q", "").strip()
    role = request.args.get("role", "").strip().lower()
    status = request.args.get("status", "").strip()

    db = get_db()
    cursor = db.cursor(dictionary=True)
    where = []
    params = []

    if search:
        where.append("(name LIKE %s OR email LIKE %s)")
        params.extend([f"%{search}%", f"%{search}%"])
    if role in ROLES:
        where.append("role=%s")
        params.append(role)
    if status in ("0", "1"):
        where.append("is_active=%s")
        params.append(int(status))

    sql = "SELECT id, name, email, role, is_active, created_at, updated_at, last_login FROM users"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY created_at DESC, id DESC"

    try:
        cursor.execute(sql, tuple(params))
        users_list = cursor.fetchall()
    finally:
        cursor.close()

    return render_template(
        "admin/users.html",
        users=users_list,
        roles=ROLES,
        selected_role=role,
        selected_status=status,
        search=search,
    )


@admin_bp.route("/users/add", methods=["GET", "POST"])
@admin_required
def add_user():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        role = normalize_role(request.form.get("role"))
        is_active = _bool_from_form("is_active")

        if not name or not email or not password:
            flash("Name, email, and password are required.", "danger")
            return render_template("admin/user_form.html", roles=ROLES, user=None, mode="add")
        if len(password) < 6:
            flash("Password must be at least 6 characters.", "danger")
            return render_template("admin/user_form.html", roles=ROLES, user=None, mode="add")

        db = get_db()
        cursor = db.cursor(dictionary=True)
        try:
            cursor.execute("SELECT id FROM users WHERE email=%s", (email,))
            if cursor.fetchone():
                flash("A user with this email already exists.", "danger")
                return render_template("admin/user_form.html", roles=ROLES, user=None, mode="add")

            cursor.execute(
                """
                INSERT INTO users (name, email, password, role, is_active)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (name, email, generate_password_hash(password), role, is_active),
            )
            db.commit()
            new_user_id = cursor.lastrowid
            log_activity("create_user", "User Management", f"Created user {email} as {role}.")
            flash("User created successfully.", "success")
            return redirect(url_for("admin.user_permissions", user_id=new_user_id))
        except Exception as exc:
            db.rollback()
            flash(f"Unable to create user: {exc}", "danger")
        finally:
            cursor.close()

    return render_template("admin/user_form.html", roles=ROLES, user=None, mode="add")


@admin_bp.route("/users/<int:user_id>/edit", methods=["GET", "POST"])
@admin_required
def edit_user(user_id):
    user = _fetch_user(user_id)
    if not user:
        flash("User not found.", "warning")
        return redirect(url_for("admin.users"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        role = normalize_role(request.form.get("role"))
        is_active = _bool_from_form("is_active")
        new_password = request.form.get("password", "")

        if not name or not email:
            flash("Name and email are required.", "danger")
            return render_template("admin/user_form.html", roles=ROLES, user=user, mode="edit")

        if user_id == session.get("user_id") and not is_active:
            flash("You cannot deactivate your own account.", "danger")
            return render_template("admin/user_form.html", roles=ROLES, user=user, mode="edit")

        db = get_db()
        cursor = db.cursor(dictionary=True)
        try:
            cursor.execute("SELECT id FROM users WHERE email=%s AND id<>%s", (email, user_id))
            if cursor.fetchone():
                flash("Another user already has this email.", "danger")
                return render_template("admin/user_form.html", roles=ROLES, user=user, mode="edit")

            if new_password:
                if len(new_password) < 6:
                    flash("Password must be at least 6 characters.", "danger")
                    return render_template("admin/user_form.html", roles=ROLES, user=user, mode="edit")
                cursor.execute(
                    """
                    UPDATE users
                    SET name=%s, email=%s, role=%s, is_active=%s, password=%s
                    WHERE id=%s
                    """,
                    (name, email, role, is_active, generate_password_hash(new_password), user_id),
                )
            else:
                cursor.execute(
                    "UPDATE users SET name=%s, email=%s, role=%s, is_active=%s WHERE id=%s",
                    (name, email, role, is_active, user_id),
                )

            db.commit()
            log_activity("edit_user", "User Management", f"Updated user {email}.")
            flash("User updated successfully.", "success")
            return redirect(url_for("admin.users"))
        except Exception as exc:
            db.rollback()
            flash(f"Unable to update user: {exc}", "danger")
        finally:
            cursor.close()

    return render_template("admin/user_form.html", roles=ROLES, user=user, mode="edit")


@admin_bp.route("/users/<int:user_id>/toggle-status", methods=["POST"])
@admin_required
def toggle_user_status(user_id):
    if user_id == session.get("user_id"):
        flash("You cannot deactivate your own account.", "danger")
        return redirect(url_for("admin.users"))

    user = _fetch_user(user_id)
    if not user:
        flash("User not found.", "warning")
        return redirect(url_for("admin.users"))

    new_status = 0 if user.get("is_active") else 1
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("UPDATE users SET is_active=%s WHERE id=%s", (new_status, user_id))
        db.commit()
        status_label = "activated" if new_status else "deactivated"
        log_activity("change_user_status", "User Management", f"{status_label.title()} user {user['email']}.")
        flash(f"User {status_label} successfully.", "success")
    except Exception as exc:
        db.rollback()
        flash(f"Unable to update user status: {exc}", "danger")
    finally:
        cursor.close()
    return redirect(url_for("admin.users"))


@admin_bp.route("/users/<int:user_id>/permissions", methods=["GET", "POST"])
@admin_required
def user_permissions(user_id):
    user = _fetch_user(user_id)
    if not user:
        flash("User not found.", "warning")
        return redirect(url_for("admin.users"))

    if request.method == "POST":
        db = get_db()
        cursor = db.cursor()
        try:
            for tab in APP_TABS:
                tab_key = tab["tab_key"]
                can_view = 1 if request.form.get(f"{tab_key}_view") else 0
                can_create = 1 if request.form.get(f"{tab_key}_create") else 0
                can_edit = 1 if request.form.get(f"{tab_key}_edit") else 0
                can_delete = 1 if request.form.get(f"{tab_key}_delete") else 0
                cursor.execute(
                    """
                    INSERT INTO user_permissions
                        (user_id, tab_key, can_view, can_create, can_edit, can_delete)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        can_view=VALUES(can_view),
                        can_create=VALUES(can_create),
                        can_edit=VALUES(can_edit),
                        can_delete=VALUES(can_delete)
                    """,
                    (user_id, tab_key, can_view, can_create, can_edit, can_delete),
                )
            db.commit()
            log_activity("update_permissions", "Permission Management", f"Updated tab permissions for {user['email']}.")
            flash("Permissions updated successfully.", "success")
            return redirect(url_for("admin.user_permissions", user_id=user_id))
        except Exception as exc:
            db.rollback()
            flash(f"Unable to save permissions: {exc}", "danger")
        finally:
            cursor.close()

    permissions = {}
    defaults = {}
    for tab in APP_TABS:
        tab_key = tab["tab_key"]
        permissions[tab_key] = get_effective_permission(user_id=user_id, role=user.get("role"), tab_key=tab_key)
        defaults[tab_key] = default_permission_for(user.get("role"), tab_key)

    return render_template(
        "admin/user_permissions.html",
        user=user,
        tabs=APP_TABS,
        permissions=permissions,
        defaults=defaults,
    )


@admin_bp.route("/analytics")
@admin_required
def analytics():
    db = get_db()
    cursor = db.cursor(dictionary=True)
    module_counts = []
    action_counts = []
    daily_counts = []
    summary = {
        "operations_today": 0,
        "operations_7_days": 0,
        "news_published_today": 0,
        "users_created_7_days": 0,
    }

    try:
        cursor.execute("SELECT COUNT(*) AS cnt FROM activity_logs WHERE DATE(created_at)=CURDATE()")
        summary["operations_today"] = cursor.fetchone()["cnt"]
        cursor.execute("SELECT COUNT(*) AS cnt FROM activity_logs WHERE created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)")
        summary["operations_7_days"] = cursor.fetchone()["cnt"]
        cursor.execute("SELECT COUNT(*) AS cnt FROM published_news WHERE DATE(published_at)=CURDATE()")
        summary["news_published_today"] = cursor.fetchone()["cnt"]
        cursor.execute("SELECT COUNT(*) AS cnt FROM users WHERE created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)")
        summary["users_created_7_days"] = cursor.fetchone()["cnt"]

        cursor.execute(
            """
            SELECT module_name, COUNT(*) AS cnt
            FROM activity_logs
            GROUP BY module_name
            ORDER BY cnt DESC
            LIMIT 10
            """
        )
        module_counts = cursor.fetchall()
        cursor.execute(
            """
            SELECT action, COUNT(*) AS cnt
            FROM activity_logs
            GROUP BY action
            ORDER BY cnt DESC
            LIMIT 10
            """
        )
        action_counts = cursor.fetchall()
        cursor.execute(
            """
            SELECT DATE(created_at) AS activity_date, COUNT(*) AS cnt
            FROM activity_logs
            WHERE created_at >= DATE_SUB(CURDATE(), INTERVAL 6 DAY)
            GROUP BY DATE(created_at)
            ORDER BY activity_date ASC
            """
        )
        daily_counts = cursor.fetchall()
    except Exception as exc:
        flash(f"Unable to load analytics completely: {exc}", "warning")
    finally:
        cursor.close()

    return render_template(
        "admin/analytics.html",
        summary=summary,
        module_counts=module_counts,
        action_counts=action_counts,
        daily_counts=daily_counts,
    )


@admin_bp.route("/activity-logs")
@admin_required
def activity_logs():
    module_name = request.args.get("module", "").strip()
    user_id = request.args.get("user_id", "").strip()
    days = request.args.get("days", "7").strip()
    try:
        days_int = max(1, min(90, int(days)))
    except ValueError:
        days_int = 7

    db = get_db()
    cursor = db.cursor(dictionary=True)
    where = ["l.created_at >= DATE_SUB(NOW(), INTERVAL %s DAY)"]
    params = [days_int]
    if module_name:
        where.append("l.module_name=%s")
        params.append(module_name)
    if user_id.isdigit():
        where.append("l.user_id=%s")
        params.append(int(user_id))

    try:
        cursor.execute("SELECT id, name, email FROM users ORDER BY name ASC")
        users_list = cursor.fetchall()
        cursor.execute("SELECT DISTINCT module_name FROM activity_logs ORDER BY module_name ASC")
        modules = [row["module_name"] for row in cursor.fetchall()]
        cursor.execute(
            f"""
            SELECT l.*, u.name AS user_name, u.email AS user_email
            FROM activity_logs l
            LEFT JOIN users u ON u.id = l.user_id
            WHERE {' AND '.join(where)}
            ORDER BY l.created_at DESC
            LIMIT 200
            """,
            tuple(params),
        )
        logs = cursor.fetchall()
    finally:
        cursor.close()

    return render_template(
        "admin/activity_logs.html",
        logs=logs,
        users=users_list,
        modules=modules,
        selected_module=module_name,
        selected_user_id=user_id,
        selected_days=days_int,
    )
