import { ArrowRight, ExternalLink, ShieldAlert, ShieldCheck } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Callout, Card, CardTitle, StatusTag, fmtDT } from '@/components/bits'
import { inr } from '@/lib/api'
import type { CasePacket } from '@/lib/api'
import { Link } from '@/lib/router'

const MODE: Record<string, { tag: string; tone: 'default' | 'solid' | 'secondary' }> = {
  live: { tag: 'Checked live', tone: 'default' },
  cached: { tag: 'Checked today (cached)', tone: 'default' },
  stale_snapshot: { tag: 'Could not verify: dated snapshot', tone: 'solid' },
  snapshot_only: { tag: 'Dated snapshot', tone: 'secondary' },
}
const METHOD: Record<string, string> = { text_layer: 'text layer', ocr: 'OCR' }
const isUrl = (s: string) => /^https?:\/\//i.test(s)
// Warnings that change what the passenger should rely on; everything else is context.
const isSerious = (w: string) => /NOT verified|CONTACT CHANGED|did not verify|Ignored unrecognised/i.test(w)
const label = (s: string) => s.replace(/_/g, ' ').replace(/^./, (x) => x.toUpperCase())

function show(v: unknown) {
  if (typeof v === 'boolean') return v ? 'Yes' : 'No'
  if (typeof v === 'string' && /^\d{4}-\d{2}-\d{2}T/.test(v)) return fmtDT(v)
  return String(v)
}

export default function OverviewTab({ c }: { c: CasePacket }) {
  const am = c.amounts ?? {}
  const comp = am.payable_compensation, short = am.shortfall
  const hero = comp ?? short ?? null
  const heroLabel = c.case_type === 'refund' ? 'Refund shortfall' : 'Compensation owed'
  const owed = hero != null && Number(hero) > 0
  const run = c.evidence_run
  const mode = MODE[run?.mode] ?? MODE.snapshot_only
  const serious = (c.warnings ?? []).filter(isSerious)
  const notes = (c.warnings ?? []).filter((w) => !isSerious(w))

  return (
    <div className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-[1.1fr_1fr]">
        <Card>
          <div className="text-sm font-semibold text-muted-foreground">{heroLabel}</div>
          <div className="mt-1 text-5xl font-extrabold tracking-tight md:text-6xl">{owed ? inr(hero) : 'Rs 0'}</div>
          {am.formula && <p className="mt-3 font-mono text-sm text-muted-foreground">{am.formula}</p>}
          {!owed && <p className="mt-3 text-sm text-muted-foreground">No payable amount from the facts given. The rights check below explains why.</p>}
          {am.expected_refund != null && <p className="mt-3 text-sm">Expected refund: <b>{inr(am.expected_refund)}</b>{am.refund_received != null && <> · received {inr(am.refund_received)}</>}</p>}
          <div className="mt-5 flex flex-wrap gap-2">
            {Object.entries(c.status_counts ?? {}).filter(([, n]) => n > 0).map(([s, n]) => <StatusTag key={s} status={s} count={n} />)}
          </div>
        </Card>
        <Card>
          <CardTitle>What the airline owes you</CardTitle>
          {c.headline?.length ? (
            <ul className="space-y-2.5 text-sm">
              {c.headline.map((h, i) => <li key={i} className="flex gap-2"><span className="mt-0.5 text-primary">•</span><span>{h.replace(/^[A-Z_ ]+: /, '')}</span></li>)}
            </ul>
          ) : <p className="text-sm text-muted-foreground">No claim is supported by the facts provided yet. See what is missing below.</p>}
          <div className="mt-5 flex items-start gap-2 border-t border-border pt-4 text-sm">
            {c.rule_pack.verified ? <ShieldCheck className="mt-0.5 size-4 shrink-0 text-primary" /> : <ShieldAlert className="mt-0.5 size-4 shrink-0 text-destructive" />}
            <span className="text-muted-foreground">
              {c.rule_pack.id} {c.rule_pack.revision}, effective {c.rule_pack.effective} · {c.rule_pack.verified ? 'verified' : <b className="text-foreground">not verified against primary text</b>}
              {c.rule_pack.source_url && <> · <a className="underline" href={c.rule_pack.source_url} target="_blank" rel="noreferrer">official source <ExternalLink className="inline size-3" /></a></>}
            </span>
          </div>
        </Card>
      </div>

      {serious.length > 0 && <div className="space-y-2">{serious.map((w, i) => <Callout key={i} tone="warn">{w}</Callout>)}</div>}
      {notes.length > 0 && (
        <Callout>
          <div className="mb-1 font-semibold">Good to know</div>
          <ul className="list-disc space-y-1 pl-4 text-muted-foreground">{notes.map((w, i) => <li key={i}>{w}</li>)}</ul>
        </Callout>
      )}

      <Card>
        <CardTitle>Rights check, condition by condition</CardTitle>
        <ul className="divide-y divide-border">
          {c.conditions.map((k) => (
            <li key={k.id} className="grid gap-2 py-4 md:grid-cols-[minmax(0,15rem)_8rem_1fr] md:gap-5">
              <div><div className="font-semibold">{k.label}</div><div className="font-mono text-xs text-muted-foreground">para {k.rule_ref}</div></div>
              <div><StatusTag status={k.status} /></div>
              <div className="text-sm">
                {k.detail}
                {k.missing?.length > 0 && <div className="mt-1 text-xs text-muted-foreground">Missing: {k.missing.join('; ')}</div>}
              </div>
            </li>
          ))}
        </ul>
      </Card>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card>
          <CardTitle>Timeline</CardTitle>
          {c.timeline.length ? (
            <ol className="space-y-3 border-l border-border pl-4 text-sm">
              {c.timeline.map((t, i) => <li key={i}><div className="font-mono text-xs text-muted-foreground">{fmtDT(t.time)}</div>{t.event}</li>)}
            </ol>
          ) : <p className="text-sm text-muted-foreground">No times given.</p>}
        </Card>
        <Card>
          <CardTitle>Still missing</CardTitle>
          {c.missing.length ? <ul className="list-disc space-y-1.5 pl-4 text-sm">{c.missing.map((m, i) => <li key={i}>{m}</li>)}</ul>
            : <p className="text-sm text-muted-foreground">Nothing required is missing.</p>}
        </Card>
        <Card>
          <CardTitle>Where to complain</CardTitle>
          <ol className="space-y-3 text-sm">
            {c.escalation.map((e) => (
              <li key={e.step} className="flex gap-3">
                <span className="grid size-6 shrink-0 place-items-center rounded-full bg-secondary text-xs font-bold">{e.step}</span>
                <div className="min-w-0">
                  <div className="font-semibold">{e.to}</div>
                  <div className="break-words text-muted-foreground">
                    {isUrl(e.how) ? <a className="underline" href={e.how} target="_blank" rel="noreferrer">{e.how}</a>
                      : e.how === 'CANNOT VERIFY' ? <b className="text-destructive">Cannot verify</b> : e.how}
                  </div>
                </div>
              </li>
            ))}
          </ol>
        </Card>
      </div>

      <Card>
        <CardTitle aside={<span className="text-sm text-muted-foreground">Where each fact came from</span>}>Evidence</CardTitle>
        {c.evidence_index.length === 0 ? <p className="text-sm text-muted-foreground">No facts were entered.</p> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="border-b border-border text-left text-xs text-muted-foreground"><th className="py-2 pr-4 font-semibold">Fact</th><th className="py-2 pr-4 font-semibold">Value</th><th className="py-2 font-semibold">Source</th></tr></thead>
              <tbody className="divide-y divide-border">
                {c.evidence_index.map((e) => (
                  <tr key={e.fact} className="align-top">
                    <td className="py-2.5 pr-4 font-semibold">{label(e.fact)}</td>
                    <td className="py-2.5 pr-4 font-mono text-xs">{show(e.value)}</td>
                    <td className="py-2.5">
                      {e.doc ? <>{e.doc}{e.page != null && <span className="text-muted-foreground"> · page {e.page}</span>}{e.method && <span className="text-muted-foreground"> · {METHOD[e.method] ?? e.method}{e.confidence != null ? ` ${Math.round(e.confidence)}%` : ''}</span>}</>
                        : <span className="text-muted-foreground">Stated by you, no document</span>}
                      {e.snippet && <div className="max-w-md truncate text-xs text-muted-foreground">“{e.snippet}”</div>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        {run && (
          <Card>
            <CardTitle aside={<Badge variant={mode.tone}>{mode.tag}</Badge>}>Airline check</CardTitle>
            <p className="text-sm">
              {run.contacts_changed ? <><b>The airline’s contacts changed since our snapshot:</b> {(run.changes ?? []).join('; ')}.</>
                : run.mode === 'live' || run.mode === 'cached' ? 'Grievance contacts re-read from the airline’s own page and unchanged.'
                  : run.reason ?? 'No live check was made.'}
              {run.live_retrieved_at && <span className="text-muted-foreground"> Page read {fmtDT(run.live_retrieved_at)}.</span>}
            </p>
            {run.calls?.length > 0 && (
              <div className="mt-3 divide-y divide-border rounded-md border border-border font-mono text-xs">
                {run.calls.map((k: { endpoint: string; credits: number; cached: boolean; status: string }, i: number) => (
                  <div key={i} className="flex justify-between gap-3 px-3 py-2"><span>{k.endpoint}</span><span className="text-muted-foreground">{k.cached ? 'cache · 0 cr' : `${k.credits} cr`} · {k.status}</span></div>
                ))}
              </div>
            )}
          </Card>
        )}
        <Card>
          <CardTitle aside={<Badge variant="solid">Lead, not proof</Badge>}>Similar cases in the news</CardTitle>
          <p className="text-xs text-muted-foreground">{c.leads?.note}</p>
          {c.leads?.items?.length ? (
            <ul className="mt-3 space-y-2.5 text-sm">
              {c.leads.items.slice(0, 4).map((l) => (
                <li key={l.url}>
                  {isUrl(l.url) ? <a className="font-semibold hover:underline" href={l.url} target="_blank" rel="noopener noreferrer">{l.title}</a> : <span className="font-semibold">{l.title}</span>}
                  <div className="text-xs text-muted-foreground">{[l.publisher, l.published].filter(Boolean).join(' · ')}</div>
                </li>
              ))}
            </ul>
          ) : <p className="mt-3 text-sm text-muted-foreground">No news leads collected for this airline yet.</p>}
        </Card>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-4 rounded-lg border border-border bg-card p-5">
        <p className="text-sm text-muted-foreground">Next: review the complaint draft. Nothing is sent until you send it yourself.</p>
        <Button asChild size="lg"><Link to={`/case/${c.case_id}/complaint`}>Review the complaint <ArrowRight /></Link></Button>
      </div>
    </div>
  )
}
