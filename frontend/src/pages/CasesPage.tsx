import { useEffect, useState } from 'react'
import { Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Container, Empty, Loading, PageHeader } from '@/components/bits'
import CaseList from '@/components/CaseList'
import { api } from '@/lib/api'
import type { CaseSummary } from '@/lib/api'
import { Link } from '@/lib/router'

export default function CasesPage() {
  const [cases, setCases] = useState<CaseSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => { api<CaseSummary[]>('/api/cases?limit=100').then(setCases).catch((e) => setError(e.message)) }, [])

  return (
    <Container>
      <PageHeader eyebrow="Cases" title="My cases" lead="Every case you have checked on this server, newest first."
        actions={<Button asChild><Link to="/new"><Plus /> Start a case</Link></Button>} />
      {error ? <Empty title="Could not load cases">{error}</Empty>
        : !cases ? <Loading />
          : cases.length === 0 ? (
            <Empty title="No cases yet">
              Start one from your e-ticket or the airline’s message. It takes a few minutes.
              <div className="mt-5"><Button asChild><Link to="/new">Start a case</Link></Button></div>
            </Empty>
          ) : <CaseList cases={cases} />}
    </Container>
  )
}
