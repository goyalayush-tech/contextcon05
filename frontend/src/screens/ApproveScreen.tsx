import { useState } from 'react'
import { ArrowLeft, Copy, Pencil } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Textarea } from '@/components/ui/textarea'
import { Badge } from '@/components/ui/badge'
import { Kicker, Pane } from '@/components/bits'
import type { CasePacket } from '@/lib/api'
import { caseRef } from '@/lib/model'

export default function ApproveScreen({ c, busy, back, approve }: { c: CasePacket; busy: boolean; back: () => void; approve: (ack: boolean) => void }) {
  const [draft, setDraft] = useState(c.complaint_draft)
  const [editing, setEditing] = useState(false)
  const run = c.evidence_run ?? {}
  const changed = !!run.contacts_changed
  const verified = run.mode === 'live' || run.mode === 'cached'
  const items = [
    'I have read the rights check',
    'The facts match my documents',
    changed ? `Airline contacts changed (${(run.changes ?? []).join('; ')}). I confirmed them on the airline’s own website`
      : verified ? 'Airline contacts re-read just now and unchanged'
        : 'I know the airline contacts come from a dated snapshot that could not be re-verified',
  ]
  const [ticks, setTicks] = useState([false, false, false])
  const all = ticks.every(Boolean)

  return (
    <div>
      <Pane>
        <Kicker className="mb-3 text-primary">4 · Complaint draft + approval · {caseRef(c.case_id)}</Kicker>
        <div className="flex flex-wrap items-center gap-3">
          <Badge variant="solid">Not sent</Badge><span className="text-sm text-muted-foreground">Draft written from supported claims only.</span>
        </div>
        <div className="mt-6 grid gap-10 md:grid-cols-[1.5fr_1fr]">
          <div>
            <Textarea className="min-h-96 font-mono text-sm leading-relaxed" value={draft} readOnly={!editing} onChange={(e) => setDraft(e.target.value)} />
            <div className="mt-3 flex gap-3">
              <Button variant="outline" size="sm" onClick={() => { navigator.clipboard.writeText(draft).then(() => toast.success('Draft copied'), () => toast.error('Copy blocked by the browser')) }}><Copy /> Copy text</Button>
              <Button variant="secondary" size="sm" onClick={() => setEditing(!editing)}><Pencil /> {editing ? 'Done editing' : 'Edit draft'}</Button>
            </div>
          </div>
          <div>
            <Kicker className="mb-3">Before you approve</Kicker>
            <div className="space-y-3">
              {items.map((t, i) => (
                <label key={i} className="flex cursor-pointer items-start gap-3 text-sm">
                  <Checkbox checked={ticks[i]} onCheckedChange={(v) => setTicks((t) => t.map((x, j) => (j === i ? v === true : x)))} className="mt-0.5" />
                  <span>{t}</span>
                </label>
              ))}
            </div>
            <p className="mt-5 text-sm text-muted-foreground">Approving records your consent only. FLIGHTBACK does not send anything — submit through the airline or AirSewa yourself.</p>
            <Button size="lg" className="mt-5 w-full" disabled={!all || busy} onClick={() => approve(changed)}>I have reviewed this — approve</Button>
          </div>
        </div>
        <div className="mt-8"><Button variant="secondary" size="lg" onClick={back}><ArrowLeft /> Back to packet</Button></div>
      </Pane>
    </div>
  )
}
