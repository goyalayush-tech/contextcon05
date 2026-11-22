import { useEffect, useRef, useState } from 'react'
import { ArrowLeft, ArrowRight, FileUp, Search } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Kicker, Pane, selectCls } from '@/components/bits'
import { api, post } from '@/lib/api'
import type { SchemaField } from '@/lib/api'
import type { Facts } from '@/lib/model'

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
interface Caps { ocr: boolean; scanned_pdf: boolean; max_bytes: number; detail: string | null }
const METHOD: Record<string, string> = { text_layer: 'text layer', ocr: 'OCR', unread: 'not read' }
const pct = (c: number | null | undefined) => (c == null ? '' : ` · ${Math.round(c)}% confidence`)
const label = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)

export default function FactsScreen(p: {
  fields: SchemaField[]; facts: Facts; setFact: (name: string, patch: Partial<Facts[string]>) => void
  kind: string; busy: boolean; back: () => void; assess: () => void
}) {
  const [doc, setDoc] = useState('airline-sms.png')
  const [text, setText] = useState('')
  const [cands, setCands] = useState<Candidate[]>([])
  const [notes, setNotes] = useState<string[]>([])
  const [target, setTarget] = useState<Record<number, string>>({})
  const [finding, setFinding] = useState(false)
  const [reading, setReading] = useState(false)
  const [docRead, setDocRead] = useState<DocResult | null>(null)
  const [caps, setCaps] = useState<Caps | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  useEffect(() => { api<Caps>('/api/documents/capabilities').then(setCaps).catch(() => setCaps(null)) }, [])

  const upload = async (file: File) => {
    if (caps && file.size > caps.max_bytes) return toast.error(`${file.name} is larger than ${caps.max_bytes / 1048576} MB.`)
    setReading(true)
    try {
      const fd = new FormData()
      fd.append('file', file)
      const r = await api<DocResult>('/api/documents', { method: 'POST', body: fd })
      setDocRead(r); setDoc(r.document.name); setTarget({}); setNotes(r.notes)
      setCands(r.candidates.map((c) => ({ ...c, docName: r.document.name, docSha: r.document.sha256 })))
      toast.success(`Read ${r.document.name}: ${r.candidates.length} possible fact${r.candidates.length === 1 ? '' : 's'}`)
    } catch (e) { toast.error((e as Error).message) } finally {
      setReading(false)
      if (fileRef.current) fileRef.current.value = ''  // allow re-uploading the same file
    }
  }

  const find = async () => {
    setFinding(true)
    try {
      const r = await post<{ candidates: Candidate[]; notes: string[] }>('/api/extract', { text, case_type: p.kind })
      setCands(r.candidates); setNotes(r.notes); setTarget({}); setDocRead(null)
    } catch (e) { toast.error((e as Error).message) } finally { setFinding(false) }
  }

  const use = (i: number) => {
    const c = cands[i]
    const name = target[i] ?? c.suggested_field ?? ''
    if (!name) return toast.message('Choose which fact this is first.')
    const f = p.fields.find((x) => x.name === name)
    if (!f) return
    const value = c.type === 'datetime' ? c.value.slice(0, 16) : c.value
    const from = c.docName ?? doc
    p.setFact(name, {
      value: String(value).replace(/,/g, ''), doc: from, snippet: c.snippet.slice(0, 120),
      page: c.page, method: c.method, confidence: c.confidence ?? undefined, doc_sha256: c.docSha,
    })
    setCands(cands.filter((_, j) => j !== i))
    toast.success(`${label(f.label)} set from ${from || 'your text'}${c.page ? `, page ${c.page}` : ''}`)
  }

  return (
    <div>
      <Pane className="border-b-2 border-divider">
        <Kicker className="mb-3 text-primary">2 · Facts with sources</Kicker>
        <h1 className="text-4xl md:text-6xl">Paste what the airline sent.</h1>
        <p className="mt-3 text-muted-foreground">Upload the e-ticket or airline message, or paste its text. We suggest facts. You confirm each one.</p>
        <div className="mt-8 flex flex-col gap-3 border-2 border-foreground p-4 md:flex-row md:items-center">
          <input ref={fileRef} type="file" accept="application/pdf,image/png,image/jpeg,.pdf,.png,.jpg,.jpeg" className="hidden"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) upload(f) }} />
          <Button disabled={reading} onClick={() => fileRef.current?.click()}><FileUp /> {reading ? 'Reading document…' : 'Upload PDF or image'}</Button>
          <div className="text-sm text-muted-foreground">
            {caps == null ? 'PDF, PNG or JPEG.' : caps.ocr
              ? `PDF, PNG or JPEG up to ${caps.max_bytes / 1048576} MB. Scans and photos are read with OCR. The file is not stored.`
              : (caps.detail ?? 'Only PDFs with selectable text can be read on this server.')}
          </div>
        </div>
        {docRead && (
          <div className="mt-3 border-2 border-t-0 border-foreground p-4 text-sm">
            <div className="font-mono text-xs font-bold tracking-wider">
              {docRead.document.name} · {docRead.document.pages} page{docRead.document.pages === 1 ? '' : 's'} · SHA-256 {docRead.document.sha256.slice(0, 12)}
            </div>
            {docRead.pages.map((pg) => (
              <details key={pg.page} className="mt-2">
                <summary className="cursor-pointer text-muted-foreground">
                  Page {pg.page}: {METHOD[pg.method] ?? pg.method}{pct(pg.confidence)}{pg.note ? ` · ${pg.note}` : ''}
                </summary>
                <pre className="mt-2 max-h-56 overflow-auto whitespace-pre-wrap border border-border p-2 font-mono text-xs">{pg.text || '(no text)'}</pre>
              </details>
            ))}
          </div>
        )}
        <div className="mt-8 grid gap-5 md:grid-cols-[1fr_1.4fr]">
          <div className="space-y-4">
            <div>
              <label className="mb-1.5 block text-xs text-foreground/70">Document name</label>
              <Input value={doc} onChange={(e) => setDoc(e.target.value)} />
            </div>
            <Button variant="outline" disabled={!text.trim() || finding} onClick={find}><Search /> {finding ? 'Reading…' : 'Find facts'}</Button>
          </div>
          <div>
            <label className="mb-1.5 block text-xs text-foreground/70">Text</label>
            <Textarea rows={5} value={text} onChange={(e) => setText(e.target.value)} placeholder="Your flight 6E 000 is cancelled. Sorry for the inconvenience." />
          </div>
        </div>
        {(cands.length > 0 || notes.length > 0) && (
          <div className="mt-6 border-2 border-foreground">
            {cands.map((c, i) => (
              <div key={i} className="flex flex-col gap-3 border-b-2 border-foreground p-4 md:flex-row md:items-center">
                <div className="min-w-0 flex-1">
                  <div className="font-mono text-xs font-bold tracking-wider">{c.value} <span className="text-muted-foreground">{c.type.toUpperCase()}</span></div>
                  <div className="truncate text-sm text-muted-foreground">“{c.snippet}”</div>
                  {c.page != null && (
                    <div className={'text-xs ' + (c.low_confidence ? 'font-bold text-destructive' : 'text-muted-foreground')}>
                      Page {c.page} · {METHOD[c.method ?? ''] ?? c.method}{pct(c.confidence)}{c.low_confidence ? ' · check this value against the document' : ''}
                    </div>
                  )}
                  {c.note && <div className="text-xs text-muted-foreground">{c.note}</div>}
                </div>
                <select className={selectCls + ' md:w-56'} value={target[i] ?? c.suggested_field ?? ''} onChange={(e) => setTarget({ ...target, [i]: e.target.value })}>
                  <option value="">Which fact is this?</option>
                  {p.fields.map((f) => <option key={f.name} value={f.name}>{label(f.label)}</option>)}
                </select>
                <Button size="sm" onClick={() => use(i)}>Use this</Button>
              </div>
            ))}
            {notes.map((n, i) => <div key={i} className="p-4 text-sm text-muted-foreground">{n}</div>)}
          </div>
        )}
      </Pane>

      <Pane>
        <Kicker className="mb-1">Facts · Times are India time</Kicker>
        <div className="divide-y divide-border">
          {p.fields.map((f) => {
            const fact = p.facts[f.name] ?? { value: '', doc: '', snippet: '' }
            const set = (v: string) => p.setFact(f.name, { value: v })
            return (
              <div key={f.name} className="grid gap-3 py-4 md:grid-cols-[1fr_1.1fr_1.2fr] md:items-start">
                <div>
                  <div className="font-extrabold">{label(f.label)}</div>
                  {f.hint && <div className="text-xs text-muted-foreground">{f.hint}</div>}
                </div>
                <div>
                  {f.type === 'bool' ? (
                    <select className={selectCls} value={fact.value} onChange={(e) => set(e.target.value)}>
                      <option value="">Don’t know</option><option value="yes">Yes</option><option value="no">No</option>
                    </select>
                  ) : f.type === 'enum' ? (
                    <select className={selectCls} value={fact.value} onChange={(e) => set(e.target.value)}>
                      <option value="">Don’t know</option>{(f.options ?? []).map((o) => <option key={o} value={o}>{o}</option>)}
                    </select>
                  ) : (
                    <Input type={f.type === 'datetime' ? 'datetime-local' : f.type === 'date' ? 'date' : f.type === 'number' ? 'number' : 'text'}
                      step={f.type === 'number' ? 'any' : undefined} value={fact.value} onChange={(e) => set(e.target.value)} />
                  )}
                  {fact.value === '' && <div className="mt-1 text-xs text-muted-foreground">Will be listed as missing</div>}
                </div>
                <div>
                  <Input placeholder="Source document" value={fact.doc} disabled={fact.value === ''} onChange={(e) => p.setFact(f.name, { doc: e.target.value, page: undefined, method: undefined, confidence: undefined, doc_sha256: undefined })} />
                  {fact.snippet && <div className="mt-1 truncate text-xs text-muted-foreground">“{fact.snippet}”</div>}
                  {fact.page != null && <div className="text-xs text-muted-foreground">Page {fact.page} · {METHOD[fact.method ?? ''] ?? fact.method}{pct(fact.confidence)}</div>}
                </div>
              </div>
            )
          })}
        </div>
        <div className="mt-8 flex justify-between gap-4">
          <Button variant="secondary" size="lg" onClick={p.back}><ArrowLeft /> Back</Button>
          <Button size="lg" disabled={p.busy} onClick={p.assess}>{p.busy ? 'Assessing…' : 'Assess my case'} <ArrowRight /></Button>
        </div>
      </Pane>
    </div>
  )
}
