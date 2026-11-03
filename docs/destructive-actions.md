# Destructive actions log

Every destructive action taken on this project is recorded here, newest first, **after** a human approved it.
Destructive means anything that removes or overwrites data or history: deleting files, rebuilding or flushing
a database, dropping tables, reversing migrations, `git reset --hard`, force-pushing, deleting branches,
discarding uncommitted changes.

Rules (see `CLAUDE.md` → "Working rules"):
1. Only the main agent performs these actions. Subagents never do.
2. Ask the human first, every time, even in auto mode: say exactly what will be removed and why.
3. Look at the target before acting; prefer a reversible option (move, rename, backup) when one exists.
4. Log it here in the same change.

| Date | Action | Target | Why | Approved by | Reversible? / backup |
|---|---|---|---|---|---|
| 2026-11-01 | Flushed local dev database and reseeded demo data | Local Postgres `stratacorp` (demo data only: 8 @civicdesk.test users, 3 buildings, 7 cases, 5 docs, 3 Q&As, 3 emails, 13 key dates, 38 audit entries) | Reseed with the council's first names (Nora, Sandesh, Sisir, Deep, Akhila, Aaron, Allen) plus issues and meetings demo data | The user, in chat (asked, then confirmed) | Backup: `tmp/backups/stratacorp-before-reseed-2026-11-01.sql` (gitignored); restore with `psql stratacorp < file` |
| 2026-11-01 | Flushed local dev database | Local Postgres `stratacorp` (all rows) | Start demo data from scratch | Done by the user themselves | Not reversible; rebuilt with `init_demo_data` |
