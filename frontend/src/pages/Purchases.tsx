import { useState } from 'react'
import { api, fmt, fmtDate, num, todayIso } from '../api'
import { AccountSelect, MethodSelect, useAccounts } from '../shared'
import { Badge, ErrorBox, Field, Notice, useAsync, useSubmit } from '../ui'

type Line = { item_id: string; description: string; quantity: string; unit: string; conversion_factor: string; unit_price: string }
const blank = (): Line => ({ item_id: '', description: '', quantity: '', unit: '', conversion_factor: '', unit_price: '' })

export default function Purchases() {
  const { data: list, reload } = useAsync(() => api('/purchases'))
  const { data: vendors, reload: rv } = useAsync(() => api('/vendors'))
  const { data: items } = useAsync(() => api('/items'))
  const [adding, setAdding] = useState(false)
  const [f, setF] = useState({ vendor_id: '', invoice_no: '', invoice_date: todayIso(), due_date: '', discount: '', tax: '', notes: '' })
  const [newVendor, setNewVendor] = useState('')
  const [lines, setLines] = useState<Line[]>([blank()])
  const accounts = useAccounts()
  const [pay, setPay] = useState({ amount: '', method: 'cash' })
  const [acct, setAcct] = useState<number | ''>('')
  const { error, busy, submit } = useSubmit()
  const itemOf = (id: string) => (items || []).find((i: any) => String(i.id) === id)
  const setLine = (i: number, patch: Partial<Line>) => setLines(ls => ls.map((l, k) => k === i ? { ...l, ...patch } : l))
  const subtotal = lines.reduce((s, l) => s + num(l.quantity) * num(l.unit_price), 0)
  const total = subtotal - num(f.discount) + num(f.tax)
  const save = () => submit(async () => {
    let vendor_id = f.vendor_id ? Number(f.vendor_id) : null
    if (newVendor.trim()) vendor_id = (await api('/vendors', { body: { name: newVendor } })).id
    const payments = num(pay.amount) > 0 ? [{ amount: pay.amount, method: pay.method, funded_by: 'account', account_id: acct, paid_date: f.invoice_date }] : []
    await api('/purchases', { body: { ...f, vendor_id, due_date: f.due_date || null, discount: f.discount || 0, tax: f.tax || 0,
      lines: lines.filter(l => l.quantity).map(l => ({ ...l, item_id: l.item_id ? Number(l.item_id) : null, conversion_factor: l.conversion_factor || null })), payments } })
    setAdding(false); setLines([blank()]); rv(); reload()
  })
  return (
    <>
      <div className="row between"><h1>Purchases</h1><button className="btn" onClick={() => setAdding(!adding)}>{adding ? 'Close form' : '+ Add purchase'}</button></div>
      {adding && <div className="card"><ErrorBox msg={error} />
        <div className="form-grid">
          <Field label="Supplier"><select value={f.vendor_id} onChange={e => setF({ ...f, vendor_id: e.target.value })}><option value="">— select —</option>{(vendors || []).map((v: any) => <option key={v.id} value={v.id}>{v.name}</option>)}</select></Field>
          <Field label="…or new supplier"><input value={newVendor} onChange={e => setNewVendor(e.target.value)} /></Field>
          <Field label="Invoice no."><input value={f.invoice_no} onChange={e => setF({ ...f, invoice_no: e.target.value })} /></Field>
          <Field label="Invoice date"><input type="date" value={f.invoice_date} onChange={e => setF({ ...f, invoice_date: e.target.value })} /></Field>
          <Field label="Due date"><input type="date" value={f.due_date} onChange={e => setF({ ...f, due_date: e.target.value })} /></Field>
          <Field label="Discount (₹)"><input value={f.discount} onChange={e => setF({ ...f, discount: e.target.value })} /></Field>
          <Field label="Tax (₹)"><input value={f.tax} onChange={e => setF({ ...f, tax: e.target.value })} /></Field>
        </div>
        <h2>Lines</h2>
        <div className="table-wrap"><table><thead><tr><th>Item</th><th>Qty</th><th>Purchase unit</th><th>Conversion → base</th><th>Unit price</th><th className="n">Line total</th><th /></tr></thead>
          <tbody>{lines.map((l, i) => { const it = itemOf(l.item_id); const needs = it?.track_stock && l.unit && l.unit.toLowerCase() !== it.base_unit.toLowerCase()
            return <tr key={i}>
              <td><select value={l.item_id} onChange={e => { const x = itemOf(e.target.value); setLine(i, { item_id: e.target.value, unit: x?.purchase_unit || x?.base_unit || l.unit, conversion_factor: x?.purchase_to_base ?? '' }) }}>
                <option value="">free text →</option>{(items || []).map((x: any) => <option key={x.id} value={x.id}>{x.name}{x.track_stock ? ' ●' : ''}</option>)}</select>
                {!l.item_id && <input className="inp" placeholder="description" value={l.description} onChange={e => setLine(i, { description: e.target.value })} />}</td>
              <td><input className="inp" style={{ width: 80 }} value={l.quantity} onChange={e => setLine(i, { quantity: e.target.value })} /></td>
              <td><input className="inp" style={{ width: 90 }} value={l.unit} onChange={e => setLine(i, { unit: e.target.value })} /></td>
              <td>{it?.track_stock ? <><input className="inp" style={{ width: 90 }} placeholder={needs ? 'required' : '1'} value={l.conversion_factor} onChange={e => setLine(i, { conversion_factor: e.target.value })} /><small className="muted"> 1 {l.unit || 'unit'} = ? {it.base_unit}</small></> : <span className="muted">no stock effect</span>}</td>
              <td><input className="inp" style={{ width: 100 }} value={l.unit_price} onChange={e => setLine(i, { unit_price: e.target.value })} /></td>
              <td className="n">{fmt(num(l.quantity) * num(l.unit_price))}</td><td><button className="btn small ghost" onClick={() => setLines(ls => ls.filter((_, k) => k !== i))}>✕</button></td></tr> })}</tbody></table></div>
        <button className="btn small secondary" onClick={() => setLines([...lines, blank()])}>+ line</button>
        <p>Total: <b>{fmt(total)}</b></p>
        <Notice msg="Stock increases only for items marked 'Track stock' (●), using the conversion factor you enter. The bill is recorded once as a payable; payments are made against it." />
        <div className="form-grid">
          <Field label="Paid now (₹) — optional"><input value={pay.amount} onChange={e => setPay({ ...pay, amount: e.target.value })} /></Field>
          <MethodSelect value={pay.method} onChange={m => setPay({ ...pay, method: m })} />
          <AccountSelect accounts={accounts} method={pay.method} value={acct} onChange={setAcct} label="Paid from account" />
        </div>
        <button className="btn" disabled={busy} onClick={save}>Save purchase</button></div>}
      <div className="table-wrap"><table><thead><tr><th>Date</th><th>Supplier</th><th>Invoice</th><th className="n">Total</th><th className="n">Paid</th><th className="n">Due</th><th>Status</th></tr></thead>
        <tbody>{(list || []).map((p: any) => <tr key={p.id}><td>{fmtDate(p.invoice_date)}</td><td>{p.vendor}</td><td>{p.invoice_no}</td><td className="n">{fmt(p.total)}</td><td className="n">{fmt(p.paid)}</td><td className="n">{fmt(p.due)}</td><td>{p.payment_status && <Badge status={p.payment_status} />}</td></tr>)}
          {!(list || []).length && <tr><td colSpan={7} className="muted">No purchases yet.</td></tr>}</tbody></table></div>
      <p className="muted">To pay a supplier bill later, open it under Expenses & Payables (category “Purchases”).</p>
    </>
  )
}
