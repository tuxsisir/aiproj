# Deploying CivicDesk (Render, Oregon)

Pilot setup: one Docker web service + Render Postgres + a 1 GB disk for uploaded files, about $15/month on the
**Hobby** workspace (Starter web instance, basic Postgres). Defined in `render.yaml`; the image is `Dockerfile`;
`bin/start` runs migrations then gunicorn (2 workers × 8 threads).

## What only you can do (accounts, keys, DNS)

### 1. Push the branch to GitHub
Render deploys from GitHub. Merge to `main` (or point the Blueprint at your branch).

### 2. Create the services on Render
1. render.com → workspace on the **Hobby** plan.
2. **New → Blueprint** → pick the repo. Render reads `render.yaml` and proposes `civicdesk` (web) and
   `civicdesk-db` (Postgres), both in **Oregon**. Check the plans it shows (`starter`, `basic-256mb`); plan
   names change, so pick the closest current ones if Render complains.
3. It asks for the `sync: false` secrets. Fill what you have now, leave the rest empty (features turn off):
   | Key | Where it comes from | Needed for |
   |---|---|---|
   | `RESEND_API_KEY` | Resend → API Keys (sending access) | every email |
   | `EMAIL_REPLY_TO` | your support address, e.g. `hello@usecivicdesk.com` | replies to app emails |
   | `ANTHROPIC_API_KEY` | console.anthropic.com → API keys | summaries, Ask the building |
   | `RESEND_INBOUND_SECRET` | Resend webhook signing secret (step 5) | forwarded-email inbox |
   | `GOOGLE_OAUTH_CLIENT_ID` / `_SECRET` | Google Cloud console (optional) | "Sign in with Google" |
4. Deploy. When it's green, `https://civicdesk.onrender.com/healthz/` says `ok`.

### 3. Point the domain at Render
`render.yaml` already lists `usecivicdesk.com` under `domains:`; Render adds `www.usecivicdesk.com` itself (redirecting
to the root). Render → `civicdesk` → Settings → Custom Domains shows the DNS records to create at your DNS provider (an A/ALIAS or CNAME-flattened record for the root,
a CNAME for `www`). If your DNS is on Cloudflare, set these records to **DNS only** (grey cloud) so Render can
issue the HTTPS certificate. Wait until Render shows the certificate as issued.

### 4. Resend: send email as @usecivicdesk.com
1. Resend → Domains → Add `usecivicdesk.com`, region closest to you (US).
2. Add the records Resend shows at your DNS provider: DKIM (TXT `resend._domainkey`), SPF (MX + TXT on the
   `send` subdomain). Also add DMARC: TXT `_dmarc` = `v=DMARC1; p=none;` (tighten later).
3. Wait for "Verified". Create an API key with sending access → `RESEND_API_KEY` on Render.
4. Free tier: 3,000 emails/month, 100/day. Enough for a pilot; check current limits.

### 5. Resend inbound (forwarded-email inbox), can wait
Each building gets an address like `eps123-ab12cd@inbox.usecivicdesk.com`.
1. Resend → enable receiving for `inbox.usecivicdesk.com` and add the MX record it shows.
2. Resend → Webhooks → add `https://usecivicdesk.com/anymail/resend/inbound/` for the `email.received` event.
   Copy the signing secret → `RESEND_INBOUND_SECRET` on Render.
3. Test: forward any email from an active member's address to the building's inbox address (shown on the
   Forwarded email page). Only active members of that building are accepted.

### 6. First admin account
Render → `civicdesk` → Shell:
```
python manage.py createsuperuser
```
Then in `/admin/` → Sites → change `example.com` to domain `usecivicdesk.com`, name `CivicDesk`.
You approve council and manager sign-ups from `/admin/` → Memberships (actions).

## Day-to-day
- **Deploy:** push to the deployed branch; Render builds and restarts (a few seconds of downtime while a disk
  is attached). Migrations run on start.
- **Logs:** Render → Logs. **Shell:** Render → Shell (`python manage.py ...`).
- **Backups:** Render Postgres (paid) has daily backups/point-in-time recovery; check the database's Recovery
  tab. The uploads disk gets Render snapshots; check the disk settings. Before any risky change, also take a
  manual `pg_dump` (Render → database → Connect → external URL).
- **HSTS:** starts at 1 hour (`SECURE_HSTS_SECONDS`). After the custom domain has worked over HTTPS for a week,
  set it to `31536000` on Render.
- **Demo data:** `init_demo_data` and the "Log in as" buttons only work with `DEBUG` on, never in production.
  Demo the product from your laptop, or create real accounts on the server.

## Known gaps (production)
- Uploads are never served from a public `/media/` URL: documents, evidence and avatars each go through a
  permission-checked view (`core/files.py::serve_upload`).
- The container runs as root. Moving to a non-root user needs the disk at `/var/data` to be writable by that user;
  check on Render before changing it.
- AI work (summaries) runs in a background thread; a restart mid-summary leaves it pending. Use "Retry summary".
- No error tracking yet (Sentry is the next small addition) and no AI cost cap per building.
