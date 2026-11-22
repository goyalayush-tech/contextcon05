import type { CaseKind, SchemaField } from './api'

/** A fact and where it came from. page/method/confidence/doc_sha256 are set when it came from an uploaded document. */
export interface Fact {
  value: string; doc: string; snippet: string
  page?: number; method?: string; confidence?: number | null; doc_sha256?: string
}
export type Facts = Record<string, Fact>
export interface FlightForm {
  flight_number: string; pnr: string; origin: string; destination: string; date: string
  block_time_hours: string; marketing_carrier: string; operating_carrier: string
}
export const emptyFlight: FlightForm = {
  flight_number: '', pnr: '', origin: '', destination: '', date: '', block_time_hours: '',
  marketing_carrier: '', operating_carrier: '',
}

export const KINDS: { key: CaseKind; title: string; cite: string }[] = [
  { key: 'cancellation', title: 'Flight cancelled', cite: 'CAR 3.3' },
  { key: 'delay', title: 'Flight delayed', cite: 'CAR 3.4' },
  { key: 'refund', title: 'Refund problem', cite: 'CAR Part II' },
]

/** API value -> form string. Datetimes lose their offset: everything on screen is India time. */
export function toForm(f: SchemaField, v: unknown): string {
  if (v == null) return ''
  if (f.type === 'bool') return v ? 'yes' : 'no'
  if (f.type === 'datetime') return String(v).slice(0, 16)
  return String(v)
}

/** Form string -> typed API value. Blank stays out of the payload: unknown facts are listed as missing, never guessed. */
export function fromForm(f: SchemaField, v: string): unknown {
  if (v === '') return undefined
  if (f.type === 'bool') return v === 'yes'
  if (f.type === 'number') return Number(v)
  if (f.type === 'datetime') return v.length === 16 ? `${v}:00+05:30` : v
  return v
}

export function buildPayload(kind: CaseKind, fields: SchemaField[], flight: FlightForm, facts: Facts) {
  const fl: Record<string, unknown> = { domestic: true }
  for (const [k, v] of Object.entries(flight)) {
    if (v === '') continue
    fl[k] = k === 'block_time_hours' ? Number(v) : v
  }
  const out: Record<string, unknown> = {}
  for (const f of fields) {
    const fact = facts[f.name]
    if (!fact) continue
    const v = fromForm(f, fact.value)
    if (v === undefined) continue
    out[f.name] = fact.doc
      ? { value: v, doc: fact.doc, snippet: fact.snippet || undefined, page: fact.page, method: fact.method,
          confidence: fact.confidence ?? undefined, doc_sha256: fact.doc_sha256 }
      : v
  }
  return { case_type: kind, flight: fl, facts: out }
}

export const caseRef = (id: string) => id.replace(/[^a-z0-9]/gi, '').slice(0, 6).toUpperCase()
