from sqlalchemy.orm import Session

from app import models


def _has_rows(db: Session, model) -> bool:
    return db.query(model).first() is not None


def seed_initial_data(db: Session) -> None:
    if not _has_rows(db, models.Announcement):
        db.add_all(
            [
                models.Announcement(
                    title="Water Tank Cleaning - Block A",
                    body="Scheduled on Sunday, 8:00 AM to 1:00 PM. Water supply may be intermittent.",
                    tag="Maintenance",
                ),
                models.Announcement(
                    title="Visitor Entry via Gate App",
                    body="All visitors must use digital gate approval for smoother and safer access.",
                    tag="Security",
                ),
                models.Announcement(
                    title="Monthly General Body Meeting",
                    body="Saturday 6:30 PM at Clubhouse Hall. Please review agenda in resources.",
                    tag="Community",
                ),
            ]
        )

    if not _has_rows(db, models.Event):
        db.add_all(
            [
                models.Event(
                    event_date="Apr 05",
                    title="Children's Sports Day",
                    details="Cricket, relay races, and fun games at the central lawn.",
                ),
                models.Event(
                    event_date="Apr 19",
                    title="Society Cleanliness Drive",
                    details="Join volunteers for a neighborhood cleanliness and plantation activity.",
                ),
                models.Event(
                    event_date="May 01",
                    title="Maharashtra Day Cultural Evening",
                    details="Music, dance, and snacks organized by residents.",
                ),
            ]
        )

    if not _has_rows(db, models.Resource):
        db.add_all(
            [
                models.Resource(
                    title="Society Bye-Laws (PDF)",
                    description="Standard rules and resident guidelines.",
                    file_url="#",
                ),
                models.Resource(
                    title="Service Request Process Guide",
                    description="How to raise and track service requests.",
                    file_url="#",
                ),
                models.Resource(
                    title="NOC Request Form",
                    description="Application format for move-in/move-out NOC.",
                    file_url="#",
                ),
            ]
        )

    if not _has_rows(db, models.SiteSetting):
        db.add(
            models.SiteSetting(
                key="about_text",
                value=(
                    "GolfMeadows is a resident-driven society in Panvel focused on "
                    "safety, transparency, and quality of life for all families."
                ),
            )
        )

    if not _has_rows(db, models.BusScheduleRow):
        db.add_all(
            [
                models.BusScheduleRow(
                    sort_order=1,
                    time_slot="6:45 AM",
                    route_detail="GolfMeadows → Panvel Railway Station",
                    remarks="Sample row — replace with official timings from the society office.",
                ),
                models.BusScheduleRow(
                    sort_order=2,
                    time_slot="8:30 AM",
                    route_detail="GolfMeadows → CBD Belapur",
                    remarks="Sample row — confirm with security / transport committee.",
                ),
            ]
        )

    if not _has_rows(db, models.LocalContact):
        seed_contacts = [
            "Amrita Supermarket",
            "Subway",
            "Sonawale (vegetable)",
            "Medical shop",
            "Apollo clinics",
            "Apollo ambulance",
            "bablu press wala",
        ]
        db.add_all(
            [
                models.LocalContact(sort_order=i, name=name, phone="", notes="")
                for i, name in enumerate(seed_contacts, start=1)
            ]
        )

    db.commit()
