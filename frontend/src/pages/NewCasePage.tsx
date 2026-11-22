import { useEffect, useMemo, useState } from 'react'
import { Check } from 'lucide-react'
import { toast } from 'sonner'
import { Container, Loading, PageHeader } from '@/components/bits'
import { api, post } from '@/lib/api'
import type { CaseKind, CasePacket, Schema } from '@/lib/api'
import { buildPayload, emptyFlight, toForm, type Facts, type FlightForm } from '@/lib/model'
import { navigate } from '@/lib/router'
import { cn } from '@/lib/utils'
import FlightStep from '@/pages/new/FlightStep'
import FactsStep from '@/pages/new/FactsStep'

const STEPS = ['What happened', 'Facts and documents']
const KEY = 'flightback:new-case'  // unfinished intake survives a refresh (this tab only)

interface Draft { step: number; kind: CaseKind; flight: FlightForm; facts: Facts }
const blank: Draft = { step: 0, kind: 'cancellation', flight: emptyFlight, facts: {} }

function loadDraft(): Draft {
  try {
    const d = JSON.parse(sessionStorage.getItem(KEY) ?? 'null')
    return d && d.flight ? { ...blank, ...d } : blank
  } catch { return blank }
}

export default function NewCasePage() {
  const [schema, setSchema] = useState<Schema | null>(null)
  const [d, setD] = useState<Draft>(loadDraft)
  const [busy, setBusy] = useState(false)
  const set = (patch: Partial<Draft>) => setD((x) => ({ ...x, ...patch }))

  useEffect(() => { sessionStorage.setItem(KEY, JSON.stringify(d)) }, [d])
  useEffect(() => {
    api<Schema>('/api/schema').then(setSchema).catch((e) => toast.error(`Cannot reach the server: ${e.message}`))
  }, [])

  // /new?sample=<key> pre-fills a synthetic example (used by the links on the home page)
  useEffect(() => {
    const key = new URLSearchParams(window.location.search).get('sample')
    if (!key || !schema) return
    api<{ case_type: CaseKind; flight: Record<string, unknown>; facts: Record<string, unknown> }>(`/api/samples/${key}`)
      .then((s) => {
        const flight = { ...emptyFlight }
        for (const k of Object.keys(emptyFlight) as (keyof FlightForm)[]) if (s.flight[k] != null) flight[k] = String(s.flight[k])
        const facts: Facts = {}
        for (const f of schema[s.case_type]) {
          const raw = s.facts[f.name]
          if (raw == null) continue
          const obj = typeof raw === 'object' && 'value' in (raw as object) ? (raw as { value: unknown; doc?: string; snippet?: string }) : null
          facts[f.name] = { value: toForm(f, obj ? obj.value : raw), doc: obj?.doc ?? '', snippet: obj?.snippet ?? '' }
        }
        setD({ step: 0, kind: s.case_type, flight, facts })
        toast.success('Example loaded. It is synthetic: edit anything you like.')
      })
      .catch((e) => toast.error(e.message))
      .finally(() => navigate('/new', { replace: true }))
  }, [schema])

  const fields = useMemo(() => schema?.[d.kind] ?? [], [schema, d.kind])
  const setFact = (name: string, patch: Partial<Facts[string]>) =>
    setD((x) => ({ ...x, facts: { ...x.facts, [name]: { ...(x.facts[name] ?? { value: '', doc: '', snippet: '' }), ...patch } } }))
  const goStep = (step: number) => { set({ step }); window.scrollTo({ top: 0 }) }

  const assess = async () => {
    setBusy(true)
    try {
      const c = await post<CasePacket>('/api/case', buildPayload(d.kind, fields, d.flight, d.facts))
      sessionStorage.removeItem(KEY)
      navigate(`/case/${c.case_id}`)
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const start = () => { sessionStorage.removeItem(KEY); setD(blank) }

  return (
    <Container>
      <PageHeader eyebrow="New case" title={d.step === 0 ? 'What happened to your flight?' : 'Add the facts'}
        lead={d.step === 0 ? 'Pick the closest match and add the flight details you have. Leave anything you do not know blank.'
          : 'Upload the e-ticket or the airline’s message, or type the facts in. You confirm every value.'} />

      <ol className="mb-8 flex flex-wrap items-center gap-2 text-sm">
        {STEPS.map((s, i) => (
          <li key={s} className="flex items-center gap-2">
            {i > 0 && <span className="h-px w-6 bg-input" />}
            <button disabled={i > d.step} onClick={() => goStep(i)}
              className={cn('flex items-center gap-2 rounded-full border px-3 py-1.5 font-semibold transition-colors disabled:cursor-default',
                i === d.step ? 'border-primary bg-accent text-accent-foreground' : i < d.step ? 'border-input bg-card hover:bg-secondary' : 'border-border text-muted-foreground')}>
              <span className={cn('grid size-5 place-items-center rounded-full text-xs', i < d.step ? 'bg-primary text-primary-foreground' : 'bg-secondary')}>
                {i < d.step ? <Check className="size-3" /> : i + 1}
              </span>
              {s}
            </button>
          </li>
        ))}
        {(Object.keys(d.facts).length > 0 || d.flight.flight_number) && (
          <li className="ml-auto"><button onClick={start} className="text-sm font-semibold text-muted-foreground hover:text-foreground">Clear and start over</button></li>
        )}
      </ol>

      {!schema ? <Loading /> : d.step === 0 ? (
        <FlightStep kind={d.kind} setKind={(kind) => set(kind === d.kind ? {} : { kind, facts: {} })}
          flight={d.flight} setFlight={(flight) => set({ flight })} next={() => goStep(1)} />
      ) : (
        <FactsStep fields={fields} facts={d.facts} setFact={setFact} busy={busy} back={() => goStep(0)} assess={assess} />
      )}
    </Container>
  )
}
