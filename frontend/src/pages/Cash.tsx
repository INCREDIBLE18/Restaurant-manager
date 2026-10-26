import { useEffect, useState } from 'react'
import { api, fmt, fmtDate, num, todayIso } from '../api'
import { Badge, ErrorBox, Field, Notice, useAsync, useSubmit } from '../ui'
import type { User } from '../App'

const LINES: [string, string, 1 | -1][] = [
  ['cash_udhari_collections', 'Cash collected against udhari (old + bill-time)', 1], ['other_cash_in', 'Other cash in', 1], ['transfers_in', 'Transfers in', 1],
  ['cash_expense_payments', 'Cash paid for expenses', -1], ['owner_reimbursements', 'Owner reimbursements paid in cash', -1], ['cash_refunds', 'Cash refunds', -1],
  ['cash_withdrawals', 'Cash withdrawals', -1], ['other_cash_out', 'Other cash out', -1], ['transfers_out', 'Transfers out (e.g. bank deposit)', -1],
]

function DayClose({ user }: { user: User }) {
  const [date, setDate] = useState(todayIso())
  const { data: d, error, reload, setData } = useAsync(() => api(`/day-closes/${date}`), [date])
  const [f, setF] = useState<any>({})
  const { error: err2, busy, submit } = useSubmit()
  const [reopenReason, setReopenReason] = useState('')
  const [showDenom, setShowDenom] = useState(false)
  const [denoms, setDenoms] = useState<Record<string, string>>({
    '500': '', '200': '', '100': '', '50': '', '20': '', '10': '', 'coins': '',
  })

  useEffect(() => {
    if (d) setF({ opening_cash: d.opening_cash, opening_note: d.opening_note, cash_sales: d.cash_sales, pos_total_sales: d.pos_total_sales ?? '', upi_sales: d.upi_sales ?? '',
      card_sales: d.card_sales ?? '', other_sales: d.other_sales ?? '', credit_sales: d.credit_sales ?? '', physical_counted: d.physical_counted ?? '', variance_reason: d.variance_reason })
  }, [d?.business_date, d?.status, d?.finalized_at])
  const locked = d?.status === 'finalized'
  const set = (k: string, v: string) => setF((p: any) => ({ ...p, [k]: v }))
  const save = () => submit('Draft saved', async () => setData(await api(`/day-closes/${date}`, { method: 'PUT', body: f })))
  const finalize = () => submit('Day finalized', async () => setData(await api(`/day-closes/${date}/finalize`, { body: f })))
  // live preview (display only; the backend recomputes on save/finalize)
  const ledgerNet = d ? LINES.reduce((s, [k, , sign]) => s + sign * num(d.ledger[k]), 0) : 0
  const expectedPreview = num(f.opening_cash) + num(f.cash_sales) + ledgerNet
  const variancePreview = f.physical_counted !== '' && f.physical_counted != null ? num(f.physical_counted) - expectedPreview : null

  const denomTotal = num(denoms['500']) * 500 + num(denoms['200']) * 200 + num(denoms['100']) * 100 +
    num(denoms['50']) * 50 + num(denoms['20']) * 20 + num(denoms['10']) * 10 + num(denoms['coins'])

  const applyDenom = () => {
    set('physical_counted', denomTotal.toFixed(2))
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault()
      if (!locked && !busy) save()
    }
  }

  return (
    <div onKeyDown={handleKeyDown}>
      <div className="row between">
        <div style={{ display: 'flex', gap: 12, alignItems: 'flex-end' }}>
          <Field label="Business date"><input type="date" value={date} onChange={e => setDate(e.target.value)} /></Field>
          {d && <div style={{ marginBottom: 8 }}>Status: <Badge status={d.status} /> {d.finalized_at && <span className="muted" style={{ marginLeft: 6 }}>finalized {fmtDate(d.finalized_at)}</span>}</div>}
        </div>
        {!locked && (
          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            <span className="muted" style={{ fontSize: '0.82rem' }}>Quick save:</span>
            <kbd className="kbd-sm kbd-accent">Ctrl+↵</kbd>
          </div>
        )}
      </div>

      <ErrorBox msg={error || err2} />
      {d && <>
        {d.warnings.map((w: string, i: number) => <Notice key={i} kind="warn" msg={w} />)}
        {d.reopen_reason && <Notice msg={`Reopened: ${d.reopen_reason}`} />}
        <div className="card"><h3>1. Opening cash & POS figures (entered from your POS closing report)</h3>
          <div className="form-grid">
            <Field label="Opening cash (₹)" hint={d.suggested_opening != null ? `Previous verified closing: ${fmt(d.suggested_opening)}` : 'No previous verified closing'}>
              <input disabled={locked} inputMode="decimal" value={f.opening_cash ?? ''} onChange={e => set('opening_cash', e.target.value)} /></Field>
            <Field label="Opening note (if different)"><input disabled={locked} value={f.opening_note ?? ''} onChange={e => set('opening_note', e.target.value)} /></Field>
            <Field label="POS total sales"><input disabled={locked} inputMode="decimal" value={f.pos_total_sales ?? ''} onChange={e => set('pos_total_sales', e.target.value)} /></Field>
            <Field label="Cash sales collected"><input disabled={locked} inputMode="decimal" value={f.cash_sales ?? ''} onChange={e => set('cash_sales', e.target.value)} /></Field>
            <Field label="UPI sales"><input disabled={locked} inputMode="decimal" value={f.upi_sales ?? ''} onChange={e => set('upi_sales', e.target.value)} /></Field>
            <Field label="Card sales"><input disabled={locked} inputMode="decimal" value={f.card_sales ?? ''} onChange={e => set('card_sales', e.target.value)} /></Field>
            <Field label="Other tender"><input disabled={locked} inputMode="decimal" value={f.other_sales ?? ''} onChange={e => set('other_sales', e.target.value)} /></Field>
            <Field label="Credit (udhari) sales"><input disabled={locked} inputMode="decimal" value={f.credit_sales ?? ''} onChange={e => set('credit_sales', e.target.value)} /></Field>
          </div>
          <p className="muted">The Item Sales PDF does not show how sales were paid, so tender totals are never inferred from it.</p>
          {d.tender_difference != null && num(d.tender_difference) !== 0 && <Notice kind="warn" msg={`POS total differs from the sum of tenders by ${fmt(d.tender_difference)}.`} />}
        </div>
        <div className="card"><h3>2. Ledger-derived cash movements (from receipts, expenses, transfers…)</h3>
          <div className="table-wrap"><table><tbody>
            <tr><td>Opening cash</td><td className="n">{fmt(f.opening_cash)}</td></tr>
            <tr><td>+ Cash sales collected (from POS)</td><td className="n">{fmt(f.cash_sales)}</td></tr>
            {LINES.map(([k, label, sign]) => <tr key={k}><td>{sign > 0 ? '+' : '−'} {label}</td><td className="n">{fmt(d.ledger[k])}</td></tr>)}
            <tr className="total-row"><td>= Expected closing cash</td><td className="n" style={{ color: 'var(--brand)', fontSize: '1.05rem' }}>{fmt(locked ? d.expected_cash : expectedPreview)}</td></tr>
          </tbody></table></div>
          <p className="muted">UPI/bank/card receipts and owner-paid expenses never change the drawer. Corrections must be posted as adjustments (or an admin reopens the day).</p>
        </div>
        <div className="card">
          <div className="row between">
            <h3>3. Count the drawer</h3>
            {!locked && (
              <button type="button" className="btn small secondary" onClick={() => setShowDenom(!showDenom)}>
                {showDenom ? 'Hide Note Counter' : '🧮 Denomination Counter'}
              </button>
            )}
          </div>

          {/* Currency Denomination Counter */}
          {!locked && showDenom && (
            <div style={{ background: 'var(--panel-elevated)', padding: 14, borderRadius: 10, border: '1px solid var(--line)', margin: '8px 0 16px' }}>
              <div className="row between" style={{ marginBottom: 8 }}>
                <span style={{ fontSize: '0.84rem', fontWeight: 700, textTransform: 'uppercase', color: 'var(--brand)' }}>
                  Cash Denomination Breakdown
                </span>
                <span style={{ fontSize: '0.95rem', fontFamily: 'JetBrains Mono, monospace' }}>
                  Total: <b style={{ color: 'var(--good)' }}>{fmt(denomTotal)}</b>
                </span>
              </div>
              <div className="denom-grid">
                {[500, 200, 100, 50, 20, 10].map(val => (
                  <div key={val} className="denom-box">
                    <span className="denom-label">₹{val} ×</span>
                    <input
                      className="denom-input"
                      inputMode="numeric"
                      placeholder="0"
                      value={denoms[String(val)]}
                      onChange={e => setDenoms({ ...denoms, [String(val)]: e.target.value })}
                    />
                    <span className="denom-subtotal">{fmt(num(denoms[String(val)]) * val)}</span>
                  </div>
                ))}
                <div className="denom-box">
                  <span className="denom-label">Coins (₹)</span>
                  <input
                    className="denom-input"
                    inputMode="decimal"
                    placeholder="0"
                    value={denoms['coins']}
                    onChange={e => setDenoms({ ...denoms, coins: e.target.value })}
                  />
                  <span className="denom-subtotal">{fmt(num(denoms['coins']))}</span>
                </div>
              </div>
              <button type="button" className="btn small" onClick={applyDenom}>
                Apply ₹{denomTotal.toFixed(2)} to Counted Cash
              </button>
            </div>
          )}

          <div className="form-grid">
            <Field label="Physical cash counted (₹)"><input disabled={locked} inputMode="decimal" value={f.physical_counted ?? ''} onChange={e => set('physical_counted', e.target.value)} placeholder="0.00" /></Field>
            <div className="field"><span>Difference</span><b style={{ fontSize: '1.45rem', fontFamily: 'JetBrains Mono, monospace' }} className={variancePreview ? (variancePreview < 0 ? 'neg' : 'pos') : ''}>
              {locked ? fmt(d.variance) : variancePreview == null ? '—' : fmt(variancePreview)}</b>
              <small>{(locked ? num(d.variance) : variancePreview ?? 0) === 0 ? 'Drawer matches perfectly' : 'Counted − expected (no automatic adjustment is made)'}</small></div>
            <Field label={`Reason / note (required at ≥ ₹${d.note_threshold})`}><input disabled={locked} value={f.variance_reason ?? ''} onChange={e => set('variance_reason', e.target.value)} placeholder="e.g. Small discrepancy, rounded off" /></Field>
          </div>
          {!locked ? <p style={{ marginTop: 16 }}><button className="btn secondary" disabled={busy} onClick={save}>Save draft <kbd className="kbd-sm" style={{ marginLeft: 4 }}>Ctrl+↵</kbd></button> <button className="btn" disabled={busy} onClick={finalize}>Finalize day</button></p>
            : user.role === 'admin' && <div className="row" style={{ marginTop: 14 }}><Field label="Reopen reason"><input value={reopenReason} onChange={e => setReopenReason(e.target.value)} placeholder="Admin override reason" /></Field>
              <button className="btn danger" disabled={!reopenReason.trim()} onClick={() => submit('Day reopened', async () => { setData(await api(`/day-closes/${date}/reopen`, { body: { reason: reopenReason } })); setReopenReason('') })}>Reopen day</button></div>}
        </div>
      </>}
      <HistoryList reloadKey={d?.status} onPick={setDate} />
    </div>
  )
}

function HistoryList({ onPick, reloadKey }: { onPick: (d: string) => void; reloadKey?: string }) {
  const { data } = useAsync(() => api('/day-closes'), [reloadKey])
  return <><h2>Closing history</h2><div className="table-wrap"><table><thead><tr><th>Date</th><th>Status</th><th className="n">Expected</th><th className="n">Counted</th><th className="n">Variance</th></tr></thead>
    <tbody>{(data || []).map((r: any) => <tr key={r.business_date} className="clickable" onClick={() => onPick(r.business_date)}><td>{fmtDate(r.business_date)}</td><td><Badge status={r.status} /></td>
      <td className="n">{fmt(r.expected_cash)}</td><td className="n">{fmt(r.physical_counted)}</td><td className={`n ${num(r.variance) < 0 ? 'neg' : ''}`}>{fmt(r.variance)}</td></tr>)}</tbody></table></div></>
}

function Cashbook() {
  const { data: accounts } = useAsync(() => api('/accounts'))
  const [aid, setAid] = useState('')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const id = aid || accounts?.[0]?.id
  const { data: rep, error, reload } = useAsync(() => (id ? api(`/reports/cashbook?account_id=${id}&date_from=${from}&date_to=${to}`) : Promise.resolve(null)), [id, from, to])
  const [m, setM] = useState({ kind: 'other_in', account_id: '', amount: '', date: todayIso(), note: '' })
  const [t, setT] = useState({ from_account_id: '', to_account_id: '', amount: '', date: todayIso(), note: '' })
  const { error: e2, busy, submit } = useSubmit()
  const [ok, setOk] = useState('')
  return (
    <>
      <div className="grid">{(accounts || []).map((a: any) => <div key={a.id} className="card stat"><div className="stat-title">{a.name}{a.is_physical_cash ? ' (drawer)' : ''}</div><div className="stat-value">{fmt(a.balance)}</div></div>)}</div>
      <div className="row"><Field label="Account"><select value={id || ''} onChange={e => setAid(e.target.value)}>{(accounts || []).map((a: any) => <option key={a.id} value={a.id}>{a.name}</option>)}</select></Field>
        <Field label="From"><input type="date" value={from} onChange={e => setFrom(e.target.value)} /></Field><Field label="To"><input type="date" value={to} onChange={e => setTo(e.target.value)} /></Field></div>
      <ErrorBox msg={error} />
      {rep && <div className="table-wrap"><table><thead><tr>{rep.columns.map((c: string) => <th key={c} className={['in', 'out', 'balance'].includes(c) ? 'n' : ''}>{c}</th>)}</tr></thead>
        <tbody>{rep.rows.map((r: any, i: number) => <tr key={i}>{rep.columns.map((c: string) => <td key={c} className={['in', 'out', 'balance'].includes(c) ? 'n' : ''}>{['in', 'out', 'balance'].includes(c) ? (num(r[c]) || c === 'balance' ? fmt(r[c]) : '') : c === 'date' ? fmtDate(r[c]) : r[c]}</td>)}</tr>)}</tbody></table></div>}
      <ErrorBox msg={e2} />{ok && <Notice kind="ok" msg={ok} />}
      <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit,minmax(320px,1fr))' }}>
        <div className="card"><h3>Other cash movement</h3><div className="form-grid">
          <Field label="Type"><select value={m.kind} onChange={e => setM({ ...m, kind: e.target.value })}><option value="other_in">Other cash in</option><option value="other_out">Other cash out</option><option value="refund">Refund</option><option value="withdrawal">Withdrawal</option></select></Field>
          <Field label="Account"><select value={m.account_id} onChange={e => setM({ ...m, account_id: e.target.value })}><option value="">— select —</option>{(accounts || []).map((a: any) => <option key={a.id} value={a.id}>{a.name}</option>)}</select></Field>
          <Field label="Amount"><input inputMode="decimal" value={m.amount} onChange={e => setM({ ...m, amount: e.target.value })} /></Field>
          <Field label="Date"><input type="date" value={m.date} onChange={e => setM({ ...m, date: e.target.value })} /></Field>
          <Field label="Note (required)"><input value={m.note} onChange={e => setM({ ...m, note: e.target.value })} /></Field></div>
          <button className="btn" disabled={busy} onClick={() => submit('Cash movement posted', async () => { await api('/cash-movements', { body: { ...m, account_id: Number(m.account_id) } }); setOk('Movement posted'); setM({ ...m, amount: '', note: '' }); reload() })}>Post</button></div>
        <div className="card"><h3>Transfer between accounts</h3><div className="form-grid">
          <Field label="From"><select value={t.from_account_id} onChange={e => setT({ ...t, from_account_id: e.target.value })}><option value="">— select —</option>{(accounts || []).map((a: any) => <option key={a.id} value={a.id}>{a.name}</option>)}</select></Field>
          <Field label="To"><select value={t.to_account_id} onChange={e => setT({ ...t, to_account_id: e.target.value })}><option value="">— select —</option>{(accounts || []).map((a: any) => <option key={a.id} value={a.id}>{a.name}</option>)}</select></Field>
          <Field label="Amount"><input inputMode="decimal" value={t.amount} onChange={e => setT({ ...t, amount: e.target.value })} /></Field>
          <Field label="Date"><input type="date" value={t.date} onChange={e => setT({ ...t, date: e.target.value })} /></Field></div>
          <p className="muted">Transfers are neither sales nor expenses.</p>
          <button className="btn" disabled={busy} onClick={() => submit('Transfer posted', async () => { await api('/transfers', { body: { ...t, from_account_id: Number(t.from_account_id), to_account_id: Number(t.to_account_id) } }); setOk('Transfer posted'); setT({ ...t, amount: '' }); reload() })}>Transfer</button></div>
      </div>
    </>
  )
}

export default function Cash({ user }: { user: User }) {
  const [tab, setTab] = useState('close')
  return (
    <>
      <h1>Daily Closing / Cashbook</h1>
      <div className="tabs"><button className={`tab ${tab === 'close' ? 'active' : ''}`} onClick={() => setTab('close')}>Daily closing</button><button className={`tab ${tab === 'book' ? 'active' : ''}`} onClick={() => setTab('book')}>Cashbook & accounts</button></div>
      {tab === 'close' ? <DayClose user={user} /> : <Cashbook />}
    </>
  )
}
