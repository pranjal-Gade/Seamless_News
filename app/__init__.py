import os
from flask import Flask
from flask_mail import Mail
from .db import init_app
from .routes.main import init_scheduler

# Module-level Mail instance so routes/auth.py can import it directly:
#   from app import mail
mail = Mail()


def create_app():
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object('config.Config')

    os.makedirs(app.instance_path, exist_ok=True)

    # Initialise DB
    init_app(app)

    # Initialise Flask-Mail
    mail.init_app(app)

    # Register blueprints
    from .routes.auth import auth_bp
    from .routes.main import main_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)

    # Start scheduler
    init_scheduler(app)

    return app