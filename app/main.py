import os
from pathlib import Path

from authlib.integrations.flask_client import OAuth
from flask import (
    Flask,
    abort,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user

from app.auth import admin_required, super_admin_required
from app.config import Config
from app.extensions import db, login_manager
from app.google_drive import (
    extract_google_drive_folder_id,
    fetch_drive_documents,
    fetch_drive_folder_images,
)
from app.models import (
    Admin,
    Announcement,
    DriveDocumentAlias,
    Event,
    Notice,
    RecipientConfig,
    UploadedFile,
)
from app.utils import (
    allowed_file,
    build_email_links,
    ensure_storage_directories,
    file_icon_for_extension,
    normalize_email,
    save_uploaded_file,
)


def create_app() -> Flask:
    app = Flask(__name__, template_folder="../templates", static_folder="../static")
    app.config.from_object(Config())
    ensure_storage_directories(app.config)

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "admin_login"

    oauth = OAuth(app)
    if app.config["GOOGLE_OAUTH_CLIENT_ID"] and app.config["GOOGLE_OAUTH_CLIENT_SECRET"]:
        oauth.register(
            name="google",
            client_id=app.config["GOOGLE_OAUTH_CLIENT_ID"],
            client_secret=app.config["GOOGLE_OAUTH_CLIENT_SECRET"],
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
        )

    @login_manager.user_loader
    def load_user(user_id: str):
        return db.session.get(Admin, int(user_id))

    with app.app_context():
        db.create_all()
        _ensure_default_recipient_config()
        _ensure_super_admin()

    @app.context_processor
    def inject_society_name():
        return {"society_name": app.config["SOCIETY_NAME"]}

    @app.route("/")
    def index():
        notices = Notice.query.order_by(Notice.priority.desc(), Notice.created_at.desc()).limit(5).all()
        announcements = Announcement.query.order_by(Announcement.created_at.desc()).limit(5).all()
        events = Event.query.order_by(Event.created_at.desc()).limit(5).all()
        uploads = UploadedFile.query.order_by(UploadedFile.created_at.desc()).limit(12).all()
        carousel_images = resolve_carousel_images(app.config)
        drive_documents = resolve_drive_documents(app.config)
        return render_template(
            "index.html",
            notices=notices,
            announcements=announcements,
            events=events,
            uploads=uploads,
            carousel_images=carousel_images,
            drive_documents=drive_documents,
            icon_resolver=file_icon_for_extension,
        )

    @app.route("/drive-documents")
    def drive_documents_page():
        documents = resolve_drive_documents(app.config)
        return render_template("drive_documents.html", drive_documents=documents)

    @app.route("/api/health")
    def health():
        return jsonify(
            {
                "status": "ok",
                "database_path": str(app.config["DB_PATH"]),
                "uploads_path": str(app.config["UPLOADS_PATH"]),
                "society_name": app.config["SOCIETY_NAME"],
            }
        )

    @app.route("/admin-login")
    def admin_login():
        if current_user.is_authenticated:
            return redirect(url_for("admin_dashboard"))
        oauth_enabled = bool(
            app.config["GOOGLE_OAUTH_CLIENT_ID"] and app.config["GOOGLE_OAUTH_CLIENT_SECRET"]
        )
        return render_template("admin_login.html", oauth_enabled=oauth_enabled)

    @app.route("/auth/google")
    def auth_google():
        if "google" not in oauth._clients:  # noqa: SLF001
            abort(503, description="Google OAuth is not configured.")
        redirect_uri = app.config["OAUTH_REDIRECT_URI"] or url_for(
            "auth_google_callback", _external=True
        )
        return oauth.google.authorize_redirect(redirect_uri)

    @app.route("/auth/callback")
    @app.route("/auth/google/callback")
    def auth_google_callback():
        if "google" not in oauth._clients:  # noqa: SLF001
            abort(503, description="Google OAuth is not configured.")
        token = oauth.google.authorize_access_token()
        user_info = token.get("userinfo") or oauth.google.userinfo()
        email = normalize_email(user_info.get("email", ""))
        if not email:
            abort(403, description="Google account email unavailable.")

        admin = Admin.query.filter_by(email=email, is_active=True).first()
        super_admin_email = normalize_email(app.config["SUPER_ADMIN_EMAIL"])
        is_super_admin = email == super_admin_email

        if is_super_admin and not admin:
            admin = Admin(
                email=email,
                is_super_admin=True,
                is_active=True,
                display_name=user_info.get("name", ""),
            )
            db.session.add(admin)
            db.session.commit()

        if not admin:
            abort(403, description="This Google account is not authorized as admin.")

        admin.display_name = user_info.get("name", admin.display_name)
        admin.is_super_admin = admin.is_super_admin or is_super_admin
        db.session.commit()
        login_user(admin)
        session["admin_email"] = admin.email
        return redirect(url_for("admin_dashboard"))

    @app.route("/logout", methods=["POST"])
    @login_required
    def logout():
        logout_user()
        return redirect(url_for("index"))

    @app.route("/admin")
    @admin_required
    def admin_dashboard():
        recipient = _get_recipient_config()
        notices = Notice.query.order_by(Notice.priority.desc(), Notice.created_at.desc()).all()
        admins = Admin.query.order_by(Admin.created_at.desc()).all()
        uploads = UploadedFile.query.order_by(UploadedFile.created_at.desc()).all()
        drive_documents = resolve_drive_documents(app.config)
        aliases = {
            row.drive_file_id: row.display_name
            for row in DriveDocumentAlias.query.order_by(DriveDocumentAlias.created_at.desc()).all()
        }
        return render_template(
            "admin.html",
            recipient=recipient,
            notices=notices,
            admins=admins,
            uploads=uploads,
            drive_documents=drive_documents,
            drive_aliases=aliases,
            icon_resolver=file_icon_for_extension,
        )

    @app.route("/api/email-links")
    def api_email_links():
        category = (request.args.get("category") or "").strip().lower()
        subject = request.args.get("subject", "").strip()
        body = request.args.get("body", "").strip()
        recipient = _recipient_for_category(category)
        if not recipient:
            return jsonify({"error": "No recipient configured for this category."}), 400
        email_links = build_email_links(recipient, subject, body)
        return jsonify({"to": recipient, **email_links})

    @app.route("/api/carousel-images")
    def api_carousel_images():
        return jsonify({"images": resolve_carousel_images(app.config)})

    @app.route("/api/drive-documents")
    def api_drive_documents():
        return jsonify({"documents": resolve_drive_documents(app.config)})

    @app.route("/admin/notices", methods=["POST"])
    @admin_required
    def admin_create_notice():
        title = request.form.get("title", "").strip()
        content = request.form.get("content", "").strip()
        priority = request.form.get("priority") == "on"
        if not title or not content:
            abort(400, description="Title and content are required.")
        db.session.add(Notice(title=title, content=content, priority=priority))
        db.session.commit()
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/notices/<int:notice_id>/delete", methods=["POST"])
    @admin_required
    def admin_delete_notice(notice_id: int):
        notice = db.session.get(Notice, notice_id)
        if not notice:
            abort(404)
        db.session.delete(notice)
        db.session.commit()
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/announcements", methods=["POST"])
    @admin_required
    def admin_create_announcement():
        title = request.form.get("title", "").strip()
        content = request.form.get("content", "").strip()
        if not title or not content:
            abort(400, description="Title and content are required.")
        db.session.add(Announcement(title=title, content=content))
        db.session.commit()
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/events", methods=["POST"])
    @admin_required
    def admin_create_event():
        title = request.form.get("title", "").strip()
        event_date = request.form.get("event_date", "").strip()
        details = request.form.get("details", "").strip()
        if not title or not event_date:
            abort(400, description="Title and event date are required.")
        db.session.add(Event(title=title, event_date=event_date, details=details))
        db.session.commit()
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/recipients", methods=["POST"])
    @admin_required
    def admin_update_recipients():
        recipient = _get_recipient_config()
        recipient.service_requests_email = normalize_email(
            request.form.get("service_requests_email", "")
        )
        recipient.amenities_email = normalize_email(request.form.get("amenities_email", ""))
        recipient.forms_email = normalize_email(request.form.get("forms_email", ""))
        recipient.office_email = normalize_email(request.form.get("office_email", ""))
        db.session.commit()
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/upload", methods=["POST"])
    @admin_required
    def admin_upload_file():
        title = request.form.get("title", "").strip()
        file = request.files.get("file")
        if not title or not file or not file.filename:
            abort(400, description="Title and file are required.")
        if not allowed_file(file.filename, app.config["ALLOWED_UPLOAD_EXTENSIONS"]):
            abort(400, description="Unsupported file type.")
        stored_name, relative_path, extension = save_uploaded_file(
            file, app.config["UPLOADS_PATH"]
        )
        db.session.add(
            UploadedFile(
                title=title,
                filename=stored_name,
                relative_path=relative_path,
                extension=extension,
                uploaded_by=current_user.email,
            )
        )
        db.session.commit()
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/drive-documents/alias", methods=["POST"])
    @admin_required
    def admin_save_drive_alias():
        drive_file_id = (request.form.get("drive_file_id") or "").strip()
        display_name = (request.form.get("display_name") or "").strip()
        if not drive_file_id:
            abort(400, description="Drive file ID is required.")
        alias = DriveDocumentAlias.query.filter_by(drive_file_id=drive_file_id).first()
        if not alias:
            alias = DriveDocumentAlias(drive_file_id=drive_file_id, display_name=display_name)
            db.session.add(alias)
        else:
            alias.display_name = display_name
        db.session.commit()
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/drive-documents/alias/<int:alias_id>/delete", methods=["POST"])
    @admin_required
    def admin_delete_drive_alias(alias_id: int):
        alias = db.session.get(DriveDocumentAlias, alias_id)
        if not alias:
            abort(404)
        db.session.delete(alias)
        db.session.commit()
        return redirect(url_for("admin_dashboard"))

    @app.route("/uploads/<path:filename>")
    def uploads_file(filename: str):
        upload_root = Path(app.config["UPLOADS_PATH"])
        return send_from_directory(upload_root, filename)

    @app.route("/admin/admins", methods=["POST"])
    @super_admin_required
    def admin_add_admin():
        email = normalize_email(request.form.get("email", ""))
        if not email:
            abort(400, description="Valid email required.")
        existing = Admin.query.filter_by(email=email).first()
        if not existing:
            db.session.add(Admin(email=email, is_super_admin=False, is_active=True))
            db.session.commit()
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/admins/<int:admin_id>/toggle", methods=["POST"])
    @super_admin_required
    def admin_toggle_admin(admin_id: int):
        admin = db.session.get(Admin, admin_id)
        if not admin:
            abort(404)
        if normalize_email(admin.email) == normalize_email(app.config["SUPER_ADMIN_EMAIL"]):
            return redirect(url_for("admin_dashboard"))
        admin.is_active = not admin.is_active
        db.session.commit()
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/admins/<int:admin_id>/remove", methods=["POST"])
    @super_admin_required
    def admin_remove_admin(admin_id: int):
        admin = db.session.get(Admin, admin_id)
        if not admin:
            abort(404)
        if admin.is_super_admin:
            return redirect(url_for("admin_dashboard"))
        db.session.delete(admin)
        db.session.commit()
        return redirect(url_for("admin_dashboard"))

    return app


def resolve_carousel_images(config_obj: dict) -> list[str]:
    folder_url = config_obj.get("GOOGLE_DRIVE_FOLDER_URL", "").strip()
    folder_id = extract_google_drive_folder_id(folder_url)
    api_key = config_obj.get("GOOGLE_DRIVE_API_KEY", "").strip()
    if folder_id and api_key:
        fetched = fetch_drive_folder_images(folder_id, api_key)
        if fetched:
            return fetched
    return config_obj["DEFAULT_CAROUSEL_IMAGES"]


def resolve_drive_documents(config_obj: dict) -> list[dict]:
    folder_url = config_obj.get("GOOGLE_DRIVE_FOLDER_URL", "").strip()
    folder_id = extract_google_drive_folder_id(folder_url)
    api_key = config_obj.get("GOOGLE_DRIVE_API_KEY", "").strip()
    if not folder_id or not api_key:
        return []
    docs = fetch_drive_documents(folder_id, api_key)
    aliases = {
        row.drive_file_id: row.display_name
        for row in DriveDocumentAlias.query.order_by(DriveDocumentAlias.created_at.desc()).all()
    }
    for doc in docs:
        mapped = aliases.get(doc["id"], "").strip()
        if mapped:
            doc["display_name"] = mapped
    return docs


def _ensure_default_recipient_config() -> None:
    existing = RecipientConfig.query.first()
    if not existing:
        db.session.add(RecipientConfig())
        db.session.commit()


def _ensure_super_admin() -> None:
    email = normalize_email(os.getenv("SUPER_ADMIN_EMAIL", ""))
    if not email:
        return
    admin = Admin.query.filter_by(email=email).first()
    if not admin:
        admin = Admin(email=email, is_super_admin=True, is_active=True)
        db.session.add(admin)
    else:
        admin.is_super_admin = True
        admin.is_active = True
    db.session.commit()


def _get_recipient_config() -> RecipientConfig:
    recipient = RecipientConfig.query.first()
    if not recipient:
        recipient = RecipientConfig()
        db.session.add(recipient)
        db.session.commit()
    return recipient


def _recipient_for_category(category: str) -> str:
    recipient = _get_recipient_config()
    fallback = normalize_email(os.getenv("SUPER_ADMIN_EMAIL", ""))
    if category == "service_requests":
        return recipient.service_requests_email or fallback
    if category == "book_amenities":
        return recipient.amenities_email or fallback
    if category == "forms":
        return recipient.forms_email or fallback
    if category == "society_office":
        return recipient.office_email or fallback
    return recipient.office_email or recipient.service_requests_email or fallback


app = create_app()


if __name__ == "__main__":
    port = int(os.getenv("PORT", "4173"))
    app.run(host="0.0.0.0", port=port)
