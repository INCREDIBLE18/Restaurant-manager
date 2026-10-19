import { useEffect, useState } from 'react'
import { api } from './api'
import { ErrorBox, Field, useSubmit } from './ui'

export type Account = { id: number; name: string; type: string; is_physical_cash: boolean; active: boolean; balance: string }
export const METHODS = ['cash', 'upi', 'card', 'bank', 'other']

export function useAccounts() {
  const [accounts, setAccounts] = useState<Account[]>([])
  useEffect(() => { api('/accounts').then(a => setAccounts(a.filter((x: Account) => x.active))).catch(() => {}) }, [])
  return accounts
}

/** Account picker restricted to accounts valid for the method (cash => physical cash drawer only). */
export function AccountSelect({ accounts, method, value, onChange, label = 'Money goes into account' }:
  { accounts: Account[]; method: string; value: number | ''; onChange: (v: number | '') => void; label?: string }) {
  const valid = accounts.filter(a => (method === 'cash') === a.is_physical_cash)
  useEffect(() => {
    if (value === '' || !valid.some(a => a.id === value)) onChange(valid[0]?.id ?? '')
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [method, accounts.length])
  return (
    <Field label={label} hint={method === 'cash' ? 'Cash must go to the physical cash drawer' : 'Non-cash methods use a non-cash account'}>
      <select value={value} onChange={e => onChange(e.target.value ? Number(e.target.value) : '')}>
        {valid.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
      </select>
    </Field>
  )
}

export function MethodSelect({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <Field label="Payment method">
      <select value={value} onChange={e => onChange(e.target.value)}>{METHODS.map(m => <option key={m} value={m}>{m.toUpperCase()}</option>)}</select>
    </Field>
  )
}

export type Customer = { id: number; name: string; phone: string; outstanding: string; advance: string }

/** Search existing customers by name/phone with keyboard arrow & enter navigation, or create a new one inline. */
export function CustomerPicker({ value, onChange }: { value: Customer | null; onChange: (c: Customer | null) => void }) {
  const [q, setQ] = useState('')
  const [list, setList] = useState<Customer[]>([])
  const [highlightIndex, setHighlightIndex] = useState(0)
  const [adding, setAdding] = useState(false)
  const [name, setName] = useState('')
  const [phone, setPhone] = useState('')
  const { error, submit, setError } = useSubmit()

  useEffect(() => {
    if (value || q.trim().length < 1) { setList([]); return }
    const t = setTimeout(() => {
      api('/customers?q=' + encodeURIComponent(q)).then(res => {
        setList(res)
        setHighlightIndex(0)
      }).catch(() => {})
    }, 180)
    return () => clearTimeout(t)
  }, [q, value])

  const create = (allow = false) => submit(async () => {
    const c = await api('/customers', { body: { name, phone, allow_duplicate: allow } })
    onChange(c); setAdding(false)
  })

  const handleInputKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (list.length > 0) {
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        setHighlightIndex(prev => Math.min(list.length - 1, prev + 1))
      } else if (e.key === 'ArrowUp') {
        e.preventDefault()
        setHighlightIndex(prev => Math.max(0, prev - 1))
      } else if (e.key === 'Enter') {
        e.preventDefault()
        if (list[highlightIndex]) {
          onChange(list[highlightIndex])
        }
      }
    }
    if ((e.altKey && e.key.toLowerCase() === 'n') || (e.ctrlKey && e.key.toLowerCase() === 'n')) {
      e.preventDefault()
      setAdding(true)
      setName(q)
    }
  }

  if (value) return (
    <div className="row between" style={{ background: 'var(--panel-elevated)', padding: '10px 14px', borderRadius: 10, border: '1px solid var(--line)', marginBottom: 12 }}>
      <div>
        <span style={{ fontSize: '0.78rem', color: 'var(--muted)', display: 'block', textTransform: 'uppercase', fontWeight: 600 }}>Selected Customer</span>
        <b style={{ fontSize: '1.05rem', color: 'var(--ink)' }}>{value.name}</b> <span className="muted" style={{ marginLeft: 8 }}>{value.phone}</span>
      </div>
      <button type="button" className="btn small ghost" onClick={() => onChange(null)}>Change <kbd className="kbd-sm" style={{ marginLeft: 4 }}>Esc</kbd></button>
    </div>
  )

  return (
    <div style={{ marginBottom: 14 }}>
      <Field label="Customer (search name or phone)" hint="Use ↑ ↓ arrows to select, ↵ Enter to choose">
        <input
          value={q}
          onChange={e => setQ(e.target.value)}
          onKeyDown={handleInputKeyDown}
          placeholder="Type customer name or mobile number…"
          autoFocus
        />
      </Field>

      {list.length > 0 && (
        <div className="table-wrap" style={{ margin: '6px 0 10px', maxHeight: 220 }}>
          <table>
            <thead>
              <tr>
                <th>Customer</th>
                <th>Phone</th>
                <th className="n">Outstanding</th>
                <th style={{ width: 60 }}>Action</th>
              </tr>
            </thead>
            <tbody>
              {list.slice(0, 8).map((c, idx) => {
                const isSelected = idx === highlightIndex
                return (
                  <tr
                    key={c.id}
                    className={`clickable ${isSelected ? 'active-row' : ''}`}
                    onClick={() => onChange(c)}
                    onMouseEnter={() => setHighlightIndex(idx)}
                  >
                    <td><b>{c.name}</b></td>
                    <td>{c.phone}</td>
                    <td className={`n ${Number(c.outstanding) > 0 ? 'neg' : ''}`}>
                      {Number(c.outstanding) > 0 ? 'Owes ₹' + c.outstanding : '—'}
                    </td>
                    <td>{isSelected ? <kbd className="kbd-sm kbd-accent">↵</kbd> : null}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {!adding ? (
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 6 }}>
          <button type="button" className="btn small secondary" onClick={() => { setAdding(true); setName(q) }}>
            + New customer <kbd className="kbd-sm" style={{ marginLeft: 4 }}>Alt+N</kbd>
          </button>
          {list.length > 0 && (
            <span style={{ fontSize: '0.78rem', color: 'var(--muted)' }}>
              Press <kbd className="kbd-sm">↑</kbd> <kbd className="kbd-sm">↓</kbd> then <kbd className="kbd-sm">↵</kbd>
            </span>
          )}
        </div>
      ) : (
        <div className="card" style={{ marginTop: 10, border: '1px solid var(--brand)' }}>
          <div style={{ fontWeight: 700, marginBottom: 8, color: 'var(--brand)' }}>Quick Add New Customer</div>
          <ErrorBox msg={error} />
          {error.includes('similar customer') && (
            <button type="button" className="btn small secondary" style={{ marginBottom: 10 }} onClick={() => create(true)}>
              Create anyway (separate customer)
            </button>
          )}
          <div className="form-grid">
            <Field label="Name"><input value={name} onChange={e => setName(e.target.value)} autoFocus /></Field>
            <Field label="Phone"><input value={phone} onChange={e => setPhone(e.target.value)} placeholder="10-digit mobile" /></Field>
          </div>
          <p style={{ margin: '8px 0 0' }}>
            <button type="button" className="btn small" onClick={() => create()}>Save customer <kbd className="kbd-sm" style={{ marginLeft: 4 }}>↵</kbd></button>{' '}
            <button type="button" className="btn small ghost" onClick={() => { setAdding(false); setError('') }}>Cancel <kbd className="kbd-sm" style={{ marginLeft: 4 }}>Esc</kbd></button>
          </p>
        </div>
      )}
    </div>
  )
}
