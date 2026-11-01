# CivicDesk — Vision

_Draft v1, 2026-11-01. This document decides what we build. If a feature doesn't serve it, it waits._

## The problem

Strata councils are blind. Everything about the building lives in email threads, a manager's portal full of
PDFs, and an agenda document rebuilt by hand before every meeting. Issues raised by council go unanswered,
matters drag on for a year with no visible progress, inspection findings get lost, and when a manager or a
council member changes, what they knew leaves with them.

When something goes wrong (an owner disputes a fine, files a CRT claim, sues the strata) the council has
to reconstruct what happened from scattered emails. A procedural gap can lose the case.

## What CivicDesk is

> **The building's system of record, shared by council and strata manager.**
> Nothing raised is lost, every rule is enforced by procedure, and every decision is on the record,
> from the first parking complaint to the day a CRT decision is issued.

- **Council** sees live status any time, decides and votes, and can get up to speed as a newcomer in minutes.
- **Strata manager** updates things once instead of rebuilding documents; the agenda and minutes come from
  the record. Their own software stays; CivicDesk is where the building's work is coordinated.
- **Owners and tenants** have no accounts. They receive notices and respond through secure links.

Business note: the manager is the distribution channel. One manager serves 10–15 buildings, so CivicDesk must
make the manager's job easier, not just watch them.

## The pillars

| Pillar | What lives there | Examples from our building |
|---|---|---|
| **Issues** | Problems someone raised. Every issue is acknowledged, owned, tracked and closed with a record. An unanswered issue is visible as unanswered. | Camera clocks out of sync, storage locker break-in, mice reports, flickering parkade lights, garage gate |
| **Projects** | Work the building decides to do: quotes, a council decision, a vendor, a cost, completion. An issue can turn into a project. | Parking signage board, EV charger in a visitor stall, moving the garbage-room camera, gutter contract, building-wide pest control |
| **Enforcement** | Cases against a unit, run strictly by procedure and built to stand up at the CRT. Bylaw contraventions and fee collection. | Short-term overstay parking, business run from a unit, garbage dumping, units refusing fire-inspection access, arrears to lien to court |
| **Maintenance** | Recurring obligations with dates and costs, which feed next year's budget. | Elevator Cat 1 every July and Cat 5 every five years, fire alarm inspection, gutters, windows, carpets, snow season |
| **Money** (Treasurer) | Budget vs actual with overruns flagged, arrears by unit and collection stage (council only), vendors and contracts, quotes compared. We read the manager's numbers; we don't replace their accounting. | Elevator 18% over budget, landscaping overrun, contract expiries |
| **Building brain** | Every document, summarized and searchable with page citations; a primer for new council members. | Bylaws, minutes, inspection and fire reports, contracts, the 56 PDFs |

**Shared by all pillars:**
- **Decisions:** council motions and votes attach to an issue, project or case and flow into the minutes.
- **Meetings:** the agenda is generated from open items, and the meeting updates them.
- **Capture:** forwarded emails and uploaded PDFs (agendas, inspection reports) become proposed issues,
  projects or maintenance items that a person confirms. AI proposes; people decide.
- **Timeline and audit log:** every item has a dated, unchangeable history.

## Enforcement must be bulletproof

The goal: if a dispute reaches the CRT or a court, the strata can produce a complete, ordered, timestamped
record showing it followed its bylaws and the Strata Property Act.

- **Procedure is enforced by the system.** Steps happen in order; a fine cannot be imposed before written
  particulars were given and the owner had the chance to answer or request a hearing. Amounts are checked
  against the bylaw.
- **Everything is logged.** Complaints, evidence, notices (what was sent, to whom, when), responses,
  hearings, votes, decisions, fines and payments. Nothing is edited after the fact; corrections are new entries.
- **Deadlines are tracked.** Response windows, hearing timelines, limitation periods for collection.
- **One click produces the evidence package** for the CRT.
- Legal rules are written from the Act and the building's bylaws, checked by a person, never from memory.

## Principles

1. **Nothing raised is lost.** Every issue has an owner and a status, and silence is visible.
2. **Procedure over memory.** The system knows the steps so busy volunteers don't have to.
3. **Record, don't rewrite.** Update once; agendas, minutes and reports come from the record.
4. **AI proposes, people decide.** AI reads documents and drafts; a person confirms anything that matters.
5. **Council-first, manager-friendly.** Built for council needs, designed so the manager wants to use it.
6. **Five minutes a week.** Council members are volunteers with their own lives.
7. **Private by default.** Arrears and personal information are council-only; data is stored in Canada.
8. **A feature must remove real email from a real council's week.** If we can't name the email, it waits.

## Not now

Owner/tenant portal and accounts, collecting payments, replacing the manager's accounting, meetings software
beyond agenda and minutes, provinces other than BC, native mobile apps, AI acting on its own.

## Settled

- **Sections:** apartment and townhouse sections have separate councils and budgets, so each section is its
  own workspace, linked under the strata plan.
- **Test data:** we only develop against anonymized copies; real building documents never enter the repository.

## Open questions

1. First pilot: would our strata manager try CivicDesk with his own October agenda as a live board?
