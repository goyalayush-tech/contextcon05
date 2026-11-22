import { useCallback, useEffect, useMemo, useState } from 'react'
import { Check, Plane, ShieldCheck } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Kicker } from '@/components/bits'
import { api, post } from '@/lib/api'
import type { CaseKind, CasePacket, Schema } from '@/lib/api'
import { buildPayload, caseRef, emptyFlight, toForm, type Facts, type FlightForm } from '@/lib/model'
import { cn } from '@/lib/utils'
import CaseScreen from '@/screens/CaseScreen'
import FactsScreen from '@/screens/FactsScreen'
import PacketScreen from '@/screens/PacketScreen'
import ApproveScreen from '@/screens/ApproveScreen'
import FollowupScreen from '@/screens/FollowupScreen'
import SourcesScreen from '@/screens/SourcesScreen'

const STEPS = ['Case', 'Facts', 'Packet', 'Approve', 'Follow-up']

export default function App() {
  const [schema, setSchema] = useState<Schema | null>(null)
  const [samples, setSamples] = useState<{ key: string; title: string; case_type: string }[]>([])
  const [step, setStep] = useState(0)
  const [reached, setReached] = useState(0)
  const [view, setView] = useState<'flow' | 'sources'>('flow')
  const [kind, setKind] = useState<CaseKind>('cancellation')
  const [flight, setFlight] = useState<FlightForm>(emptyFlight)
  const [facts, setFacts] = useState<Facts>({})
  const [data, setData] = useState<CasePacket | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api<Schema>('/api/schema').then(setSchema).catch((e) => toast.error(`Backend not reachable: ${e.message}`))
    api('/api/samples').then(setSamples).catch(() => {})
  }, [])

  const fields = useMemo(() => schema?.[kind] ?? [], [schema, kind])
  const go = (n: number) => {
    setStep(n)
    setReached((r) => Math.max(r, n))
    setView('flow')
    window.scrollTo({ top: 0 })
  }

  const setFact = (name: string, patch: Partial<Facts[string]>) =>
    setFacts((f) => ({ ...f, [name]: { ...(f[name] ?? { value: '', doc: '', snippet: '' }), ...patch } }))

  const changeKind = (k: CaseKind) => {
    if (k !== kind) {
      setKind(k)
      setFacts({})
    }
  }

  const loadSample = async (key: string) => {
    if (!schema) return
    try {
      const s = await api<{ case_type: CaseKind; flight: Record<string, unknown>; facts: Record<string, unknown> }>(`/api/samples/${key}`)
      const fl = { ...emptyFlight }
      for (const k of Object.keys(emptyFlight) as (keyof FlightForm)[]) if (s.flight[k] != null) fl[k] = String(s.flight[k])
      const nf: Facts = {}
      for (const f of schema[s.case_type]) {
        const raw = s.facts[f.name]
        if (raw == null) continue
        const isObj = typeof raw === 'object' && 'value' in (raw as object)
        const value = isObj ? (raw as { value: unknown }).value : raw
        const o = isObj ? (raw as { doc?: string; snippet?: string }) : {}
        nf[f.name] = { value: toForm(f, value), doc: o.doc ?? '', snippet: o.snippet ?? '' }
      }
      setKind(s.case_type)
      setFlight(fl)
      setFacts(nf)
      setData(null)
      setReached(0)
      toast.success('Synthetic example loaded. Edit anything you like.')
    } catch (e) {
      toast.error((e as Error).message)
    }
  }

  const assess = async () => {
    setBusy(true)
    try {
      const c = await post<CasePacket>('/api/case', buildPayload(kind, fields, flight, facts))
      setData(c)
      go(2)
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const reload = useCallback(async () => {
    if (data) setData(await api<CasePacket>(`/api/case/${data.case_id}`))
  }, [data])

  const approve = async (ack: boolean) => {
    if (!data) return
    setBusy(true)
    try {
      await post(`/api/case/${data.case_id}/approve`, { acknowledge_contact_change: ack })
      setData(await api<CasePacket>(`/api/case/${data.case_id}`))
      toast.success('Approved. Nothing was sent.')
      go(4)
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const reset = () => {
    setData(null)
    setFacts({})
    setFlight(emptyFlight)
    setStep(0)
    setReached(0)
    setView('flow')
  }
  const approved = data?.approval?.state === 'approved_by_passenger'
  const done = (i: number) => (i < 3 ? reached > i : i === 3 ? approved : false)

  return (
    <div className="mx-auto min-h-screen max-w-6xl border-x-2 border-divider bg-background">
      <header className="border-b-2 border-divider">
        <div className="flex items-center justify-between gap-3 px-6 py-4 md:px-12">
          <button onClick={() => setView('flow')} className="flex min-w-0 cursor-pointer items-center gap-2 text-lg font-extrabold tracking-tight md:text-xl">
            <Plane className="size-5 text-primary" /> FLIGHTBACK
            {data && (
              <span className="hidden font-mono text-xs font-bold tracking-wider text-muted-foreground uppercase md:inline">
                · Case {caseRef(data.case_id)}
              </span>
            )}
          </button>
          <div className="flex shrink-0 items-center gap-1 md:gap-2">
            <Button variant={view === 'sources' ? 'default' : 'secondary'} size="sm" onClick={() => setView(view === 'sources' ? 'flow' : 'sources')}>
              <ShieldCheck /> <span className="hidden sm:inline">Sources</span>
            </Button>
            <Button variant="ghost" size="sm" onClick={reset}>New case</Button>
          </div>
        </div>
        {view === 'flow' && (
          <>
            <nav className="hidden border-t-2 border-divider md:grid md:grid-cols-5">
              {STEPS.map((s, i) => {
                const ok = i <= reached && (i < 2 || data !== null)
                return (
                  <button
                    key={s}
                    disabled={!ok}
                    onClick={() => go(i)}
                    className={cn(
                      'flex cursor-pointer items-center gap-2 px-6 py-3 text-left font-mono text-xs font-bold tracking-[0.08em] uppercase disabled:cursor-default',
                      i > 0 && 'border-l-2 border-divider',
                      i === step ? 'bg-primary text-primary-foreground' : ok ? 'hover:bg-foreground/7' : 'text-muted-foreground',
                    )}
                  >
                    <span>{i + 1}</span>
                    <span>{s}</span>
                    {done(i) && i !== step && <Check className="size-3.5 text-primary" />}
                  </button>
                )
              })}
            </nav>
            <div className="border-t-2 border-divider px-6 py-2 font-mono text-xs font-bold tracking-[0.08em] uppercase md:hidden">
              Step {step + 1} / 5 · {STEPS[step]}
            </div>
          </>
        )}
      </header>

      <main>
        <div key={view === 'sources' ? 'sources' : step} className="animate-in fade-in slide-in-from-bottom-2 duration-200">
            {view === 'sources' ? (
              <SourcesScreen />
            ) : step === 0 ? (
              <CaseScreen kind={kind} setKind={changeKind} flight={flight} setFlight={setFlight} samples={samples} loadSample={loadSample} next={() => go(1)} />
            ) : step === 1 ? (
              <FactsScreen fields={fields} facts={facts} setFact={setFact} kind={kind} busy={busy} back={() => go(0)} assess={assess} />
            ) : !data ? (
              <div className="p-12">
                <Kicker>Start from step 1</Kicker>
              </div>
            ) : step === 2 ? (
              <PacketScreen c={data} next={() => go(3)} />
            ) : step === 3 ? (
              <ApproveScreen key={data.case_id} c={data} busy={busy} back={() => go(2)} approve={approve} />
            ) : (
              <FollowupScreen c={data} reload={reload} />
            )}
        </div>
      </main>
      <footer className="border-t-2 border-divider px-6 py-4 font-mono text-xs tracking-wide text-muted-foreground uppercase md:px-12">
        FLIGHTBACK never sends anything on your behalf · Rights engine is deterministic · News is a lead, not proof
      </footer>
    </div>
  )
}
