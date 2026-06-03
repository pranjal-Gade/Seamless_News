# Admin Portal + Role/Permission Changes

## Roles added
- `admin`
- `editor`
- `user` / Basic User

## Access logic
- Admin has full access.
- Editor has access to Dashboard, View Master, News Processing, and Chatbot by default.
- Basic User has access to Dashboard and Chatbot by default.
- Admin can customize tab-level permissions for each user.

## New backend files
- `app/permissions.py`
- `app/routes/admin.py`

## New templates
- `app/templates/admin/dashboard.html`
- `app/templates/admin/users.html`
- `app/templates/admin/user_form.html`
- `app/templates/admin/user_permissions.html`
- `app/templates/admin/analytics.html`
- `app/templates/admin/activity_logs.html`
- `app/templates/main/access_denied.html`

## Updated files
- `app/__init__.py`
- `app/db.py`
- `app/routes/auth.py`
- `app/routes/main.py`
- `app/templates/partials/navbar.html`
- `app/templates/main/view_keywords.html`
- `app/templates/main/view_websites.html`
- `app/templates/main/view_news_type.html`
- `app/templates/main/view_commodity.html`
- `app/templates/main/all_non_published_news.html`
- `app/templates/main/today_published_news.html`
- `app/test.py`

## Database changes
The app now creates/migrates these admin/permission fields and tables automatically in `init_db()`:

### users table additions
- `role`
- `is_active`
- `last_login`
- `updated_at`

### New tables
- `app_tabs`
- `role_permissions`
- `user_permissions`
- `activity_logs`
- `chatbot_history`

## Bootstrap admin behavior
- If an existing database has users but no admin, the first existing user is promoted to admin during DB initialization.
- If the database is empty, the first signup user is created as admin.
- All later signup users are basic users by default.

## Protected sections
- View Master routes are protected by `view_master` permission.
- News Processing routes are protected by `news_processing` permission.
- Settings route is protected by `settings` permission.
- Admin routes require `admin` role.

## Admin portal URLs
- `/admin/dashboard`
- `/admin/users`
- `/admin/users/add`
- `/admin/users/<user_id>/edit`
- `/admin/users/<user_id>/permissions`
- `/admin/analytics`
- `/admin/activity-logs`

## Validation completed
- Python syntax validation passed with `python -m py_compile`.
- Jinja template parsing validation passed.
