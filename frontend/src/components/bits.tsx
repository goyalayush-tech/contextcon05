import type { ReactNode } from 'react'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

/** The mono, tracked section label used all over the Modernist screens. */
export function Kicker({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn('font-mono text-xs font-bold tracking-[0.08em] uppercase', className)}>{children}</div>
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
      {count != null && ` ×${count}`}
    </Badge>
  )
}

export function Field({ label, hint, children }: { label: string; hint?: string | null; children: ReactNode }) {
  return (
    <div>
      <label className="mb-1.5 block text-xs text-foreground/70">{label}</label>
      {hint && <div className="mb-1 text-xs text-muted-foreground">{hint}</div>}
      {children}
    </div>
  )
}

/** A full-width bordered region of the screen, with the 2px Modernist rules between regions. */
export function Pane({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn('p-6 md:p-12', className)}>{children}</div>
}

/** Native select styled like the Input primitive (Radix Select cannot hold an empty value, and "Don't know" is one). */
export const selectCls =
  'h-10 w-full border border-input bg-transparent px-3 text-sm outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary'

export const when = (ts: number) => new Date(ts > 1e12 ? ts : ts * 1000).toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })

export function fmtDT(v: unknown): string {
  if (typeof v !== 'string') return String(v)
  const d = new Date(v)
  return isNaN(+d) ? v : d.toLocaleString('en-IN', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'Asia/Kolkata' })
}
