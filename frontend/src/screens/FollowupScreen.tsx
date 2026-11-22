import { useState } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Kicker, Field, Pane, selectCls, when } from '@/components/bits'
import { post } from '@/lib/api'
import type { CasePacket } from '@/lib/api'
import { caseRef } from '@/lib/model'

const EVENTS = [
  { key: 'complaint_submitted', label: 'I submitted the complaint' },
  { key: 'airline_response', label: 'The airline responded' },
  { key: 'airline_rejection', label: 'The airline rejected it' },
  { key: 'refund_received', label: 'I received a refund' },
]
const NAMES: Record<string, string> = Object.fromEntries(EVENTS.map((e) => [e.key, e.label.replace(/^I /, 'You ')]))

export default function FollowupScreen({ c, reload }: { c: CasePacket; reload: () => Promise<void> }) {
  const [kind, setKind] = useState('complaint_submitted')
  const [ref, setRef] = useState('')
  const [reason, setReason] = useState('')
  const [amount, setAmount] = useState('')
  const [next, setNext] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const record = async () => {
    const data: Record<string, unknown> = {}
    if (ref) data.reference = ref
    if (kind === 'airline_rejection' && reason) data.reason = reason
    if (kind === 'refund_received' && amount) data.amount = Number(amount)
    setBusy(true)
    try {
      const r = await post<{ next_step: string; duplicate_ignored: boolean }>(`/api/case/${c.case_id}/followup`, { kind, data })
      setNext(r.next_step); if (r.duplicate_ignored) toast.message('Already recorded; ignored the duplicate.')
      await reload(); setRef(''); setReason(''); setAmount('')
    } catch (e) { toast.error((e as Error).message) } finally { setBusy(false) }
  }

  const history = [...(c.followups ?? [])].reverse()
  return (
    <div>
      <Pane>
        <Kicker className="mb-3 text-primary">5 · After you submit · {caseRef(c.case_id)}</Kicker>
        <h1 className="text-4xl md:text-6xl">Approved. Now you send it.</h1>
        <p className="mt-3 text-muted-foreground">Tell us what happens next and we will advise the next step.</p>
        <div className="mt-8 grid gap-10 md:grid-cols-2">
          <div className="space-y-5">
            <Field label="What happened?">
              <select className={selectCls} value={kind} onChange={(e) => setKind(e.target.value)}>{EVENTS.map((e) => <option key={e.key} value={e.key}>{e.label}</option>)}</select>
            </Field>
            <Field label="Reference no."><Input value={ref} onChange={(e) => setRef(e.target.value)} placeholder="IGO-2026-558213" /></Field>
            {kind === 'airline_rejection' && <Field label="Reason given by the airline"><Input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. weather" /></Field>}
            {kind === 'refund_received' && <Field label="Amount received (Rs)"><Input type="number" value={amount} onChange={(e) => setAmount(e.target.value)} /></Field>}
            <Button size="lg" disabled={busy} onClick={record}>Record</Button>
          </div>
          <div className="space-y-8">
            {next && (
              <div className="border-2 border-primary bg-accent p-5"><Kicker className="mb-2 text-accent-foreground">Next step</Kicker><p className="text-sm font-semibold text-accent-foreground">{next}</p></div>
            )}
            <div>
              <Kicker className="mb-3">History</Kicker>
              {history.length === 0 ? <p className="text-sm text-muted-foreground">Nothing recorded yet.</p> : (
                <ul className="divide-y divide-border text-sm">
                  {history.map((h, i) => (
                    <li key={i} className="flex gap-4 py-2"><span className="w-20 shrink-0 font-mono text-xs text-muted-foreground">{when(h.ts)}</span><span>{NAMES[h.kind] ?? h.kind}{h.data?.reference ? ` · ${h.data.reference}` : ''}{h.data?.amount != null ? ` · Rs ${h.data.amount}` : ''}</span></li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </div>
      </Pane>
    </div>
  )
}
