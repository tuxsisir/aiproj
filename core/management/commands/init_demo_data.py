"""
Presentable demo data for local development and demos. DEBUG only, fictional and anonymized.

Creates DEMO STRATA (EPS 123) with a five-person council, the strata manager (who also manages two other
buildings), a pending newcomer, bylaws, enforcement cases in every stage, documents with summaries and saved
questions, forwarded emails and key dates. All dates are relative to today, so the calendar always looks current.

Run on an empty database (after migrate). Refuses to run twice; flush the database to start over.
Generated PDFs land in MEDIA_ROOT/documents/; a flush doesn't remove them, so old copies pile up in dev.
"""
import datetime

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from core.dev import DEMO_PLAN, demo_strata, ensure_dev_accounts
from core.models import AuditLog, User
from core.services import record_audit_log
from dockets.models import Bylaw, CouncilVote, Incident, IncidentEvent
from documents.models import Document, DocumentQuestion
from inbox.models import InboundEmail
from inbox.services import get_or_create_inbox
from schedule.models import KeyDate
from stratas.models import Membership, StrataPlan

# Council members beyond the dev accounts (president and treasurer). Same password as the dev accounts.
EXTRA_COUNCIL = [
    ("vp@civicdesk.test", "Victor", "Vice", Membership.Position.VICE_PRESIDENT, "210"),
    ("secretary@civicdesk.test", "Selena", "Secretary", Membership.Position.SECRETARY, "406"),
    ("member@civicdesk.test", "Max", "Member", Membership.Position.MEMBER_AT_LARGE, "115"),
]

OTHER_BUILDINGS = [
    {"plan_number": "BCS 2041", "name": "Harbourview Terrace", "street_address": "88 Harbour Way",
     "city": "North Vancouver", "postal_code": "V7L 1A1", "total_units": 64},
    {"plan_number": "EPS 5872", "name": "Cedar Row Townhomes", "street_address": "4500 Cedar Row",
     "city": "Burnaby", "postal_code": "V5G 2B2", "total_units": 24},
]

EXTRA_BYLAWS = [
    ("4(1)", "Use of Strata Lot: No Business Open to the Public", 200),
    ("8(2)", "Visitor Parking: 24-Hour Limit, No EV Charging", 100),
    ("11(3)", "Garbage, Recycling & Bulky Items", 150),
]


def ago(days=0, hours=0):
    return timezone.now() - datetime.timedelta(days=days, hours=hours)


def ahead(days=0, hours=0):
    return timezone.now() + datetime.timedelta(days=days, hours=hours)


class Command(BaseCommand):
    help = "Create presentable demo data (DEBUG only, empty database)."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Refusing to create demo data with known passwords while DEBUG is off.")
        if StrataPlan.objects.filter(plan_number=DEMO_PLAN, incidents__isnull=False).exists():
            raise CommandError("Demo data already exists. Flush the database first to start over.")

        with transaction.atomic():
            self.seed()

        self.stdout.write(self.style.SUCCESS("Demo data ready. Log in with the 'Log in as' buttons on the login page."))
        self.stdout.write("  Council (5): president, treasurer, vp, secretary, member @civicdesk.test")
        self.stdout.write("  Also: manager (3 buildings), newcomer (pending), admin. Password: DEV_ACCOUNT_PASSWORD.")

    def seed(self):
        strata = demo_strata()
        StrataPlan.objects.filter(pk=strata.pk).update(
            name="DEMO STRATA", street_address="123 Demo Street", city="Vancouver", postal_code="V6B 1A1",
            total_units=96,
        )
        strata.refresh_from_db()

        self.users = ensure_dev_accounts(strata)
        self.admin, self.manager = self.users["admin"], self.users["manager"]
        self.president, self.treasurer = self.users["president"], self.users["treasurer"]
        self.council = self.seed_council(strata)

        self.seed_other_buildings()
        bylaws = self.seed_bylaws(strata)
        self.seed_incidents(strata, bylaws)
        documents = self.seed_documents(strata)
        self.seed_questions(strata, documents)
        self.seed_inbox(strata)
        self.seed_key_dates(strata)
        self.stdout.write(f"  {strata}: {strata.incidents.count()} cases, {strata.documents.count()} documents, "
                          f"{strata.inbound_emails.count()} emails, {strata.key_dates.count()} key dates")

    # ---------------------------------------------------------------- people and buildings

    def seed_council(self, strata):
        for email, first, last, position, unit in EXTRA_COUNCIL:
            user = User.objects.filter(email=email).first() or User(email=email, username=email)
            user.first_name, user.last_name = first, last
            user.set_password(settings.DEV_ACCOUNT_PASSWORD)
            user.save()
            Membership.objects.update_or_create(
                user=user, strata=strata,
                defaults={"role": Membership.Role.COUNCIL, "position": position, "unit_number": unit,
                          "status": Membership.Status.ACTIVE},
            )
        Membership.objects.filter(strata=strata, status=Membership.Status.ACTIVE).update(
            reviewed_by=self.admin, reviewed_at=ago(days=200)
        )
        return {m.user.email: m for m in strata.memberships.active().council().select_related("user")}

    def seed_other_buildings(self):
        """The manager's other buildings, so the building switcher has something to switch to."""
        for spec in OTHER_BUILDINGS:
            building, _ = StrataPlan.objects.get_or_create(plan_number=spec["plan_number"], defaults=spec)
            Membership.objects.update_or_create(
                user=self.manager, strata=building,
                defaults={"role": Membership.Role.MANAGER, "status": Membership.Status.ACTIVE},
            )
            KeyDate.objects.get_or_create(
                strata=building, title="Annual General Meeting",
                defaults={"date": timezone.localdate() + datetime.timedelta(days=45),
                          "category": KeyDate.Category.MEETING, "created_by": self.manager},
            )

    def seed_bylaws(self, strata):
        for code, title, fine in EXTRA_BYLAWS:
            Bylaw.objects.get_or_create(
                strata=strata, code=code,
                defaults={"title": title, "standard_fine": fine, "created_by": self.manager},
            )
        return {b.code: b for b in strata.bylaws.all()}

    # ---------------------------------------------------------------- enforcement

    def seed_incidents(self, strata, bylaws):
        council = self.council
        others = [council["vp@civicdesk.test"], council["secretary@civicdesk.test"], council["member@civicdesk.test"]]
        everyone = [council["president@civicdesk.test"], council["treasurer@civicdesk.test"], *others]

        # 1. New complaint, waiting on the manager.
        case = self.incident(
            strata, bylaws["8(2)"], "Visitor stall overstay: white SUV", "305", ago(days=3),
            "A white SUV registered to unit 305 has been parked in visitor stall V4 for four days. "
            "Photos taken on three separate days, with the windshield timestamp visible.",
        )
        self.event(case, IncidentEvent.EventType.RECURRENCE, "Still parked in V4 this morning. Photo added.", ago(days=1),
                   self.president)

        # 2. Common property deficiency raised by council.
        self.incident(
            strata, None, "Storage room 5: broken door strike plate", "", ago(days=6),
            "Strike plate on storage room 5 is bent and the door does not latch. Two lockers were entered last "
            "month. Needs a locksmith and a check of the other storage room doors.",
            incident_type=Incident.Type.DEFICIENCY, created_by=self.president,
        )

        # 3. Notice issued, response due in 4 days.
        case = self.incident(
            strata, bylaws["4(1)"], "Home bakery with customer pick-ups", "207", ago(days=12),
            "Customers are buzzed in several times a day to collect cake orders advertised online, "
            "including evenings. Two residents complained about strangers in the lobby.",
        )
        self.notice(case, issued=ago(days=10))

        # 4. Notice issued, owner never answered: overdue.
        case = self.incident(
            strata, bylaws["8(2)"], "EV charging from visitor stall outlet", "410", ago(days=25),
            "Extension cord run from the visitor stall outlet to a vehicle on four nights. "
            "Common-property electricity is not for private charging.",
        )
        self.notice(case, issued=ago(days=19))

        # 5. Owner replied; council is voting. President and treasurer have not voted yet.
        case = self.incident(
            strata, bylaws["11(3)"], "Mattress and furniture dumped in garbage room", "112", ago(days=24),
            "A mattress, a chair and a bookshelf were left in the parkade garbage room. The hauler charged "
            "a bulky-item fee. Camera footage shows the items arriving.",
        )
        self.notice(case, issued=ago(days=21))
        self.owner_reply(case, ago(days=15),
                         "The furniture was left by our movers, not by us. We will pay the hauling fee "
                         "but ask that the fine be waived.")
        self.votes(case, [(m, True) for m in others[:2]] + [(others[2], False)], ago(days=4))

        # 6. Fined and the fine notice sent.
        case = self.incident(
            strata, bylaws["26(1)"], "Unit listed for nightly rentals", "803", ago(days=60),
            "Unit 803 listed on a short-term rental site with nightly rates; three different guests seen "
            "with suitcases using the lockbox on the bike-room railing.",
        )
        self.notice(case, issued=ago(days=55))
        self.owner_reply(case, ago(days=47), "We request a hearing.", hearing=True)
        self.votes(case, [(m, True) for m in everyone[:4]] + [(everyone[4], False)], ago(days=30))
        self.resolve(case, Incident.Status.RESOLVED_FINED, ago(days=30))
        self.event(case, IncidentEvent.EventType.FINE_DISPATCHED,
                   "Fine notice of $1,000 sent to the owner under bylaw 26(1).", ago(days=28), self.manager)
        self.audit(case, self.manager, AuditLog.Action.FINE_DISPATCHED, ago(days=28))

        # 7. Dismissed after the owner's explanation.
        case = self.incident(
            strata, bylaws["3(4)"], "Renovation noise before 8 am", "502", ago(days=45),
            "Drilling and hammering heard from 7:15 am on two weekdays.",
        )
        self.notice(case, issued=ago(days=42))
        self.owner_reply(case, ago(days=38),
                         "Our contractor started early without telling us. We have moved the start time to "
                         "9 am and apologized to our neighbours.")
        self.votes(case, [(m, False) for m in everyone[:4]] + [(everyone[4], True)], ago(days=33))
        self.resolve(case, Incident.Status.RESOLVED_DISMISSED, ago(days=33))

    def incident(self, strata, bylaw, title, unit, when, description, incident_type=Incident.Type.BYLAW,
                 created_by=None):
        created_by = created_by or self.manager
        case = Incident.objects.create(
            strata=strata, bylaw=bylaw, title=title, unit_number=unit, description=description,
            incident_type=incident_type, created_by=created_by,
            recipient_email=f"unit{unit}@example.com" if unit else "",
        )
        Incident.objects.filter(pk=case.pk).update(created_at=when, updated_at=when)
        self.audit(case, created_by, AuditLog.Action.CREATE, when)
        return case

    def notice(self, case, issued):
        case.notice_issued_at = issued
        case.statutory_deadline = issued + datetime.timedelta(days=14)
        case.status = Incident.Status.NOTICE_ISSUED
        case.save()
        Incident.objects.filter(pk=case.pk).update(updated_at=issued)
        self.event(case, IncidentEvent.EventType.STATUTORY_NOTICE,
                   f"Section 135 notice sent to {case.recipient_email}. The owner has 14 days to respond "
                   "in writing or request a hearing.", issued, self.manager)
        self.audit(case, self.manager, AuditLog.Action.NOTICE_DISPATCHED, issued)

    def owner_reply(self, case, when, text, hearing=False):
        kind = IncidentEvent.EventType.HEARING_REQUESTED if hearing else IncidentEvent.EventType.OWNER_STATEMENT
        self.event(case, kind, text, when, created_by=None)
        case.status = Incident.Status.VOTING_OPEN
        case.save()
        Incident.objects.filter(pk=case.pk).update(updated_at=when)
        self.audit(case, None, AuditLog.Action.STATUS_CHANGE, when, "Owner responded; council vote opened")

    def votes(self, case, ballots, when):
        for membership, approve in ballots:
            CouncilVote.objects.create(
                incident=case, member=membership, approve_fine=approve,
                notes="Levy the fine." if approve else "Dismiss with a warning.",
            )
            self.audit(case, membership.user, AuditLog.Action.VOTE_CAST, when,
                       f"Vote cast: {'Levy Fine' if approve else 'Dismiss'}")
        CouncilVote.objects.filter(incident=case).update(created_at=when)

    def resolve(self, case, status, when):
        case.status = status
        case.save()
        Incident.objects.filter(pk=case.pk).update(updated_at=when)

    def event(self, case, kind, text, when, created_by=None):
        IncidentEvent.objects.create(incident=case, event_type=kind, description=text, occurred_at=when,
                                     created_by=created_by)

    def audit(self, obj, actor, action, when, summary=None):
        log = record_audit_log(obj, actor, action=action, custom_summary=summary)
        AuditLog.objects.filter(pk=log.pk).update(created_at=when)  # demo history only; real logs are never edited

    # ---------------------------------------------------------------- building brain

    def seed_documents(self, strata):
        from weasyprint import HTML

        documents = {}
        for key, (title, category, pages, summary) in DOCUMENTS.items():
            html = "".join(f'<section style="page-break-after: always">{page}</section>' for page in pages)
            pdf = HTML(string=f"<html><body style='font-family: sans-serif; font-size: 12pt'>"
                              f"<h1 style='font-size: 16pt'>{title}</h1>{html}</body></html>").write_pdf()
            document = Document(
                strata=strata, title=title, category=category, uploaded_by=self.manager, summary=summary,
                summary_status=Document.SummaryStatus.READY, summarized_at=ago(days=20),
            )
            document.file.save(f"{key}.pdf", ContentFile(pdf), save=False)
            document.save()
            uploaded = ago(days=90 - 15 * len(documents))
            Document.objects.filter(pk=document.pk).update(created_at=uploaded, updated_at=uploaded)
            documents[key] = document
        return documents

    def seed_questions(self, strata, documents):
        def cite(key, page, quote):
            return {"document_id": str(documents[key].pk), "title": documents[key].title, "page": page, "quote": quote}

        qa = [
            (self.president, "How long can a visitor park in the visitor stalls?", [
                {"text": "Visitors may park in a visitor stall for up to 24 hours in any 72-hour period.",
                 "citations": [cite("bylaws", 2, "A visitor stall may be used for no more than 24 hours in any 72-hour period.")]},
                {"text": " Residents may not park in visitor stalls, and vehicles over the limit can be towed after a warning tag.",
                 "citations": [cite("parking_rules", 1, "Vehicles exceeding the limit may be towed at the owner's expense 24 hours after a warning tag is placed.")]},
            ]),
            (self.treasurer, "When does our fiscal year start, and was a special levy approved?", [
                {"text": "The fiscal year runs from April 1 to March 31.",
                 "citations": [cite("agm_minutes", 1, "The fiscal year of the strata corporation is April 1 to March 31.")]},
                {"text": " No special levy was approved at the last AGM; the operating budget passed with a 4% fee increase.",
                 "citations": [cite("agm_minutes", 2, "Resolution 3 (special levy for lobby renovation) was defeated.")]},
            ]),
            (self.manager, "What is the water damage deductible?", [
                {"text": "The water damage deductible is $50,000 per occurrence.",
                 "citations": [cite("insurance", 1, "Water damage: $50,000 deductible per occurrence.")]},
            ]),
        ]
        for days, (asked_by, question, answer) in zip([9, 5, 1], qa):
            saved = DocumentQuestion.objects.create(strata=strata, asked_by=asked_by, question=question,
                                                    answer=answer, usage={"model": "demo"})
            DocumentQuestion.objects.filter(pk=saved.pk).update(created_at=ago(days=days))

    # ---------------------------------------------------------------- forwarded email

    def seed_inbox(self, strata):
        get_or_create_inbox(strata)
        for spec in EMAILS:
            InboundEmail.objects.create(
                strata=strata, forwarded_by=self.users[spec["forwarded_by"]], from_email=spec["from_email"],
                from_name=spec["from_name"], subject=spec["subject"], body_text=spec["body"],
                received_at=ago(days=spec["days_ago"]), summary=spec["summary"], status=InboundEmail.Status.READY,
            )

    # ---------------------------------------------------------------- calendar

    def seed_key_dates(self, strata):
        today = timezone.localdate()
        for title, offset, category, yearly, note, by in KEY_DATES:
            date = offset if isinstance(offset, datetime.date) else today + datetime.timedelta(days=offset)
            if isinstance(offset, datetime.date):
                date = date.replace(year=today.year)
            key_date = KeyDate.objects.create(
                strata=strata, title=title, date=date, category=category, repeats_yearly=yearly, note=note,
                created_by=self.users[by],
            )
            self.audit(key_date, self.users[by], AuditLog.Action.CREATE, ago(days=30))


# ==================================================================== content (fictional)

DOCUMENTS = {
    "bylaws": ("Bylaws (consolidated 2024)", Document.Category.BYLAWS, [
        "<h2>Division 1: Use of property</h2>"
        "<p>3(4) An owner, tenant or occupant must not cause a nuisance or hazard, or unreasonable noise. "
        "Construction noise is permitted only between 8:00 am and 6:00 pm on weekdays and 10:00 am and "
        "5:00 pm on Saturdays.</p>"
        "<p>4(1) A strata lot must not be used for a business that invites customers or the public into the "
        "building.</p>",
        "<h2>Division 2: Parking</h2>"
        "<p>8(1) Residents must park only in their assigned stalls.</p>"
        "<p>8(2) A visitor stall may be used for no more than 24 hours in any 72-hour period. Visitor stall "
        "outlets must not be used to charge vehicles.</p>",
        "<h2>Division 3: Pets, garbage, rentals and fines</h2>"
        "<p>3(5) Dogs must be leashed on common property. No more than two pets per strata lot.</p>"
        "<p>11(3) Bulky items must not be left in the garbage room; the owner pays any hauling fee.</p>"
        "<p>26(1) A strata lot must not be rented for less than 30 days.</p>"
        "<p>Fines: up to $200 per contravention, $1,000 per day for short-term rentals. A continuing "
        "contravention may be fined every 7 days.</p>",
    ], {
        "overview": "The consolidated bylaws of DEMO STRATA: how lots and common property may be used, "
                    "parking, pets, garbage, rentals and the fines council can impose.",
        "topics": [
            {"name": "Noise & use of lots", "points": [
                {"text": "Construction noise only 8 am–6 pm weekdays, 10 am–5 pm Saturdays.", "pages": [1]},
                {"text": "No business that brings customers into the building.", "pages": [1]}]},
            {"name": "Parking", "points": [
                {"text": "Visitor stalls: 24 hours in any 72-hour period.", "pages": [2]},
                {"text": "No charging vehicles from visitor stall outlets.", "pages": [2]}]},
            {"name": "Pets", "points": [{"text": "Dogs leashed on common property; two pets per lot.", "pages": [3]}]},
            {"name": "Garbage", "points": [{"text": "Bulky items not allowed in the garbage room; owner pays hauling.", "pages": [3]}]},
            {"name": "Rentals", "points": [{"text": "Minimum rental term is 30 days.", "pages": [3]}]},
        ],
        "key_numbers": [
            {"text": "Fine up to $200 per contravention.", "pages": [3]},
            {"text": "$1,000 per day for short-term rentals.", "pages": [3]},
            {"text": "Continuing contraventions can be fined every 7 days.", "pages": [3]},
        ],
    }),
    "parking_rules": ("Rules: Parkade & Visitor Parking (2025)", Document.Category.RULES, [
        "<p>Visitors must display a visitor pass from the concierge binder. Vehicles exceeding the limit may "
        "be towed at the owner's expense 24 hours after a warning tag is placed. Stall V1 is reserved for "
        "trades and moving trucks with a booking.</p>",
    ], {
        "overview": "Council rules for the parkade: visitor passes, towing and the trades stall.",
        "topics": [{"name": "Parking", "points": [
            {"text": "Visitors need a pass from the concierge binder.", "pages": [1]},
            {"text": "Towing allowed 24 hours after a warning tag.", "pages": [1]},
            {"text": "Stall V1 is for booked trades and moves.", "pages": [1]}]}],
        "key_numbers": [{"text": "24 hours between warning tag and towing.", "pages": [1]}],
    }),
    "agm_minutes": ("AGM Minutes: November 2025", Document.Category.MINUTES, [
        "<p>Quorum confirmed: 41 of 96 lots represented. The fiscal year of the strata corporation is April 1 "
        "to March 31. Council elected: five members.</p>",
        "<p>Resolution 1 (2026/27 operating budget, 4% fee increase): carried. Resolution 2 (contingency "
        "reserve contribution of $60,000): carried. Resolution 3 (special levy for lobby renovation) was "
        "defeated.</p>",
    ], {
        "overview": "Minutes of the November 2025 annual general meeting: quorum, council election, budget and "
                    "resolutions.",
        "topics": [
            {"name": "Governance", "points": [{"text": "41 of 96 lots represented; five council members elected.", "pages": [1]}]},
            {"name": "Finance", "points": [
                {"text": "Fiscal year is April 1 to March 31.", "pages": [1]},
                {"text": "Operating budget passed with a 4% fee increase.", "pages": [2]},
                {"text": "Lobby renovation special levy defeated.", "pages": [2]}]},
        ],
        "key_numbers": [
            {"text": "$60,000 contingency reserve contribution.", "pages": [2]},
            {"text": "4% strata fee increase.", "pages": [2]},
        ],
    }),
    "insurance": ("Insurance Summary 2025–2026", Document.Category.INSURANCE, [
        "<p>Policy renews annually. Building replacement value: $42,000,000. Water damage: $50,000 deductible "
        "per occurrence. Earthquake: 15% deductible. Sewer backup: $25,000 deductible.</p>",
    ], {
        "overview": "Summary of the strata's building insurance: coverage and deductibles.",
        "topics": [{"name": "Insurance", "points": [
            {"text": "Building insured for $42M replacement value.", "pages": [1]},
            {"text": "Renews every year.", "pages": [1]}]}],
        "key_numbers": [
            {"text": "Water damage deductible $50,000.", "pages": [1]},
            {"text": "Earthquake deductible 15%.", "pages": [1]},
            {"text": "Sewer backup deductible $25,000.", "pages": [1]},
        ],
    }),
    "fire_report": ("Fire & Life-Safety Inspection Report", Document.Category.OTHER, [
        "<p>Annual inspection of alarms, sprinklers, extinguishers and emergency lighting. 87 of 96 suites "
        "inspected; 9 suites gave no access and must be re-booked.</p>",
        "<p>Deficiencies: two emergency lights in the parkade failed the battery test; the storage room 5 "
        "door does not latch; one extinguisher in the gym is past its service date.</p>",
    ], {
        "overview": "This year's fire and life-safety inspection: results, suites missed and deficiencies to fix.",
        "topics": [
            {"name": "Access", "points": [{"text": "9 suites gave no access and need a re-booked visit.", "pages": [1]}]},
            {"name": "Deficiencies", "points": [
                {"text": "Two parkade emergency lights failed the battery test.", "pages": [2]},
                {"text": "Storage room 5 door does not latch.", "pages": [2]},
                {"text": "Gym extinguisher past its service date.", "pages": [2]}]},
        ],
        "key_numbers": [{"text": "87 of 96 suites inspected.", "pages": [1]}],
    }),
}

EMAILS = [
    {
        "forwarded_by": "president", "from_email": "resident.302@example.com", "from_name": "Resident, unit 302",
        "subject": "Fwd: Parkade gate stuck open again", "days_ago": 2,
        "body": "The parkade gate has been stuck open since Sunday night. This is the third time this month. "
                "Anyone can walk in and the storage rooms are right there.",
        "summary": {
            "title": "Parkade gate stuck open (third time this month)",
            "summary": "A resident reports the parkade gate has stayed open since Sunday night, the third failure "
                       "this month. With storage rooms nearby, it is a security risk. No repair has been booked.",
            "category": "Maintenance & Repairs", "urgency": "high",
            "people": [{"name": "Resident, unit 302", "role": "Reporter", "email": "resident.302@example.com"}],
            "action_items": [{"task": "Book the gate contractor for a repair", "owner": "Strata manager", "due": "This week"},
                             {"task": "Ask for a quote to replace the gate operator", "owner": "Strata manager", "due": "Next council meeting"}],
            "open_questions": ["Is the gate operator still under warranty?"],
            "suggested_next_step": "Have the manager book an emergency repair and bring a replacement quote to council.",
        },
    },
    {
        "forwarded_by": "treasurer", "from_email": "office@gutterpros.example.com", "from_name": "GutterPros Ltd.",
        "subject": "Fwd: Quote: 3-year gutter cleaning contract", "days_ago": 6,
        "body": "Please find our quote for twice-yearly gutter and downspout cleaning: $3,400 per year, price "
                "locked for three years if signed before the end of the month.",
        "summary": {
            "title": "Gutter cleaning: 3-year contract quote",
            "summary": "GutterPros quotes $3,400 a year for twice-yearly gutter cleaning, with the price locked for "
                       "three years if signed by month end. Council has not compared other quotes yet.",
            "category": "Contractors & Quotes", "urgency": "normal",
            "people": [{"name": "GutterPros Ltd.", "role": "Vendor", "email": "office@gutterpros.example.com"}],
            "action_items": [{"task": "Get two comparison quotes", "owner": "Strata manager", "due": "Before month end"}],
            "open_questions": ["What did we pay last year?", "Is downspout flushing included?"],
            "suggested_next_step": "Compare against last year's cost and two other quotes before the price-lock deadline.",
        },
    },
    {
        "forwarded_by": "manager", "from_email": "owner.118@example.com", "from_name": "Owner, unit 118",
        "subject": "Fwd: Storage locker broken into", "days_ago": 9,
        "body": "My storage locker in room 5 was opened and my bike is gone. The room door doesn't close properly. "
                "Can someone check the cameras?",
        "summary": {
            "title": "Storage room 5 locker break-in, bike stolen",
            "summary": "An owner reports their locker in storage room 5 was entered and a bike stolen. The room "
                       "door does not latch. They ask for camera footage to be reviewed.",
            "category": "Owner Request", "urgency": "high",
            "people": [{"name": "Owner, unit 118", "role": "Owner", "email": "owner.118@example.com"}],
            "action_items": [{"task": "Pull camera footage for the past week", "owner": "Strata manager", "due": "Within 7 days"},
                             {"task": "Fix the storage room 5 door latch", "owner": "Strata manager", "due": "As soon as possible"}],
            "open_questions": ["Are the camera clocks correct? Earlier footage had the wrong time."],
            "suggested_next_step": "Review footage and repair the door; tell the owner to file a police report.",
        },
    },
]

KEY_DATES = [
    # (title, days from today or a fixed month/day, category, yearly, note, added by)
    ("Snow-clearing contract review", 3, KeyDate.Category.CONTRACT, False, "Current contract ends this season.", "treasurer"),
    ("Re-book fire inspection for 9 suites", 10, KeyDate.Category.INSPECTION, False, "Suites missed at the annual inspection.", "manager"),
    ("Council meeting", 14, KeyDate.Category.MEETING, False, "Agenda: gate repair, gutter quotes, enforcement.", "president"),
    ("Annual General Meeting", 23, KeyDate.Category.MEETING, True, "Notice must go out at least two weeks before.", "president"),
    ("Insurance renewal", 25, KeyDate.Category.INSURANCE, True, "Get the broker's renewal summary first.", "treasurer"),
    ("Budget draft due to council", 40, KeyDate.Category.FINANCE, False, "", "treasurer"),
    ("Gutter cleaning (fall)", -12, KeyDate.Category.CONTRACT, False, "Done by GutterPros.", "manager"),
    ("Fiscal year starts", datetime.date(2000, 4, 1), KeyDate.Category.FINANCE, True, "April 1 to March 31.", "treasurer"),
    ("Elevator annual safety test (Cat 1)", datetime.date(2000, 7, 15), KeyDate.Category.INSPECTION, True, "", "manager"),
    ("Window washing", datetime.date(2000, 5, 20), KeyDate.Category.CONTRACT, True, "", "manager"),
    ("Carpet cleaning", datetime.date(2000, 9, 10), KeyDate.Category.CONTRACT, True, "Once a year.", "manager"),
]
