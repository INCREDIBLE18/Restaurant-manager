import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api, downloadCsv, fmt, fmtDate, todayIso } from '../api'
import { Icon } from '../icons'
import { toast } from '../toast'
import { ErrorBox, Field, useAsync } from '../ui'

type Def = { key: string; label: string; desc: string; dates?: boolean; needs?: 'customer' | 'account' }
const GROUPS: { title: string; icon: string; items: Def[] }[] = [
  { title: 'Udhari', icon: 'users', items: [
    { key: 'customer-outstanding', label: 'Customer outstanding', desc: 'Who owes what, oldest bill, last payment' },
    { key: 'customer-aging', label: 'Aging (0-30 / 31-60 / 61-90 / 90+)', desc: 'Open udhari by bill age per customer' },
    { key: 'bill-outstanding', label: 'Open bills', desc: 'Bill-wise collected and remaining', dates: true },
    { key: 'udhari-collections', label: 'Collections', desc: 'Receipts with method, account and allocation', dates: true },
    { key: 'customer-statement', label: 'Customer statement', desc: 'Running ledger for one customer', dates: true, needs: 'customer' },
  ] },
  { title: 'Profit & expenses', icon: 'chart', items: [
    { key: 'pnl-summary', label: 'Profit & loss (estimate)', desc: 'POS sales minus expenses incurred', dates: true },
    { key: 'expense-summary', label: 'Expenses by category', desc: 'Incurred, paid and unpaid', dates: true },
    { key: 'unpaid-expenses', label: 'Unpaid & part-paid', desc: 'What you still owe suppliers', dates: true },
    { key: 'paid-by-source', label: 'Paid by / source', desc: 'Which account or person funded expenses', dates: true },
    { key: 'owner-ledger', label: 'Owner reimbursement', desc: 'Owner-funded expenses and repayments', dates: true },
  ] },
  { title: 'Cash', icon: 'lock', items: [
    { key: 'cashbook', label: 'Cashbook', desc: 'Every movement in one account', dates: true, needs: 'account' },
    { key: 'daily-closing', label: 'Daily closings', desc: 'Expected vs counted cash per day', dates: true },
  ] },
  { title: 'Sales & stock', icon: 'box', items: [
    { key: 'item-sales-summary', label: 'Item sales', desc: 'From confirmed Item Sales imports', dates: true },
    { key: 'purchase-summary', label: 'Purchases', desc: 'Supplier bills and payment status', dates: true },
    { key: 'stock-movements', label: 'Stock movements', desc: 'Running quantity per tracked item', dates: true },
    { key: 'import-history', label: 'Import history', desc: 'Every uploaded report and its status' },
  ] },
]
const ALL = GROUPS.flatMap(g => g.items)
const NOT_MONEY = /qty|count|days|rows|lines|bills|batch|warnings|open_bills|phone/i
const DATE = /^(date|due_date|last_payment|oldest_open_bill|last_collection|report_date|uploaded)$/

function iso(d: Date) { return d.toLocaleDateString('en-CA') }
function presets() {
  const t = new Date(todayIso())
  const som = new Date(t.getFullYear(), t.getMonth(), 1)
  const lmS = new Date(t.getFullYear(), t.getMonth() - 1, 1), lmE = new Date(t.getFullYear(), t.getMonth(), 0)
  const d7 = new Date(t); d7.setDate(t.getDate() - 6)
  const fy = new Date(t.getMonth() >= 3 ? t.getFullYear() : t.getFullYear() - 1, 3, 1)
  return [
    { label: 'Today', from: iso(t), to: iso(t) }, { label: 'Last 7 days', from: iso(d7), to: iso(t) },
    { label: 'This month', from: iso(som), to: iso(t) }, { label: 'Last month', from: iso(lmS), to: iso(lmE) },
    { label: 'This FY', from: iso(fy), to: iso(t) }, { label: 'All time', from: '', to: '' },
  ]
}

export default function Reports() {
  const [sp, setSp] = useSearchParams()
  const [name, setName] = useState(sp.get('r') && ALL.some(a => a.key === sp.get('r')) ? sp.get('r')! : 'customer-outstanding')
  const [p, setP] = useState({ date_from: '', date_to: '', customer_id: '', account_id: '' })
  const [q, setQ] = useState('')
  const def = ALL.find(a => a.key === name)!
  useEffect(() => { setSp({ r: name }, { replace: true }) }, [name, setSp])
  const params = Object.entries(p).filter(([k, v]) => v && (def.dates || !k.startsWith('date')) && (k !== 'customer_id' || def.needs === 'customer') && (k !== 'account_id' || def.needs === 'account'))
  const qs = new URLSearchParams(params).toString()
  const { data: customers } = useAsync(() => api('/customers'))
  const { data: accounts } = useAsync(() => api('/accounts'))
  const blocked = (def.needs === 'customer' && !p.customer_id) || (def.needs === 'account' && !p.account_id)
  const { data: rep, error, loading } = useAsync(() => (blocked ? Promise.resolve(null) : api(`/reports/${name}?${qs}`)), [name, qs, blocked])

  const cell = (c: string, v: any) => {
    if (v === null || v === undefined || v === '') return ''
    if (DATE.test(c)) return fmtDate(String(v))
    if (typeof v === 'string' && /^-?\d+(\.\d+)?$/.test(v) && !NOT_MONEY.test(c)) return fmt(v)
    return String(v)
  }
  const isNum = (c: string, rows: any[]) => rows.some(r => typeof r[c] === 'string' && /^-?\d+(\.\d+)?$/.test(r[c])) && !/phone/i.test(c)
  const rows = (rep?.rows || []).filter((r: any) => !q || JSON.stringify(r).toLowerCase().includes(q.toLowerCase()))
  const exportCsv = async () => {
    try { await downloadCsv(`/reports/${name}?${qs}&format=csv`, `${name}${p.date_from ? '_' + p.date_from : ''}${p.date_to ? '_' + p.date_to : ''}.csv`); toast('CSV downloaded') }
    catch (e: any) { toast(e.message || 'Export failed', 'error') }
  }

  return (
    <div className="reports">
      <div className="page-head">
        <div><h1>Reports</h1><p className="muted">Every figure comes from the posted ledger; CSV export matches what you see.</p></div>
        <div className="page-actions no-print">
          <button className="btn secondary" disabled={!rep} onClick={exportCsv}><Icon name="download" size={16} /> Export CSV</button>
          <button className="btn secondary" disabled={!rep} onClick={() => window.print()}><Icon name="printer" size={16} /> Print</button>
        </div>
      </div>
      <div className="reports-layout">
        <nav className="report-nav no-print" aria-label="Reports">
          {GROUPS.map(g => (
            <div key={g.title} className="report-group">
              <div className="side-group-title"><Icon name={g.icon} size={13} /> {g.title}</div>
              {g.items.map(it => (
                <button key={it.key} className={`report-link ${it.key === name ? 'active' : ''}`} onClick={() => setName(it.key)}>
                  <b>{it.label}</b><small>{it.desc}</small>
                </button>
              ))}
            </div>
          ))}
        </nav>
        <section className="report-body">
          <div className="panel">
            <div className="toolbar no-print">
              {def.dates && <>
                <Field label="From"><input type="date" value={p.date_from} onChange={e => setP({ ...p, date_from: e.target.value })} /></Field>
                <Field label="To"><input type="date" value={p.date_to} onChange={e => setP({ ...p, date_to: e.target.value })} /></Field>
              </>}
              {def.needs === 'customer' && <Field label="Customer"><select value={p.customer_id} onChange={e => setP({ ...p, customer_id: e.target.value })}><option value="">Select a customer…</option>{(customers || []).map((c: any) => <option key={c.id} value={c.id}>{c.name}{c.phone ? ` · ${c.phone}` : ''}</option>)}</select></Field>}
              {def.needs === 'account' && <Field label="Account"><select value={p.account_id} onChange={e => setP({ ...p, account_id: e.target.value })}><option value="">Select an account…</option>{(accounts || []).map((a: any) => <option key={a.id} value={a.id}>{a.name}</option>)}</select></Field>}
              <Field label="Filter rows"><input value={q} onChange={e => setQ(e.target.value)} placeholder="Type to filter…" /></Field>
            </div>
            {def.dates && <div className="chips no-print">{presets().map(pr => (
              <button key={pr.label} className={`chip ${p.date_from === pr.from && p.date_to === pr.to ? 'active' : ''}`} onClick={() => setP({ ...p, date_from: pr.from, date_to: pr.to })}>{pr.label}</button>
            ))}</div>}
          </div>
          <ErrorBox msg={error} />
          {blocked && <div className="empty-state panel"><Icon name="search" size={28} /><div>Choose a {def.needs} to see this report.</div></div>}
          {loading && !rep && !blocked && <div className="skeleton" style={{ height: 240 }} />}
          {rep && !blocked && <>
            <div className="report-title"><h2>{rep.title}</h2><span className="muted small">{p.date_from || p.date_to ? `${fmtDate(p.date_from) || 'start'} → ${fmtDate(p.date_to) || 'today'}` : 'All dates'} · {rows.length} row(s)</span></div>
            {Object.keys(rep.totals).length > 0 && (
              <div className="summary-strip">{Object.entries(rep.totals).map(([k, v]) => (
                <div key={k}><span>{k.replace(/_/g, ' ')}</span><b className={String(v).startsWith('-') ? 'neg' : ''}>{/qty/.test(k) ? String(v) : fmt(v)}</b></div>
              ))}</div>
            )}
            <div className="table-wrap"><table>
              <thead><tr>{rep.columns.map((c: string) => <th key={c} className={isNum(c, rep.rows) ? 'n' : ''}>{c.replace(/_/g, ' ')}</th>)}</tr></thead>
              <tbody>
                {rows.map((r: any, i: number) => <tr key={i} className={r.section === 'Result' ? 'total-row' : ''}>{rep.columns.map((c: string) => <td key={c} className={isNum(c, rep.rows) ? 'n' : ''}>{cell(c, r[c])}</td>)}</tr>)}
                {!rows.length && <tr><td colSpan={rep.columns.length}><div className="empty-mini"><Icon name="info" /> No data for these filters.</div></td></tr>}
              </tbody>
            </table></div>
          </>}
        </section>
      </div>
    </div>
  )
}
