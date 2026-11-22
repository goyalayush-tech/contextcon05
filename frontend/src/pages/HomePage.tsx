import { useEffect, useState } from 'react'
import { ArrowRight, ArrowUpRight, BadgeCheck, FileSearch, FileText, Hand, Plane, ScanText, ShieldAlert, ShieldCheck } from 'lucide-react'
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
      <section className="home-hero">
        <Container className="grid gap-5 py-12 md:grid-cols-[.96fr_1.04fr] md:items-center md:gap-10 md:py-16">
          <div className="home-hero-copy">
            <Badge variant="default" className="home-hero-badge mb-5">For domestic flights in India</Badge>
            <h1 className="text-4xl md:text-6xl">Your flight changed.<br /><span>Let’s find your way forward.</span></h1>
            <p className="mt-5 max-w-xl text-base text-muted-foreground md:text-lg">
              See which passenger rights may apply, what facts are still missing, and how to prepare a complaint—without guesswork or payout promises.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Button asChild size="lg" className="home-hero-cta"><Link to="/new">Check my case <ArrowRight /></Link></Button>
              <Button asChild size="lg" variant="secondary"><Link to="/cases">My cases</Link></Button>
            </div>
            <div className="home-hero-trust mt-5">
              <span><ShieldCheck /> Rules with sources</span><i aria-hidden="true" /><span>Nothing is sent for you</span>
            </div>
            {samples.length > 0 && (
              <div className="mt-6">
                <div className="mb-2 text-xs font-semibold text-muted-foreground">Want to see a worked example?</div>
                <div className="flex flex-col items-start gap-1.5">
                  {samples.slice(0, 2).map((s) => (
                    <Link key={s.key} to={`/new?sample=${s.key}`} className="text-sm font-semibold text-primary hover:underline">{s.title} →</Link>
                  ))}
                </div>
                <span className="mt-1 block text-[11px] text-muted-foreground">Synthetic examples only · no real passenger data</span>
              </div>
            )}
          </div>

          <div className="home-hero-art" role="img" aria-label="A flight path through a sunset sky, leading to a clear case packet">
            <div className="home-window-sky">
              <div className="home-sun" />
              <div className="home-cloud home-cloud-a" />
              <div className="home-cloud home-cloud-b" />
              <div className="home-route-caption home-route-start"><span>WHEN PLANS CHANGE</span><b>Start with your facts</b></div>
              <div className="home-route-caption home-route-end"><span>YOUR NEXT STEP</span><b>Clear, cited, yours</b></div>
              <svg className="home-flight-path" viewBox="0 0 520 230" fill="none" aria-hidden="true">
                <path d="M24 194C126 34 248 47 319 125s126 86 177 6" stroke="rgba(255,255,255,.72)" strokeWidth="2" strokeDasharray="5 9" />
                <circle cx="25" cy="193" r="5" fill="white" />
                <circle cx="496" cy="131" r="5" fill="white" />
                <path d="m253 53 24-8 22-20 8 2-13 22 22 7-2 5-28-3-15 17-5-1 6-20-20 5z" fill="white" />
              </svg>
            </div>
            <div className="home-window-rim" aria-hidden="true" />
            <div className="home-window-card">
              <div className="home-window-card-head">
                <span className="home-window-card-icon"><BadgeCheck /></span>
                <span><small>YOUR CASE PACKET</small><b>A clearer way forward</b></span>
                <ArrowUpRight className="home-window-card-arrow" />
              </div>
              <div className="home-window-checks">
                <span><BadgeCheck /> Rule-by-rule check</span>
                <span><FileText /> Draft for you to review</span>
              </div>
              <div className="home-window-note"><Plane /> You choose what happens next. Nothing is auto-submitted.</div>
            </div>
            <div className="home-window-seal"><span>NO</span><b>PAYOUT<br />PROMISES</b></div>
          </div>
        </Container>
      </section>

      <Container>
        <section id="how-it-works" className="py-14 md:py-20">
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
