import { useEffect, useRef, useState } from 'react'
import { ArrowLeft, ArrowRight, ClipboardPaste, FileUp, Loader2, Search, X } from 'lucide-react'
import { toast } from 'sonner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Callout, Card, CardTitle, selectCls } from '@/components/bits'
import { api, post } from '@/lib/api'
import type { SchemaField } from '@/lib/api'
import type { Facts } from '@/lib/model'
import { cn } from '@/lib/utils'

interface Candidate {
  type: string; value: string; suggested_field: string | null; snippet: string; note?: string
  // set for suggestions read from an uploaded document
  page?: number; method?: string; confidence?: number | null; low_confidence?: boolean; docName?: string; docSha?: string
}
interface DocPage { page: number; method: string; chars: number; confidence: number | null; note?: string | null; text: string }
interface DocResult {
  document: { name: string; type: string; pages: number; sha256: string; methods: string[] }
  pages: DocPage[]; candidates: Candidate[]; notes: string[]
}
interface Caps { ocr: boolean; max_bytes: number; detail: string | null }

const METHOD: Record<string, string> = { text_layer: 'text layer', ocr: 'OCR', unread: 'not read' }
const pct = (c: number | null | undefined) => (c == null ? '' : ` · ${Math.round(c)}% confidence`)
const label = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)
const MB = 1048576

export default function FactsStep(p: {
  fields: SchemaField[]; facts: Facts; setFact: (name: string, patch: Partial<Facts[string]>) => void
  busy: boolean; back: () => void; assess: () => void
}) {
  const [tab, setTab] = useState<'upload' | 'paste'>('upload')
  const [text, setText] = useState('')
  const [pasteName, setPasteName] = useState('airline message')
  const [cands, setCands] = useState<Candidate[]>([])
  const [notes, setNotes] = useState<string[]>([])
  const [target, setTarget] = useState<Record<number, string>>({})
  const [working, setWorking] = useState(false)
  const [docRead, setDocRead] = useState<DocResult | null>(null)
  const [caps, setCaps] = useState<Caps | null>(null)
  const [dragging, setDragging] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  useEffect(() => { api<Caps>('/api/documents/capabilities').then(setCaps).catch(() => setCaps(null)) }, [])

  const show = (c: Candidate[], n: string[]) => { setCands(c); setNotes(n); setTarget({}) }

  const upload = async (file: File) => {
    if (caps && file.size > caps.max_bytes) return toast.error(`${file.name} is larger than ${caps.max_bytes / MB} MB.`)
    setWorking(true)
    try {
      const fd = new FormData()
      fd.append('file', file)
      const r = await api<DocResult>('/api/documents', { method: 'POST', body: fd })
      setDocRead(r)
      show(r.candidates.map((c) => ({ ...c, docName: r.document.name, docSha: r.document.sha256 })), r.notes)
    } catch (e) { toast.error((e as Error).message) } finally {
      setWorking(false)
      if (fileRef.current) fileRef.current.value = ''  // allow re-uploading the same file
    }
  }

  const findInText = async () => {
    setWorking(true)
    try {
      const r = await post<{ candidates: Candidate[]; notes: string[] }>('/api/extract', { text })
      setDocRead(null)
      show(r.candidates.map((c) => ({ ...c, docName: pasteName || 'pasted text' })), r.notes)
    } catch (e) { toast.error((e as Error).message) } finally { setWorking(false) }
  }

  const use = (i: number) => {
    const c = cands[i]
    const name = target[i] ?? c.suggested_field ?? ''
    const f = p.fields.find((x) => x.name === name)
    if (!f) return toast.message('Choose which fact this is first.')
    const value = c.type === 'datetime' ? c.value.slice(0, 16) : c.type === 'bool' ? (String(c.value) === 'true' ? 'yes' : 'no') : c.value
    p.setFact(name, {
      value: String(value).replace(/,/g, ''), doc: c.docName ?? '', snippet: c.snippet.slice(0, 160),
      page: c.page, method: c.method, confidence: c.confidence ?? undefined, doc_sha256: c.docSha,
    })
    setCands(cands.filter((_, j) => j !== i))
    toast.success(`${label(f.label)} set${c.page ? ` from page ${c.page}` : ''}`)
  }

  const filled = p.fields.filter((f) => (p.facts[f.name]?.value ?? '') !== '').length

  return (
    <div className="space-y-6">
      <Card>
        <div className="mb-5 inline-flex rounded-md border border-border bg-secondary p-1 text-sm">
          {([['upload', 'Upload a document', FileUp], ['paste', 'Paste text', ClipboardPaste]] as const).map(([k, t, Icon]) => (
            <button key={k} onClick={() => setTab(k)}
              className={cn('flex items-center gap-2 rounded px-3 py-1.5 font-semibold', tab === k ? 'bg-card shadow-sm' : 'text-muted-foreground')}>
              <Icon className="size-4" /> {t}
            </button>
          ))}
        </div>

        {tab === 'upload' ? (
          <div
            onDragOver={(e) => { e.preventDefault(); setDragging(true) }} onDragLeave={() => setDragging(false)}
            onDrop={(e) => { e.preventDefault(); setDragging(false); const f = e.dataTransfer.files?.[0]; if (f) upload(f) }}
            className={cn('flex flex-col items-center justify-center rounded-lg border-2 border-dashed px-6 py-10 text-center transition-colors',
              dragging ? 'border-primary bg-accent/50' : 'border-input')}>
            <input ref={fileRef} type="file" accept="application/pdf,image/png,image/jpeg,.pdf,.png,.jpg,.jpeg" className="hidden"
              onChange={(e) => { const f = e.target.files?.[0]; if (f) upload(f) }} />
            {working ? <Loader2 className="size-7 animate-spin text-primary" /> : <FileUp className="size-7 text-muted-foreground" />}
            <div className="mt-3 font-semibold">{working ? 'Reading your document…' : 'Drop your e-ticket or airline message here'}</div>
            <div className="mt-1 text-sm text-muted-foreground">
              {caps == null ? 'PDF, PNG or JPEG.' : caps.ocr
                ? `PDF, PNG or JPEG up to ${caps.max_bytes / MB} MB. Scans and screenshots are read with OCR. The file is not stored.`
                : (caps.detail ?? 'Only PDFs with selectable text can be read on this server.')}
            </div>
            <Button className="mt-5" variant="secondary" disabled={working} onClick={() => fileRef.current?.click()}>Choose a file</Button>
          </div>
        ) : (
          <div className="grid gap-4 md:grid-cols-[1fr_16rem]">
            <Textarea rows={6} value={text} onChange={(e) => setText(e.target.value)}
              placeholder="Paste the SMS, email or e-ticket text, e.g. “Your flight 6E 123 on 20 Nov 2026 17:00 has been cancelled…”" />
            <div className="space-y-3">
              <div>
                <label className="mb-1.5 block text-sm font-semibold">Where is it from?</label>
                <Input value={pasteName} onChange={(e) => setPasteName(e.target.value)} placeholder="airline SMS" />
              </div>
              <Button className="w-full" variant="secondary" disabled={!text.trim() || working} onClick={findInText}>
                {working ? <Loader2 className="animate-spin" /> : <Search />} Find facts
              </Button>
            </div>
          </div>
        )}

        {docRead && (
          <div className="mt-5 rounded-md border border-border bg-background p-4 text-sm">
            <div className="flex flex-wrap items-center gap-2 font-semibold">
              {docRead.document.name}
              <span className="font-normal text-muted-foreground">
                · {docRead.document.pages} page{docRead.document.pages === 1 ? '' : 's'} · SHA-256 {docRead.document.sha256.slice(0, 12)}
              </span>
            </div>
            {docRead.pages.map((pg) => (
              <details key={pg.page} className="mt-2">
                <summary className="cursor-pointer text-muted-foreground">
                  Page {pg.page}: {METHOD[pg.method] ?? pg.method}{pct(pg.confidence)}{pg.note ? ` · ${pg.note}` : ''}
                </summary>
                <pre className="mt-2 max-h-56 overflow-auto rounded border border-border bg-card p-3 font-mono text-xs whitespace-pre-wrap">{pg.text || '(no text)'}</pre>
              </details>
            ))}
          </div>
        )}

        {(cands.length > 0 || notes.length > 0) && (
          <div className="mt-5">
            <div className="mb-2 flex items-center justify-between">
              <div className="text-sm font-bold">Suggested facts <span className="font-normal text-muted-foreground">· confirm each one</span></div>
              {cands.length > 0 && <button onClick={() => show([], [])} className="text-muted-foreground hover:text-foreground" aria-label="Dismiss"><X className="size-4" /></button>}
            </div>
            <div className="divide-y divide-border rounded-md border border-border">
              {cands.map((c, i) => (
                <div key={i} className="flex flex-col gap-3 p-3.5 md:flex-row md:items-center">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-mono text-sm font-bold">{String(c.value)}</span>
                      {c.page != null && <Badge variant={c.low_confidence ? 'solid' : 'secondary'}>Page {c.page} · {METHOD[c.method ?? ''] ?? c.method}{pct(c.confidence)}</Badge>}
                    </div>
                    <div className="mt-0.5 truncate text-sm text-muted-foreground">“{c.snippet}”</div>
                    {c.low_confidence && <div className="text-xs font-semibold text-destructive">Low OCR confidence: check this value against the document.</div>}
                    {c.note && <div className="text-xs text-muted-foreground">{c.note}</div>}
                  </div>
                  <select className={selectCls + ' md:w-60'} value={target[i] ?? c.suggested_field ?? ''} onChange={(e) => setTarget({ ...target, [i]: e.target.value })}>
                    <option value="">Which fact is this?</option>
                    {p.fields.map((f) => <option key={f.name} value={f.name}>{label(f.label)}</option>)}
                  </select>
                  <Button size="sm" onClick={() => use(i)}>Use this</Button>
                </div>
              ))}
              {notes.map((n, i) => <div key={`n${i}`} className="p-3.5 text-sm text-muted-foreground">{n}</div>)}
            </div>
          </div>
        )}
      </Card>

      <Card>
        <CardTitle aside={<span className="text-sm text-muted-foreground">{filled} of {p.fields.length} filled · times are India time</span>}>Facts</CardTitle>
        <div className="divide-y divide-border">
          {p.fields.map((f) => {
            const fact = p.facts[f.name] ?? { value: '', doc: '', snippet: '' }
            const set = (v: string) => p.setFact(f.name, { value: v })
            return (
              <div key={f.name} className="grid gap-3 py-4 md:grid-cols-[1fr_1fr_1.1fr] md:items-start">
                <div>
                  <div className="font-semibold">{label(f.label)}</div>
                  {f.hint && <div className="text-xs text-muted-foreground">{f.hint}</div>}
                </div>
                <div>
                  {f.type === 'bool' ? (
                    <select className={selectCls} value={fact.value} onChange={(e) => set(e.target.value)}>
                      <option value="">Don’t know</option><option value="yes">Yes</option><option value="no">No</option>
                    </select>
                  ) : f.type === 'enum' ? (
                    <select className={selectCls} value={fact.value} onChange={(e) => set(e.target.value)}>
                      <option value="">Don’t know</option>{(f.options ?? []).map((o) => <option key={o} value={o}>{o.replace(/_/g, ' ')}</option>)}
                    </select>
                  ) : (
                    <Input type={f.type === 'datetime' ? 'datetime-local' : f.type === 'date' ? 'date' : f.type === 'number' ? 'number' : 'text'}
                      step={f.type === 'number' ? 'any' : undefined} value={fact.value} onChange={(e) => set(e.target.value)} />
                  )}
                </div>
                <div>
                  <Input placeholder={fact.value === '' ? 'Source (once a value is set)' : 'Source document'} value={fact.doc} disabled={fact.value === ''}
                    onChange={(e) => p.setFact(f.name, { doc: e.target.value, page: undefined, method: undefined, confidence: undefined, doc_sha256: undefined })} />
                  {fact.snippet && <div className="mt-1 truncate text-xs text-muted-foreground">“{fact.snippet}”</div>}
                  {fact.page != null && <div className="text-xs text-muted-foreground">Page {fact.page} · {METHOD[fact.method ?? ''] ?? fact.method}{pct(fact.confidence)}</div>}
                </div>
              </div>
            )
          })}
        </div>
      </Card>

      {filled === 0 && <Callout>You can assess with no facts, but every condition will come back as unknown. Add what you have first.</Callout>}
      <div className="flex justify-between gap-4">
        <Button variant="secondary" size="lg" onClick={p.back}><ArrowLeft /> Back</Button>
        <Button size="lg" disabled={p.busy} onClick={p.assess}>{p.busy ? <><Loader2 className="animate-spin" /> Checking your case…</> : <>Check my case <ArrowRight /></>}</Button>
      </div>
    </div>
  )
}
