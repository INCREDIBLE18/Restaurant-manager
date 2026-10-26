import { useRef, useState } from 'react'
import { api, fmt, fmtDate, getToken, num, todayIso } from '../api'
import { Badge, ErrorBox, Field, Notice, useAsync, useSubmit } from '../ui'
import type { User } from '../App'

function ImportReview({ id, user, items, onClose }: { id: number; user: User; items: any[]; onClose: () => void }) {
  const { data: b, error, reload, setData } = useAsync(() => api(`/imports/${id}`), [id])
  const { error: e2, busy, submit } = useSubmit()
  const [ack, setAck] = useState(false)
  const [override, setOverride] = useState(false)
  const [reason, setReason] = useState('')
  const [showAll, setShowAll] = useState(false)
  if (!b) return <ErrorBox msg={error} />
  const draft = b.status === 'draft'
  const s = b.summary
  const patch = (rid: number, body: any) => submit(async () => { await api(`/imports/${id}/rows/${rid}`, { method: 'PATCH', body }); await reload() })
  const openFile = async () => {
    const res = await fetch(`/api/v1/imports/${id}/file`, { headers: { Authorization: `Bearer ${getToken()}` } })
    window.open(URL.createObjectURL(await res.blob()), '_blank')
  }
  const isSales = b.report_type === 'item_sales'
  const rows = b.rows.filter((r: any) => showAll || r.match_status !== 'structural')
  return (
    <div className="card">
      <div className="row between"><h2 style={{ margin: 0 }}>Review import #{b.id}: {b.filename} <Badge status={b.status} /></h2><button className="btn ghost" onClick={onClose}>Back to list</button></div>
      <ErrorBox msg={e2 || error} />
      {b.warnings.map((w: string, i: number) => <Notice key={i} kind={w.startsWith('DUPLICATE') ? 'error' as any : 'warn'} msg={w} />)}
      {!isSales && <Notice msg="Stock Position import: ONLY item names and UOM labels are used to build a pending catalogue. Every quantity and value in that report (Open, Purchase, Issued, Closing, values) is ignored and never stored." />}
      <dl className="kv">
        <dt>Report type</dt><dd>{b.report_type.replace('_', ' ')} · read by <b>{b.extraction_method}</b>{b.extraction_method === 'local_ocr' && ' (OCR can misread digits and letters — check every flagged row)'}</dd>
        <dt>Outlet / print info</dt><dd>{b.outlet_name} {b.print_info && `· printed ${b.print_info}`}</dd>
        <dt>Report (business) date</dt><dd>{draft ? <input type="date" value={b.report_date || ''} onChange={e => submit(async () => setData(await api(`/imports/${id}`, { method: 'PATCH', body: { report_date: e.target.value } })))} /> : fmtDate(b.report_date)}
          {isSales && !b.report_date && <span className="neg"> required</span>}</dd>
        <dt>Original file</dt><dd><button className="btn small ghost" onClick={openFile}>Open original</button></dd>
      </dl>
      <div className="grid" style={{ marginTop: 10 }}>
        <div className="card stat"><div className="stat-title">Rows</div><div>{s.item_rows} item rows · {s.accepted_rows} accepted · {s.excluded_structural} structural/excluded</div></div>
        {isSales && <div className="card stat"><div className="stat-title">Accepted totals</div><div>Qty <b>{s.accepted_qty}</b> · Amount <b>{fmt(s.accepted_amount)}</b></div>
          <div className="stat-sub">Printed grand total: {s.printed_qty ?? '—'} / {s.printed_total != null ? fmt(s.printed_total) : '—'}</div></div>}
        {isSales && s.printed_total != null && <div className={`card stat ${num(s.amount_variance) || num(s.qty_variance) ? 'warn' : 'good'}`}><div className="stat-title">Reconciliation with printed total</div>
          <div>Amount diff <b>{fmt(s.amount_variance)}</b> · Qty diff <b>{s.qty_variance}</b></div></div>}
        <div className={`card stat ${s.unresolved ? 'bad' : ''}`}><div className="stat-title">Unresolved / flagged</div><div>{s.unresolved} unmapped · {s.needs_review} need review</div></div>
      </div>
      {draft && isSales && s.unresolved > 0 && <div className="row">
        <button className="btn secondary" disabled={busy} onClick={() => submit(async () => { setData(await api(`/imports/${id}/bulk`, { body: { action: 'use_suggestions' } })) })}>Use all suggested matches</button>
        <button className="btn secondary" disabled={busy} onClick={() => submit(async () => { setData(await api(`/imports/${id}/bulk`, { body: { action: 'create_new' } })) })}>Create new pending items for all remaining unmapped rows</button>
        <span className="muted">Fix OCR typos in the name column first (e.g. “Roval” → “Royal”). Nothing is saved until you confirm.</span></div>}
      <label className="check"><input type="checkbox" checked={showAll} onChange={e => setShowAll(e.target.checked)} />Show structural rows (headings, sub totals, grand total — never imported)</label>
      <div className="table-wrap" style={{ maxHeight: '60vh' }}><table>
        <thead><tr><th>#</th><th>pg</th><th>Type</th><th>Source text</th><th>{isSales ? 'Item name (editable)' : 'Catalogue name (editable)'}</th>{isSales && <><th className="n">Qty</th><th className="n">Amount</th></>}{!isSales && <th>UOM</th>}<th>Mapping</th><th>Notes</th><th>Import?</th></tr></thead>
        <tbody>{rows.map((r: any) => {
          const struct = r.match_status === 'structural'
          return <tr key={r.id} className={struct ? 'struct' : r.needs_review ? 'flag' : ''}>
            <td>{r.seq}</td><td>{r.page}</td><td>{r.row_type}</td><td>{r.raw_name}</td>
            <td>{struct || !draft ? r.name : <input className="inp" defaultValue={r.name} onBlur={e => e.target.value !== r.name && patch(r.id, { name: e.target.value })} />}</td>
            {isSales && <><td className="n">{struct || !draft ? r.qty : <input className="inp" style={{ width: 70 }} defaultValue={r.qty ?? ''} onBlur={e => e.target.value !== String(r.qty ?? '') && patch(r.id, { qty: e.target.value })} />}</td>
              <td className="n">{struct || !draft ? fmt(r.amount) : <input className="inp" style={{ width: 90 }} defaultValue={r.amount ?? ''} onBlur={e => e.target.value !== String(r.amount ?? '') && patch(r.id, { amount: e.target.value })} />}</td></>}
            {!isSales && <td>{r.uom}</td>}
            <td>{struct ? '' : isSales ? (draft ? <>
              <select className="inp" value={r.item_id || (r.create_item ? 'new' : '')} onChange={e => patch(r.id, e.target.value === 'new' ? { create_item: true } : { item_id: e.target.value ? Number(e.target.value) : null, create_item: false })}>
                <option value="">— choose —</option><option value="new">➕ Create new item</option>{items.map(i => <option key={i.id} value={i.id}>{i.name}</option>)}</select>
              {r.suggested_item_id && !r.item_id && <button className="btn small secondary" onClick={() => patch(r.id, { item_id: r.suggested_item_id })}>Suggest: {r.suggested_item_name}</button>}
            </> : r.item_name || (r.create_item ? 'new item' : '')) : (r.item_name ? `exists: ${r.item_name}` : 'new pending item')}</td>
            <td style={{ maxWidth: 260 }}>{r.notes}{r.exclude_reason && <span className="muted"> {r.exclude_reason}</span>}</td>
            <td>{struct ? '—' : <input type="checkbox" disabled={!draft} checked={r.accepted} onChange={e => patch(r.id, { accepted: e.target.checked })} aria-label={`Import row ${r.seq}`} />}</td></tr>
        })}</tbody></table></div>
      {draft && <div className="card">
        {(s.needs_review > 0 || num(s.amount_variance) || num(s.qty_variance)) && <label className="check"><input type="checkbox" checked={ack} onChange={e => setAck(e.target.checked)} />
          I have reviewed the flagged rows / variances against the original report</label>}
        {b.duplicate_of_id && <><Notice kind="warn" msg={`This looks like a duplicate of import #${b.duplicate_of_id}. Importing again is blocked.`} />
          {user.role === 'admin' && <><label className="check"><input type="checkbox" checked={override} onChange={e => setOverride(e.target.checked)} />Admin override: import anyway (deliberate)</label>
            {override && <Field label="Override reason (required)"><input value={reason} onChange={e => setReason(e.target.value)} /></Field>}</>}</>}
        <p><button className="btn" disabled={busy || s.unresolved > 0} onClick={() => submit('Import confirmed', async () => { setData(await api(`/imports/${id}/confirm`, { body: { acknowledge_warnings: ack, override_duplicate: override, override_reason: reason } })) })}>Confirm import</button>{' '}
          <button className="btn ghost" disabled={busy} onClick={() => submit('Import rejected', async () => { await api(`/imports/${id}/reject`, { body: { reason: 'Rejected by reviewer' } }); onClose() })}>Reject</button>
          {s.unresolved > 0 && <span className="neg"> Resolve {s.unresolved} unmapped row(s) first (map, create new item, or untick “Import?”).</span>}</p>
        <p className="muted">Nothing is saved to sales, items or stock until you press Confirm import.</p></div>}
      {b.status === 'confirmed' && user.role === 'admin' && <ReverseBox id={id} onDone={reload} />}
    </div>
  )
}

function ReverseBox({ id, onDone }: { id: number; onDone: () => void }) {
  const [reason, setReason] = useState('')
  const { error, submit } = useSubmit()
  return <div className="card"><ErrorBox msg={error} /><div className="row"><Field label="Reverse this import (admin) — reason"><input value={reason} onChange={e => setReason(e.target.value)} /></Field>
    <button className="btn danger" disabled={!reason.trim()} onClick={() => submit('Import reversed', async () => { await api(`/imports/${id}/reverse`, { body: { reason } }); onDone() })}>Reverse</button></div></div>
}

function Imports({ user }: { user: User }) {
  const { data: list, reload } = useAsync(() => api('/imports'))
  const { data: items } = useAsync(() => api('/items'))
  const [type, setType] = useState('item_sales')
  const [date, setDate] = useState('')
  const { data: cfg } = useAsync(() => api('/settings'))
  const [useAi, setUseAi] = useState(false)
  const file = useRef<HTMLInputElement>(null)
  const { error, busy, submit } = useSubmit()
  const [openId, setOpenId] = useState<number | null>(null)
  const upload = () => submit(async () => {
    const f = file.current?.files?.[0]
    if (!f) throw new Error('Choose a PDF, image or CSV file')
    const fd = new FormData(); fd.append('report_type', type); fd.append('report_date', date); fd.append('use_ai', String(useAi && type === 'item_sales')); fd.append('file', f)
    const b = await api('/imports/preview', { form: fd })
    await reload(); setOpenId(b.id)
  })
  if (openId) return <ImportReview id={openId} user={user} items={items || []} onClose={() => { setOpenId(null); reload() }} />
  return (
    <>
      <div className="card"><h3>Import a report</h3><ErrorBox msg={error} />
        <div className="form-grid">
          <Field label="Report type"><select value={type} onChange={e => setType(e.target.value)}><option value="item_sales">Item Sales (daily)</option><option value="stock_position">Stock Position (item names only)</option></select></Field>
          <Field label="Report date (optional — read from file when possible)"><input type="date" value={date} onChange={e => setDate(e.target.value)} /></Field>
          <Field label="File (PDF, image or CSV)"><input ref={file} type="file" accept=".pdf,.png,.jpg,.jpeg,.csv" /></Field>
        </div>
        {cfg?.gemini_enabled === 'true' && type === 'item_sales' && <><label className="check"><input type="checkbox" checked={useAi} onChange={e => setUseAi(e.target.checked)} />Read with AI (Gemini) instead of local OCR — experimental</label>
          {useAi && <Notice kind="warn" msg="Only the report page images are sent to Google; no customer or ledger data. On the sample report the AI misread the date and totals, so every row will be flagged and must be checked against the printed totals." />}</>}
        <button className="btn" disabled={busy} onClick={upload}>{busy ? 'Reading file… scanned PDFs can take a few minutes' : 'Upload & preview'}</button>
        <p className="muted">Scanned PDFs are read locally (OCR). The result is only a preview for you to correct and confirm.</p>
      </div>
      <h2>Import history</h2>
      <div className="table-wrap"><table><thead><tr><th>#</th><th>Type</th><th>Report date</th><th>File</th><th>Method</th><th>Rows</th><th>Warnings</th><th>Status</th></tr></thead>
        <tbody>{(list || []).map((b: any) => <tr key={b.id} className="clickable" onClick={() => setOpenId(b.id)}><td>{b.id}</td><td>{b.report_type}</td><td>{fmtDate(b.report_date)}</td><td>{b.filename}</td><td>{b.extraction_method}</td>
          <td>{b.summary.item_rows}</td><td>{b.warnings.length}</td><td><Badge status={b.status} /></td></tr>)}
          {!(list || []).length && <tr><td colSpan={8} className="muted">No imports yet.</td></tr>}</tbody></table></div>
    </>
  )
}

function Catalogue() {
  const [q, setQ] = useState('')
  const [pending, setPending] = useState(false)
  const { data, error, reload } = useAsync(() => api(`/items?q=${encodeURIComponent(q)}${pending ? '&pending=true' : ''}`), [q, pending])
  const [name, setName] = useState('')
  const { error: e2, submit } = useSubmit()
  const upd = (id: number, body: any) => submit(async () => { await api(`/items/${id}`, { method: 'PATCH', body }); reload() })
  return (
    <>
      <div className="row"><Field label="Search"><input value={q} onChange={e => setQ(e.target.value)} /></Field>
        <label className="check"><input type="checkbox" checked={pending} onChange={e => setPending(e.target.checked)} />Pending review only</label>
        <Field label="Add item"><input value={name} onChange={e => setName(e.target.value)} placeholder="Item name" /></Field>
        <button className="btn" onClick={() => submit('Item added', async () => { await api('/items', { body: { name } }); setName(''); reload() })}>Add</button></div>
      <ErrorBox msg={error || e2} />
      <div className="table-wrap"><table><thead><tr><th>Item</th><th>Category</th><th>Kind</th><th>Base unit</th><th>UOM hint</th><th>Track stock</th><th>Low-stock at</th><th>Status</th></tr></thead>
        <tbody>{(data || []).map((i: any) => <tr key={i.id}><td>{i.name}{i.aliases.length > 0 && <div className="muted" style={{ fontSize: '.75rem' }}>aka {i.aliases.join(', ')}</div>}</td><td>{i.category}</td>
          <td><select value={i.kind} onChange={e => upd(i.id, { kind: e.target.value })}><option value="product">Product</option><option value="prepared_dish">Prepared dish</option></select></td>
          <td><input className="inp" style={{ width: 70 }} defaultValue={i.base_unit} onBlur={e => e.target.value !== i.base_unit && upd(i.id, { base_unit: e.target.value })} /></td><td>{i.uom_hint}</td>
          <td><input type="checkbox" checked={i.track_stock} disabled={i.kind === 'prepared_dish'} onChange={e => upd(i.id, { track_stock: e.target.checked })} aria-label={`Track stock ${i.name}`} /></td>
          <td><input className="inp" style={{ width: 70 }} defaultValue={i.low_stock_threshold ?? ''} onBlur={e => upd(i.id, { low_stock_threshold: e.target.value })} /></td>
          <td>{i.pending ? <><Badge status="draft" /> <button className="btn small ghost" onClick={() => upd(i.id, { pending: false })}>Mark reviewed</button></> : <Badge status="confirmed" />}</td></tr>)}</tbody></table></div>
      <Notice msg="Prepared dishes never deduct raw-ingredient stock (no recipes in this version). Only items marked Track stock take part in stock movements." />
    </>
  )
}

function Stock({ user }: { user: User }) {
  const { data, error, reload } = useAsync(() => api('/inventory/stock'))
  const { data: mv, reload: rm } = useAsync(() => api('/inventory/movements'))
  const [f, setF] = useState({ item_id: '', quantity: '', date: todayIso(), reason: '', movement_type: 'wastage' })
  const { error: e2, submit } = useSubmit()
  return (
    <>
      <ErrorBox msg={error || e2} />
      <div className="table-wrap"><table><thead><tr><th>Item</th><th>Baseline</th><th className="n">Opening count</th><th className="n">Net movement since</th><th className="n">Estimated stock</th><th>Last movement</th><th /></tr></thead>
        <tbody>{(data || []).map((s: any) => <tr key={s.item_id}><td>{s.name}</td><td>{s.baseline_status === 'set' ? `set ${fmtDate(s.baseline_date)}` : <span className="neg">Opening baseline unknown</span>}</td>
          <td className="n">{s.baseline_qty ?? '—'}</td><td className="n">{s.net_movement_since_baseline}</td><td className="n">{s.estimated_stock ?? '—'} {s.estimated_stock != null ? s.base_unit : ''}</td><td>{fmtDate(s.last_movement)}</td>
          <td>{s.below_threshold && <span className="badge bad">low</span>}</td></tr>)}
          {!(data || []).length && <tr><td colSpan={7} className="muted">No stock-tracked items. Mark items “Track stock” in the Catalogue tab.</td></tr>}</tbody></table></div>
      <div className="card"><h3>Count / adjust</h3>
        <div className="form-grid">
          <Field label="Item"><select value={f.item_id} onChange={e => setF({ ...f, item_id: e.target.value })}><option value="">— select —</option>{(data || []).map((s: any) => <option key={s.item_id} value={s.item_id}>{s.name}</option>)}</select></Field>
          <Field label="Quantity"><input value={f.quantity} onChange={e => setF({ ...f, quantity: e.target.value })} /></Field>
          <Field label="Date"><input type="date" value={f.date} onChange={e => setF({ ...f, date: e.target.value })} /></Field>
          <Field label="Reason"><input value={f.reason} onChange={e => setF({ ...f, reason: e.target.value })} /></Field>
          <Field label="Movement type"><select value={f.movement_type} onChange={e => setF({ ...f, movement_type: e.target.value })}>
            <option value="wastage">Wastage (out)</option><option value="adjustment_in">Adjustment in</option><option value="adjustment_out">Adjustment out</option><option value="supplier_return">Supplier return (out)</option><option value="sale_return">Sale return (in)</option></select></Field></div>
        <button className="btn" onClick={() => submit('Adjustment posted', async () => { await api('/inventory/adjustments', { body: { ...f, item_id: Number(f.item_id) } }); reload(); rm() })}>Post adjustment</button>{' '}
        {user.role === 'admin' && <button className="btn secondary" onClick={() => submit('Opening count recorded', async () => { await api('/inventory/opening-counts', { body: { item_id: Number(f.item_id), quantity: f.quantity, date: f.date, reason: f.reason || 'Manually counted' } }); reload(); rm() })}>Record verified opening count (admin)</button>}
        <p className="muted">Stock is never typed directly: opening counts and adjustments are ledger entries with a reason. Figures from the Stock Position PDF are never used.</p></div>
      <h2>Movement ledger</h2>
      <div className="table-wrap"><table><thead><tr><th>Date</th><th>Item</th><th>Type</th><th className="n">Qty</th><th>Source</th><th>Reason</th></tr></thead>
        <tbody>{(mv || []).slice(0, 200).map((m: any) => <tr key={m.id}><td>{fmtDate(m.business_date)}</td><td>{m.item}</td><td>{m.movement_type}</td><td className="n">{m.quantity}</td><td>{m.source_type}{m.import_batch_id ? ` import#${m.import_batch_id}` : ''}</td><td>{m.reason}</td></tr>)}</tbody></table></div>
    </>
  )
}

export default function Inventory({ user }: { user: User }) {
  const [tab, setTab] = useState('imports')
  return (
    <>
      <h1>Inventory & PDF Imports</h1>
      <div className="tabs">{[['imports', 'PDF imports'], ['items', 'Item catalogue'], ['stock', 'Stock & movements']].map(([k, l]) => <button key={k} className={`tab ${tab === k ? 'active' : ''}`} onClick={() => setTab(k)}>{l}</button>)}</div>
      {tab === 'imports' && <Imports user={user} />}{tab === 'items' && <Catalogue />}{tab === 'stock' && <Stock user={user} />}
    </>
  )
}
