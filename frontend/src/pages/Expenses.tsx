import { useState } from 'react'
import { api, fmt, fmtDate, num, openAttachment, todayIso } from '../api'
import { AccountSelect, MethodSelect, useAccounts } from '../shared'
import { Badge, ErrorBox, Field, Modal, Notice, useAsync, useSubmit } from '../ui'
import type { User } from '../App'

const CATEGORIES = ['Gas', 'Vegetables', 'Meat & Fish', 'Salary', 'Rent', 'Electricity', 'Repairs', 'Packaging', 'Transport', 'Misc']

function PaymentForm({ expense, onDone, accounts }: { expense: any; onDone: () => void; accounts: any[] }) {
  const [p, setP] = useState({ amount: String(expense.due ?? ''), paid_date: todayIso(), method: 'cash', funded_by: 'account', paid_by: '', reference: '', notes: '', reimbursable: true })
  const [acct, setAcct] = useState<number | ''>('')
  const { error, busy, submit } = useSubmit()
  return (
    <div className="card"><h3>Add payment</h3><ErrorBox msg={error} />
      <div className="form-grid">
        <Field label="Amount (₹)" hint={`Remaining payable ${fmt(expense.due)}`}><input inputMode="decimal" value={p.amount} onChange={e => setP({ ...p, amount: e.target.value })} /></Field>
        <Field label="Date"><input type="date" value={p.paid_date} onChange={e => setP({ ...p, paid_date: e.target.value })} /></Field>
        <Field label="Funded by"><select value={p.funded_by} onChange={e => setP({ ...p, funded_by: e.target.value })}>
          <option value="account">Restaurant account (cash / bank / UPI…)</option><option value="owner">Owner — personal money</option></select></Field>
        <MethodSelect value={p.method} onChange={m => setP({ ...p, method: m })} />
        {p.funded_by === 'account' && <AccountSelect accounts={accounts} method={p.method} value={acct} onChange={setAcct} label="Paid from account" />}
        <Field label="Paid by (person)"><input value={p.paid_by} onChange={e => setP({ ...p, paid_by: e.target.value })} /></Field>
        <Field label="Reference"><input value={p.reference} onChange={e => setP({ ...p, reference: e.target.value })} /></Field>
      </div>
      {p.funded_by === 'owner' && <>
        <Notice msg="Recorded once as an expense. The restaurant's cash/bank is NOT reduced; an amount owed to the owner is created." />
        <label className="check"><input type="checkbox" checked={p.reimbursable} onChange={e => setP({ ...p, reimbursable: e.target.checked })} />Reimbursable (uncheck if it is a non-reimbursable owner contribution)</label></>}
      <button className="btn" disabled={busy} onClick={() => submit('Payment recorded', async () => { await api(`/expenses/${expense.id}/payments`, { body: { ...p, account_id: p.funded_by === 'account' ? acct : null } }); onDone() })}>Save payment</button>
    </div>
  )
}

function ExpenseModal({ id, user, onClose, onChange }: { id: number; user: User; onClose: () => void; onChange: () => void }) {
  const accounts = useAccounts()
  const { data: e, reload } = useAsync(() => api(`/expenses/${id}`), [id])
  const [reason, setReason] = useState('')
  const [voiding, setVoiding] = useState<number | null>(null)
  const { error, submit } = useSubmit()
  if (!e) return null
  return (
    <Modal title={`${e.category} — ${fmt(e.total)}`} onClose={onClose}>
      <dl className="kv"><dt>Status</dt><dd><Badge status={e.status} /></dd><dt>Date</dt><dd>{fmtDate(e.expense_date)}</dd><dt>Payee</dt><dd>{e.payee_name || '—'}</dd>
        <dt>Paid / Due</dt><dd>{fmt(e.paid)} / <b>{fmt(e.due)}</b></dd><dt>Due date</dt><dd>{fmtDate(e.due_date)}</dd><dt>Description</dt><dd>{e.description}</dd>
        {e.attachment && <><dt>Attachment</dt><dd><button className="btn small secondary" onClick={() => openAttachment(e.attachment)}>Open bill / photo</button></dd></>}</dl>
      <ErrorBox msg={error} />
      <h3>Payments</h3>
      <div className="table-wrap"><table><thead><tr><th>Date</th><th className="n">Amount</th><th>Method</th><th>Source</th><th>Paid by</th><th>Status</th><th /></tr></thead>
        <tbody>{e.payments.map((p: any) => <tr key={p.id} className={p.status === 'voided' ? 'voided' : ''}><td>{fmtDate(p.paid_date)}</td><td className="n">{fmt(p.amount)}</td><td>{p.method}</td><td>{p.account}</td><td>{p.paid_by}</td><td><Badge status={p.status} /></td>
          <td>{user.role === 'admin' && p.status === 'posted' && <button className="btn small ghost" onClick={() => setVoiding(p.id)}>Void</button>}</td></tr>)}
          {!e.payments.length && <tr><td colSpan={7} className="muted">No payments — nothing has left any account.</td></tr>}</tbody></table></div>
      {voiding && <div className="card"><Field label="Reason for voiding this payment"><input value={reason} onChange={e => setReason(e.target.value)} /></Field>
        <button className="btn danger" onClick={() => submit('Payment voided', async () => { await api(`/expense-payments/${voiding}/void`, { body: { reason } }); setVoiding(null); setReason(''); reload(); onChange() })}>Confirm void</button></div>}
      {user.role === 'admin' && e.status !== 'voided' && !e.payments.some((p: any) => p.status === 'posted') && <div className="card"><Field label="Void this expense (entered by mistake) — reason"><input value={reason} onChange={ev => setReason(ev.target.value)} /></Field>
        <button className="btn danger" disabled={!reason.trim()} onClick={() => submit('Expense voided', async () => { await api(`/expenses/${id}/void`, { body: { reason } }); onChange(); onClose() })}>Void expense</button></div>}
      {e.status !== 'paid' && e.status !== 'voided' && <PaymentForm expense={e} accounts={accounts} onDone={() => { reload(); onChange() }} />}
    </Modal>
  )
}

function AddExpense({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const accounts = useAccounts()
  const { data: vendors, reload: rv } = useAsync(() => api('/vendors'))
  const [f, setF] = useState({ expense_date: todayIso(), category: 'Gas', description: '', vendor_id: '', payee_name: '', bill_ref: '', total: '', due_date: '', notes: '' })
  const [payNow, setPayNow] = useState(false)
  const [pay, setPay] = useState({ amount: '', method: 'cash', funded_by: 'account', paid_by: '' })
  const [acct, setAcct] = useState<number | ''>('')
  const [newVendor, setNewVendor] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const { error, busy, submit } = useSubmit()
  const save = () => submit('Expense saved', async () => {
    let attachment = ''
    if (file) { const fd = new FormData(); fd.append('file', file); attachment = (await api('/attachments', { form: fd })).attachment }
    let vendor_id: number | null = f.vendor_id ? Number(f.vendor_id) : null
    if (newVendor.trim()) { vendor_id = (await api('/vendors', { body: { name: newVendor } })).id }
    const payments = payNow ? [{ ...pay, account_id: pay.funded_by === 'account' ? acct : null, paid_date: f.expense_date }] : []
    await api('/expenses', { body: { ...f, vendor_id, due_date: f.due_date || null, attachment, payments } })
    rv(); onDone()
  })
  return (
    <Modal title="Add expense" onClose={onClose}><ErrorBox msg={error} />
      <div className="form-grid">
        <Field label="Date"><input type="date" value={f.expense_date} onChange={e => setF({ ...f, expense_date: e.target.value })} /></Field>
        <Field label="Category"><input list="cats" value={f.category} onChange={e => setF({ ...f, category: e.target.value })} /><datalist id="cats">{CATEGORIES.map(c => <option key={c} value={c} />)}</datalist></Field>
        <Field label="Amount (₹)"><input inputMode="decimal" value={f.total} onChange={e => setF({ ...f, total: e.target.value })} /></Field>
        <Field label="Vendor / payee"><select value={f.vendor_id} onChange={e => setF({ ...f, vendor_id: e.target.value })}><option value="">— none —</option>{(vendors || []).map((v: any) => <option key={v.id} value={v.id}>{v.name}</option>)}</select></Field>
        <Field label="…or new vendor"><input value={newVendor} onChange={e => setNewVendor(e.target.value)} /></Field>
        <Field label="Vendor bill no."><input value={f.bill_ref} onChange={e => setF({ ...f, bill_ref: e.target.value })} /></Field>
        <Field label="Due date"><input type="date" value={f.due_date} onChange={e => setF({ ...f, due_date: e.target.value })} /></Field>
        <Field label="Description"><input value={f.description} onChange={e => setF({ ...f, description: e.target.value })} /></Field>
        <Field label="Bill photo / PDF"><input type="file" accept=".pdf,.png,.jpg,.jpeg,.webp" onChange={e => setFile(e.target.files?.[0] || null)} /></Field>
      </div>
      <label className="check"><input type="checkbox" checked={payNow} onChange={e => setPayNow(e.target.checked)} />Paid (fully or partly) right now</label>
      {payNow && <div className="form-grid">
        <Field label="Amount paid now (₹)"><input inputMode="decimal" value={pay.amount} onChange={e => setPay({ ...pay, amount: e.target.value })} /></Field>
        <Field label="Funded by"><select value={pay.funded_by} onChange={e => setPay({ ...pay, funded_by: e.target.value })}><option value="account">Restaurant account</option><option value="owner">Owner personal money</option></select></Field>
        <MethodSelect value={pay.method} onChange={m => setPay({ ...pay, method: m })} />
        {pay.funded_by === 'account' && <AccountSelect accounts={accounts} method={pay.method} value={acct} onChange={setAcct} label="Paid from account" />}
        <Field label="Paid by (person)"><input value={pay.paid_by} onChange={e => setPay({ ...pay, paid_by: e.target.value })} /></Field></div>}
      <p className="muted">Status is derived from payments: add more payment splits later from the expense detail.</p>
      <button className="btn" disabled={busy} onClick={save}>Save expense <kbd className="kbd-sm kbd-accent" style={{ marginLeft: 6 }}>Ctrl+↵</kbd></button>
    </Modal>
  )
}

function ReimburseOwner({ onDone }: { onDone: () => void }) {
  const accounts = useAccounts()
  const { data: o, reload } = useAsync(() => api('/owner/ledger'))
  const [amount, setAmount] = useState('')
  const [method, setMethod] = useState('cash')
  const [acct, setAcct] = useState<number | ''>('')
  const { error, busy, submit } = useSubmit()
  if (!o) return null
  return (
    <div className="card"><h3>Owner reimbursement</h3>
      <p>Due to owner: <b>{fmt(o.balance.due_to_owner)}</b> · Funded {fmt(o.balance.owner_funded)} · Reimbursed {fmt(o.balance.reimbursed)} · Non-reimbursable contributions {fmt(o.balance.contributions)}</p>
      <ErrorBox msg={error} />
      <div className="form-grid"><Field label="Amount (₹)"><input inputMode="decimal" value={amount} onChange={e => setAmount(e.target.value)} /></Field>
        <MethodSelect value={method} onChange={setMethod} /><AccountSelect accounts={accounts} method={method} value={acct} onChange={setAcct} label="Paid from account" /></div>
      <button className="btn secondary" disabled={busy || !(num(amount) > 0)} onClick={() => submit('Owner reimbursed', async () => { await api('/owner/reimburse', { body: { amount, method, account_id: acct } }); setAmount(''); reload(); onDone() })}>Reimburse owner</button>
      <p className="muted">This reduces the account and the owed balance. It does not create a new expense.</p>
    </div>
  )
}

export default function Expenses({ user }: { user: User }) {
  const sp = new URLSearchParams(window.location.search)
  const [filters, setFilters] = useState({ status: '', category: '', q: sp.get('q') || '', date_from: '', date_to: '', source: '', paid_by: '' })
  const qs = new URLSearchParams(Object.entries(filters).filter(([, v]) => v)).toString()
  const { data, error, reload } = useAsync(() => api('/expenses?' + qs), [qs])
  const accounts = useAccounts()
  const [adding, setAdding] = useState(false)
  const [openId, setOpenId] = useState<number | null>(sp.get('open') ? Number(sp.get('open')) : null)
  const [owner, setOwner] = useState(false)
  const total = (data || []).reduce((s: number, e: any) => s + num(e.due), 0)
  return (
    <>
      <div className="row between"><h1>Expenses & Payables</h1><div><button className="btn" onClick={() => setAdding(true)}>+ Add expense <kbd className="kbd-sm kbd-accent" style={{ marginLeft: 4 }}>F9</kbd></button> <button className="btn secondary" onClick={() => setOwner(!owner)}>Reimburse owner</button></div></div>
      {owner && <ReimburseOwner onDone={reload} />}
      <div className="row">
        <Field label="Status"><select value={filters.status} onChange={e => setFilters({ ...filters, status: e.target.value })}><option value="">All</option><option value="due">Unpaid + part-paid</option><option value="unpaid">Unpaid</option><option value="partial">Partially paid</option><option value="paid">Paid</option><option value="overdue">Overdue</option></select></Field>
        <Field label="Category"><input value={filters.category} onChange={e => setFilters({ ...filters, category: e.target.value })} /></Field>
        <Field label="From"><input type="date" value={filters.date_from} onChange={e => setFilters({ ...filters, date_from: e.target.value })} /></Field>
        <Field label="To"><input type="date" value={filters.date_to} onChange={e => setFilters({ ...filters, date_to: e.target.value })} /></Field>
        <Field label="Paid from"><select value={filters.source} onChange={e => setFilters({ ...filters, source: e.target.value })}><option value="">Any</option>{accounts.map(a => <option key={a.id}>{a.name}</option>)}<option>Owner (personal funds)</option></select></Field>
        <Field label="Paid by"><input value={filters.paid_by} onChange={e => setFilters({ ...filters, paid_by: e.target.value })} /></Field>
        <Field label="Search"><input value={filters.q} onChange={e => setFilters({ ...filters, q: e.target.value })} /></Field>
      </div>
      <ErrorBox msg={error} />
      <div className="table-wrap"><table>
        <thead><tr><th>Date</th><th>Category</th><th>Payee</th><th>Description</th><th className="n">Amount</th><th className="n">Paid</th><th className="n">Payable</th><th>Source(s)</th><th>Last paid</th><th>Status</th></tr></thead>
        <tbody>{(data || []).map((e: any) => <tr key={e.id} className="clickable" onClick={() => setOpenId(e.id)}>
          <td>{fmtDate(e.expense_date)}</td><td>{e.category}</td><td>{e.payee_name}</td><td>{e.description}</td><td className="n">{fmt(e.total)}</td><td className="n">{fmt(e.paid)}</td><td className="n">{fmt(e.due)}</td>
          <td>{e.sources.join(', ')}</td><td>{fmtDate(e.last_payment_date)}</td><td><Badge status={e.status} />{e.overdue && <span className="badge bad">overdue</span>}</td></tr>)}
          {!(data || []).length && <tr><td colSpan={10} className="muted">No expenses match.</td></tr>}
          <tr className="total-row"><td colSpan={6}>Total payable in this view</td><td className="n">{fmt(total)}</td><td colSpan={3} /></tr></tbody></table></div>
      {adding && <AddExpense onClose={() => setAdding(false)} onDone={() => { setAdding(false); reload() }} />}
      {openId && <ExpenseModal id={openId} user={user} onClose={() => setOpenId(null)} onChange={reload} />}
    </>
  )
}
