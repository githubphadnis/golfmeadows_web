import os

os.environ["DATABASE_PATH"] = "/workspace/tmp/test-db/society.db"
os.environ["UPLOADS_PATH"] = "/workspace/tmp/test-uploads"
os.environ["FLASK_SECRET_KEY"] = "test-secret"
os.environ["SUPER_ADMIN_EMAIL"] = "admin@golfmeadows.org"

from app.main import app
from app.models import TileContent


def test_admin_tile_content_update_route() -> None:
    with app.app_context():
        row = TileContent.query.filter_by(tile_key="service_requests").first()
        assert row is not None
        old_title = row.title
        old_blurb = row.blurb

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["_user_id"] = "1"
            session["_fresh"] = True
            session["admin_email"] = "admin@golfmeadows.org"

        payload = {
            "service_requests_title": "Resident Help Desk",
            "service_requests_blurb": "Updated by automated test.",
            "book_amenities_title": "Book Amenities",
            "book_amenities_blurb": "Reserve clubhouse, hall, and common spaces.",
            "forms_title": "Forms",
            "forms_blurb": "Access downloadable forms and circulars.",
            "society_office_title": "Society Office",
            "society_office_blurb": "Contact the office for administrative support.",
            "announcements_title": "Announcements",
            "announcements_blurb": "Latest society announcements and updates.",
            "events_title": "Events",
            "events_blurb": "Upcoming cultural and community events.",
            "useful_links_title": "Useful Links",
            "useful_links_blurb": "Essential external links for residents.",
            "hero_subtitle_title": "Hero Subtitle",
            "hero_subtitle_blurb": "Stay updated with notices, events, services, and community resources.",
            "notices_desc_title": "Notices from the Managing Committee",
            "notices_desc_blurb": "Priority notices and updates from the Managing Committee.",
        }
        response = client.post("/admin/tile-content", data=payload, follow_redirects=False)
        assert response.status_code == 302

    with app.app_context():
        row = TileContent.query.filter_by(tile_key="service_requests").first()
        assert row is not None
        assert row.title == "Resident Help Desk"
        assert row.blurb == "Updated by automated test."
        row.title = old_title
        row.blurb = old_blurb
