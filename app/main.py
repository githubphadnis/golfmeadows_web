import os
from pathlib import Path

from authlib.integrations.flask_client import OAuth
from flask import (
    Flask,
    abort,
    jsonify,
    redirect,
    Response,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user
import requests
from werkzeug.middleware.proxy_fix import ProxyFix

from app.auth import admin_required, super_admin_required
from app.config import Config
from app.extensions import db, login_manager
from app.google_drive import (
    extract_google_drive_folder_id,
    fetch_drive_carousel_images,
    fetch_drive_documents,
)
from app.models import (
    Admin,
    Announcement,
    DriveDocumentMapping,
    Event,
    Notice,
    RecipientConfig,
    TileContent,
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
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
    app.config["SESSION_COOKIE_SECURE"] = True
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
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
        _ensure_default_tile_content()
        _ensure_super_admin(app.config["SUPER_ADMIN_EMAIL"])

    @app.context_processor
    def inject_society_name():
        return {
            "society_name": app.config["SOCIETY_NAME"],
            "tile_content": _get_tile_content(),
        }

    @app.route("/")
    def index():
        notices = Notice.query.order_by(Notice.priority.desc(), Notice.created_at.desc()).limit(5).all()
        announcements = Announcement.query.order_by(Announcement.created_at.desc()).limit(5).all()
        events = Event.query.order_by(Event.created_at.desc()).limit(5).all()
        uploads = UploadedFile.query.order_by(UploadedFile.created_at.desc()).limit(12).all()
        return render_template(
            "index.html",
            notices=notices,
            announcements=announcements,
            events=events,
            uploads=uploads,
            carousel_images=resolve_carousel_images(app.config),
            drive_documents=resolve_drive_documents(app.config),
            tile_content=_get_tile_content(),
            icon_resolver=file_icon_for_extension,
        )

    @app.route("/api/hero-image/<file_id>")
    def hero_image_proxy(file_id: str):
        api_key = app.config.get("GOOGLE_DRIVE_API_KEY", "").strip()
        if not file_id or not api_key:
            abort(404)
        if file_id.startswith("https-fallback-"):
            defaults = app.config.get("DEFAULT_CAROUSEL_IMAGES", [])
            try:
                index = int(file_id.rsplit("-", 1)[1])
                fallback_url = defaults[index]
            except (IndexError, ValueError):
                abort(404)
            try:
                fallback_response = requests.get(fallback_url, timeout=15)
                fallback_response.raise_for_status()
            except requests.RequestException as exc:
                app.logger.error("Hero fallback image fetch failed: %s", exc)
                abort(502, description="Unable to fetch fallback hero image.")
            return Response(
                fallback_response.content,
                mimetype=fallback_response.headers.get("Content-Type", "image/jpeg"),
            )
        drive_url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media&key={api_key}"
        try:
            response = requests.get(drive_url, timeout=15)
            response.raise_for_status()
        except requests.RequestException as exc:
            if "response" in locals() and response is not None:
                app.logger.error(
                    "Hero proxy Drive API error: %s - %s",
                    response.status_code,
                    response.text,
                )
            else:
                app.logger.error("Hero proxy Drive API request failed: %s", exc)
            abort(502, description="Unable to fetch hero image.")

        content_type = response.headers.get("Content-Type", "image/jpeg")
        return Response(response.content, mimetype=content_type)

    @app.route("/notices")
    def notices_page():
        notices = Notice.query.order_by(Notice.priority.desc(), Notice.created_at.desc()).all()
        return render_template(
            "section_page.html",
            page_title="Notices from the Managing Committee",
            tile_key="notices_desc",
            tile_content=_get_tile_content(),
            cards=[
                {"title": notice.title, "description": notice.content, "meta": "Priority" if notice.priority else ""}
                for notice in notices
            ],
        )

    @app.route("/announcements")
    def announcements_page():
        announcements = Announcement.query.order_by(Announcement.created_at.desc()).all()
        return render_template(
            "section_page.html",
            page_title="Announcements",
            tile_key="announcements",
            tile_content=_get_tile_content(),
            cards=[
                {"title": row.title, "description": row.content, "meta": row.created_at.strftime("%Y-%m-%d")}
                for row in announcements
            ],
        )

    @app.route("/events")
    def events_page():
        events = Event.query.order_by(Event.created_at.desc()).all()
        return render_template(
            "section_page.html",
            page_title="Events",
            tile_key="events",
            tile_content=_get_tile_content(),
            cards=[
                {"title": row.title, "description": row.details or "Community event", "meta": row.event_date}
                for row in events
            ],
        )

    @app.route("/service-requests")
    def service_requests_page():
        return render_template(
            "section_page.html",
            page_title="Service Requests",
            tile_key="service_requests",
            tile_content=_get_tile_content(),
            cards=[
                {"title": "Maintenance", "description": "Report plumbing, electrical, or common area issues.", "meta": ""},
                {"title": "Housekeeping", "description": "Raise a cleaning or garbage management request.", "meta": ""},
                {"title": "Security", "description": "Inform the team about visitor/security concerns.", "meta": ""},
            ],
        )

    @app.route("/book-amenities")
    def book_amenities_page():
        return render_template(
            "section_page.html",
            page_title="Book Amenities",
            tile_key="book_amenities",
            tile_content=_get_tile_content(),
            cards=[
                {"title": "Club House", "description": "Book for meetings and social gatherings.", "meta": ""},
                {"title": "Multipurpose Hall", "description": "Reserve for private and community events.", "meta": ""},
                {"title": "Sports Area", "description": "Schedule sports courts and recreation blocks.", "meta": ""},
            ],
        )

    @app.route("/forms")
    def forms_page():
        uploads = UploadedFile.query.order_by(UploadedFile.created_at.desc()).all()
        cards = [
            {
                "title": item.title,
                "description": f"Local upload ({item.extension.upper()})",
                "meta": item.created_at.strftime("%Y-%m-%d"),
                "href": url_for("uploads_file", filename=item.relative_path),
            }
            for item in uploads
        ]
        for doc in resolve_drive_documents(app.config):
            cards.append(
                {
                    "title": doc["display_name"],
                    "description": "Google Drive document",
                    "meta": doc.get("extension", "").upper(),
                    "href": doc.get("web_content_link") or doc.get("web_view_link"),
                }
            )
        return render_template(
            "section_page.html",
            page_title="Forms",
            tile_key="forms",
            tile_content=_get_tile_content(),
            cards=cards,
        )

    @app.route("/society-office")
    def society_office_page():
        return render_template(
            "section_page.html",
            page_title="Society Office",
            tile_key="society_office",
            tile_content=_get_tile_content(),
            cards=[
                {"title": "General Enquiries", "description": "Administrative and resident support desk.", "meta": ""},
                {"title": "Billing Desk", "description": "Maintenance dues and receipt support.", "meta": ""},
                {"title": "Facility Desk", "description": "Parking, access cards, and permissions.", "meta": ""},
            ],
        )

    @app.route("/useful-links")
    def useful_links_page():
        return render_template(
            "section_page.html",
            page_title="Useful Links",
            tile_key="useful_links",
            tile_content=_get_tile_content(),
            cards=[
                {"title": "MahaRERA", "description": "State real estate authority portal.", "href": "https://www.maharera.mahaonline.gov.in/", "meta": ""},
                {"title": "MSEDCL", "description": "Electricity utility portal.", "href": "https://mahadiscom.in/", "meta": ""},
                {"title": "Municipal Services", "description": "Municipal citizen services.", "href": "https://portal.mcgm.gov.in/", "meta": ""},
            ],
        )

    @app.route("/drive-documents")
    def drive_documents_page():
        documents = resolve_drive_documents(app.config)
        return render_template("drive_documents.html", drive_documents=documents, tile_content=_get_tile_content())

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

    @app.route("/api/email-links")
    def api_email_links():
        category = (request.args.get("category") or "").strip().lower()
        subject = request.args.get("subject", "").strip()
        body = request.args.get("body", "").strip()
        recipient = _recipient_for_category(category, app.config["SUPER_ADMIN_EMAIL"])
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
        email = normalize_email((user_info.get("email") or "").lower())
        if not email:
            abort(403, description="Google account email unavailable.")

        super_admin_email = normalize_email(app.config["SUPER_ADMIN_EMAIL"])
        is_super_admin = email == super_admin_email
        admin = Admin.query.filter_by(email=email, is_active=True).first()

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
        aliases = DriveDocumentMapping.query.order_by(DriveDocumentMapping.created_at.desc()).all()
        drive_aliases = {row.drive_file_id: row.display_name for row in aliases}
        alias_index = {row.drive_file_id: row.id for row in aliases}
        return render_template(
            "admin.html",
            recipient=recipient,
            notices=notices,
            admins=admins,
            uploads=uploads,
            drive_documents=drive_documents,
            drive_aliases=drive_aliases,
            alias_index=alias_index,
            tile_content=_get_tile_content(),
            icon_resolver=file_icon_for_extension,
        )

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

    @app.route("/admin/tile-content", methods=["POST"])
    @admin_required
    def admin_update_tile_content():
        for key in _tile_defaults().keys():
            title = (request.form.get(f"{key}_title") or "").strip()
            blurb = (request.form.get(f"{key}_blurb") or "").strip()
            row = TileContent.query.filter_by(tile_key=key).first()
            if not row:
                row = TileContent(tile_key=key, title=title or key.replace("_", " ").title(), blurb=blurb)
                db.session.add(row)
            else:
                if title:
                    row.title = title
                row.blurb = blurb
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
        alias = DriveDocumentMapping.query.filter_by(drive_file_id=drive_file_id).first()
        if not alias:
            alias = DriveDocumentMapping(drive_file_id=drive_file_id, display_name=display_name)
            db.session.add(alias)
        else:
            alias.display_name = display_name
        db.session.commit()
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/drive-documents/alias/<int:alias_id>/delete", methods=["POST"])
    @admin_required
    def admin_delete_drive_alias(alias_id: int):
        alias = db.session.get(DriveDocumentMapping, alias_id)
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
    folder_id = _resolve_hero_folder_id(config_obj)
    api_key = config_obj.get("GOOGLE_DRIVE_API_KEY", "").strip()
    if folder_id and api_key:
        fetched = fetch_drive_carousel_images(folder_id, api_key)
        if fetched:
            return fetched
    defaults = config_obj.get("DEFAULT_CAROUSEL_IMAGES", [])
    if isinstance(defaults, list):
        fallback: list[dict[str, str]] = []
        for idx, item in enumerate(defaults):
            value = str(item).strip()
            if value:
                fallback.append({"id": f"https-fallback-{idx}", "url": value})
        return fallback
    return []


def resolve_drive_documents(config_obj: dict) -> list[dict]:
    folder_id = _resolve_docs_folder_id(config_obj)
    api_key = config_obj.get("GOOGLE_DRIVE_API_KEY", "").strip()
    if not folder_id or not api_key:
        return []
    docs = fetch_drive_documents(folder_id, api_key)
    aliases = {
        row.drive_file_id: row.display_name
        for row in DriveDocumentMapping.query.order_by(DriveDocumentMapping.created_at.desc()).all()
    }
    normalized: list[dict] = []
    for doc in docs:
        file_id = (doc.get("file_id") or "").strip()
        if not file_id:
            continue
        original_name = (doc.get("name") or "").strip()
        mapped = aliases.get(file_id, "").strip()
        normalized.append(
            {
                "file_id": file_id,
                "name": original_name,
                "display_name": mapped or original_name,
                "thumbnail_link": (doc.get("thumbnail_link") or "").strip(),
                "web_content_link": (doc.get("web_content_link") or "").strip(),
                "web_view_link": (doc.get("web_view_link") or "").strip(),
                "extension": (doc.get("extension") or "").strip(),
            }
        )
    return normalized


def _tile_defaults() -> dict[str, dict[str, str]]:
    return {
        "hero_subtitle": {
            "title": "Hero Subtitle",
            "blurb": "Stay updated with notices, events, services, and community resources.",
        },
        "notices_desc": {
            "title": "Notices from the Managing Committee",
            "blurb": "Priority notices and updates from the Managing Committee.",
        },
        "announcements": {
            "title": "Announcements",
            "blurb": "Latest society announcements and updates.",
        },
        "events": {
            "title": "Events",
            "blurb": "Upcoming cultural and community events.",
        },
        "service_requests": {
            "title": "Service Requests",
            "blurb": "Need help from the society office? Email directly.",
        },
        "book_amenities": {
            "title": "Book Amenities",
            "blurb": "Reserve clubhouse, hall, and common spaces.",
        },
        "forms": {
            "title": "Forms",
            "blurb": "Access downloadable forms and circulars.",
        },
        "society_office": {
            "title": "Society Office",
            "blurb": "Contact the office for administrative support.",
        },
        "useful_links": {
            "title": "Useful Links",
            "blurb": "Essential external links for residents.",
        },
    }


def _ensure_default_recipient_config() -> None:
    existing = RecipientConfig.query.first()
    if not existing:
        db.session.add(RecipientConfig())
        db.session.commit()


def _ensure_default_tile_content() -> None:
    defaults = _tile_defaults()
    existing = {row.tile_key: row for row in TileContent.query.all()}
    created = False
    for key, value in defaults.items():
        if key not in existing:
            db.session.add(
                TileContent(
                    tile_key=key,
                    title=value["title"],
                    blurb=value["blurb"],
                )
            )
            created = True
    if created:
        db.session.commit()


def _ensure_super_admin(email: str) -> None:
    normalized = normalize_email(email)
    if not normalized:
        return
    admin = Admin.query.filter_by(email=normalized).first()
    if not admin:
        admin = Admin(email=normalized, is_super_admin=True, is_active=True)
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


def _get_tile_content() -> dict[str, dict[str, str]]:
    defaults = _tile_defaults()
    data = {
        row.tile_key: {"title": row.title, "blurb": row.blurb}
        for row in TileContent.query.all()
    }
    for key, value in defaults.items():
        data.setdefault(key, value)
    return data


def _recipient_for_category(category: str, fallback_email: str) -> str:
    recipient = _get_recipient_config()
    fallback = normalize_email(fallback_email)
    if category == "service_requests":
        return recipient.service_requests_email or fallback
    if category == "book_amenities":
        return recipient.amenities_email or fallback
    if category == "forms":
        return recipient.forms_email or fallback
    if category == "society_office":
        return recipient.office_email or fallback
    return recipient.office_email or recipient.service_requests_email or fallback


def _resolve_hero_folder_id(config_obj: dict) -> str:
    return (config_obj.get("GOOGLE_DRIVE_HERO_FOLDER_ID") or "").strip()


def _resolve_docs_folder_id(config_obj: dict) -> str:
    folder_id = (config_obj.get("GOOGLE_DRIVE_DOCS_FOLDER_ID") or "").strip()
    if folder_id:
        return folder_id
    folder_url = (config_obj.get("GOOGLE_DRIVE_FOLDER_URL") or "").strip()
    if folder_url:
        return extract_google_drive_folder_id(folder_url)
    return ""


app = create_app()


if __name__ == "__main__":
    port = int(os.getenv("PORT", "4273"))
    app.run(host="0.0.0.0", port=port)
