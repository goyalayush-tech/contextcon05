import { useState } from 'react'
import { ArrowRight, Loader2 } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardTitle, Field, selectCls, when } from '@/components/bits'
import { post } from '@/lib/api'
import type { CasePacket } from '@/lib/api'

const EVENTS = [
  { key: 'complaint_submitted', label: 'I submitted the complaint', past: 'Complaint submitted' },
  { key: 'airline_response', label: 'The airline replied', past: 'Airline replied' },
  { key: 'airline_rejection', label: 'The airline rejected it', past: 'Airline rejected it' },
  { key: 'refund_received', label: 'I received a refund', past: 'Refund received' },
]
const PAST: Record<string, string> = Object.fromEntries(EVENTS.map((e) => [e.key, e.past]))

export default function FollowupTab({ c, reload }: { c: CasePacket; reload: () => Promise<void> }) {
  const [kind, setKind] = useState('complaint_submitted')
  const [ref, setRef] = useState('')
  const [detail, setDetail] = useState('')
  const [amount, setAmount] = useState('')
  const [busy, setBusy] = useState(false)

  const record = async () => {
    const data: Record<string, unknown> = {}
    if (ref.trim()) data.reference = ref.trim()
    if (kind === 'airline_rejection' && detail.trim()) data.reason = detail.trim()
    if (kind === 'airline_response' && detail.trim()) data.summary = detail.trim()
    if (kind === 'refund_received') {
      if (amount === '' || Number.isNaN(Number(amount))) return toast.error('Enter the amount you received.')
      data.amount = Number(amount)
    }
    setBusy(true)
    try {
      const r = await post<{ duplicate_ignored: boolean }>(`/api/case/${c.case_id}/followup`, { kind, data })
      if (r.duplicate_ignored) toast.message('That was already recorded a moment ago, so it was not added twice.')
      else toast.success('Recorded')
      await reload()
      setRef(''); setDetail(''); setAmount('')
    } catch (e) { toast.error((e as Error).message) } finally { setBusy(false) }
  }

  const history = [...(c.followups ?? [])].reverse()
  return (
    <div className="space-y-6">
      <div className="rounded-lg border border-primary/30 bg-accent p-5 text-accent-foreground">
        <div className="flex items-center gap-2 text-xs font-bold tracking-[0.12em] uppercase"><ArrowRight className="size-4" /> Your next step</div>
        <p className="mt-2 text-base font-semibold">{c.next_step}</p>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardTitle>Record what happened</CardTitle>
          <div className="space-y-4">
            <Field label="What happened?">
              <select className={selectCls} value={kind} onChange={(e) => setKind(e.target.value)}>
                {EVENTS.map((e) => <option key={e.key} value={e.key}>{e.label}</option>)}
              </select>
            </Field>
            <Field label="Reference number" hint="The complaint or ticket number the airline gave you, if any.">
              <Input value={ref} onChange={(e) => setRef(e.target.value)} placeholder="e.g. IGO-2026-558213" />
            </Field>
            {kind === 'airline_rejection' && <Field label="Reason they gave"><Input value={detail} onChange={(e) => setDetail(e.target.value)} placeholder="e.g. bad weather" /></Field>}
            {kind === 'airline_response' && <Field label="What they said"><Input value={detail} onChange={(e) => setDetail(e.target.value)} placeholder="Short summary" /></Field>}
            {kind === 'refund_received' && <Field label="Amount received (Rs)"><Input type="number" min="0" value={amount} onChange={(e) => setAmount(e.target.value)} /></Field>}
            <Button disabled={busy} onClick={record}>{busy && <Loader2 className="animate-spin" />} Record</Button>
          </div>
        </Card>
        <Card>
          <CardTitle>History</CardTitle>
          {history.length === 0 ? <p className="text-sm text-muted-foreground">Nothing recorded yet.</p> : (
            <ol className="space-y-3 border-l border-border pl-4 text-sm">
              {history.map((h, i) => (
                <li key={i}>
                  <div className="font-mono text-xs text-muted-foreground">{when(h.ts)}</div>
                  <div className="font-semibold">{PAST[h.kind] ?? h.kind}</div>
                  <div className="text-muted-foreground">
                    {[h.data?.reference && `Ref ${h.data.reference}`, h.data?.reason && `Reason: ${h.data.reason}`, h.data?.summary,
                      h.data?.amount != null && `Rs ${h.data.amount}`].filter(Boolean).join(' · ')}
                  </div>
                </li>
              ))}
            </ol>
          )}
        </Card>
      </div>
    </div>
  )
}
