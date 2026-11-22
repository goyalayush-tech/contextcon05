import { useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Container, Empty } from '@/components/bits'
import Layout from '@/components/Layout'
import { Link, usePath } from '@/lib/router'
import HomePage from '@/pages/HomePage'
import NewCasePage from '@/pages/NewCasePage'
import CasesPage from '@/pages/CasesPage'
import CasePage, { type CaseTab } from '@/pages/CasePage'
import SourcesPage from '@/pages/SourcesPage'

const TITLES: [RegExp, string][] = [
  [/^\/$/, 'FLIGHTBACK · Flight disruption case packets'],
  [/^\/new$/, 'Start a case · FLIGHTBACK'],
  [/^\/cases$/, 'My cases · FLIGHTBACK'],
  [/^\/case\//, 'Case · FLIGHTBACK'],
  [/^\/sources$/, 'Sources · FLIGHTBACK'],
]

function route(path: string) {
  if (path === '/') return <HomePage />
  if (path === '/new') return <NewCasePage />
  if (path === '/cases') return <CasesPage />
  if (path === '/sources') return <SourcesPage />
  const m = path.match(/^\/case\/([^/]+)(?:\/(complaint|followup))?\/?$/)
  if (m) return <CasePage key={m[1]} id={decodeURIComponent(m[1])} tab={(m[2] as CaseTab) ?? 'overview'} />
  return (
    <Container className="pt-14">
      <Empty title="Page not found">
        There is nothing at {path}.
        <div className="mt-5"><Button asChild><Link to="/">Go home</Link></Button></div>
      </Empty>
    </Container>
  )
}

export default function App() {
  const path = usePath()
  useEffect(() => { document.title = TITLES.find(([re]) => re.test(path))?.[1] ?? 'FLIGHTBACK' }, [path])
  return <Layout path={path}>{route(path)}</Layout>
}
