from flask import Flask
from flask_cors import CORS
from config import config
from backend.routes.chat import chat_bp
from backend.routes.config import config_bp
from backend.services.scheduler import SchedulerService
from backend.logging import configure_logging
import os


def create_app(config_name="default"):
    configure_logging()
    app = Flask(
        __name__, static_folder="frontend/static", template_folder="frontend/templates"
    )

    app.config.from_object(config[config_name])

    CORS(app)

    # Initialize extensions
    with app.app_context():
        # Start Background Scheduler (only in main process to avoid duplicates in debug mode with reloader)
        if os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not app.debug:
            SchedulerService.start_polling()

    # Register Blueprints
    app.register_blueprint(config_bp, url_prefix="/api/config")
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

    @app.route("/configure")
    def configure():
        return render_template("configure.html")

    return app


if __name__ == "__main__":
    app = create_app(os.getenv("FLASK_CONFIG") or "default")
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
