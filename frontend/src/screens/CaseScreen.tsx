import { useEffect, useState } from 'react'
import { ArrowRight } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Field, Kicker, Pane, selectCls } from '@/components/bits'
import { api } from '@/lib/api'
import type { CaseKind } from '@/lib/api'
import { KINDS, type FlightForm } from '@/lib/model'
import { cn } from '@/lib/utils'

interface Airline { code: string; airline: string }

export default function CaseScreen(p: {
  kind: CaseKind; setKind: (k: CaseKind) => void
  flight: FlightForm; setFlight: (f: FlightForm) => void
  samples: { key: string; title: string; case_type: string }[]
  loadSample: (key: string) => void
  next: () => void
}) {
  const [airlines, setAirlines] = useState<Airline[]>([])
  useEffect(() => { api<Airline[]>('/api/airlines').then(setAirlines).catch(() => {}) }, [])
  const set = (k: keyof FlightForm) => (e: { target: { value: string } }) => p.setFlight({ ...p.flight, [k]: e.target.value })
  const f = p.flight

  return (
    <div>
      <Pane className="border-b-2 border-divider">
        <Kicker className="mb-3 text-primary">1 · Intake: what happened + flight</Kicker>
        <h1 className="text-4xl md:text-6xl">What happened to your flight?</h1>
        <p className="mt-3 max-w-xl text-muted-foreground">Pick the closest match. You can change it later. Domestic Indian flights only.</p>
        <div className="mt-8 grid gap-0 border-2 border-foreground md:grid-cols-3">
          {KINDS.map((k, i) => (
            <button key={k.key} onClick={() => p.setKind(k.key)}
              className={cn('flex cursor-pointer items-center justify-between gap-3 p-5 text-left transition-colors',
                i > 0 && 'border-t-2 border-foreground md:border-t-0 md:border-l-2',
                p.kind === k.key ? 'bg-primary text-primary-foreground' : 'hover:bg-foreground/7')}>
              <span className="text-lg font-extrabold">{k.title}</span>
              <span className="font-mono text-xs tracking-wider uppercase opacity-80">{k.cite}</span>
            </button>
          ))}
        </div>
        <div className="mt-5 flex flex-wrap items-center gap-x-3 gap-y-2 text-sm text-muted-foreground">
          <span>No booking at hand?</span>
          {p.samples.map((s) => (
            <Button key={s.key} variant="link" size="xs" className="h-auto max-w-full shrink justify-start px-0 py-0.5 text-left leading-snug whitespace-normal" onClick={() => p.loadSample(s.key)}>
              {s.title} →
            </Button>
          ))}
        </div>
      </Pane>

      <Pane>
        <Kicker className="mb-6">Your flight</Kicker>
        <div className="grid gap-5 md:grid-cols-3">
          <Field label="Flight number"><Input value={f.flight_number} onChange={set('flight_number')} placeholder="6E 000" /></Field>
          <Field label="Booking ref (PNR)"><Input value={f.pnr} onChange={set('pnr')} placeholder="SAMPLE1" /></Field>
          <Field label="Flight date"><Input type="date" value={f.date} onChange={set('date')} /></Field>
          <Field label="From"><Input value={f.origin} onChange={set('origin')} placeholder="DEL" maxLength={3} className="uppercase" /></Field>
          <Field label="To"><Input value={f.destination} onChange={set('destination')} placeholder="JAI" maxLength={3} className="uppercase" /></Field>
          <Field label="Block time (hours)"><Input type="number" step="0.1" min="0" value={f.block_time_hours} onChange={set('block_time_hours')} placeholder="1.0" /></Field>
          <Field label="Ticket shows">
            <select className={selectCls} value={f.marketing_carrier} onChange={set('marketing_carrier')}>
              <option value="">Choose airline</option>
              {airlines.map((a) => <option key={a.code} value={a.code}>{a.airline} ({a.code})</option>)}
            </select>
          </Field>
          <Field label="Operated by" hint={undefined}>
            <select className={selectCls} value={f.operating_carrier} onChange={set('operating_carrier')}>
              <option value="">Not stated on ticket</option>
              {airlines.map((a) => <option key={a.code} value={a.code}>{a.airline} ({a.code})</option>)}
            </select>
          </Field>
        </div>
        <div className="mt-8 flex flex-wrap items-center justify-between gap-4">
          <p className="max-w-md text-sm text-muted-foreground">Unknown fields stay blank. We list them as missing instead of guessing.</p>
          <Button size="lg" onClick={p.next}>Continue to facts <ArrowRight /></Button>
        </div>
      </Pane>
    </div>
  )
}
