// Thin client for the FLIGHTBACK FastAPI backend. Shapes are the ones in flightback/packet.py and app.py.
/* eslint-disable @typescript-eslint/no-explicit-any */

export type CaseKind = 'cancellation' | 'delay' | 'refund'

export interface SchemaField {
  name: string
  label: string
  type: 'datetime' | 'date' | 'bool' | 'enum' | 'number' | 'text'
  options?: string[] | null
  hint?: string | null
}
export type Schema = Record<CaseKind, SchemaField[]>

export interface Condition {
  id: string
  label: string
  status: string
  rule_ref: string
  detail: string
  missing: string[]
}

export interface CasePacket {
  case_id: string
  case_type: CaseKind
  flight: Record<string, any>
  rule_pack: { id: string; revision: string; effective: string; verified: boolean; source_url?: string }
  airline: { status: string; code: string | null; notes: string[]; identity: any; grievance: any }
  timeline: { time: string; event: string }[]
  conditions: Condition[]
  amounts: Record<string, any>
  headline: string[]
  status_counts: Record<string, number>
  missing: string[]
  evidence_index: {
    fact: string; value: any; doc: string | null; snippet?: string | null; provenance: string
    page?: number; method?: string; confidence?: number; doc_sha256?: string
  }[]
  escalation: { step: number; to: string; how: string; note: string }[]
  complaint_draft: string
  warnings: string[]
  evidence_run: any
  leads: { label: string; note: string; items: Lead[] }
  approval: { state: string; approved_at?: number | null }
  followups?: { ts: number; kind: string; data: any }[]
}

export interface Lead {
  code?: string
  title: string
  url: string
  published: string | null
  publisher: string | null
  matched: string[]
}

export async function api<T = any>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, init)
  const j = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(typeof j.detail === 'string' ? j.detail : r.statusText)
  return j as T
}

export const post = <T = any>(path: string, body: unknown = {}) =>
  api<T>(path, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) })

export const inr = (n: number | string | null | undefined) =>
  n == null ? '—' : 'Rs ' + Number(n).toLocaleString('en-IN', { maximumFractionDigits: 2 })
