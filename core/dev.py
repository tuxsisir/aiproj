"""
Local development accounts and one-click "log in as". DEBUG only: the URLs are not registered,
the views 404 and the seed command refuses to run when DEBUG is off.

All accounts use the reserved .test domain, which can never receive real email.
Password for every account: settings.DEV_ACCOUNT_PASSWORD (from .env).
"""
from django.conf import settings
from django.contrib.auth import get_user_model, login
from django.http import Http404
from django.shortcuts import redirect
from django.views.decorators.http import require_POST

from stratas.models import Membership, StrataPlan

DEMO_PLAN = "EPS 123"

# key -> account. Order is the order shown in the switcher.
DEV_ACCOUNTS = {
    "admin": {"email": "admin@civicdesk.test", "first_name": "Platform", "last_name": "Admin",
              "label": "Platform admin", "superuser": True},
    "manager": {"email": "manager@civicdesk.test", "first_name": "Mike", "last_name": "Manager",
                "label": "Strata manager", "role": Membership.Role.MANAGER},
    "president": {"email": "president@civicdesk.test", "first_name": "Sara", "last_name": "President",
                  "label": "Council president", "role": Membership.Role.COUNCIL,
                  "position": Membership.Position.PRESIDENT, "unit": "PH1"},
    "treasurer": {"email": "treasurer@civicdesk.test", "first_name": "Tom", "last_name": "Treasurer",
                  "label": "Council treasurer", "role": Membership.Role.COUNCIL,
                  "position": Membership.Position.TREASURER, "unit": "304"},
    "newcomer": {"email": "newcomer@civicdesk.test", "first_name": "Nina", "last_name": "Newcomer",
                 "label": "Pending member", "role": Membership.Role.COUNCIL,
                 "position": Membership.Position.MEMBER_AT_LARGE, "unit": "512",
                 "status": Membership.Status.PENDING},
}

# Old demo emails (real domains) are renamed to their .test replacement.
LEGACY_EMAILS = {"manager@manager.com": "manager", "council@council.com": "president"}


def demo_strata():
    strata = StrataPlan.objects.filter(plan_number=DEMO_PLAN).first()
    return strata or StrataPlan.objects.create(
        plan_number=DEMO_PLAN, name="DEMO STRATA", street_address="123 Demo Street", city="Vancouver",
        postal_code="V6B 1A1", total_units=100,
    )


def ensure_dev_accounts(strata=None):
    """Create or repair every dev account (idempotent). Returns {key: user}."""
    User = get_user_model()
    strata = strata or demo_strata()

    for old_email, key in LEGACY_EMAILS.items():
        new_email = DEV_ACCOUNTS[key]["email"]
        if not User.objects.filter(email=new_email).exists():
            User.objects.filter(email=old_email).update(email=new_email, username=new_email)

    users = {}
    for key, spec in DEV_ACCOUNTS.items():
        user = User.objects.filter(email=spec["email"]).first() or User(email=spec["email"])
        user.username = spec["email"]
        user.first_name = spec["first_name"]
        user.last_name = spec["last_name"]
        user.is_active = True
        user.is_staff = user.is_superuser = spec.get("superuser", False)
        user.set_password(settings.DEV_ACCOUNT_PASSWORD)
        user.save()
        users[key] = user

        if "role" in spec:
            Membership.objects.update_or_create(
                user=user, strata=strata,
                defaults={
                    "role": spec["role"],
                    "position": spec.get("position", ""),
                    "unit_number": spec.get("unit", ""),
                    "status": spec.get("status", Membership.Status.ACTIVE),
                },
            )
    return users


def dev_tools(request):
    """Context processor: the account switcher data, only in DEBUG."""
    if not settings.DEBUG:
        return {}
    return {"dev_accounts": [{"key": key, **spec} for key, spec in DEV_ACCOUNTS.items()]}


@require_POST
def login_as(request, key):
    if not settings.DEBUG or key not in DEV_ACCOUNTS:
        raise Http404
    user = get_user_model().objects.filter(email=DEV_ACCOUNTS[key]["email"]).first()
    if user is None:
        user = ensure_dev_accounts()[key]
    request.session.pop("active_strata_id", None)
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    return redirect("admin:index" if DEV_ACCOUNTS[key].get("superuser") else "dashboard")
