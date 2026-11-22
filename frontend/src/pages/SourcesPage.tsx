import { useCallback, useEffect, useState } from 'react'
import { ExternalLink, RefreshCw } from 'lucide-react'
import { toast } from 'sonner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardTitle, Container, Loading, PageHeader } from '@/components/bits'
import { api, post } from '@/lib/api'
import type { Lead } from '@/lib/api'

interface Row { code: string; airline: string; grievance_status: string; retrieved_at: string | null; age_hours: number | null; stale: boolean; has_live_source: boolean; leads: number }
interface Fresh { airlines: Row[]; fresh_within_hours: number; case_ceiling: number }
interface Watch { id: number; status: string; entities: number; credits_consumed: number; last_run_at: string | null; expires_at: string }
interface RulePack { id: string; title: string; revision: string; effective: string; verified: boolean; source_url: string | null; note: string }

function routeBadge(r: Row) {
  if (r.grievance_status === 'primary_verified') return <Badge>Verified</Badge>
  if (r.grievance_status === 'primary_blocked') return <Badge variant="solid">Blocked: cannot verify</Badge>
  if (!r.has_live_source) return <Badge variant="secondary">Identity only</Badge>
  return <Badge variant="secondary">Not verified</Badge>
}
const age = (h: number | null) => (h == null ? '—' : h < 1 ? 'under 1 h' : h < 48 ? `${Math.round(h)} h` : `${Math.round(h / 24)} days`)
const isUrl = (s: string) => /^https?:\/\//i.test(s)

export default function SourcesPage() {
  const [fresh, setFresh] = useState<Fresh | null>(null)
  const [packs, setPacks] = useState<RulePack[]>([])
  const [watch, setWatch] = useState<Watch | null>(null)
  const [leads, setLeads] = useState<Lead[]>([])
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => {
    api<Fresh>('/api/freshness').then(setFresh).catch(() => {})
    api<RulePack[]>('/api/rules').then(setPacks).catch(() => {})
    api<Watch & { id: number | null }>('/api/watch').then((w) => setWatch(w.id ? w : null)).catch(() => setWatch(null))
    api<{ items: Lead[] }>('/api/leads?limit=10').then((r) => setLeads(r.items)).catch(() => setLeads([]))
  }, [])
  useEffect(() => { load() }, [load])

  const pull = async () => {
    setBusy(true)
    try {
      const r = await post<{ leads_new?: number }>('/api/watch/sync')
      toast.success(`Watch synced${r.leads_new != null ? `: ${r.leads_new} new lead${r.leads_new === 1 ? '' : 's'}` : ''}`)
      load()
    } catch (e) { toast.error((e as Error).message) } finally { setBusy(false) }
  }

  return (
    <Container>
      <PageHeader eyebrow="Sources" title="What we rely on, and how fresh it is"
        lead={`The rules come from DGCA’s official text. Airline complaint contacts are read from each airline’s own website; every new case re-checks its airline live (up to ${fresh?.case_ceiling ?? 3} credits).`} />

      <div className="space-y-6">
        <Card>
          <CardTitle>Rules</CardTitle>
          <ul className="divide-y divide-border">
            {packs.map((p) => (
              <li key={p.id} className="grid gap-2 py-4 md:grid-cols-[1fr_auto] md:items-start">
                <div>
                  <div className="font-semibold">{p.title}</div>
                  <div className="text-sm text-muted-foreground">{p.id} · {p.revision} · effective {p.effective}</div>
                  <div className="mt-1 text-sm text-muted-foreground">{p.note}</div>
                </div>
                <div className="flex items-center gap-3">
                  {p.verified ? <Badge>Verified</Badge> : <Badge variant="solid">Not verified</Badge>}
                  {p.source_url && <a className="text-sm font-semibold text-primary hover:underline" href={p.source_url} target="_blank" rel="noreferrer">Official text <ExternalLink className="inline size-3" /></a>}
                </div>
              </li>
            ))}
          </ul>
        </Card>

        <Card>
          <CardTitle aside={fresh && <span className="text-sm text-muted-foreground">Older than {fresh.fresh_within_hours} h counts as stale</span>}>Airline complaint routes</CardTitle>
          {!fresh ? <Loading /> : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead><tr className="border-b border-border text-left text-xs text-muted-foreground">
                  <th className="py-2 pr-4 font-semibold">Airline</th><th className="py-2 pr-4 font-semibold">Grievance route</th>
                  <th className="py-2 pr-4 font-semibold">Last checked</th><th className="py-2 text-right font-semibold">News leads</th>
                </tr></thead>
                <tbody className="divide-y divide-border">
                  {fresh.airlines.map((r) => (
                    <tr key={r.code}>
                      <td className="py-3 pr-4"><span className="font-semibold">{r.airline}</span> <span className="font-mono text-xs text-muted-foreground">{r.code}</span></td>
                      <td className="py-3 pr-4">{routeBadge(r)}</td>
                      <td className={'py-3 pr-4 ' + (r.has_live_source && r.stale ? 'font-semibold text-destructive' : 'text-muted-foreground')}>
                        {r.has_live_source ? `${age(r.age_hours)} ago${r.stale ? ' · stale' : ''}` : 'No page configured'}
                      </td>
                      <td className="py-3 text-right font-mono">{r.leads}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        <Card>
          <CardTitle aside={<Badge variant="solid">Lead, not proof</Badge>}>Passenger-rights news</CardTitle>
          <p className="text-sm text-muted-foreground">Headlines about airlines’ passenger disputes. A pointer for your own research, never evidence: the rights check never uses them.</p>
          <ul className="mt-4 divide-y divide-border">
            {leads.length === 0 && <li className="py-3 text-sm text-muted-foreground">No leads collected yet.</li>}
            {leads.map((l) => (
              <li key={l.url} className="grid gap-1 py-3 md:grid-cols-[3.5rem_1fr_auto] md:gap-4">
                <span className="font-mono text-xs font-bold">{l.code}</span>
                {isUrl(l.url) ? <a className="text-sm font-semibold hover:underline" href={l.url} target="_blank" rel="noopener noreferrer">{l.title}</a> : <span className="text-sm font-semibold">{l.title}</span>}
                <span className="text-xs text-muted-foreground md:text-right">{[l.publisher, l.published].filter(Boolean).join(' · ')}</span>
              </li>
            ))}
          </ul>
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-border pt-4">
            <p className="text-xs text-muted-foreground">
              {watch ? `Crustdata watch #${watch.id} · ${watch.status} · ${watch.entities} airlines · expires ${watch.expires_at} · ${watch.credits_consumed} credits billed`
                : 'No news watch is set up on this server.'}
            </p>
            {watch && <Button variant="secondary" size="sm" disabled={busy} onClick={pull}><RefreshCw className={busy ? 'animate-spin' : ''} /> Pull new leads</Button>}
          </div>
        </Card>
      </div>
    </Container>
  )
}
