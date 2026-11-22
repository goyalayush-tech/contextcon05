import { ChevronRight } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { KIND_LABEL, StatusTag, when } from '@/components/bits'
import { inr } from '@/lib/api'
import type { CaseSummary } from '@/lib/api'
import { caseRef } from '@/lib/model'
import { Link } from '@/lib/router'

function amount(c: CaseSummary) {
  if (c.payable_compensation != null && Number(c.payable_compensation) > 0) return { label: 'Compensation', value: inr(c.payable_compensation) }
  if (c.shortfall != null && Number(c.shortfall) > 0) return { label: 'Refund shortfall', value: inr(c.shortfall) }
  return null
}

export default function CaseList({ cases }: { cases: CaseSummary[] }) {
  return (
    <ul className="divide-y divide-border overflow-hidden rounded-lg border border-border bg-card">
      {cases.map((c) => {
        const a = amount(c)
        const route = [c.origin, c.destination].filter(Boolean).join(' → ')
        const supported = c.status_counts.SUPPORTED ?? 0
        return (
          <li key={c.case_id}>
            <Link to={`/case/${c.case_id}`} className="flex items-center gap-4 px-5 py-4 transition-colors hover:bg-secondary/60">
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-bold">{KIND_LABEL[c.case_type] ?? c.case_type}</span>
                  <span className="text-sm text-muted-foreground">
                    {[c.flight_number, route, c.date].filter(Boolean).join(' · ') || 'Flight details not given'}
                  </span>
                </div>
                <div className="mt-1.5 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                  <span className="font-mono">#{caseRef(c.case_id)}</span>
                  <span>· {when(c.created_at)}</span>
                  {supported > 0 && <StatusTag status="SUPPORTED" count={supported} />}
                  {c.approval === 'approved_by_passenger' ? <Badge variant="outline">Approved</Badge> : <Badge variant="secondary">Draft</Badge>}
                  {c.followups > 0 && <Badge variant="secondary">{c.followups} update{c.followups === 1 ? '' : 's'}</Badge>}
                </div>
              </div>
              {a && (
                <div className="hidden text-right sm:block">
                  <div className="text-xs text-muted-foreground">{a.label}</div>
                  <div className="font-bold">{a.value}</div>
                </div>
              )}
              <ChevronRight className="size-4 shrink-0 text-muted-foreground" />
            </Link>
          </li>
        )
      })}
    </ul>
  )
}
