import { useState } from 'react'
import { CheckCircle2, Copy, Loader2, RotateCcw, Save } from 'lucide-react'
import { toast } from 'sonner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Textarea } from '@/components/ui/textarea'
import { Callout, Card, CardTitle, when } from '@/components/bits'
import { post, put } from '@/lib/api'
import type { CasePacket } from '@/lib/api'
import { navigate } from '@/lib/router'

export default function ComplaintTab({ c, onChange, reload }: { c: CasePacket; onChange: (c: CasePacket) => void; reload: () => Promise<void> }) {
  const [draft, setDraft] = useState(c.complaint_draft)
  const [synced, setSynced] = useState(c.complaint_draft)
  const [saving, setSaving] = useState(false)
  const [approving, setApproving] = useState(false)
  if (synced !== c.complaint_draft) {  // the stored draft changed (saved, restored): show it
    setSynced(c.complaint_draft)
    setDraft(c.complaint_draft)
  }

  const dirty = draft !== c.complaint_draft
  const approved = c.approval.state === 'approved_by_passenger'
  const run = c.evidence_run ?? {}
  const changed = !!run.contacts_changed
  const verified = run.mode === 'live' || run.mode === 'cached'
  const items = [
    'I have read the rights check',
    'The facts match my documents',
    changed ? `The airline’s contacts changed (${(run.changes ?? []).join('; ')}). I confirmed them on the airline’s own website.`
      : verified ? 'The airline’s contacts were re-read today and are unchanged'
        : 'I know the airline’s contacts come from a dated snapshot that could not be re-checked today',
  ]
  const [ticks, setTicks] = useState(items.map(() => false))

  const save = async (text: string | null) => {
    setSaving(true)
    try {
      const r = await put<CasePacket>(`/api/case/${c.case_id}/draft`, { text })
      onChange(r)
      if (r.approval_withdrawn) toast.warning('The draft changed, so your approval was withdrawn. Approve the new text when ready.')
      else toast.success(text === null ? 'Generated draft restored' : 'Draft saved')
      return r
    } catch (e) { toast.error((e as Error).message); return null } finally { setSaving(false) }
  }

  const approve = async () => {
    setApproving(true)
    try {
      if (dirty && !(await save(draft))) return  // approve exactly the text that is stored
      await post(`/api/case/${c.case_id}/approve`, { acknowledge_contact_change: changed })
      await reload()
      toast.success('Approved. Nothing was sent.')
      navigate(`/case/${c.case_id}/followup`)
    } catch (e) { toast.error((e as Error).message) } finally { setApproving(false) }
  }

  const copy = () => navigator.clipboard.writeText(draft).then(() => toast.success('Copied to clipboard'), () => toast.error('Your browser blocked copying'))

  return (
    <div className="grid gap-6 lg:grid-cols-[1.6fr_1fr]">
      <Card>
        <CardTitle aside={<div className="flex items-center gap-2">
          {c.draft_edited && <Badge variant="secondary">Edited by you</Badge>}
          {dirty && <Badge variant="solid">Unsaved changes</Badge>}
        </div>}>Complaint draft</CardTitle>
        <Textarea className="min-h-[28rem] font-mono text-[13px] leading-relaxed" value={draft} onChange={(e) => setDraft(e.target.value)} spellCheck />
        <div className="mt-3 flex flex-wrap gap-2">
          <Button variant="secondary" size="sm" onClick={copy}><Copy /> Copy</Button>
          <Button variant="secondary" size="sm" disabled={!dirty || saving} onClick={() => save(draft)}>
            {saving ? <Loader2 className="animate-spin" /> : <Save />} Save changes
          </Button>
          {(c.draft_edited || dirty) && (
            <Button variant="ghost" size="sm" disabled={saving} onClick={() => { setDraft(c.generated_draft); save(null) }}><RotateCcw /> Restore generated draft</Button>
          )}
        </div>
        <p className="mt-3 text-xs text-muted-foreground">Written from supported claims only. Add your name and contact details before sending.</p>
      </Card>

      <div className="space-y-6">
        {approved ? (
          <Card>
            <div className="flex items-center gap-2 font-bold"><CheckCircle2 className="size-5 text-primary" /> Approved by you</div>
            <p className="mt-2 text-sm text-muted-foreground">
              {c.approval.approved_at ? `On ${when(c.approval.approved_at)}. ` : ''}Nothing was sent. Submit it through the airline’s channel or AirSewa, then record it in Follow-up.
            </p>
            {dirty && <Callout tone="warn" className="mt-4">Saving these changes will withdraw your approval until you approve the new text.</Callout>}
            <Button className="mt-5 w-full" variant="secondary" onClick={() => navigate(`/case/${c.case_id}/followup`)}>Go to follow-up</Button>
          </Card>
        ) : (
          <Card>
            <CardTitle>Before you approve</CardTitle>
            <div className="space-y-3">
              {items.map((t, i) => (
                <label key={i} className="flex cursor-pointer items-start gap-3 text-sm">
                  <Checkbox checked={ticks[i]} onCheckedChange={(v) => setTicks((x) => x.map((y, j) => (j === i ? v === true : y)))} className="mt-0.5" />
                  <span>{t}</span>
                </label>
              ))}
            </div>
            <Button size="lg" className="mt-6 w-full" disabled={!ticks.every(Boolean) || approving} onClick={approve}>
              {approving ? <Loader2 className="animate-spin" /> : null} {dirty ? 'Save and approve' : 'Approve this draft'}
            </Button>
            <p className="mt-3 text-xs text-muted-foreground">Approval records your consent only. FLIGHTBACK never sends anything for you.</p>
          </Card>
        )}
        <Card>
          <CardTitle>Send it to</CardTitle>
          <ol className="space-y-2 text-sm">
            {c.escalation.slice(0, 2).map((e) => <li key={e.step}><b>{e.to}</b><div className="break-words text-muted-foreground">{e.how}</div></li>)}
          </ol>
        </Card>
      </div>
    </div>
  )
}
