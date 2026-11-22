import { useCallback, useEffect, useState } from 'react'
import { RefreshCw } from 'lucide-react'
import { toast } from 'sonner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Kicker, Pane } from '@/components/bits'
import { api, post } from '@/lib/api'
import type { Lead } from '@/lib/api'

interface Row { code: string; airline: string; grievance_status: string; age_hours: number | null; stale: boolean; has_live_source: boolean; leads: number }
interface Watch { id: number; status: string; entities: number; credits_consumed: number; notifications_count: number; last_run_at: string; expires_at: string }

function route(r: Row) {
  if (r.grievance_status === 'primary_verified') return <Badge>Verified</Badge>
  if (r.grievance_status === 'primary_blocked') return <Badge variant="solid">Cannot verify · blocked</Badge>
  return <Badge variant="secondary">Identity only</Badge>
}
const age = (h: number | null) => (h == null ? 'n/a' : h < 1 ? '<1 h' : h < 48 ? `${Math.round(h)} h` : `${Math.round(h / 24)} d`)

export default function SourcesScreen() {
  const [fresh, setFresh] = useState<{ airlines: Row[]; fresh_within_hours: number; case_ceiling: number } | null>(null)
  const [watch, setWatch] = useState<Watch | null>(null)
  const [leads, setLeads] = useState<Lead[]>([])
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    api('/api/freshness').then(setFresh).catch(() => {})
    api<Watch>('/api/watch').then(setWatch).catch(() => setWatch(null))
    api<{ items: Lead[] }>('/api/leads?limit=8').then((r) => setLeads(r.items)).catch(() => setLeads([]))
  }, [])
  useEffect(() => { load() }, [load])

  const pull = async () => {
    setBusy(true)
    try {
      const r = await post<{ leads_new?: number }>('/api/watch/sync')
      toast.success(`Watch synced${r.leads_new != null ? ` · ${r.leads_new} new leads` : ''}`); await load()
    } catch (e) { toast.error((e as Error).message) } finally { setBusy(false) }
  }

  return (
    <div>
      <Pane className="border-b-2 border-divider">
        <Kicker className="mb-3 text-primary">Sources · Evidence freshness</Kicker>
        <h1 className="text-4xl md:text-6xl">How fresh is what we know?</h1>
        <p className="mt-3 max-w-xl text-muted-foreground">Each case re-reads its airline’s grievance page live under a {fresh?.case_ceiling ?? 3}-credit ceiling. This board shows the last verified snapshot.</p>
        <div className="mt-8">
          <Table>
            <TableHeader><TableRow><TableHead>Airline</TableHead><TableHead>Grievance route</TableHead><TableHead>Age</TableHead><TableHead className="text-right">Leads</TableHead></TableRow></TableHeader>
            <TableBody>
              {(fresh?.airlines ?? []).map((r) => (
                <TableRow key={r.code}>
                  <TableCell className="font-extrabold">{r.airline} <span className="font-mono text-xs font-normal text-muted-foreground">{r.code}</span></TableCell>
                  <TableCell>{route(r)}</TableCell>
                  <TableCell className="font-mono text-xs">{r.has_live_source ? age(r.age_hours) : 'n/a'}</TableCell>
                  <TableCell className="text-right font-mono text-xs">{r.leads}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </Pane>
      <Pane>
        <div className="flex flex-wrap items-center gap-3"><Kicker>Precedent leads</Kicker><Badge variant="solid">LEAD, NOT PROOF</Badge></div>
        <p className="mt-2 text-sm text-muted-foreground">News is a pointer, never evidence. The rights engine never sees it.</p>
        <ul className="mt-5 divide-y divide-border">
          {leads.length === 0 && <li className="py-3 text-sm text-muted-foreground">No leads yet. Pull the watch to fetch some.</li>}
          {leads.map((l) => (
            <li key={l.url} className="grid gap-1 py-3 md:grid-cols-[4rem_1fr_9rem] md:gap-4">
              <span className="font-mono text-xs font-bold">{l.code}</span>
              <a className="text-sm font-semibold hover:underline" href={l.url} target="_blank" rel="noreferrer">{l.title}</a>
              <span className="text-xs text-muted-foreground md:text-right">{[l.publisher, l.published].filter(Boolean).join(' · ')}</span>
            </li>
          ))}
        </ul>
        <div className="mt-8 flex flex-wrap items-center justify-between gap-4 border-t-2 border-divider pt-6">
          <p className="font-mono text-xs tracking-wide text-muted-foreground uppercase">
            {watch ? `Crustdata watch #${watch.id} · ${watch.status} · ${watch.entities} airlines · ${watch.credits_consumed} credits billed` : 'No Crustdata watch configured'}
          </p>
          <Button variant="outline" disabled={busy || !watch} onClick={pull}><RefreshCw className={busy ? 'animate-spin' : ''} /> Pull new leads</Button>
        </div>
      </Pane>
    </div>
  )
}
