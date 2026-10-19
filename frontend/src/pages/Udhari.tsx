import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, downloadCsv, fmt, fmtDate, num, openAttachment, todayIso } from '../api'
import { AccountSelect, Customer, CustomerPicker, MethodSelect, useAccounts } from '../shared'
import { Badge, ErrorBox, Field, Modal, Notice, PrintButton, useAsync, useSubmit } from '../ui'
import type { User } from '../App'

export function Customers() {
  const [importing, setImporting] = useState(false)
  const [q, setQ] = useState('')
  const [filter, setFilter] = useState('')
  const { data, error, loading } = useAsync(() => api(`/customers?q=${encodeURIComponent(q)}&filter=${filter}`), [q, filter])
  return (
    <>
      <div className="row between">
        <h1>Udhari / Customers</h1>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <Link className="btn" to="/udhari/new-bill">+ Add udhari bill <kbd className="kbd-sm kbd-accent" style={{ marginLeft: 4 }}>F3</kbd></Link>
          <Link className="btn secondary" to="/receive">Receive payment <kbd className="kbd-sm" style={{ marginLeft: 4 }}>F4</kbd></Link>
          <button className="btn ghost" onClick={() => setImporting(true)}>Import old udhari (CSV)</button>
        </div>
      </div>
      {importing && <ImportOld onClose={() => setImporting(false)} />}
      <div className="row">
        <Field label="Search name or phone"><input value={q} onChange={e => setQ(e.target.value)} placeholder="Search by customer name or phone…" autoFocus /></Field>
        <Field label="Show"><select value={filter} onChange={e => setFilter(e.target.value)}>
          <option value="">All customers</option><option value="owing">Owing money</option><option value="overdue">Overdue</option></select></Field>
      </div>
      <ErrorBox msg={error} />
      <div className="table-wrap"><table>
        <thead><tr><th>Customer</th><th>Phone</th><th className="n">Outstanding</th><th className="n">Advance</th><th>Oldest open bill</th><th>Last collection</th></tr></thead>
        <tbody>{(data || []).map((c: any) => (
          <tr key={c.id}><td><Link to={`/udhari/${c.id}`} style={{ fontWeight: 600 }}>{c.name}</Link></td><td>{c.phone}</td>
            <td className={`n ${num(c.outstanding) > 0 ? 'neg' : ''}`}>{fmt(c.outstanding)}</td><td className="n">{num(c.advance) ? fmt(c.advance) : '—'}</td>
            <td>{fmtDate(c.oldest_open_bill_date)}</td><td>{fmtDate(c.last_collection)}</td></tr>))}
          {!loading && !(data || []).length && <tr><td colSpan={6} className="muted">No customers yet. Add an udhari bill to create one.</td></tr>}
        </tbody></table></div>
    </>
  )
}

export function AddBill() {
  const nav = useNavigate()
  const accounts = useAccounts()
  const [cust, setCust] = useState<Customer | null>(null)
  const [f, setF] = useState({ bill_no: '', pos_bill_no: '', business_date: todayIso(), total: '', paid_now: '', method: 'cash', notes: '', in_pos_report: true, count_as_new_sale: false, allow_duplicate: false })
  const [acct, setAcct] = useState<number | ''>('')
  const [file, setFile] = useState<File | null>(null)
  const [lines, setLines] = useState<{ item_name: string; quantity: string; unit_price: string }[]>([])
  const { error, busy, submit } = useSubmit()
  const linesTotal = lines.reduce((t, l) => t + num(l.quantity) * num(l.unit_price), 0)
  const set = (k: string, v: any) => setF(p => ({ ...p, [k]: v }))
  const outstanding = Math.max(0, num(f.total) - num(f.paid_now))
  const save = () => submit(async () => {
    if (!cust) throw new Error('Select or create the customer first')
    let attachment = ''
    if (file) { const fd = new FormData(); fd.append('file', file); attachment = (await api('/attachments', { form: fd })).attachment }
    const b = await api('/credit-bills', { body: { ...f, customer_id: cust.id, account_id: num(f.paid_now) > 0 ? acct : null, attachment,
      lines: lines.filter(l => l.item_name.trim()).map(l => ({ item_name: l.item_name, quantity: l.quantity || 1, unit_price: l.unit_price || 0, line_total: (num(l.quantity || 1) * num(l.unit_price)).toFixed(2) })) } })
    nav(`/udhari/${cust.id}?saved=${encodeURIComponent(b.bill_no)}`)
  })

  const handleCardKeyDown = (e: React.KeyboardEvent) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault()
      save()
    }
    if (e.key === 'F10') {
      e.preventDefault()
      save()
    }
    if (e.altKey && e.key.toLowerCase() === 'l') {
      e.preventDefault()
      setLines(ls => [...ls, { item_name: '', quantity: '1', unit_price: '' }])
    }
  }

  return (
    <>
      <div className="row between">
        <h1>Add udhari (credit) bill</h1>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <span className="muted" style={{ fontSize: '0.82rem' }}>Quick save:</span>
          <kbd className="kbd-sm kbd-accent">Ctrl+↵</kbd>
          <span className="muted" style={{ fontSize: '0.82rem' }}>or</span>
          <kbd className="kbd-sm">F10</kbd>
        </div>
      </div>
      <div className="card" onKeyDown={handleCardKeyDown}><ErrorBox msg={error} />
        {error.includes('already exists') && <label className="check"><input type="checkbox" checked={f.allow_duplicate} onChange={e => set('allow_duplicate', e.target.checked)} />Allow this duplicate bill number, then press Save again</label>}
        <CustomerPicker value={cust} onChange={setCust} />
        <div className="form-grid">
          <Field label="Bill number"><input value={f.bill_no} onChange={e => set('bill_no', e.target.value)} placeholder="e.g. B-1049" /></Field>
          <Field label="POS bill number (optional)"><input value={f.pos_bill_no} onChange={e => set('pos_bill_no', e.target.value)} placeholder="POS slip no." /></Field>
          <Field label="Bill date"><input type="date" value={f.business_date} onChange={e => set('business_date', e.target.value)} /></Field>
          <Field label="Bill total (₹)"><input inputMode="decimal" value={f.total} onChange={e => set('total', e.target.value)} placeholder="0.00" /></Field>
          <Field label="Received now (₹)" hint="Leave blank if nothing was paid"><input inputMode="decimal" value={f.paid_now} onChange={e => set('paid_now', e.target.value)} placeholder="0.00" /></Field>
          <div className="field"><span>Udhari (calculated)</span><b style={{ fontSize: '1.45rem', color: outstanding > 0 ? 'var(--bad)' : 'var(--good)' }}>{fmt(outstanding)}</b></div>
        </div>

        {/* Quick Cashier Tender Buttons */}
        <div className="tender-presets">
          <span className="tender-preset-label">Quick Tender:</span>
          {num(f.total) > 0 && <button type="button" className="tender-btn" onClick={() => set('paid_now', f.total)}>Full ({fmt(f.total)})</button>}
          <button type="button" className="tender-btn" onClick={() => set('paid_now', '0')}>₹0 (All Udhari)</button>
          {num(f.total) > 100 && <button type="button" className="tender-btn" onClick={() => set('paid_now', '100')}>₹100</button>}
          {num(f.total) > 200 && <button type="button" className="tender-btn" onClick={() => set('paid_now', '200')}>₹200</button>}
          {num(f.total) > 500 && <button type="button" className="tender-btn" onClick={() => set('paid_now', '500')}>₹500</button>}
          {num(f.total) > 1000 && <button type="button" className="tender-btn" onClick={() => set('paid_now', '1000')}>₹1000</button>}
          {num(f.total) > 2000 && <button type="button" className="tender-btn" onClick={() => set('paid_now', '2000')}>₹2000</button>}
        </div>

        {num(f.paid_now) > 0 && <div className="form-grid">
          <MethodSelect value={f.method} onChange={v => set('method', v)} />
          <AccountSelect accounts={accounts} method={f.method} value={acct} onChange={setAcct} />
        </div>}
        <label className="check"><input type="checkbox" checked={f.in_pos_report} onChange={e => setF(p => ({ ...p, in_pos_report: e.target.checked, count_as_new_sale: e.target.checked ? false : p.count_as_new_sale }))} />
          Already included in the POS daily report (do not count sale or stock again)</label>
        {!f.in_pos_report && <label className="check"><input type="checkbox" checked={f.count_as_new_sale} onChange={e => set('count_as_new_sale', e.target.checked)} />Count as a new sale (this bill is NOT in the POS report)</label>}
        {f.in_pos_report && num(f.paid_now) > 0 && <Notice msg="Because this bill is in the POS report, the amount received now is assumed to be inside the POS tender totals and is not added to the cashbook a second time." />}
        <div className="form-grid">
          <Field label="Notes"><input value={f.notes} onChange={e => set('notes', e.target.value)} placeholder="e.g. Table 4, parcel, special discount" /></Field>
          <Field label="Photo / PDF of paper bill (optional)"><input type="file" accept=".pdf,.png,.jpg,.jpeg,.webp" onChange={e => setFile(e.target.files?.[0] || null)} /></Field>
        </div>
        <h3>Item lines (optional)</h3>
        {lines.map((l, i) => <div className="row" key={i}>
          <Field label="Item"><input value={l.item_name} onChange={e => setLines(ls => ls.map((x, k) => k === i ? { ...x, item_name: e.target.value } : x))} placeholder="Dish / beverage name" /></Field>
          <Field label="Qty"><input style={{ width: 80 }} value={l.quantity} onChange={e => setLines(ls => ls.map((x, k) => k === i ? { ...x, quantity: e.target.value } : x))} /></Field>
          <Field label="Price"><input style={{ width: 100 }} value={l.unit_price} onChange={e => setLines(ls => ls.map((x, k) => k === i ? { ...x, unit_price: e.target.value } : x))} /></Field>
          <button type="button" className="btn small ghost" onClick={() => setLines(ls => ls.filter((_, k) => k !== i))}>✕</button></div>)}
        <p><button type="button" className="btn small secondary" onClick={() => setLines([...lines, { item_name: '', quantity: '1', unit_price: '' }])}>+ item line <kbd className="kbd-sm" style={{ marginLeft: 4 }}>Alt+L</kbd></button>
          {lines.length > 0 && <> Lines total {fmt(linesTotal)} <button type="button" className="btn small ghost" onClick={() => set('total', linesTotal.toFixed(2))}>Use as bill total</button></>}</p>
        <p style={{ marginTop: 18 }}>
          <button className="btn" disabled={busy} onClick={save}>
            <span>Save udhari bill</span> <kbd className="kbd-sm kbd-accent" style={{ marginLeft: 6 }}>Ctrl+↵</kbd>
          </button>
        </p>
      </div>
    </>
  )
}

export function CustomerDetail({ user }: { user: User }) {
  const { id } = useParams()
  const { data: c, error, reload } = useAsync(() => api(`/customers/${id}`), [id])
  const { data: led } = useAsync(() => api(`/customers/${id}/ledger`), [id, c])
  const [tab, setTab] = useState('statement')
  const [editing, setEditing] = useState(false)
  const [billId, setBillId] = useState<number | null>(null)
  const [copied, setCopied] = useState('')
  const { data: cfg } = useAsync(() => api('/settings'))
  const [voidTarget, setVoidTarget] = useState<{ kind: 'receipts' | 'credit-bills'; id: number; label: string } | null>(null)
  const saved = new URLSearchParams(window.location.search).get('saved')
  if (!c) return <ErrorBox msg={error} />
  return (
    <>
      <div className="row between"><h1>{c.name} <small className="muted">{c.phone}</small></h1>
        <div className="no-print"><Link className="btn" to={`/receive?customer=${c.id}`}>Collect payment</Link> <Link className="btn secondary" to="/udhari/new-bill">+ Bill</Link> <PrintButton />
          <button className="btn ghost" onClick={() => setEditing(true)}>Edit customer</button>
          <button className="btn ghost" disabled={!(num(c.outstanding) > 0)} onClick={() => { const open = c.bills.filter((b: any) => num(b.outstanding) > 0)
            const txt = `Namaste ${c.name}, this is a gentle reminder from ${cfg?.restaurant_name || 'us'}: your pending balance is ${fmt(c.outstanding)}` + (open.length ? ` (${open.map((b: any) => `bill ${b.bill_no} dated ${fmtDate(b.business_date)}: ${fmt(b.outstanding)}`).join('; ')})` : '') + '. Thank you!'
            navigator.clipboard?.writeText(txt).then(() => setCopied('Reminder text copied — paste it into WhatsApp/SMS yourself (nothing is sent automatically).'), () => setCopied(txt)) }}>Copy reminder text</button>
          <button className="btn ghost" onClick={() => downloadCsv(`/reports/customer-statement?customer_id=${c.id}&format=csv`, `statement-${c.name}.csv`)}>CSV</button></div></div>
      {copied && <Notice msg={copied} />}
      {saved && <Notice kind="ok" msg={`Bill ${saved} saved.`} />}
      <div className="card"><dl className="kv">
        <dt>Outstanding</dt><dd className={num(c.outstanding) > 0 ? 'neg' : ''}><b>{fmt(c.outstanding)}</b> across {c.open_bills} open bill(s)</dd>
        <dt>Unallocated advance</dt><dd>{fmt(c.advance)}</dd><dt>Net position</dt><dd>{fmt(c.net)}</dd></dl></div>
      <div className="tabs no-print">{['statement', 'bills', 'receipts'].map(t => <button key={t} className={`tab ${tab === t ? 'active' : ''}`} onClick={() => setTab(t)}>{t}</button>)}</div>
      {tab === 'statement' && led && <div className="table-wrap"><table>
        <thead><tr><th>Date</th><th>Type</th><th>Ref</th><th className="n">Debit (bill)</th><th className="n">Credit (receipt)</th><th>Allocated to</th><th className="n">Balance</th></tr></thead>
        <tbody>{led.rows.map((r: any, i: number) => <tr key={i}><td>{fmtDate(r.date)}</td><td>{r.type}</td><td>{r.ref}</td>
          <td className="n">{num(r.debit) ? fmt(r.debit) : ''}</td><td className="n">{num(r.credit) ? fmt(r.credit) : ''}</td><td>{r.details}</td><td className="n">{fmt(r.balance)}</td></tr>)}
          <tr className="total-row"><td colSpan={6}>Closing balance</td><td className="n">{fmt(led.closing_balance)}</td></tr></tbody></table></div>}
      {tab === 'bills' && <div className="table-wrap"><table>
        <thead><tr><th>Bill</th><th>Date</th><th className="n">Total</th><th className="n">Collected</th><th className="n">Outstanding</th><th>Age</th><th>Status</th><th>POS</th><th /></tr></thead>
        <tbody>{c.bills.map((b: any) => <tr key={b.id}><td>{b.bill_no} <span className="muted">{b.pos_bill_no}</span></td><td>{fmtDate(b.business_date)}</td>
          <td className="n">{fmt(b.total)}</td><td className="n">{fmt(b.collected)}</td><td className="n">{fmt(b.outstanding)}</td><td>{b.outstanding > 0 ? b.age_days + ' d' : ''}</td>
          <td><Badge status={b.status} /></td><td>{b.in_pos_report ? 'in POS report' : 'app-only'}</td>
          <td><button className="btn small ghost" onClick={() => setBillId(b.id)}>Details</button> {user.role === 'admin' && b.record_status === 'posted' && <button className="btn small ghost" onClick={() => setVoidTarget({ kind: 'credit-bills', id: b.id, label: `bill ${b.bill_no}` })}>Void</button>}</td></tr>)}</tbody></table></div>}
      {tab === 'receipts' && <div className="table-wrap"><table>
        <thead><tr><th>Receipt</th><th>Date</th><th className="n">Amount</th><th>Method / account</th><th>Received by</th><th>Allocated to</th><th className="n">Unallocated</th><th>Status</th><th /></tr></thead>
        <tbody>{c.receipts.map((r: any) => <tr key={r.id} className={r.status === 'voided' ? 'voided' : ''}><td>{r.receipt_no}</td><td>{fmtDate(r.receipt_date)}</td><td className="n">{fmt(r.amount)}</td>
          <td>{r.method} → {r.account}{r.reference && ` (${r.reference})`}</td><td>{r.received_by}</td>
          <td>{r.allocations.filter((a: any) => a.active).map((a: any) => `${a.bill_no}: ${fmt(a.amount)}`).join(', ')}</td><td className="n">{num(r.unallocated) ? fmt(r.unallocated) : ''}</td>
          <td><Badge status={r.status} /></td><td><button className="btn small ghost" onClick={() => printReceipt(r, cfg)}>Print</button> {user.role === 'admin' && r.status === 'posted' && <button className="btn small ghost" onClick={() => setVoidTarget({ kind: 'receipts', id: r.id, label: `receipt ${r.receipt_no}` })}>Void</button>}</td></tr>)}</tbody></table></div>}
      {editing && <EditCustomer c={c} onClose={() => setEditing(false)} onDone={() => { setEditing(false); reload() }} />}
      {billId && <BillModal id={billId} onClose={() => setBillId(null)} />}
      {voidTarget && <VoidModal target={voidTarget} onClose={() => setVoidTarget(null)} onDone={() => { setVoidTarget(null); reload() }} />}
    </>
  )
}

function VoidModal({ target, onClose, onDone }: { target: { kind: string; id: number; label: string }; onClose: () => void; onDone: () => void }) {
  const [reason, setReason] = useState('')
  const { error, busy, submit } = useSubmit()
  return (
    <Modal title={`Void ${target.label}`} onClose={onClose}>
      <Notice kind="warn" msg="Voiding keeps the original record and posts a reversal; it cannot be undone." />
      <ErrorBox msg={error} />
      <Field label="Reason (required)"><input value={reason} onChange={e => setReason(e.target.value)} autoFocus /></Field>
      <p><button className="btn danger" disabled={busy || !reason.trim()} onClick={() => submit(async () => { await api(`/${target.kind}/${target.id}/void`, { body: { reason } }); onDone() })}>Void</button></p>
    </Modal>
  )
}

function EditCustomer({ c, onClose, onDone }: { c: any; onClose: () => void; onDone: () => void }) {
  const [f, setF] = useState({ name: c.name, phone: c.phone, address: c.address, notes: c.notes, active: c.active })
  const { error, busy, submit } = useSubmit()
  return (
    <Modal title="Edit customer" onClose={onClose}><ErrorBox msg={error} />
      <div className="form-grid">
        <Field label="Name"><input value={f.name} onChange={e => setF({ ...f, name: e.target.value })} /></Field>
        <Field label="Phone"><input value={f.phone} onChange={e => setF({ ...f, phone: e.target.value })} /></Field>
        <Field label="Address"><input value={f.address} onChange={e => setF({ ...f, address: e.target.value })} /></Field>
        <Field label="Notes"><input value={f.notes} onChange={e => setF({ ...f, notes: e.target.value })} /></Field></div>
      <label className="check"><input type="checkbox" checked={f.active} onChange={e => setF({ ...f, active: e.target.checked })} />Active</label>
      <button className="btn" disabled={busy} onClick={() => submit(async () => { await api(`/customers/${c.id}`, { method: 'PATCH', body: f }); onDone() })}>Save</button>
    </Modal>
  )
}

function BillModal({ id, onClose }: { id: number; onClose: () => void }) {
  const { data: b, error } = useAsync(() => api(`/credit-bills/${id}`), [id])
  if (!b) return <Modal title="Bill" onClose={onClose}><ErrorBox msg={error} /></Modal>
  return (
    <Modal title={`Bill ${b.bill_no}`} onClose={onClose}>
      <dl className="kv"><dt>Date</dt><dd>{fmtDate(b.business_date)}</dd><dt>Total</dt><dd>{fmt(b.total)}</dd><dt>Collected</dt><dd>{fmt(b.collected)}</dd>
        <dt>Outstanding</dt><dd><b>{fmt(b.outstanding)}</b></dd><dt>POS bill no.</dt><dd>{b.pos_bill_no || '—'}</dd>
        <dt>In POS report</dt><dd>{b.in_pos_report ? 'Yes (not counted again as a sale)' : 'No — app-only'}</dd><dt>Notes</dt><dd>{b.notes || '—'}</dd>
        {b.attachment && <><dt>Paper bill</dt><dd><button className="btn small secondary" onClick={() => openAttachment(b.attachment)}>Open attachment</button></dd></>}</dl>
      {b.lines.length > 0 && <div className="table-wrap"><table><thead><tr><th>Item</th><th className="n">Qty</th><th className="n">Price</th><th className="n">Total</th></tr></thead>
        <tbody>{b.lines.map((l: any, i: number) => <tr key={i}><td>{l.item_name}</td><td className="n">{l.quantity}</td><td className="n">{fmt(l.unit_price)}</td><td className="n">{fmt(l.line_total)}</td></tr>)}</tbody></table></div>}
      <h3>Payments against this bill</h3>
      <div className="table-wrap"><table><thead><tr><th>Date</th><th>Receipt</th><th className="n">Amount</th><th>Status</th></tr></thead>
        <tbody>{b.allocations.map((a: any, i: number) => <tr key={i} className={a.active ? '' : 'voided'}><td>{fmtDate(a.date)}</td><td>{a.receipt_no}</td><td className="n">{fmt(a.amount)}</td><td>{a.active ? 'active' : 'voided'}</td></tr>)}
          {!b.allocations.length && <tr><td colSpan={4} className="muted">None yet.</td></tr>}</tbody></table></div>
    </Modal>
  )
}

export function printReceipt(r: any, cfg: any) {
  const w = window.open('', '_blank', 'width=420,height=640')
  if (!w) return
  const esc = (x: unknown) => String(x ?? '').replace(/[&<>"]/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[ch] as string))
  w.document.write(`<html><head><title>${esc(r.receipt_no)}</title><style>body{font:14px system-ui;padding:16px;max-width:380px}h2{margin:0}table{width:100%;border-collapse:collapse}td{padding:3px 0}hr{border:0;border-top:1px dashed #888}</style></head><body>
    <h2>${esc(cfg?.restaurant_name)}</h2><div>${esc(cfg?.address)} ${esc(cfg?.phone)}</div><hr><b>Payment receipt ${esc(r.receipt_no)}</b>${r.status === 'voided' ? ' (VOIDED)' : ''}
    <table><tr><td>Date</td><td>${esc(fmtDate(r.receipt_date))}</td></tr><tr><td>Customer</td><td>${esc(r.customer)}</td></tr><tr><td>Amount</td><td><b>${esc(fmt(r.amount))}</b></td></tr>
    <tr><td>Method</td><td>${esc(r.method)} ${esc(r.reference)}</td></tr><tr><td>Received by</td><td>${esc(r.received_by)}</td></tr></table><hr>
    <div>Applied to: ${r.allocations.filter((a: any) => a.active).map((a: any) => `${esc(a.bill_no)} ${esc(fmt(a.amount))}`).join(', ') || '—'}</div>
    ${num(r.unallocated) > 0 ? `<div>Advance balance: ${esc(fmt(r.unallocated))}</div>` : ''}<hr><div>Thank you</div><script>window.print()</script></body></html>`)
  w.document.close()
}

function ImportOld({ onClose }: { onClose: () => void }) {
  const [res, setRes] = useState<any>(null)
  const [file, setFile] = useState<File | null>(null)
  const { error, busy, submit } = useSubmit()
  const run = (dry: boolean) => submit(async () => {
    if (!file) throw new Error('Choose a CSV file first')
    const fd = new FormData(); fd.append('file', file)
    setRes(await api(`/credit-bills/import-csv?dry_run=${dry}`, { form: fd }))
  })
  return (
    <Modal title="Import existing udhari (opening balances)" onClose={onClose}>
      <p className="muted">CSV columns: <code>customer, phone, bill_no, date (YYYY-MM-DD), amount, paid</code> (paid = already received before go-live, optional). All rows must be valid or nothing is imported. No cash is posted.</p>
      <ErrorBox msg={error} />
      <Field label="CSV file"><input type="file" accept=".csv" onChange={e => { setFile(e.target.files?.[0] || null); setRes(null) }} /></Field>
      <p><button className="btn secondary" disabled={busy} onClick={() => run(true)}>Check file</button>{' '}
        <button className="btn" disabled={busy || !res?.ok || res?.committed} onClick={() => run(false)}>Import</button></p>
      {res && <><Notice kind={res.ok ? 'ok' : 'warn'} msg={res.message} />
        <div className="table-wrap" style={{ maxHeight: 260 }}><table><thead><tr><th>Line</th><th>Customer</th><th>Bill</th><th className="n">Amount</th><th>Issues</th></tr></thead>
          <tbody>{res.rows.map((r: any) => <tr key={r.line} className={r.issues.length ? 'flag' : ''}><td>{r.line}</td><td>{r.customer}</td><td>{r.bill_no}</td><td className="n">{r.amount}</td><td>{r.issues.join('; ')}</td></tr>)}</tbody></table></div></>}
    </Modal>
  )
}
