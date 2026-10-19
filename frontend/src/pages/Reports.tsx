import { useState } from 'react'
import { api, downloadCsv, fmt, fmtDate } from '../api'
import { ErrorBox, Field, PrintButton, useAsync } from '../ui'

const LABELS: Record<string, string> = {
  'customer-outstanding': 'Customer outstanding', 'customer-statement': 'Customer statement', 'udhari-collections': 'Udhari collections',
  'bill-outstanding': 'Bill outstanding detail', 'expense-summary': 'Expense summary', 'unpaid-expenses': 'Unpaid / part-paid expenses',
  'paid-by-source': 'Paid by / source', 'owner-ledger': 'Owner reimbursement ledger', cashbook: 'Cashbook', 'daily-closing': 'Daily closing',
  'item-sales-summary': 'Item sales summary', 'purchase-summary': 'Purchase summary', 'stock-movements': 'Stock movement ledger', 'import-history': 'Import history',
}
const MONEY = /(total|due|paid|amount|balance|debit|credit|incurred|unpaid|collected|adjusted|outstanding|advance|cash|sales|expected|variance|in|out|running)$/i
const DATE = /^(date|due_date|last_payment|oldest_open_bill|last_collection|report_date)$/

export default function Reports() {
  const [name, setName] = useState('customer-outstanding')
  const [p, setP] = useState({ date_from: '', date_to: '', customer_id: '', account_id: '', item_id: '' })
  const qs = new URLSearchParams(Object.entries(p).filter(([, v]) => v)).toString()
  const { data: customers } = useAsync(() => api('/customers'))
  const { data: accounts } = useAsync(() => api('/accounts'))
  const { data: rep, error, loading } = useAsync(() => ((name === 'customer-statement' && !p.customer_id) || (name === 'cashbook' && !p.account_id)) ? Promise.resolve(null) : api(`/reports/${name}?${qs}`), [name, qs])
  const cell = (c: string, v: any) => v === null || v === undefined || v === '' ? '' : DATE.test(c) ? fmtDate(v) : (typeof v === 'string' && /^-?\d+(\.\d+)?$/.test(v) && MONEY.test(c) && !/qty|count|days|rows|lines|bills|batch/i.test(c)) ? fmt(v) : String(v)
  return (
    <>
      <h1>Reports</h1>
      <div className="row no-print">
        <Field label="Report"><select value={name} onChange={e => setName(e.target.value)}>{Object.entries(LABELS).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></Field>
        <Field label="From"><input type="date" value={p.date_from} onChange={e => setP({ ...p, date_from: e.target.value })} /></Field>
        <Field label="To"><input type="date" value={p.date_to} onChange={e => setP({ ...p, date_to: e.target.value })} /></Field>
        {name === 'customer-statement' && <Field label="Customer"><select value={p.customer_id} onChange={e => setP({ ...p, customer_id: e.target.value })}><option value="">— select —</option>{(customers || []).map((c: any) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></Field>}
        {name === 'cashbook' && <Field label="Account"><select value={p.account_id} onChange={e => setP({ ...p, account_id: e.target.value })}><option value="">— select —</option>{(accounts || []).map((a: any) => <option key={a.id} value={a.id}>{a.name}</option>)}</select></Field>}
        <button className="btn secondary" disabled={!rep} onClick={() => downloadCsv(`/reports/${name}?${qs}&format=csv`, `${name}.csv`)}>Export CSV</button><PrintButton />
      </div>
      <ErrorBox msg={error} />
      {loading && <p>Loading…</p>}
      {rep && <><h2>{rep.title}</h2><div className="table-wrap"><table>
        <thead><tr>{rep.columns.map((c: string) => <th key={c}>{c.replace(/_/g, ' ')}</th>)}</tr></thead>
        <tbody>{rep.rows.map((r: any, i: number) => <tr key={i}>{rep.columns.map((c: string) => <td key={c} className={MONEY.test(c) ? 'n' : ''}>{cell(c, r[c])}</td>)}</tr>)}
          {!rep.rows.length && <tr><td colSpan={rep.columns.length} className="muted">No data for these filters.</td></tr>}
          {Object.keys(rep.totals).length > 0 && <tr className="total-row"><td colSpan={rep.columns.length}>{Object.entries(rep.totals).map(([k, v]) => `${k.replace(/_/g, ' ')}: ${/qty/.test(k) ? v : fmt(v)}`).join('   ·   ')}</td></tr>}</tbody></table></div></>}
    </>
  )
}
