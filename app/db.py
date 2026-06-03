import mysql.connector
from flask import current_app, g


def create_database_if_not_exists():
    db_name = current_app.config['MYSQL_DB']

    conn = mysql.connector.connect(
        host=current_app.config['MYSQL_HOST'],
        user=current_app.config['MYSQL_USER'],
        password=current_app.config['MYSQL_PASSWORD']
    )
    cursor = conn.cursor()
    cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{db_name}`")
    conn.commit()
    cursor.close()
    conn.close()


def get_db():
    if 'db' not in g:
        create_database_if_not_exists()

        g.db = mysql.connector.connect(
            host=current_app.config['MYSQL_HOST'],
            user=current_app.config['MYSQL_USER'],
            password=current_app.config['MYSQL_PASSWORD'],
            database=current_app.config['MYSQL_DB']
        )
    return g.db


def close_db(e=None):
    db = g.pop('db', None)
    if db is not None and db.is_connected():
        db.close()



def _column_exists(cursor, table_name, column_name):
    cursor.execute(f"SHOW COLUMNS FROM `{table_name}` LIKE %s", (column_name,))
    return cursor.fetchone() is not None


def _add_column_if_missing(cursor, table_name, column_name, ddl):
    if not _column_exists(cursor, table_name, column_name):
        cursor.execute(f"ALTER TABLE `{table_name}` ADD COLUMN {ddl}")


def _seed_admin_permissions(cursor):
    tabs = [
        ('dashboard', 'Dashboard', 'main.home', '/home', 'Main', 10),
        ('view_master', 'View Master', 'main.view_keywords', '/view-keywords', 'Operations', 20),
        ('news_processing', 'News Processing', 'main.all_non_published_news', '/all-non-published-news', 'Operations', 30),
        ('settings', 'Settings', 'main.user_settings', '/user-settings', 'System', 40),
        ('chatbot', 'Chatbot', 'main.chatbot', '/chatbot', 'Main', 50),
        ('admin_dashboard', 'Admin Dashboard', 'admin.dashboard', '/admin/dashboard', 'Admin', 60),
        ('user_management', 'User Management', 'admin.users', '/admin/users', 'Admin', 70),
        ('permission_management', 'Permission Management', 'admin.user_permissions', '/admin/users', 'Admin', 80),
        ('analytics', 'Operations Analytics', 'admin.analytics', '/admin/analytics', 'Admin', 90),
        ('activity_logs', 'Activity Logs', 'admin.activity_logs', '/admin/activity-logs', 'Admin', 100),
    ]
    for tab in tabs:
        cursor.execute(
            """
            INSERT INTO app_tabs (tab_key, tab_name, endpoint, route_url, category, display_order)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                tab_name=VALUES(tab_name),
                endpoint=VALUES(endpoint),
                route_url=VALUES(route_url),
                category=VALUES(category),
                display_order=VALUES(display_order),
                is_active=1
            """,
            tab,
        )

    role_defaults = {
        'admin': {
            'dashboard': (1, 1, 1, 1),
            'view_master': (1, 1, 1, 1),
            'news_processing': (1, 1, 1, 1),
            'settings': (1, 1, 1, 1),
            'chatbot': (1, 1, 1, 1),
            'admin_dashboard': (1, 1, 1, 1),
            'user_management': (1, 1, 1, 1),
            'permission_management': (1, 1, 1, 1),
            'analytics': (1, 1, 1, 1),
            'activity_logs': (1, 1, 1, 1),
        },
        'editor': {
            'dashboard': (1, 0, 0, 0),
            'view_master': (1, 1, 1, 1),
            'news_processing': (1, 1, 1, 1),
            'settings': (0, 0, 0, 0),
            'chatbot': (1, 1, 0, 0),
            'admin_dashboard': (0, 0, 0, 0),
            'user_management': (0, 0, 0, 0),
            'permission_management': (0, 0, 0, 0),
            'analytics': (0, 0, 0, 0),
            'activity_logs': (0, 0, 0, 0),
        },
        'user': {
            'dashboard': (1, 0, 0, 0),
            'view_master': (0, 0, 0, 0),
            'news_processing': (0, 0, 0, 0),
            'settings': (0, 0, 0, 0),
            'chatbot': (1, 1, 0, 0),
            'admin_dashboard': (0, 0, 0, 0),
            'user_management': (0, 0, 0, 0),
            'permission_management': (0, 0, 0, 0),
            'analytics': (0, 0, 0, 0),
            'activity_logs': (0, 0, 0, 0),
        },
    }
    for role, tabs_map in role_defaults.items():
        for tab_key, permissions in tabs_map.items():
            cursor.execute(
                """
                INSERT INTO role_permissions
                    (role, tab_key, can_view, can_create, can_edit, can_delete)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    can_view=VALUES(can_view),
                    can_create=VALUES(can_create),
                    can_edit=VALUES(can_edit),
                    can_delete=VALUES(can_delete)
                """,
                (role, tab_key, *permissions),
            )


def init_db():
    db = get_db()
    cursor = db.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            email VARCHAR(150) NOT NULL UNIQUE,
            password VARCHAR(255) NOT NULL,
            role VARCHAR(20) NOT NULL DEFAULT 'user',
            is_active TINYINT(1) NOT NULL DEFAULT 1,
            last_login DATETIME DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS news_articles (
            id INT AUTO_INCREMENT PRIMARY KEY,
            title VARCHAR(500) NOT NULL,
            source VARCHAR(255),
            url TEXT,
            published_date DATETIME,
            content LONGTEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS keywords (
            id INT AUTO_INCREMENT PRIMARY KEY,
            sr_no INT NOT NULL UNIQUE,
            keyword LONGTEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS websites (
            id INT AUTO_INCREMENT PRIMARY KEY,
            sr_no INT NOT NULL UNIQUE,
            websites LONGTEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS news (
            id INT AUTO_INCREMENT PRIMARY KEY,
            sr_no INT NOT NULL UNIQUE,
            news_type LONGTEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS commodity (
            id INT AUTO_INCREMENT PRIMARY KEY,
            sr_no INT NOT NULL UNIQUE,
            commodity LONGTEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
       CREATE TABLE IF NOT EXISTS non_published_news (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    news_date       DATE,
    news_type       LONGTEXT,
    news_headline   LONGTEXT,
    news_text       LONGTEXT,
    news_url        TEXT,
    keywords        LONGTEXT,
    date_of_insert  DATETIME DEFAULT CURRENT_TIMESTAMP,
    published       TINYINT(1) NOT NULL DEFAULT 0
);
    """)
    cursor.execute("""
       CREATE TABLE IF NOT EXISTS published_news (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    source_id           INT,                          -- original id from non_published_news
    news_date           DATE,
    news_type           LONGTEXT,
    news_headline       LONGTEXT,
    news_text           LONGTEXT,
    news_url            TEXT,
    keywords            LONGTEXT,
    date_of_insert      DATETIME,                     -- original insert date from source
    published_at        DATETIME DEFAULT CURRENT_TIMESTAMP,  -- when it was published
    pdf_path            VARCHAR(500),                 -- path to generated PDF file
    email_sent          TINYINT(1) DEFAULT 0,         -- 0 = not sent, 1 = sent
    email_sent_at       DATETIME DEFAULT NULL
);
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS chatbot_concerns (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NULL,
        concern_text LONGTEXT NOT NULL,
        status VARCHAR(50) DEFAULT 'open',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
""")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_settings (
    id                    INT AUTO_INCREMENT PRIMARY KEY,
    user_id               INT DEFAULT 1,          -- link to users.id if needed
    run_frequency         VARCHAR(20) DEFAULT '1', -- '1','2','5','10','24','custom'
    custom_frequency      INT DEFAULT NULL,         -- hours, only if run_frequency='custom'
    scraper_enabled       TINYINT(1) DEFAULT 1,
    publish_mode          VARCHAR(10) DEFAULT 'manual', -- 'auto' or 'manual'
    content_categories    VARCHAR(255) DEFAULT 'all',   -- comma-separated: 'all','agricultural','weather', etc.
    email_recipient       VARCHAR(255) DEFAULT 'niyati.b@seamlessautomations.com',
    email_cc              TEXT DEFAULT NULL,
    email_subject_prefix  VARCHAR(255) DEFAULT 'Daily News Alert',
    email_on_publish      TINYINT(1) DEFAULT 1,
    updated_at            DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS chatbot_history (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NULL,
        session_id VARCHAR(100) DEFAULT NULL,
        user_message LONGTEXT,
        bot_reply LONGTEXT,
        msg_type VARCHAR(50) DEFAULT 'chat',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_chatbot_history_user (user_id),
        INDEX idx_chatbot_history_session (session_id),
        INDEX idx_chatbot_history_created (created_at)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS app_tabs (
        id INT AUTO_INCREMENT PRIMARY KEY,
        tab_key VARCHAR(100) NOT NULL UNIQUE,
        tab_name VARCHAR(150) NOT NULL,
        endpoint VARCHAR(150) DEFAULT NULL,
        route_url VARCHAR(255) DEFAULT NULL,
        category VARCHAR(100) DEFAULT NULL,
        display_order INT DEFAULT 0,
        is_active TINYINT(1) DEFAULT 1,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS role_permissions (
        id INT AUTO_INCREMENT PRIMARY KEY,
        role VARCHAR(20) NOT NULL,
        tab_key VARCHAR(100) NOT NULL,
        can_view TINYINT(1) DEFAULT 0,
        can_create TINYINT(1) DEFAULT 0,
        can_edit TINYINT(1) DEFAULT 0,
        can_delete TINYINT(1) DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY uq_role_tab (role, tab_key)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_permissions (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NOT NULL,
        tab_key VARCHAR(100) NOT NULL,
        can_view TINYINT(1) DEFAULT 0,
        can_create TINYINT(1) DEFAULT 0,
        can_edit TINYINT(1) DEFAULT 0,
        can_delete TINYINT(1) DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY uq_user_tab (user_id, tab_key),
        INDEX idx_user_permissions_user (user_id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS activity_logs (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NULL,
        action VARCHAR(100) NOT NULL,
        module_name VARCHAR(100) NOT NULL,
        description LONGTEXT,
        ip_address VARCHAR(100) DEFAULT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_activity_user (user_id),
        INDEX idx_activity_module (module_name),
        INDEX idx_activity_created (created_at)
    )
    """)


    # ═══ SCHEMA MIGRATIONS ═══
    # Admin portal / permissions migrations for existing databases
    try:
        _add_column_if_missing(cursor, 'users', 'role', "role VARCHAR(20) NOT NULL DEFAULT 'user'")
        _add_column_if_missing(cursor, 'users', 'is_active', "is_active TINYINT(1) NOT NULL DEFAULT 1")
        _add_column_if_missing(cursor, 'users', 'last_login', "last_login DATETIME DEFAULT NULL")
        _add_column_if_missing(cursor, 'users', 'updated_at', "updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP")
        _add_column_if_missing(cursor, 'user_settings', 'sync_all_schedules', "sync_all_schedules TINYINT(1) DEFAULT 1")
        _add_column_if_missing(cursor, 'user_settings', 'schedule_all', "schedule_all JSON DEFAULT NULL")
        _add_column_if_missing(cursor, 'user_settings', 'schedule_agricultural', "schedule_agricultural JSON DEFAULT NULL")
        _add_column_if_missing(cursor, 'user_settings', 'schedule_weather', "schedule_weather JSON DEFAULT NULL")
        _add_column_if_missing(cursor, 'user_settings', 'schedule_financial', "schedule_financial JSON DEFAULT NULL")
        _add_column_if_missing(cursor, 'user_settings', 'schedule_energy', "schedule_energy JSON DEFAULT NULL")
        _add_column_if_missing(cursor, 'user_settings', 'schedule_global', "schedule_global JSON DEFAULT NULL")
        _seed_admin_permissions(cursor)
        db.commit()

        cursor.execute("SELECT COUNT(*) FROM users WHERE role='admin'")
        admin_count = cursor.fetchone()[0]
        if not admin_count:
            cursor.execute("SELECT id FROM users ORDER BY id ASC LIMIT 1")
            first_user = cursor.fetchone()
            if first_user:
                cursor.execute("UPDATE users SET role='admin', is_active=1 WHERE id=%s", (first_user[0],))
                db.commit()
                print(f"[DB] First existing user id={first_user[0]} promoted to admin for bootstrap.")
    except Exception as e:
        print(f"[DB] Admin portal migration failed: {e}")

    # Upgrade existing published_news table columns to LONGTEXT if needed
    try:
        cursor.execute("SHOW COLUMNS FROM published_news LIKE 'news_type'")
        col = cursor.fetchone()
        if col and 'VARCHAR' in str(col).upper():
            print("[DB] Upgrading published_news columns to LONGTEXT...")
            cursor.execute("ALTER TABLE published_news MODIFY news_type LONGTEXT")
            cursor.execute("ALTER TABLE published_news MODIFY news_headline LONGTEXT")
            cursor.execute("ALTER TABLE published_news MODIFY keywords LONGTEXT")
            db.commit()
            print("[DB] Schema migration completed")
    except Exception as e:
        print(f"[DB] Schema check failed (might be first run): {e}")

    
    db.commit()
    cursor.close()


def init_app(app):
    app.teardown_appcontext(close_db)

    with app.app_context():
        create_database_if_not_exists()
        init_db()