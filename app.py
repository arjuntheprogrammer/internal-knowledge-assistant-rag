from flask import Flask
from flask_cors import CORS
from config import config
from backend.routes.chat import chat_bp
from backend.routes.config import config_bp
from backend.services.scheduler import SchedulerService
from backend.logging import configure_logging
import os


def create_app(config_name="default"):
    # Load production secrets first (before other initialization)
    if config_name == "production" or os.getenv("FLASK_CONFIG") == "production":
        from backend.services.secrets import setup_production_environment
        setup_production_environment()

    configure_logging()
    app = Flask(
        __name__, static_folder="frontend/static", template_folder="frontend/templates"
    )

    app.config.from_object(config[config_name])

    # Handle Proxy headers for Cloud Run HTTPS
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    CORS(app)

    # Initialize extensions
    with app.app_context():
        # Start Background Scheduler
        if os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not app.debug:
            SchedulerService.start_polling()

    @app.context_processor
    def inject_firebase_config():
        # Read directly from os.getenv to ensure values are read after secrets are loaded
        return {
            "firebase_config": {
                "apiKey": os.getenv("FIREBASE_API_KEY"),
                "authDomain": os.getenv("FIREBASE_AUTH_DOMAIN"),
                "projectId": os.getenv("FIREBASE_PROJECT_ID"),
                "storageBucket": os.getenv("FIREBASE_STORAGE_BUCKET"),
                "messagingSenderId": os.getenv("FIREBASE_MESSAGING_SENDER_ID"),
                "appId": os.getenv("FIREBASE_APP_ID"),
            }
        }


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

    @app.route("/privacy")
    def privacy():
        return render_template("privacy.html")

    @app.route("/terms")
    def terms():
        return render_template("terms.html")

    @app.route("/robots.txt")
    @app.route("/sitemap.xml")
    def static_from_root():
        from flask import send_from_directory
        return send_from_directory(app.static_folder, request.path[1:])

    return app


if __name__ == "__main__":
    app = create_app(os.getenv("FLASK_CONFIG") or "default")
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
