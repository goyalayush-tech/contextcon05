import { useEffect, useState } from 'react'
import { ArrowRight, CalendarX2, Clock, Wallet } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardTitle, Field, selectCls } from '@/components/bits'
import { api } from '@/lib/api'
import type { CaseKind } from '@/lib/api'
import { KINDS, type FlightForm } from '@/lib/model'
import { cn } from '@/lib/utils'

interface Airline { code: string; airline: string }
const ICON = { cancellation: CalendarX2, delay: Clock, refund: Wallet }
const BLURB = {
  cancellation: 'The airline cancelled the flight.',
  delay: 'The flight left late, or will.',
  refund: 'A refund is late, short or stuck in a credit shell.',
}

export default function FlightStep(p: {
  kind: CaseKind; setKind: (k: CaseKind) => void
  flight: FlightForm; setFlight: (f: FlightForm) => void
  next: () => void
}) {
  const [airlines, setAirlines] = useState<Airline[]>([])
  useEffect(() => { api<Airline[]>('/api/airlines').then(setAirlines).catch(() => {}) }, [])
  const f = p.flight
  const set = (k: keyof FlightForm) => (e: { target: { value: string } }) =>
    p.setFlight({ ...f, [k]: k === 'origin' || k === 'destination' ? e.target.value.toUpperCase() : e.target.value })

  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-3">
        {KINDS.map((k) => {
          const Icon = ICON[k.key]
          const on = p.kind === k.key
          return (
            <button key={k.key} onClick={() => p.setKind(k.key)} aria-pressed={on}
              className={cn('rounded-lg border bg-card p-5 text-left transition-all',
                on ? 'border-primary ring-2 ring-primary/20' : 'border-border hover:border-input')}>
              <div className="flex items-center justify-between">
                <span className={cn('grid size-9 place-items-center rounded-md', on ? 'bg-primary text-primary-foreground' : 'bg-secondary')}><Icon className="size-4" /></span>
                <span className="font-mono text-xs text-muted-foreground">{k.cite}</span>
              </div>
              <div className="mt-4 text-lg font-bold">{k.title}</div>
              <div className="mt-1 text-sm text-muted-foreground">{BLURB[k.key]}</div>
            </button>
          )
        })}
      </div>

      <Card>
        <CardTitle>Your flight</CardTitle>
        <div className="grid gap-5 md:grid-cols-3">
          <Field label="Flight number"><Input value={f.flight_number} onChange={set('flight_number')} placeholder="6E 123" /></Field>
          <Field label="Booking reference (PNR)"><Input value={f.pnr} onChange={set('pnr')} placeholder="ABC123" /></Field>
          <Field label="Flight date"><Input type="date" value={f.date} onChange={set('date')} /></Field>
          <Field label="From"><Input value={f.origin} onChange={set('origin')} placeholder="DEL" maxLength={3} /></Field>
          <Field label="To"><Input value={f.destination} onChange={set('destination')} placeholder="BOM" maxLength={3} /></Field>
          <Field label="Flight time (hours)" hint="Gate to gate, from the ticket.">
            <Input type="number" step="0.1" min="0" value={f.block_time_hours} onChange={set('block_time_hours')} placeholder="2.0" />
          </Field>
          <Field label="Airline on the ticket">
            <select className={selectCls} value={f.marketing_carrier} onChange={set('marketing_carrier')}>
              <option value="">Choose airline</option>
              {airlines.map((a) => <option key={a.code} value={a.code}>{a.airline} ({a.code})</option>)}
            </select>
          </Field>
          <Field label="Operated by" hint="Look for “operated by” on the ticket. This airline owes you.">
            <select className={selectCls} value={f.operating_carrier} onChange={set('operating_carrier')}>
              <option value="">Not stated on ticket</option>
              {airlines.map((a) => <option key={a.code} value={a.code}>{a.airline} ({a.code})</option>)}
            </select>
          </Field>
        </div>
      </Card>

      <div className="flex flex-wrap items-center justify-between gap-4">
        <p className="text-sm text-muted-foreground">Blank fields are listed as missing, never guessed.</p>
        <Button size="lg" onClick={p.next}>Continue <ArrowRight /></Button>
      </div>
    </div>
  )
}
