import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, fmt, fmtDate, num, todayIso } from '../api'
import { AccountSelect, Customer, CustomerPicker, MethodSelect, useAccounts } from '../shared'
import { ErrorBox, Field, Notice, useSubmit } from '../ui'

export default function ReceivePayment() {
  const [params] = useSearchParams()
  const accounts = useAccounts()
  const [cust, setCust] = useState<Customer | null>(null)
  const [bills, setBills] = useState<any[]>([])
  const [amount, setAmount] = useState('')
  const [alloc, setAlloc] = useState<Record<number, string>>({})
  const [f, setF] = useState({ receipt_date: todayIso(), method: 'cash', reference: '', received_by: '', notes: '' })
  const [acct, setAcct] = useState<number | ''>('')
  const [done, setDone] = useState<any>(null)
  const { error, busy, submit } = useSubmit()

  useEffect(() => {
    const cid = params.get('customer')
    if (cid) api(`/customers/${cid}`).then(setCust).catch(() => {})
  }, [params])

  useEffect(() => {
    if (!cust) { setBills([]); return }
    api(`/credit-bills?customer_id=${cust.id}&open_only=true`).then(setBills).catch(() => {})
  }, [cust, done])

  const allocated = Object.values(alloc).reduce((s, v) => s + num(v), 0)
  const unallocated = num(amount) - allocated
  const totalOutstanding = bills.reduce((s, b) => s + num(b.outstanding), 0)

  const suggest = async (targetAmount?: number) => {
    const val = targetAmount ?? num(amount)
    if (!cust || !(val > 0)) return
    const s = await api(`/receipts/suggest-allocation?customer_id=${cust.id}&amount=${val}`)
    const m: Record<number, string> = {}
    s.allocations.forEach((a: any) => { m[a.bill_id] = a.amount })
    setAlloc(m)
  }

  const applyFullOutstanding = () => {
    if (totalOutstanding > 0) {
      setAmount(totalOutstanding.toFixed(2))
      suggest(totalOutstanding)
    }
  }

  const save = () => submit(async () => {
    if (!cust) throw new Error('Select a customer')
    const allocations = Object.entries(alloc).filter(([, v]) => num(v) > 0).map(([bill_id, amt]) => ({ bill_id: Number(bill_id), amount: amt }))
    if (allocated > num(amount)) throw new Error('Allocated amount is more than the amount received')
    const r = await api('/receipts', { body: { ...f, customer_id: cust.id, amount, account_id: acct, allocations } })
    setDone(r); setAmount(''); setAlloc({})
  })

  const handleCardKeyDown = (e: React.KeyboardEvent) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault()
      if (num(amount) > 0 && !busy) save()
    }
    if (e.key === 'F10') {
      e.preventDefault()
      if (num(amount) > 0 && !busy) save()
    }
    if (e.altKey && e.key.toLowerCase() === 's') {
      e.preventDefault()
      suggest()
    }
  }

  return (
    <>
      <div className="row between">
        <h1>Receive payment</h1>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <span className="muted" style={{ fontSize: '0.82rem' }}>Quick save:</span>
          <kbd className="kbd-sm kbd-accent">Ctrl+↵</kbd>
          <span className="muted" style={{ fontSize: '0.82rem' }}>or</span>
          <kbd className="kbd-sm">F10</kbd>
        </div>
      </div>

      {done && <Notice kind="ok" msg={`Receipt ${done.receipt_no} saved: ${fmt(done.amount)} ${done.unallocated > 0 ? `(unallocated advance ${fmt(done.unallocated)})` : ''}.`} />}

      <div className="card" onKeyDown={handleCardKeyDown}>
        <ErrorBox msg={error} />
        <CustomerPicker value={cust} onChange={c => { setCust(c); setDone(null); setAlloc({}) }} />

        {cust && <>
          <div className="row between" style={{ marginTop: 14 }}>
            <h2 style={{ margin: 0 }}>Open bills</h2>
            {totalOutstanding > 0 && (
              <span style={{ fontSize: '0.9rem', color: 'var(--muted)' }}>
                Total Due: <b style={{ color: 'var(--bad)', fontSize: '1.1rem' }}>{fmt(totalOutstanding)}</b>
              </span>
            )}
          </div>

          <div className="table-wrap"><table>
            <thead><tr><th>Bill</th><th>Date</th><th>Age</th><th className="n">Total</th><th className="n">Collected</th><th className="n">Outstanding</th><th className="n">Apply (₹)</th></tr></thead>
            <tbody>{bills.map(b => <tr key={b.id}>
              <td><b>{b.bill_no}</b></td><td>{fmtDate(b.business_date)}</td><td>{b.age_days} d</td><td className="n">{fmt(b.total)}</td><td className="n">{fmt(b.collected)}</td><td className="n" style={{ color: 'var(--bad)', fontWeight: 600 }}>{fmt(b.outstanding)}</td>
              <td className="n"><input className="inp" style={{ width: 110, textAlign: 'right' }} inputMode="decimal" value={alloc[b.id] ?? ''} onChange={e => setAlloc(p => ({ ...p, [b.id]: e.target.value }))} aria-label={`Apply to ${b.bill_no}`} /></td></tr>)}
              {!bills.length && <tr><td colSpan={7} className="muted">No open bills. Any amount received will be kept as customer advance.</td></tr>}</tbody></table></div>

          <div className="form-grid">
            <Field label="Amount received (₹)"><input inputMode="decimal" value={amount} onChange={e => setAmount(e.target.value)} placeholder="0.00" autoFocus /></Field>
            <Field label="Date"><input type="date" value={f.receipt_date} onChange={e => setF({ ...f, receipt_date: e.target.value })} /></Field>
            <MethodSelect value={f.method} onChange={m => setF({ ...f, method: m })} />
            <AccountSelect accounts={accounts} method={f.method} value={acct} onChange={setAcct} />
            <Field label="Reference / transaction ID"><input value={f.reference} onChange={e => setF({ ...f, reference: e.target.value })} placeholder="UPI Ref / UTR / Cheque" /></Field>
            <Field label="Received by"><input value={f.received_by} onChange={e => setF({ ...f, received_by: e.target.value })} placeholder="Cashier name" /></Field>
            <Field label="Notes"><input value={f.notes} onChange={e => setF({ ...f, notes: e.target.value })} /></Field>
          </div>

          {/* Rapid Tender Presets */}
          <div className="tender-presets">
            <span className="tender-preset-label">Quick Tender:</span>
            {totalOutstanding > 0 && (
              <button type="button" className="tender-btn" style={{ borderColor: 'var(--brand)', color: 'var(--brand)', fontWeight: 700 }} onClick={applyFullOutstanding}>
                Settle Full ({fmt(totalOutstanding)})
              </button>
            )}
            <button type="button" className="tender-btn" onClick={() => setAmount('100')}>₹100</button>
            <button type="button" className="tender-btn" onClick={() => setAmount('200')}>₹200</button>
            <button type="button" className="tender-btn" onClick={() => setAmount('500')}>₹500</button>
            <button type="button" className="tender-btn" onClick={() => setAmount('1000')}>₹1000</button>
            <button type="button" className="tender-btn" onClick={() => setAmount('2000')}>₹2000</button>
          </div>

          <div className="row" style={{ alignItems: 'center', marginTop: 10 }}>
            <button className="btn secondary small" onClick={() => suggest()} disabled={!(num(amount) > 0)}>
              Suggest oldest bill first <kbd className="kbd-sm" style={{ marginLeft: 4 }}>Alt+S</kbd>
            </button>
            <div style={{ fontSize: '0.9rem' }}>
              Allocated <b>{fmt(allocated)}</b> · {unallocated >= 0 ? <>Unallocated advance <b style={{ color: 'var(--good)' }}>{fmt(unallocated)}</b></> : <span className="neg">Over-allocated by {fmt(-unallocated)}</span>}
            </div>
          </div>

          {unallocated > 0 && num(amount) > 0 && <Notice kind="warn" msg="Money not allocated to a bill is stored as a customer advance (not discarded)." />}

          <p style={{ marginTop: 18 }}>
            <button className="btn" disabled={busy || !(num(amount) > 0)} onClick={save}>
              Save receipt <kbd className="kbd-sm kbd-accent" style={{ marginLeft: 6 }}>Ctrl+↵</kbd>
            </button>{' '}
            <Link className="btn ghost" to={`/udhari/${cust.id}`}>View ledger</Link>
          </p>
        </>}
      </div>
    </>
  )
}
