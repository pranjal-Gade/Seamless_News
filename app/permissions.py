from functools import wraps

from flask import flash, redirect, request, session, url_for

from app.db import get_db


ROLES = ("admin", "editor", "user")
ROLE_LABELS = {
    "admin": "Admin",
    "editor": "Editor",
    "user": "Basic User",
}

APP_TABS = [
    {
        "tab_key": "dashboard",
        "tab_name": "Dashboard",
        "endpoint": "main.home",
        "url": "/home",
        "category": "Main",
        "display_order": 10,
    },
    {
        "tab_key": "view_master",
        "tab_name": "View Master",
        "endpoint": "main.view_keywords",
        "url": "/view-keywords",
        "category": "Operations",
        "display_order": 20,
    },
    {
        "tab_key": "news_processing",
        "tab_name": "News Processing",
        "endpoint": "main.all_non_published_news",
        "url": "/all-non-published-news",
        "category": "Operations",
        "display_order": 30,
    },
    {
        "tab_key": "settings",
        "tab_name": "Settings",
        "endpoint": "main.user_settings",
        "url": "/user-settings",
        "category": "System",
        "display_order": 40,
    },
    {
        "tab_key": "chatbot",
        "tab_name": "Chatbot",
        "endpoint": "main.chatbot",
        "url": "/chatbot",
        "category": "Main",
        "display_order": 50,
    },
    {
        "tab_key": "admin_dashboard",
        "tab_name": "Admin Dashboard",
        "endpoint": "admin.dashboard",
        "url": "/admin/dashboard",
        "category": "Admin",
        "display_order": 60,
    },
    {
        "tab_key": "user_management",
        "tab_name": "User Management",
        "endpoint": "admin.users",
        "url": "/admin/users",
        "category": "Admin",
        "display_order": 70,
    },
    {
        "tab_key": "permission_management",
        "tab_name": "Permission Management",
        "endpoint": "admin.user_permissions",
        "url": "/admin/users",
        "category": "Admin",
        "display_order": 80,
    },
    {
        "tab_key": "analytics",
        "tab_name": "Operations Analytics",
        "endpoint": "admin.analytics",
        "url": "/admin/analytics",
        "category": "Admin",
        "display_order": 90,
    },
    {
        "tab_key": "activity_logs",
        "tab_name": "Activity Logs",
        "endpoint": "admin.activity_logs",
        "url": "/admin/activity-logs",
        "category": "Admin",
        "display_order": 100,
    },
]

ROLE_DEFAULTS = {
    "admin": {
        "dashboard": (1, 1, 1, 1),
        "view_master": (1, 1, 1, 1),
        "news_processing": (1, 1, 1, 1),
        "settings": (1, 1, 1, 1),
        "chatbot": (1, 1, 1, 1),
        "admin_dashboard": (1, 1, 1, 1),
        "user_management": (1, 1, 1, 1),
        "permission_management": (1, 1, 1, 1),
        "analytics": (1, 1, 1, 1),
        "activity_logs": (1, 1, 1, 1),
    },
    "editor": {
        "dashboard": (1, 0, 0, 0),
        "view_master": (1, 1, 1, 1),
        "news_processing": (1, 1, 1, 1),
        "settings": (0, 0, 0, 0),
        "chatbot": (1, 1, 0, 0),
        "admin_dashboard": (0, 0, 0, 0),
        "user_management": (0, 0, 0, 0),
        "permission_management": (0, 0, 0, 0),
        "analytics": (0, 0, 0, 0),
        "activity_logs": (0, 0, 0, 0),
    },
    "user": {
        "dashboard": (1, 0, 0, 0),
        "view_master": (0, 0, 0, 0),
        "news_processing": (0, 0, 0, 0),
        "settings": (0, 0, 0, 0),
        "chatbot": (1, 1, 0, 0),
        "admin_dashboard": (0, 0, 0, 0),
        "user_management": (0, 0, 0, 0),
        "permission_management": (0, 0, 0, 0),
        "analytics": (0, 0, 0, 0),
        "activity_logs": (0, 0, 0, 0),
    },
}


def normalize_role(role):
    role = (role or "user").strip().lower()
    return role if role in ROLES else "user"


def get_current_role():
    return normalize_role(session.get("user_role"))


def get_role_label(role=None):
    return ROLE_LABELS.get(normalize_role(role or get_current_role()), "Basic User")


def _permission_tuple_to_dict(values):
    can_view, can_create, can_edit, can_delete = values
    return {
        "can_view": int(bool(can_view)),
        "can_create": int(bool(can_create)),
        "can_edit": int(bool(can_edit)),
        "can_delete": int(bool(can_delete)),
    }


def default_permission_for(role, tab_key):
    role = normalize_role(role)
    values = ROLE_DEFAULTS.get(role, {}).get(tab_key, (0, 0, 0, 0))
    return _permission_tuple_to_dict(values)


def get_user_permission(user_id, tab_key):
    if not user_id:
        return None
    db = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT can_view, can_create, can_edit, can_delete
            FROM user_permissions
            WHERE user_id=%s AND tab_key=%s
            """,
            (user_id, tab_key),
        )
        return cursor.fetchone()
    except Exception:
        return None
    finally:
        cursor.close()


def get_effective_permission(user_id=None, role=None, tab_key=None):
    if not tab_key:
        return _permission_tuple_to_dict((0, 0, 0, 0))

    user_id = user_id or session.get("user_id")
    role = normalize_role(role or session.get("user_role"))

    if role == "admin":
        return _permission_tuple_to_dict((1, 1, 1, 1))

    override = get_user_permission(user_id, tab_key)
    if override is not None:
        return {
            "can_view": int(bool(override.get("can_view"))),
            "can_create": int(bool(override.get("can_create"))),
            "can_edit": int(bool(override.get("can_edit"))),
            "can_delete": int(bool(override.get("can_delete"))),
        }

    return default_permission_for(role, tab_key)


def has_permission(tab_key, action="view", user_id=None, role=None):
    action = (action or "view").lower()
    col = {
        "view": "can_view",
        "create": "can_create",
        "edit": "can_edit",
        "delete": "can_delete",
    }.get(action, "can_view")

    perm = get_effective_permission(user_id=user_id, role=role, tab_key=tab_key)
    return bool(perm.get(col))


def permission_required(tab_key, action="view"):
    def decorator(view):
        @wraps(view)
        def wrapped_view(*args, **kwargs):
            if "user_id" not in session:
                flash("Please log in to continue.", "warning")
                return redirect(url_for("auth.login"))

            if not has_permission(tab_key, action):
                flash("You do not have permission to access this page.", "danger")
                return redirect(url_for("main.access_denied"))

            return view(*args, **kwargs)
        return wrapped_view
    return decorator


def admin_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to continue.", "warning")
            return redirect(url_for("auth.login"))
        if get_current_role() != "admin":
            flash("Only Admin users can access this section.", "danger")
            return redirect(url_for("main.access_denied"))
        return view(*args, **kwargs)
    return wrapped_view


def load_allowed_tabs():
    return [tab for tab in APP_TABS if has_permission(tab["tab_key"], "view")]


def log_activity(action, module_name, description="", user_id=None):
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            """
            INSERT INTO activity_logs (user_id, action, module_name, description, ip_address)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                user_id or session.get("user_id"),
                (action or "").strip()[:100],
                (module_name or "").strip()[:100],
                description or "",
                request.headers.get("X-Forwarded-For", request.remote_addr),
            ),
        )
        db.commit()
        cursor.close()
    except Exception as exc:
        print(f"[ACTIVITY LOG ERROR] {exc}")
