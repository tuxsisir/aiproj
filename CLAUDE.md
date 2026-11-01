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
- Email: `anymail` + Resend; console backend when `DEBUG` and no `RESEND_API_KEY`. **All email goes through
  `core/emails.py`** (`EMAILS` registry + `send(key, to, context)`; templates in `core/templates/emails/`,
  plain text derived from HTML, one private copy per recipient). allauth emails route there via
  `core.adapters.AccountAdapter`; welcome email on `user_signed_up` (`core/signals.py`).
  Staff preview of every email with sample data: `/admin/emails/` (`core/email_previews.py` holds the samples;
  add sample context there when a new email needs new variables).
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
- `documents` — building document library: `Document` (PDF, category, structured AI `summary` JSON,
  `summary_status`, `claude_file_id`) and `DocumentQuestion` (saved Q&A with page citations). All Claude calls
  live in `documents/ai.py` (shared client/model/fallback in `core/ai.py`; Files API, citations, prompt caching);
  `documents/services.py` orchestrates. Slow AI work runs via `core.background.run_after_commit` (daemon thread). PDFs are served only via
  the permission-checked `documents:file` view. Needs `ANTHROPIC_API_KEY`; without it the UI says AI isn't set up.
- `inbox` — per-building forwarding address (`Inbox`, `<plan>-<hex>@INBOUND_EMAIL_DOMAIN`) and `InboundEmail`
  with an AI issue summary. anymail's Resend inbound webhook (`/anymail/resend/inbound/`) fires the `inbound`
  signal (`inbox/signals.py`); only active members of that building are accepted; the summary is emailed back to
  the forwarder. Try locally: `manage.py inbox_simulate <PLAN> <member email> <thread.txt>`.
- `payments` — Stripe checkout, customer portal, webhook at `/payments/webhooks/stripe/`.

## Architecture conventions (see `docs/PLAN.md`)
- Function-based views only, kept thin; business rules + side effects in each app's `services.py`.
- Validate input with Django forms; never trust POSTed choice values.
- Common reads as QuerySet methods: `Membership.objects.active().council()`, `.pending()`, `.managers()`.
- `stratas.decorators.membership_required` for views that need an active building membership.
- Permission checks via `membership.is_council` / `membership.is_manager`; display via `membership.title`.
- Data conversions go in their own migration (Postgres "pending trigger events" error otherwise).
- Owners/tenants have no accounts; they only use token links.
- AI "working" UI: `<c-ai.working message=... hint=.../>` + `.ai-*` classes in `core/static/core/ai.css`
  (`.ai-indicator` for HTMX loading slots, `.ai-reveal` on results).

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
- `record_audit_log`: pass an explicit `AuditLog.Action` for events (CREATE after `objects.create()`, VOTE_CAST…);
  without one it only logs inferred field UPDATEs. Audit logs are viewable read-only in admin.
- Manual timeline entries go through `dockets.forms.IncidentEventForm` (NOTE / RECURRENCE / EVIDENCE only).
- `incident.bylaw` is nullable; notice/fine emails dereference it.
- Documents/inbox tests mock `documents.ai` / `inbox.ai`; never call the real API from tests.
- Root-level `test_*.py` scripts are NOT tests; they write to the real DB on import. Always run tests with
  app labels (below) so the runner never discovers them.

## Commands
- Env: `.venv` on Python **3.13** (`.python-version`), managed with uv. Use `.venv/bin/python`.
  Setup: `uv venv --python 3.13 .venv && uv pip install --python .venv/bin/python -r requirements.txt`.
  (System default Python is 3.15, which Django 5.2 doesn't support.)
- Local DB is Postgres `stratacorp` (from `.env`), already migrated with demo data.
- **Local logins** (DEBUG only, `core/dev.py`): one-click "Log in as" on the login page and a "Dev:" switcher in
  the dashboard header. Accounts: admin / manager / president / treasurer / newcomer (pending) `@civicdesk.test`,
  password `DEV_ACCOUNT_PASSWORD`. Recreate/repair anytime: `manage.py seed_dev_accounts`. Demo users must use
  reserved domains (.test / example.*) so they never receive real email.
- `python manage.py runserver`, `python manage.py migrate`, `python manage.py init_demo_data`
- Tests: `.venv/bin/python manage.py test core stratas dockets documents inbox payments` (dev-login tests in
  `core/tests_dev.py` use their own urlconf because tests run with DEBUG off) (factories in `core/testing.py`).
- Quick throwaway DB: `DATABASE_URL="sqlite://:memory:" python manage.py shell -c "..."` (run `migrate` first inside).

## Style
- Python: `ruff`. Templates: `djlint`, one HTML attribute per line.
- Design language "blueprint & lamplight": night ink `#0a0f1c` + blueprint grid, warm paper `#f6f3ec`,
  lamp amber `#ffb547` = activity, violet `#8b7bff` = AI. Type: Fraunces (display, 600; italic 500 for accents), Geist (UI),
  Geist Mono (plan labels). Brand: `<c-brand.wordmark/>` / `<c-brand.mark/>`.
- Landing (`core/templates/landing.html`) is standalone with `core/static/core/landing.css|js` (living building,
  ask demo, reveals). App-wide motion in `core/static/core/alive.css|js`: `.btn-glow` on primary buttons,
  `.card-hover`, `.live-dot`, `data-count-up`, `.page-enter` wraps dashboard content. Always respect
  `prefers-reduced-motion`. Public pages are light-only (`dark:` follows the `.dark` class, not the OS).
- Dashboard: dark-mode capable, theme preference in `localStorage`.
- Visual checks: `DEBUG_TOOLBAR=False manage.py runserver` + headless Chrome screenshots (min width 500px;
  CSS animations don't advance in headless virtual time, so freeze them via `document.getAnimations()`).
