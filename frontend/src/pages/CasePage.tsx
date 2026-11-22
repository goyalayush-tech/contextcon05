import { useCallback, useEffect, useState } from 'react'
import { ArrowLeft, CheckCircle2 } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Container, Empty, KIND_LABEL, Loading, when } from '@/components/bits'
import { api } from '@/lib/api'
import type { CasePacket } from '@/lib/api'
import { caseRef } from '@/lib/model'
import { Link } from '@/lib/router'
import { cn } from '@/lib/utils'
import OverviewTab from '@/pages/case/OverviewTab'
import ComplaintTab from '@/pages/case/ComplaintTab'
import FollowupTab from '@/pages/case/FollowupTab'

export type CaseTab = 'overview' | 'complaint' | 'followup'
const TABS: { key: CaseTab; label: string }[] = [
  { key: 'overview', label: 'Rights check' },
  { key: 'complaint', label: 'Complaint' },
  { key: 'followup', label: 'Follow-up' },
]

export default function CasePage({ id, tab }: { id: string; tab: CaseTab }) {
  const [c, setC] = useState<CasePacket | null>(null)
  const [error, setError] = useState<string | null>(null)

  const reload = useCallback(async () => {
    try { setC(await api<CasePacket>(`/api/case/${encodeURIComponent(id)}`)); setError(null) }
    catch (e) { setError((e as Error).message) }
  }, [id])
  useEffect(() => { reload() }, [reload])  // the page is keyed by case id, so state starts fresh per case

  if (error) {
    return (
      <Container className="pt-14">
        <Empty title={error === 'unknown case' ? 'Case not found' : 'Could not load this case'}>
          {error === 'unknown case' ? 'It may have been created on another device or database.' : error}
          <div className="mt-5 flex justify-center gap-3">
            <Button asChild variant="secondary"><Link to="/cases">My cases</Link></Button>
            <Button asChild><Link to="/new">Start a case</Link></Button>
          </div>
        </Empty>
      </Container>
    )
  }
  if (!c) return <Container><Loading label="Loading case…" /></Container>

  const fl = c.flight ?? {}
  const route = [fl.origin, fl.destination].filter(Boolean).join(' → ')
  const approved = c.approval.state === 'approved_by_passenger'
  const base = `/case/${c.case_id}`

  return (
    <>
      <div className="border-b border-border bg-card">
        <Container className="pt-8">
          <Link to="/cases" className="inline-flex items-center gap-1.5 text-sm font-semibold text-muted-foreground hover:text-foreground">
            <ArrowLeft className="size-4" /> My cases
          </Link>
          <div className="mt-4 flex flex-wrap items-start justify-between gap-4">
            <div>
              <h1 className="text-2xl md:text-4xl">
                {KIND_LABEL[c.case_type]}{fl.flight_number ? ` · ${fl.flight_number}` : ''}
              </h1>
              <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground">
                <span className="font-mono">#{caseRef(c.case_id)}</span>
                {route && <span>{route}</span>}
                {fl.date && <span>{fl.date}</span>}
                {c.airline?.identity?.name && <span>{c.airline.identity.name}</span>}
                <span>Created {when(c.created_at)}</span>
              </div>
            </div>
            {approved
              ? <Badge variant="outline" className="py-1"><CheckCircle2 className="size-3.5" /> Approved by you · not sent</Badge>
              : <Badge variant="secondary" className="py-1">Awaiting your approval</Badge>}
          </div>
          <nav className="mt-6 -mb-px flex gap-1 overflow-x-auto">
            {TABS.map((t) => (
              <Link key={t.key} to={t.key === 'overview' ? base : `${base}/${t.key}`}
                className={cn('border-b-2 px-4 py-3 text-sm font-semibold whitespace-nowrap transition-colors',
                  tab === t.key ? 'border-primary text-foreground' : 'border-transparent text-muted-foreground hover:text-foreground')}>
                {t.label}
              </Link>
            ))}
          </nav>
        </Container>
      </div>
      <Container className="pt-8">
        {tab === 'overview' ? <OverviewTab c={c} />
          : tab === 'complaint' ? <ComplaintTab c={c} onChange={setC} reload={reload} />
            : <FollowupTab c={c} reload={reload} />}
      </Container>
    </>
  )
}
