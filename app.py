from flask import Flask
from flask_cors import CORS
from config import config
from backend.services.db import Database
from backend.models.user import User
from backend.routes.auth import auth_bp
from backend.routes.admin import admin_bp
from backend.routes.chat import chat_bp
from backend.services.scheduler import SchedulerService
import os


def create_app(config_name="default"):
    app = Flask(
        __name__, static_folder="frontend/static", template_folder="frontend/templates"
    )

    app.config.from_object(config[config_name])

    CORS(app)

    # Initialize extensions and db
    with app.app_context():
        Database.initialize()
        User.create_admin_if_not_exists()

        # Start Background Scheduler (only in main process to avoid duplicates in debug mode with reloader)
        if os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not app.debug:
            SchedulerService.start_polling()

    # Register Blueprints
    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(admin_bp, url_prefix="/api/admin")
    app.register_blueprint(chat_bp, url_prefix="/api/chat")

    from flask import render_template

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/login")
    def login():
        return render_template("login.html")

    @app.route("/signup")
    def signup():
        return render_template("signup.html")

    @app.route("/admin/dashboard")
    def admin_dashboard():
        return render_template("admin.html")

    return app


if __name__ == "__main__":
    app = create_app(os.getenv("FLASK_CONFIG") or "default")
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
