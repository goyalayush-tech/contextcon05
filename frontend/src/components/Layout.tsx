import type { ReactNode } from 'react'
import { Plane, Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Container } from '@/components/bits'
import { Link } from '@/lib/router'
import { cn } from '@/lib/utils'

const NAV = [
  { to: '/cases', label: 'My cases', match: (p: string) => p === '/cases' || p.startsWith('/case/') },
  { to: '/sources', label: 'Sources', match: (p: string) => p === '/sources' },
]

export default function Layout({ path, children }: { path: string; children: ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-30 border-b border-border bg-background/90 backdrop-blur">
        <Container className="flex h-16 items-center justify-between gap-2">
          <Link to="/" className="flex shrink-0 items-center gap-2 text-base font-extrabold tracking-tight sm:text-lg">
            <span className="grid size-8 place-items-center rounded-md bg-primary text-primary-foreground"><Plane className="size-4" /></span>
            <span className="hidden min-[420px]:inline">FLIGHTBACK</span>
          </Link>
          <nav className="flex items-center gap-0.5 sm:gap-2">
            {NAV.map((n) => (
              <Link key={n.to} to={n.to}
                className={cn('rounded-md px-2 py-2 text-sm font-semibold whitespace-nowrap transition-colors sm:px-3',
                  n.match(path) ? 'bg-secondary text-foreground' : 'text-muted-foreground hover:text-foreground')}>
                {n.label}
              </Link>
            ))}
            <Button asChild size="sm" className="ml-1 px-2.5 sm:ml-2 sm:px-3">
              <Link to="/new" aria-label="Start a case"><Plus /> <span className="hidden sm:inline">Start a case</span></Link>
            </Button>
          </nav>
        </Container>
      </header>

      <main className="flex-1 pb-20">{children}</main>

      <footer className="border-t border-border bg-card">
        <Container className="grid gap-8 py-10 text-sm md:grid-cols-[1.4fr_1fr_1fr]">
          <div>
            <div className="flex items-center gap-2 font-extrabold"><Plane className="size-4 text-primary" /> FLIGHTBACK</div>
            <p className="mt-2 max-w-sm text-muted-foreground">
              Passenger-rights case packets for Indian domestic flights, checked against the DGCA Civil Aviation Requirements.
              Not legal advice.
            </p>
          </div>
          <div className="space-y-2">
            <div className="font-bold">Product</div>
            <Link to="/new" className="block text-muted-foreground hover:text-foreground">Start a case</Link>
            <Link to="/cases" className="block text-muted-foreground hover:text-foreground">My cases</Link>
            <Link to="/sources" className="block text-muted-foreground hover:text-foreground">Sources and freshness</Link>
          </div>
          <div className="space-y-2">
            <div className="font-bold">Promises</div>
            <p className="text-muted-foreground">Nothing is ever sent for you.</p>
            <p className="text-muted-foreground">The rights check is deterministic.</p>
            <p className="text-muted-foreground">News is a lead, never proof.</p>
          </div>
        </Container>
      </footer>
    </div>
  )
}
