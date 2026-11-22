import { ArrowRight, ExternalLink, ShieldAlert, ShieldCheck } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Kicker, Pane, StatusTag, fmtDT } from '@/components/bits'
import { inr } from '@/lib/api'
import type { CasePacket } from '@/lib/api'
import { caseRef } from '@/lib/model'

const MODE: Record<string, { tag: string; tone: 'default' | 'solid' | 'secondary' | 'outline' }> = {
  live: { tag: 'Checked live', tone: 'default' },
  cached: { tag: 'Checked · cached ≤24 h', tone: 'default' },
  stale_snapshot: { tag: 'Cannot verify · dated snapshot', tone: 'solid' },
  snapshot_only: { tag: 'Snapshot only', tone: 'secondary' },
}

export function EvidenceRun({ run }: { run: CasePacket['evidence_run'] }) {
  if (!run) return null
  const m = MODE[run.mode] ?? MODE.snapshot_only
  return (
    <div className="border-2 border-foreground p-5">
      <div className="flex flex-wrap items-center gap-3">
        <Kicker>Evidence run</Kicker><Badge variant={m.tone}>{m.tag}</Badge>
        {run.ceiling != null && <span className="font-mono text-xs text-muted-foreground">{run.spent ?? 0} of {run.ceiling} credits spent</span>}
      </div>
      <p className="mt-3 text-sm">
        {run.contacts_changed ? <><b>Airline contacts changed vs snapshot:</b> {(run.changes ?? []).join('; ')}.</>
          : run.mode === 'live' || run.mode === 'cached' ? 'Contacts unchanged vs snapshot.'
            : run.reason ?? 'No live check was made.'}
        {run.live_retrieved_at && <span className="text-muted-foreground"> Page read {fmtDT(run.live_retrieved_at)}.</span>}
      </p>
      {run.calls?.length > 0 && (
        <div className="mt-3 divide-y divide-border font-mono text-xs">
          {run.calls.map((c: { endpoint: string; credits: number; cached: boolean; status: string }, i: number) => (
            <div key={i} className="flex justify-between gap-3 py-1.5"><span>{c.endpoint}</span><span className="text-muted-foreground">{c.cached ? 'cache · 0' : `${c.credits} cr`} · {c.status}</span></div>
          ))}
        </div>
      )}
    </div>
  )
}

export default function PacketScreen({ c, next }: { c: CasePacket; next: () => void }) {
  const am = c.amounts ?? {}
  const hero = am.payable_compensation ?? am.shortfall ?? null
  const heroLabel = am.shortfall != null && am.payable_compensation == null ? 'Refund shortfall' : 'Compensation owed'
  const owed = hero != null && Number(hero) > 0
  return (
    <div>
      <Pane className="border-b-2 border-divider">
        <div className="grid gap-10 md:grid-cols-[1.2fr_1fr]">
          <div>
            <Kicker className="mb-3 text-primary">3 · Case packet · {caseRef(c.case_id)}</Kicker>
            <Kicker className="text-muted-foreground">{heroLabel}</Kicker>
            <div className="mt-1 text-6xl font-extrabold tracking-tight md:text-8xl">{owed ? inr(hero) : 'Rs 0'}</div>
            {am.formula && <p className="mt-3 max-w-lg font-mono text-sm text-muted-foreground">{am.formula}</p>}
            {!owed && <p className="mt-3 max-w-lg text-sm text-muted-foreground">No payable amount from the facts given. See the rights check for why.</p>}
          </div>
          <div>
            <Kicker className="mb-3">Summary</Kicker>
            <div className="flex flex-wrap gap-2">
              {Object.entries(c.status_counts ?? {}).filter(([, n]) => n > 0).map(([s, n]) => <StatusTag key={s} status={s} count={n} />)}
            </div>
            <ul className="mt-4 space-y-2 text-sm">{(c.headline ?? []).map((h, i) => <li key={i}>{h.replace(/^[A-Z_ ]+: /, "")}</li>)}</ul>
            <p className="mt-4 flex items-start gap-2 text-sm">
              {c.rule_pack.verified ? <ShieldCheck className="mt-0.5 size-4 shrink-0 text-primary" /> : <ShieldAlert className="mt-0.5 size-4 shrink-0 text-primary" />}
              <span>
                Rule pack {c.rule_pack.verified ? 'verified' : <b>NOT verified</b>} — {c.rule_pack.id} {c.rule_pack.revision}, effective {c.rule_pack.effective}.
                {c.rule_pack.source_url && <> <a className="underline" href={c.rule_pack.source_url} target="_blank" rel="noreferrer">Official source <ExternalLink className="inline size-3" /></a></>}
              </span>
            </p>
          </div>
        </div>
        {c.warnings?.length > 0 && (
          <div className="mt-8 space-y-2">
            {c.warnings.map((w, i) => <div key={i} className="border-2 border-primary bg-accent p-3 text-sm font-semibold text-accent-foreground">{w}</div>)}
          </div>
        )}
      </Pane>

      <Pane className="border-b-2 border-divider">
        <Kicker className="mb-4">Rights check, condition by condition</Kicker>
        <Table>
          <TableHeader><TableRow><TableHead>Condition</TableHead><TableHead>Status</TableHead><TableHead>Why</TableHead></TableRow></TableHeader>
          <TableBody>
            {c.conditions.map((k) => (
              <TableRow key={k.id}>
                <TableCell className="align-top whitespace-normal"><div className="font-extrabold">{k.label}</div><div className="font-mono text-xs text-muted-foreground">{k.rule_ref}</div></TableCell>
                <TableCell className="align-top"><StatusTag status={k.status} /></TableCell>
                <TableCell className="align-top whitespace-normal">{k.detail}{k.missing?.length > 0 && <div className="mt-1 text-xs text-muted-foreground">Missing: {k.missing.join(', ')}</div>}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Pane>

      <Pane className="border-b-2 border-divider">
        <div className="grid gap-10 md:grid-cols-3">
          <div>
            <Kicker className="mb-3">Timeline</Kicker>
            <ul className="space-y-2 text-sm">{c.timeline.map((t, i) => <li key={i}><span className="font-mono text-xs text-muted-foreground">{fmtDT(t.time)}</span><br />{t.event}</li>)}</ul>
          </div>
          <div>
            <Kicker className="mb-3">Still missing</Kicker>
            {c.missing.length ? <ul className="list-disc space-y-1 pl-4 text-sm">{c.missing.map((m, i) => <li key={i}>{m}</li>)}</ul> : <p className="text-sm text-muted-foreground">Nothing missing.</p>}
          </div>
          <div>
            <Kicker className="mb-3">Where to complain</Kicker>
            <ol className="space-y-2 text-sm">{c.escalation.map((e) => <li key={e.step}><b>{e.step} · {e.to}</b><br /><span className="text-muted-foreground">{/^https?:/.test(e.how) ? <a className="underline" href={e.how} target="_blank" rel="noreferrer">{e.how}</a> : e.how}</span></li>)}</ol>
          </div>
        </div>
      </Pane>

      <Pane>
        <div className="grid gap-8 md:grid-cols-2">
          <EvidenceRun run={c.evidence_run} />
          <div className="border-2 border-foreground p-5">
            <div className="flex flex-wrap items-center gap-3"><Kicker>Precedent leads</Kicker><Badge variant="solid">LEAD, NOT PROOF</Badge></div>
            <p className="mt-2 text-xs text-muted-foreground">{c.leads?.note ?? 'News is a pointer, never evidence. The rights engine never sees it.'}</p>
            {c.leads?.items?.length ? (
              <ul className="mt-3 space-y-2 text-sm">
                {c.leads.items.slice(0, 3).map((l) => (
                  <li key={l.url}><a className="font-semibold underline-offset-2 hover:underline" href={l.url} target="_blank" rel="noreferrer">{l.title}</a><div className="text-xs text-muted-foreground">{[l.publisher, l.published].filter(Boolean).join(' · ')}</div></li>
                ))}
              </ul>
            ) : <p className="mt-3 text-sm text-muted-foreground">No leads for this airline yet.</p>}
          </div>
        </div>
        <div className="mt-8 flex flex-wrap items-center justify-between gap-4">
          <p className="text-sm text-muted-foreground">Next: review the complaint draft. Nothing is sent.</p>
          <Button size="lg" onClick={next}>Review complaint draft <ArrowRight /></Button>
        </div>
      </Pane>
    </div>
  )
}
