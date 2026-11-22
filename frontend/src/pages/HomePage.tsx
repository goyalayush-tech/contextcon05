import { useEffect, useState } from 'react'
import { ArrowRight, BadgeCheck, FileSearch, FileText, Hand, ScanText, ShieldAlert, ShieldCheck } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, Container, Eyebrow } from '@/components/bits'
import CaseList from '@/components/CaseList'
import { api } from '@/lib/api'
import type { CaseSummary } from '@/lib/api'
import { Link } from '@/lib/router'

interface RulePack { id: string; title: string; revision: string; effective: string; verified: boolean; source_url: string | null }
interface Sample { key: string; title: string; case_type: string }
interface Fresh { airlines: { code: string; airline: string; grievance_status: string }[] }

const STEPS = [
  { icon: Hand, title: 'Tell us what happened', text: 'Cancelled, delayed, or a refund that went wrong. Add the flight details you have.' },
  { icon: ScanText, title: 'Add your documents', text: 'Upload the e-ticket or airline message. We read it, including scans, and you confirm each fact.' },
  { icon: FileSearch, title: 'Get your case packet', text: 'Every DGCA condition checked, the compensation formula, a timeline and what is still missing.' },
  { icon: FileText, title: 'You send the complaint', text: 'A draft addressed to the right officer. You approve it and submit it yourself. We never send anything.' },
]

const CHECKS = [
  { title: 'Flight cancelled', cite: 'CAR Part IV · 3.3', points: ['Notice windows (2 weeks / 24 hours)', 'Compensation: min(cap, basic fare + fuel)', 'Contact-details and extraordinary-circumstance exceptions'] },
  { title: 'Flight delayed', cite: 'CAR Part IV · 3.4', points: ['Meals by block time', 'Alternate flight or refund after 6 hours', 'Hotel for overnight and night-flight delays'] },
  { title: 'Refund problem', cite: 'CAR Part II', points: ['Refund deadline by payment mode', 'Statutory taxes and fees refunded', 'Charge cap and credit-shell consent'] },
]

export default function HomePage() {
  const [cases, setCases] = useState<CaseSummary[] | null>(null)
  const [packs, setPacks] = useState<RulePack[]>([])
  const [samples, setSamples] = useState<Sample[]>([])
  const [fresh, setFresh] = useState<Fresh | null>(null)

  useEffect(() => {
    api<CaseSummary[]>('/api/cases?limit=3').then(setCases).catch(() => setCases([]))
    api<RulePack[]>('/api/rules').then(setPacks).catch(() => {})
    api<Sample[]>('/api/samples').then(setSamples).catch(() => {})
    api<Fresh>('/api/freshness').then(setFresh).catch(() => {})
  }, [])

  const verifiedAirlines = fresh?.airlines.filter((a) => a.grievance_status === 'primary_verified').length

  return (
    <>
      <section className="border-b border-border bg-card">
        <Container className="grid gap-10 py-14 md:grid-cols-[1.3fr_1fr] md:items-center md:py-20">
          <div>
            <Badge variant="default" className="mb-5">For domestic flights in India</Badge>
            <h1 className="text-4xl leading-[1.05] md:text-6xl">Your flight went wrong. Your case, ready in minutes.</h1>
            <p className="mt-5 max-w-xl text-lg text-muted-foreground">
              FLIGHTBACK checks your facts against the DGCA rules, works out what the airline owes you, and drafts the complaint.
              You stay in control: nothing is sent without you.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Button asChild size="lg"><Link to="/new">Start a case <ArrowRight /></Link></Button>
              <Button asChild size="lg" variant="secondary"><Link to="/cases">My cases</Link></Button>
            </div>
          </div>
          <Card className="bg-background">
            <Eyebrow className="mb-4">What you get</Eyebrow>
            <ul className="space-y-3 text-sm">
              {['A condition-by-condition rights check with the paragraph it applies',
                'The compensation or refund shortfall, with its formula',
                'The airline’s escalation route, verified from its own website',
                'A complaint draft written from supported claims only'].map((t) => (
                <li key={t} className="flex gap-3"><BadgeCheck className="mt-0.5 size-4 shrink-0 text-primary" /> {t}</li>
              ))}
            </ul>
            {samples.length > 0 && (
              <div className="mt-6 border-t border-border pt-4">
                <div className="mb-2 text-xs font-semibold text-muted-foreground">No booking at hand? Try an example:</div>
                <div className="flex flex-col gap-1.5">
                  {samples.slice(0, 3).map((s) => (
                    <Link key={s.key} to={`/new?sample=${s.key}`} className="text-sm font-semibold text-primary hover:underline">{s.title} →</Link>
                  ))}
                </div>
              </div>
            )}
          </Card>
        </Container>
      </section>

      <Container>
        <section className="py-14 md:py-20">
          <Eyebrow className="mb-3 text-primary">How it works</Eyebrow>
          <h2 className="max-w-2xl text-3xl md:text-4xl">From a mess of messages to a complete case.</h2>
          <div className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
            {STEPS.map((s, i) => (
              <Card key={s.title}>
                <div className="flex items-center gap-3">
                  <span className="grid size-9 place-items-center rounded-md bg-accent text-accent-foreground"><s.icon className="size-4" /></span>
                  <span className="text-sm font-bold text-muted-foreground">Step {i + 1}</span>
                </div>
                <h3 className="mt-4 text-lg">{s.title}</h3>
                <p className="mt-2 text-sm text-muted-foreground">{s.text}</p>
              </Card>
            ))}
          </div>
        </section>

        <section className="pb-14 md:pb-20">
          <Eyebrow className="mb-3 text-primary">What we check</Eyebrow>
          <h2 className="max-w-2xl text-3xl md:text-4xl">The rules, applied exactly as written.</h2>
          <div className="mt-10 grid gap-5 md:grid-cols-3">
            {CHECKS.map((c) => (
              <Card key={c.title}>
                <div className="flex items-start justify-between gap-3">
                  <h3 className="text-lg">{c.title}</h3>
                  <span className="shrink-0 font-mono text-xs text-muted-foreground">{c.cite}</span>
                </div>
                <ul className="mt-4 space-y-2 text-sm text-muted-foreground">
                  {c.points.map((p) => <li key={p} className="flex gap-2"><span className="text-primary">•</span>{p}</li>)}
                </ul>
              </Card>
            ))}
          </div>
          <div className="mt-6 grid gap-4 md:grid-cols-3">
            {packs.map((p) => (
              <div key={p.id} className="flex items-start gap-3 rounded-lg border border-border bg-card p-4 text-sm">
                {p.verified ? <ShieldCheck className="mt-0.5 size-4 shrink-0 text-primary" /> : <ShieldAlert className="mt-0.5 size-4 shrink-0 text-destructive" />}
                <div>
                  <div className="font-semibold">{p.id.replace('DGCA-CAR-S3-M-', 'CAR Part ')} · {p.revision}</div>
                  <div className="text-muted-foreground">
                    {p.verified ? 'Verified against the official text' : 'Not yet verified against primary text: refund timing is flagged'} · effective {p.effective}
                  </div>
                </div>
              </div>
            ))}
            {fresh && (
              <Link to="/sources" className="flex items-start gap-3 rounded-lg border border-border bg-card p-4 text-sm hover:bg-secondary/60">
                <BadgeCheck className="mt-0.5 size-4 shrink-0 text-primary" />
                <div>
                  <div className="font-semibold">{verifiedAirlines} of {fresh.airlines.length} airline grievance routes verified</div>
                  <div className="text-muted-foreground">Read from each airline’s own page, dated and hashed →</div>
                </div>
              </Link>
            )}
          </div>
        </section>

        {cases && cases.length > 0 && (
          <section className="pb-6">
            <div className="mb-5 flex items-end justify-between gap-4">
              <h2 className="text-2xl md:text-3xl">Recent cases</h2>
              <Link to="/cases" className="text-sm font-semibold text-primary hover:underline">All cases →</Link>
            </div>
            <CaseList cases={cases} />
          </section>
        )}
      </Container>
    </>
  )
}
