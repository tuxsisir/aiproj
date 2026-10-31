# CivicDesk (repo: stratacorp)

SaaS for BC strata corporations to run bylaw enforcement under the Strata Property Act s.135:
complaint intake → manager review → s.135 notice → owner response / hearing request → council vote → fine.
Planned production domain: `usecivicdesk.com`.

## Stack (what the code actually uses)
- Django **5.2** (`requirements.txt`), not 6.0 — `.agy/rules/project-rules.md` is stale (it also mentions
  pgvector `DocumentChunk` and a `django-tailwind` build, neither of which exists).
- Frontend: Tailwind v4 **browser CDN**, Alpine.js, HTMX 1.9, ApexCharts, all loaded from CDNs in
  `core/templates/base_dashboard.html` / `base_public.html`. No `theme/` app or CSS build step.
- UI components: `django-cotton` + `django-cotton-ui` (`core/templates/cotton/`), `heroicons` as template builtin.
- Auth: `django-allauth`, email-only login, Google OAuth; signup form `core.forms.CustomSignupForm`.
- Email: `anymail` + Resend; console backend when `DEBUG` and no `RESEND_API_KEY`.
- PDFs: WeasyPrint (needs system Pango/Cairo libs).
- Payments: Stripe (`payments/`), per-user `UserSubscription`; `subscription_required` decorator is unused.
- DB: `DATABASE_URL` via django-environ (Postgres in `.env`, SQLite fallback). Settings read `.env`.
- Dev-only scripts in repo root (`strip_dark.py`, `update_*.py`, `test_*.py`) and `tmp/` (gitignored) are
  leftovers from agy edits — not part of the app.

## Apps
- `core` — `User` (UUID pk, avatar, phone, brokerage), `BaseModel` (UUID pk + timestamps),
  `FieldTrackerMixin` (dirty-field snapshot via `TRACKED_FIELDS`), immutable `AuditLog` (generic FK),
  `core/services.py::record_audit_log`, landing/dashboard/profile views, `init_demo_data` command.
- `stratas` — `StrataPlan` (tenant boundary), `Membership` (user↔strata: `role` COUNCIL | MANAGER drives
  permissions; `position` PRESIDENT / VICE_PRESIDENT / TREASURER / SECRETARY / MEMBER_AT_LARGE is the council
  office; `status` PENDING | ACTIVE | REJECTED | INACTIVE), `StrataInvitation` (model exists, not wired up),
  onboarding, pending page, strata switcher. Lifecycle logic in `stratas/services.py`; input validation in
  `stratas/forms.py`. Platform admin (superuser) approves/rejects via Django admin actions on Memberships.
- `dockets` — `Bylaw` (per strata; defaults seeded by `post_save` signal in `dockets/signals.py`),
  `Incident` (status machine + `manager_token` / `owner_token` for zero-login portals), `IncidentEvent`
  (timeline), `CouncilVote`. All workflow logic lives in `dockets/views.py` (function views).
- `payments` — Stripe checkout, customer portal, webhook at `/payments/webhooks/stripe/`.

## Architecture conventions (see `docs/PLAN.md`)
- Function-based views only, kept thin; business rules + side effects in each app's `services.py`.
- Validate input with Django forms; never trust POSTed choice values.
- Common reads as QuerySet methods: `Membership.objects.active().council()`, `.pending()`, `.managers()`.
- Permission checks via `membership.is_council` / `membership.is_manager`; display via `membership.title`.
- Data conversions go in their own migration (Postgres "pending trigger events" error otherwise).
- Owners/tenants have no accounts; they only use token links.

## Multi-tenancy conventions
- `stratas.middleware.ActiveStrataMiddleware` sets `request.strata` / `request.membership` from
  `session["active_strata_id"]` (only ACTIVE memberships; falls back to the oldest) and redirects users
  without one to `membership_pending` (if a request is pending) or onboarding, except `EXEMPT_PATHS`.
- Every tenant query must filter by `strata=request.strata` (e.g. `get_object_or_404(Incident, pk=pk, strata=request.strata)`).
- Only managers can switch strata; council members are locked to one building.

## Incident status flow
`IN_REVIEW` → (manager `dispatch_section_135`, sets 14-day `statutory_deadline`) `NOTICE_ISSUED`
→ (owner portal response) `VOTING_OPEN` → (all council voted) `RESOLVED_FINED` | `RESOLVED_DISMISSED`
→ manager `dispatch_fine_notice` + `generate_fine_pdf`. `RESPONSE_RECEIVED` exists but is unused.

## Gotchas
- `record_audit_log` returns `None` (writes nothing) when the instance is not new and has no dirty fields —
  this includes right after `objects.create()`, so create / vote / fine-dispatch logs are silently dropped.
- `incident.bylaw` is nullable; notice/fine emails dereference it.
- `DEFAULT_FROM_EMAIL` default is `civicdesk.app`, not the real domain.
- Root-level `test_*.py` scripts are NOT tests; they write to the real DB on import. Always run tests with
  app labels (below) so the runner never discovers them.

## Commands
- Env: `.venv` on Python **3.13** (`.python-version`), managed with uv. Use `.venv/bin/python`.
  Setup: `uv venv --python 3.13 .venv && uv pip install --python .venv/bin/python -r requirements.txt`.
  (System default Python is 3.15, which Django 5.2 doesn't support.)
- Local DB is Postgres `stratacorp` (from `.env`), already migrated with demo data.
- `python manage.py runserver`, `python manage.py migrate`, `python manage.py init_demo_data`
- Tests: `.venv/bin/python manage.py test core stratas dockets payments` (factories in `core/testing.py`).
- Quick throwaway DB: `DATABASE_URL="sqlite://:memory:" python manage.py shell -c "..."` (run `migrate` first inside).

## Style
- Python: `ruff`. Templates: `djlint`, one HTML attribute per line.
- Dark-mode, shadcn-inspired UI; theme preference in `localStorage`.
