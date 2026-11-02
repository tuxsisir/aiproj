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
- Overview page (`/dashboard/`): logic in `core/overview.py` (`needs_you` per role, `pillars`, `recent_activity`,
  manager `portfolio`); `core.views.dashboard` only renders it. When a pillar gains things that wait on someone,
  add them to `needs_you`.
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
- `issues` — **Building issues** (`/issues/`): things wrong with the building that need fixing. `Issue` (status
  OPEN → ACKNOWLEDGED → IN_PROGRESS → RESOLVED/CLOSED with a required outcome; owner = any active member; fix-by
  date feeds the calendar; `source_email` when raised from a forwarded email) and `IssueUpdate` (append-only
  timeline). Logic in `issues/services.py`. No procedure or CRT path; that's enforcement.
- `meetings` — council / general meetings (`/meetings/`). `Meeting` (PLANNED → HELD "minutes in draft" → APPROVED,
  locked; or CANCELLED) and `AgendaItem` (position, minutes, decision, `in_camera`, optional `issue` / `incident`).
  `services.build_agenda` drafts the agenda from standard items + chosen open issues + enforcement cases (cases are
  always in camera). Marking held emails council for approval; approving posts each decision to the linked issue/case timeline
  (never draft decisions: a case timeline is a legal record). Held/approve lock the row against double submits. Only
  council approves. Printable minutes at `<pk>/minutes/`; `?copy=owners` hides in-camera details and guests.
- **Naming:** code names stay (`dockets`, `Incident`); users see "Enforcement" / "enforcement case". Enforcement is
  bylaw-only: new cases are always `Incident.Type.BYLAW`; building problems are Issues.
- `schedule` — building calendar at `/calendar/`. `schedule/feed.py` merges dated events from every pillar
  (`SOURCES`: key dates, enforcement notices/deadlines, issue fix-by dates, meetings; add a source when a pillar gains dates). `KeyDate` =
  hand-entered dates (AGM, insurance renewal…), optionally yearly. Named `schedule` because `calendar` would
  shadow Python's stdlib module. `TIME_ZONE` is `America/Vancouver` so "today" and deadlines are Pacific.
- `payments` — Stripe checkout, customer portal, webhook at `/payments/webhooks/stripe/`.

## Architecture conventions (see `docs/PLAN.md`)
- Function-based views only, kept thin; business rules + side effects in each app's `services.py`.
- Validate input with Django forms; never trust POSTed choice values.
- Common reads as QuerySet methods: `Membership.objects.active().council()`, `.pending()`, `.managers()`.
- `stratas.decorators.membership_required` for views that need an active building membership.
- Permission checks via `membership.is_council` / `membership.is_manager`; display via `membership.title`.
- Data conversions go in their own migration (Postgres "pending trigger events" error otherwise).
- Owners/tenants have no accounts; they only use token links.
- Uploaded files are never linked by `.url`: serve them through a view that checks access, then
  `core.files.serve_upload` (images/PDF inline, anything else downloads). `/media/` is only served in DEBUG.
- **Selects:** never a native `<select>`. Use `<c-listbox :field="form.x" />` (form field: options, current value,
  empty label) or `<c-listbox name=".." value=".."> <c-ui.menu.item value=".." label=".."/> </c-listbox>`
  (`core/templates/cotton/listbox.html`, cotton-ui listbox; submits via a hidden input). Pass hand-written labels
  through `|safe_quotes`: cotton-ui puts them in single-quoted JS. Listen for the bubbling `select-change` event
  to react in Alpine. Field partials use `{% if field|is_select %}`.
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

## Working rules (agents)
- **Only the main agent writes, edits or removes files.** Subagents (`.claude/agents/`: `code-reviewer`,
  `qa-tester`) only read, run tests and report; throwaway files go in `$TMPDIR`, never the repo.
- **Before every commit, run `code-reviewer`** on the change and fix Critical/High findings (or tell the human
  why not). Run `qa-tester` after a feature is complete.
- **Destructive actions need human approval every time, even in auto mode**: deleting files, rebuilding or
  flushing a database, reversing migrations, `git reset --hard`, force-push, deleting branches, discarding
  changes. Say exactly what will go and why, look at it first, prefer a reversible option, then log it in
  `docs/destructive-actions.md`. `.claude/settings.json` makes Claude Code ask before these commands.

## Gotchas
- `record_audit_log`: pass an explicit `AuditLog.Action` for events (CREATE after `objects.create()`, VOTE_CAST…);
  without one it only logs inferred field UPDATEs. Audit logs are viewable read-only in admin.
- Manual timeline entries go through `dockets.forms.IncidentEventForm` (NOTE / RECURRENCE / EVIDENCE only).
- `incident.bylaw` is nullable; notice/fine emails dereference it.
- Datetimes are stored in UTC and shown in `TIME_ZONE` (America/Vancouver). Templates (`|date`) convert for you;
  in Python never call `.strftime()` / `.date()` on a DB datetime directly: use `timezone.localtime(dt)` or
  `timezone.localdate()` first.
- `cotton-ui.css` ships its own Tailwind utilities build. The Tailwind browser `<script>` must come **after** it in
  `<head>` (base templates), or its `.hidden`/`.flex`/… override responsive classes like `hidden sm:inline`.
- Sidebar nav lives in `core/templates/cotton/sidebar/nav.html`, grouped by pillar; unbuilt pillars use `soon="true"`.
- Documents/inbox tests mock `documents.ai` / `inbox.ai`; never call the real API from tests.
- Root-level `test_*.py` scripts are NOT tests; they write to the real DB on import. Always run tests with
  app labels (below) so the runner never discovers them.

## Deployment
Render (Oregon), see `docs/DEPLOY.md`: `render.yaml` blueprint (Docker web + Postgres + 1 GB disk at
`/var/data`), `Dockerfile` (WeasyPrint libs, collectstatic at build), `bin/start` (migrate → gunicorn 2×8 threads).
Production = `DEBUG=False`: `SECRET_KEY` required, HTTPS redirect/secure cookies/HSTS, WhiteNoise static files,
`/healthz/` for the platform. Secrets live only in Render's env vars.

## Commands
- Env: `.venv` on Python **3.13** (`.python-version`), managed with uv. Use `.venv/bin/python`.
  Setup: `uv venv --python 3.13 .venv && uv pip install --python .venv/bin/python -r requirements.txt`.
  (System default Python is 3.15, which Django 5.2 doesn't support.)
- Local DB is Postgres `stratacorp` (from `.env`), already migrated with demo data.
- **Local logins** (DEBUG only, `core/dev.py`): one-click "Log in as" on the login page and a "Dev:" switcher in
  the dashboard header. Accounts: admin / manager / president / treasurer / newcomer (pending) `@civicdesk.test`,
  password `DEV_ACCOUNT_PASSWORD`. Recreate/repair anytime: `manage.py seed_dev_accounts`. Demo users must use
  reserved domains (.test / example.*) so they never receive real email.
- `python manage.py runserver`, `python manage.py migrate`
- Demo data: `manage.py init_demo_data` (DEBUG only, run on an empty/flushed DB, refuses to run twice). DEMO STRATA
  gets a 7-person council (president = Nora, treasurer = Sisir, plus sandesh (VP), deep, akhila, aaron, allen
  @civicdesk.test, first names only), the manager (plus two
  other buildings), a pending newcomer, cases in every enforcement stage, summarized documents with saved Q&A,
  forwarded emails and key dates, all dated relative to today. Content is fictional; keep it that way.
- Tests: `.venv/bin/python manage.py test core stratas dockets documents inbox payments schedule issues meetings` (dev-login tests in
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
