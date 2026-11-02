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
| | | | | | |
