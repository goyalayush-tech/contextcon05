# FLIGHTBACK

**Your flight was disrupted. FLIGHTBACK investigates, checks your rights and prepares the complaint. Nothing is ever sent for you.**

Built at ContextCon 05 (BITS Pilani, 22 Nov 2026). Category: *My Own Idea: any service people are paid to do.*

## The service

A passenger whose Indian domestic flight was cancelled or delayed, or whose refund went wrong, today has to work out:
who operated the flight, which DGCA rule applies, whether the notice was early enough, what compensation the formula gives,
whether the refund is late or short, and where to complain. People are paid to do exactly this (claims desks, travel-desk
staff). FLIGHTBACK does it from the passenger's facts and returns a **case packet**: a condition-by-condition rights check,
the compensation or refund-shortfall calculation with its formula, a timeline, an evidence index, what is still missing,
the airline's escalation route and a complaint draft.

It does not claim to replace the airline's refund desk, AirSewa or a consumer commission. It takes the passenger from a mess
of messages to a complete, evidence-backed case, then waits for the passenger's approval.

## What it does today

| Area | Status |
|---|---|
| Cancellation assessment (CAR Part IV 3.3): notice windows, compensation trigger, `min(cap, basic fare + fuel)`, contact-info and extraordinary-circumstances exceptions, same-ticket connections | Built, tested at every boundary |
| Delay assessment (CAR Part IV 3.4): meal thresholds by block time, "more than 6 hours" with the right baseline, night-flight hotel rule, no invented cash compensation | Built, tested at every boundary |
| Refund assessment (CAR Part II): timelines by payment mode, statutory taxes and fees, charge cap, credit-shell consent, 48-hour look-in, shortfall | Built. **Rule pack not fully verified, and says so on every refund case** |
| Operating-airline resolution (marketing vs operating carrier) | Built |
| Per-case evidence run: every case re-checks its operating airline through Crustdata under its own credit ceiling, shows the calls and credits in the packet, falls back to the labelled snapshot on any failure, and blocks approval until a changed contact address is confirmed | Built, tested with fake transport and run against real cached responses |
| Crustdata watch on the six airlines (company news added, pull-only) feeding "LEAD, NOT PROOF" precedent leads; freshness board | Built. Watch #57487 created and its baseline read on 22 Nov 2026 (0 credits). It cannot see grievance-page text, so contact changes come from the Web Fetch hash check |
| Airline identity and grievance route through Crustdata | Live refresh run on 22 Nov 2026: IndiGo and Air India verified from the airline's own page (contacts unchanged vs the snapshot); Akasa Air blocked (HTTP 403) and reported as CANNOT VERIFY; a repeat call is served from cache for 0 credits. Dated snapshot committed for offline replay |
| Complaint draft, escalation route, passenger approval gate, follow-up tracking with next-step advice | Built. Approval and follow-ups are idempotent and persisted |
| Document upload and OCR | **Not built.** Facts are entered with the document and quote each came from |
| Flight-status data (actual departure and arrival) | **Not built.** No Crustdata endpoint provides it, so the passenger supplies it |
| International flights, denied boarding, downgrading | Out of scope, reported as NOT_APPLICABLE |

## Run it

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt httpx
cp .env.example .env            # add CRUSTDATA_API_KEY (optional: without it the app replays the dated snapshot)
.venv/bin/uvicorn flightback.app:app --port 8000
# open http://localhost:8000 and pick a synthetic example
```

The UI is a React 19 + Vite + Tailwind v4 + shadcn/ui app in `frontend/`, built into `flightback/static/dist` and committed, so Python alone serves it (no Node needed to run). To change it:

```bash
cd frontend && npm install && npm run build      # or `npm run dev` (proxies /api to :8000)
```

If `static/dist` is missing, FastAPI falls back to the single-file `static/index.html`.

Tests (127): `.venv/bin/python -m unittest discover -s tests -t .` — no credits used; the Crustdata client is tested with a fake transport.

## How it works

See [docs/architecture.md](docs/architecture.md) for the diagram, the sequence of a case, the Crustdata usage table and the
scaling answer.

- **Rights engine** (`flightback/rules.py`): pure functions, no LLM. Every condition returns `SUPPORTED`, `NOT_SUPPORTED`,
  `UNKNOWN`, `REVIEW_REQUIRED` or `NOT_APPLICABLE` with the paragraph, the inputs used and what is missing. Nothing is assumed.
- **Rule packs are versioned data**: revision, dated, effective date, source URL and a `verified` flag.
- **Packet builder** (`flightback/packet.py`): runs the engine, attaches airline evidence, builds the timeline, and writes the
  complaint draft from supported claims only.
- **Crustdata client** (`flightback/crustdata.py`): rate limiter, SQLite cache, runtime-adjustable credit ceiling that survives
  restart, per-call ledger, typed errors.
- **Airline refresh** (`flightback/airlines.py`): identify by official domain, fetch the grievance page, keep only the relevant
  passage with URL, retrieval time and SHA-256, and report changes against the snapshot.

## Sources and checks

Full record: [docs/rule-verification.md](docs/rule-verification.md).

- **DGCA CAR Section 3, Series M, Part IV (Rev. 4, effective 15 Feb 2023): verified** against the official PDF, paragraph by paragraph.
  Two corrections to our own spec came out of it: the 24-hour to two-week window depends on whether an alternate flight or
  refund was *offered*, and ATC, weather and security causes are named extraordinary circumstances (paras 1.4 and 1.5).
- **DGCA CAR Part II (Rev. 3, 2026): not verified.** The only Part II on dgca.gov.in that we could retrieve is an older version
  (21 working days for agent refunds). The 14 working days and 7-day look-in figures come from news reports. For agent and portal
  refunds the engine therefore says "late" only past 21 working days (breaches both versions) and sends the 14 to 21 day band
  to review.
- **News is a lead, not evidence.** Crustdata's company news has real dates and links but is mostly market and earnings
  noise, and cannot confirm what happened on a given flight. A title filter keeps only passenger-dispute headlines (36 of
  about 500 items in the first read), they are labelled "LEAD, NOT PROOF", and the rights engine never sees them. A first,
  looser filter let through traffic statistics and a licence approval; the false positives are now test cases.
- **Airline contacts are dated records.** Airlines' own pages name different officers on different pages, so the packet quotes the
  email addresses, the page, the retrieval time and a content hash, and shows a conflict warning.

## Approaches tried and what did not work

- Crustdata **Web Fetch returns empty content for PDFs**, including the DGCA CAR, even in browser-like mode. The rule text was read from a direct download.
- Crustdata **Web Search ignores the `site:` filter** and returns redirect links. Airline pages are therefore found by known official domain, not by search.
- **`success: true` does not mean the page loaded.** Akasa Air's page returned HTTP 403 inside a "successful" response. The client trusts `http_status`; Akasa is recorded as "CANNOT VERIFY" and the packet says so.
- Crustdata's company-type label for some airlines looks wrong or stale (Air India shows "Government Agency"). It is not used in any decision.
- A live Air India fetch hit a 60 s read timeout and surfaced as an unhandled 500. The client now retries network errors twice, logs the failure in the ledger and raises a typed error; the refresh reports `error` instead of crashing.
- An earlier idea to treat Crustdata as a source of flight facts was dropped: it cannot confirm a PNR, a departure time or a refund.

## What it could do next

- Document intake with OCR, writing each extracted value with its page and snippet straight into the evidence index.
- A flight-data provider for actual departure and arrival times.
- Rule packs for denied boarding (CAR 3.2), downgrading (3.5) and EU/UK 261 for international flights.
- Webhook delivery for the watch so leads arrive without a manual "Pull new leads".
- A partner API so a travel agency can offer the same packet to its customers, with its own credit ceiling.

## Limits to know

- This is not legal advice. It reports what the cited CAR paragraphs say about the facts provided.
- All demo cases are synthetic. No real passenger data is stored in this repository.
- Before production use, re-check both CARs for amendments after the revisions recorded here.
