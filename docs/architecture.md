# FLIGHTBACK architecture

```mermaid
flowchart LR
  P[Passenger] --> UI[Web UI<br/>facts + source quotes]
  UI --> API[FastAPI]
  API --> PK[Packet builder]
  PK --> RE[Rights engine<br/>deterministic, no LLM]
  RE --> R1[Cancellation<br/>CAR Part IV 3.3]
  RE --> R2[Delay<br/>CAR Part IV 3.4]
  RE --> R3[Refund<br/>CAR Part II]
  PK --> EV[Airline evidence<br/>snapshot + refreshed]
  API --> DB[(SQLite<br/>cases, follow-ups,<br/>cache, credit ledger)]
  API -->|refresh| CD[Crustdata client<br/>rate limit, cache,<br/>credit ceiling, ledger]
  CD --> C1[/company/identify/]
  CD --> C2[/web/enrich/live/]
  C1 --> EV
  C2 -->|http_status + passage + hash| EV
  PK --> OUT[Case packet<br/>assessment, timeline, evidence index,<br/>escalation route, complaint draft]
  OUT --> AP{Passenger approves?}
  AP -->|yes| MAN[Passenger submits manually<br/>airline channel / AirSewa]
  MAN --> FU[Follow-ups logged<br/>next step suggested]
  FU --> DB
```

## What is deterministic and what is data

| Layer | Source of truth | Can it be wrong silently? |
|---|---|---|
| Legal rules (`flightback/rules.py`) | Official DGCA PDFs, checked paragraph by paragraph (`docs/rule-verification.md`) | No: each pack carries `verified` and a source URL; the unverified Part II warns on every refund case |
| Passenger facts | The passenger's documents, quoted in the evidence index | No: facts with no document are labelled "stated by passenger, no document" |
| Airline identity and grievance route | Crustdata, dated, with HTTP status and passage hash | No: blocked, empty or conflicting pages become "CANNOT VERIFY" or a conflict warning |
| Compensation amount | `min(cap, basic fare + fuel charge)`, computed only when every input is known | No: missing inputs are named, no amount is shown |

## Cancellation case lifecycle

```mermaid
sequenceDiagram
  participant U as Passenger
  participant A as API
  participant E as Rights engine
  participant S as SQLite
  U->>A: facts + source quotes
  A->>E: CancellationFacts
  E-->>A: conditions (SUPPORTED / NOT_SUPPORTED / UNKNOWN / REVIEW_REQUIRED / NOT_APPLICABLE)
  A->>S: save case (idempotent by content hash)
  A-->>U: packet + complaint draft (NOT SENT)
  U->>A: approve
  A->>S: record consent once (repeat is a no-op)
  U->>A: "airline rejected: weather"
  A-->>U: next step: ask for the extraordinary-circumstance records, escalate to appellate authority
```

## Crustdata usage

| Call | Why | Cost control |
|---|---|---|
| `/company/identify` by official domain | Canonical airline identity; domain match at confidence >= 0.9, else REVIEW_REQUIRED | 0.2 credits, cached 24h |
| `/web/enrich/live` on the airline's grievance page | Dated nodal officer / appellate authority emails | 1 credit per page, cached; only the relevant passage and its SHA-256 are stored |

Every call passes through one client: per-endpoint rate limit (5/min core, 10/min web on this key), credit ceiling that can
be cut at runtime and survives a restart, a ledger row per call with `X-Request-Id` and `X-Credits-Used`, 429 backoff using
`x-ratelimit-reset`, and typed 402 / 403 errors.

## Scaling answer (100x volume, or a second client)

- The rights engine is a pure function of the facts: scale it horizontally with no coordination.
- Airline evidence is shared across all passengers: one refresh per airline per day, not per case. At 100x the Crustdata spend does not grow with case volume.
- A second client (a travel agency) gets its own case namespace and, if needed, its own credit ceiling through the same ledger.
- The limit that does grow is document handling. That is why intake records every fact's source document and quote, ready for an extraction step.
