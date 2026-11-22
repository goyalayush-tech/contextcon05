import type { ReactNode } from 'react'
import { AlertTriangle, Loader2 } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

/** Page-width wrapper used by every page. */
export function Container({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn('mx-auto w-full max-w-6xl px-5 md:px-8', className)}>{children}</div>
}

/** Small uppercase label above a heading or a group. */
export function Eyebrow({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn('text-xs font-bold tracking-[0.12em] text-muted-foreground uppercase', className)}>{children}</div>
}

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn('rounded-lg border border-border bg-card p-5 md:p-6', className)}>{children}</div>
}

export function CardTitle({ children, aside, className }: { children: ReactNode; aside?: ReactNode; className?: string }) {
  return (
    <div className={cn('mb-4 flex flex-wrap items-center justify-between gap-2', className)}>
      <h3 className="text-base font-bold tracking-tight">{children}</h3>
      {aside}
    </div>
  )
}

export function PageHeader({ eyebrow, title, lead, actions }: { eyebrow?: ReactNode; title: ReactNode; lead?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="flex flex-col gap-5 pt-10 pb-8 md:flex-row md:items-end md:justify-between md:pt-14">
      <div className="max-w-2xl">
        {eyebrow && <Eyebrow className="mb-3 text-primary">{eyebrow}</Eyebrow>}
        <h1 className="text-3xl md:text-5xl">{title}</h1>
        {lead && <p className="mt-3 text-base text-muted-foreground md:text-lg">{lead}</p>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap gap-3">{actions}</div>}
    </div>
  )
}

const STATUS: Record<string, { label: string; variant: 'default' | 'secondary' | 'outline' | 'solid' | 'destructive' }> = {
  SUPPORTED: { label: 'Supported', variant: 'default' },
  UNKNOWN: { label: 'Unknown', variant: 'secondary' },
  NOT_APPLICABLE: { label: 'N/A', variant: 'outline' },
  NOT_SUPPORTED: { label: 'Not supported', variant: 'destructive' },
  REVIEW_REQUIRED: { label: 'Needs review', variant: 'solid' },
}

export function StatusTag({ status, count }: { status: string; count?: number }) {
  const s = STATUS[status] ?? { label: status, variant: 'secondary' as const }
  return (
    <Badge variant={s.variant}>
      {s.label}
      {count != null && ` · ${count}`}
    </Badge>
  )
}

export function Field({ label, hint, children }: { label: string; hint?: string | null; children: ReactNode }) {
  return (
    <div>
      <label className="mb-1.5 block text-sm font-semibold">{label}</label>
      {hint && <div className="mb-1.5 text-xs text-muted-foreground">{hint}</div>}
      {children}
    </div>
  )
}

export function Callout({ children, tone = 'info', className }: { children: ReactNode; tone?: 'info' | 'warn'; className?: string }) {
  return (
    <div className={cn('flex gap-3 rounded-md border p-3.5 text-sm',
      tone === 'warn' ? 'border-primary/30 bg-accent text-accent-foreground' : 'border-border bg-secondary text-foreground', className)}>
      {tone === 'warn' && <AlertTriangle className="mt-0.5 size-4 shrink-0" />}
      <div>{children}</div>
    </div>
  )
}

export function Loading({ label = 'Loading…' }: { label?: string }) {
  return <div className="flex items-center gap-2 py-16 text-sm text-muted-foreground"><Loader2 className="size-4 animate-spin" /> {label}</div>
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed border-input px-6 py-12 text-center">
      <div className="font-bold">{title}</div>
      {children && <div className="mt-2 text-sm text-muted-foreground">{children}</div>}
    </div>
  )
}

/** Native select styled like Input (Radix Select cannot hold an empty value, and "Don't know" is one). */
export const selectCls =
  'h-10 w-full rounded-md border border-input bg-card px-3 text-sm outline-none focus-visible:border-primary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary/40'

export const when = (ts: number) =>
  new Date(ts > 1e12 ? ts : ts * 1000).toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })

export function fmtDT(v: unknown): string {
  if (typeof v !== 'string') return String(v)
  const d = new Date(v)
  return isNaN(+d) ? v : d.toLocaleString('en-IN', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'Asia/Kolkata' })
}

export const KIND_LABEL: Record<string, string> = { cancellation: 'Cancellation', delay: 'Delay', refund: 'Refund' }
