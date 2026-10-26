import { Link, useNavigate } from 'react-router-dom'
import { api, fmt, fmtDate, num } from '../api'
import { Icon } from '../icons'
import { ErrorBox, useAsync } from '../ui'

const compact = new Intl.NumberFormat('en-IN', { notation: 'compact', maximumFractionDigits: 1 })

function Kpi({ icon, label, value, sub, tone, to }: { icon: string; label: string; value: string | number; sub?: React.ReactNode; tone?: 'bad' | 'good' | 'warn' | 'info'; to?: string }) {
  const body = (
    <>
      <div className="kpi-top"><span className={`kpi-icon ${tone || ''}`}><Icon name={icon} size={18} /></span><span className="kpi-label">{label}</span></div>
      <div className={`kpi-value ${tone || ''}`}>{value}</div>
      {sub && <div className="kpi-sub">{sub}</div>}
    </>
  )
  return to ? <Link to={to} className="kpi kpi-link">{body}</Link> : <div className="kpi">{body}</div>
}

function TrendChart({ data }: { data: any[] }) {
  const max = Math.max(1, ...data.flatMap(d => [num(d.collections), num(d.expenses), num(d.credit_given)]))
  const W = 640, H = 180, pad = 24, bw = (W - pad * 2) / data.length
  const y = (v: number) => H - pad - (v / max) * (H - pad * 2)
  return (
    <div className="chart-wrap">
      <svg viewBox={`0 0 ${W} ${H}`} className="chart" role="img" aria-label="Collections, credit given and expenses per day">
        {[0.25, 0.5, 0.75, 1].map(f => <line key={f} x1={pad} x2={W - pad} y1={y(max * f)} y2={y(max * f)} className="chart-grid" />)}
        {data.map((d, i) => {
          const x = pad + i * bw
          const w = Math.max(3, bw / 3 - 2)
          return (
            <g key={d.date}>
              <title>{`${fmtDate(d.date)}\nCollected ${fmt(d.collections)}\nCredit given ${fmt(d.credit_given)}\nExpenses paid ${fmt(d.expenses)}`}</title>
              <rect x={x + 2} y={y(num(d.collections))} width={w} height={H - pad - y(num(d.collections))} rx={2} className="bar-good" />
              <rect x={x + 2 + w + 1} y={y(num(d.credit_given))} width={w} height={H - pad - y(num(d.credit_given))} rx={2} className="bar-warn" />
              <rect x={x + 2 + 2 * (w + 1)} y={y(num(d.expenses))} width={w} height={H - pad - y(num(d.expenses))} rx={2} className="bar-bad" />
              {(i % Math.ceil(data.length / 7) === 0 || i === data.length - 1) &&
                <text x={x + bw / 2} y={H - 6} textAnchor="middle" className="chart-label">{d.date.slice(8, 10)}/{d.date.slice(5, 7)}</text>}
            </g>
          )
        })}
        <text x={pad} y={14} className="chart-label">₹{compact.format(max)}</text>
      </svg>
      <div className="legend"><span><i className="dot good" />Collected</span><span><i className="dot warn" />Credit given</span><span><i className="dot bad" />Expenses paid</span></div>
    </div>
  )
}

function AgingBar({ aging }: { aging: any[] }) {
  const total = aging.reduce((s, a) => s + num(a.amount), 0)
  const tones = ['good', 'info', 'warn', 'bad']
  if (!total) return <div className="empty-mini"><Icon name="check" /> No udhari outstanding</div>
  return (
    <>
      <div className="stack-bar" role="img" aria-label="Outstanding by age">
        {aging.map((a, i) => num(a.amount) > 0 && <span key={a.bucket} className={`seg ${tones[i]}`} style={{ flex: num(a.amount) }} title={`${a.bucket} days: ${fmt(a.amount)}`} />)}
      </div>
      <div className="aging-grid">
        {aging.map((a, i) => (
          <div key={a.bucket}><span className={`dot ${tones[i]}`} /><span className="muted">{a.bucket} days</span><b>{fmt(a.amount)}</b>
            <small className="muted">{total ? Math.round((num(a.amount) / total) * 100) : 0}%</small></div>
        ))}
      </div>
    </>
  )
}

export default function Dashboard() {
  const navigate = useNavigate()
  const { data: d, error, loading } = useAsync(() => api('/dashboard'))
  const { data: ins } = useAsync(() => api('/dashboard/insights'))
  if (loading && !d) return <DashboardSkeleton />
  if (!d) return <ErrorBox msg={error} />

  const alerts: { tone: string; text: string; to: string }[] = []
  ;(ins?.unclosed_days || []).slice(0, 3).forEach((day: string) => alerts.push({ tone: 'warn', text: `Cash for ${fmtDate(day)} was never finalized`, to: '/cash' }))
  if (d.duplicate_warnings) alerts.push({ tone: 'bad', text: `${d.duplicate_warnings} import(s) look like duplicates`, to: '/inventory' })
  if (d.draft_imports) alerts.push({ tone: 'info', text: `${d.draft_imports} report import(s) waiting for review`, to: '/inventory' })
  if (d.overdue_customers) alerts.push({ tone: 'warn', text: `${d.overdue_customers} customer(s) overdue more than ${d.overdue_days_setting} days`, to: '/udhari' })
  ;(ins?.payables_due_soon || []).filter((p: any) => p.overdue).slice(0, 2).forEach((p: any) => alerts.push({ tone: 'bad', text: `${p.payee}: ${fmt(p.due)} overdue since ${fmtDate(p.due_date)}`, to: '/expenses' }))

  return (
    <div className="dash">
      <div className="page-head">
        <div>
          <h1>Good {greeting()}</h1>
          <p className="muted">Here is where things stand on {fmtDate(d.today)}.</p>
        </div>
        <div className="page-actions">
          <button className="btn secondary" onClick={() => navigate('/cash')}><Icon name="lock" size={16} /> Close the day</button>
          <button className="btn" onClick={() => navigate('/receive')}><Icon name="wallet" size={16} /> Receive payment</button>
        </div>
      </div>

      {alerts.length > 0 && (
        <div className="alert-list">
          {alerts.map((a, i) => <Link key={i} to={a.to} className={`alert-row ${a.tone}`}><Icon name="alert" size={16} /><span>{a.text}</span><Icon name="chevronRight" size={16} /></Link>)}
        </div>
      )}

      <div className="kpi-grid">
        <Kpi icon="users" label="Udhari outstanding" value={fmt(d.total_outstanding)} tone={num(d.total_outstanding) > 0 ? 'bad' : 'good'} to="/udhari"
          sub={d.overdue_customers ? `${d.overdue_customers} overdue · ${fmt(d.overdue_amount)}` : 'Nobody overdue'} />
        <Kpi icon="wallet" label="Collected today" value={fmt(d.collected_today)} tone="good" sub="Old udhari received" to="/reports" />
        <Kpi icon="lock" label="Expected cash in drawer" value={fmt(d.expected_closing_cash)} tone="info" sub={`Day is ${d.day_status}`} to="/cash" />
        <Kpi icon="receipt" label="Unpaid bills & expenses" value={fmt(d.unpaid_expenses_amount)} tone={d.unpaid_expenses_count ? 'warn' : undefined}
          sub={`${d.unpaid_expenses_count} open payable(s)`} to="/expenses" />
        <Kpi icon="rupee" label="Owed to owner" value={fmt(d.owner_due)} sub="Owner-paid, not reimbursed" to="/expenses" />
      </div>

      <div className="dash-grid">
        <section className="panel span-2">
          <div className="panel-head"><h3>Last 14 days</h3><span className="muted small">Hover a day for exact figures</span></div>
          {ins ? <TrendChart data={ins.trend} /> : <div className="skeleton" style={{ height: 200 }} />}
        </section>

        <section className="panel">
          <div className="panel-head"><h3>Udhari by age</h3><Link to="/reports?r=customer-aging" className="small">Aging report</Link></div>
          {ins ? <AgingBar aging={ins.aging} /> : <div className="skeleton" style={{ height: 120 }} />}
        </section>

        <section className="panel">
          <div className="panel-head"><h3>Top balances</h3><Link to="/udhari?filter=owing" className="small">All customers</Link></div>
          {!ins ? <div className="skeleton" style={{ height: 160 }} /> : ins.top_debtors.length === 0 ? <div className="empty-mini"><Icon name="check" /> Nobody owes money</div> : (
            <ul className="list">
              {ins.top_debtors.map((c: any) => (
                <li key={c.customer_id}><Link to={`/udhari/${c.customer_id}`}>
                  <span className="avatar sm">{c.name.slice(0, 1).toUpperCase()}</span>
                  <span className="list-main"><b>{c.name}</b><small className="muted">{c.phone || 'No phone'} · oldest {c.oldest_days} d</small></span>
                  <b className={c.oldest_days > d.overdue_days_setting ? 'neg' : ''}>{fmt(c.outstanding)}</b>
                </Link></li>
              ))}
            </ul>
          )}
        </section>

        <section className="panel">
          <div className="panel-head"><h3>Payables due this week</h3><Link to="/expenses" className="small">Expenses</Link></div>
          {!ins ? <div className="skeleton" style={{ height: 160 }} /> : ins.payables_due_soon.length === 0 ? <div className="empty-mini"><Icon name="check" /> Nothing due in the next 7 days</div> : (
            <ul className="list">
              {ins.payables_due_soon.map((p: any) => (
                <li key={p.id}><Link to={`/expenses?open=${p.id}`}>
                  <span className={`avatar sm ${p.overdue ? 'bad' : ''}`}><Icon name="receipt" size={14} /></span>
                  <span className="list-main"><b>{p.payee}</b><small className={p.overdue ? 'neg' : 'muted'}>{p.overdue ? 'Overdue · ' : 'Due '}{fmtDate(p.due_date)}</small></span>
                  <b>{fmt(p.due)}</b>
                </Link></li>
              ))}
            </ul>
          )}
        </section>

        <section className="panel">
          <div className="panel-head"><h3>Accounts</h3><Link to="/cash" className="small">Cashbook</Link></div>
          <ul className="list">
            {d.accounts.map((a: any) => (
              <li key={a.name}><div className="list-row">
                <span className="avatar sm"><Icon name={a.physical_cash ? 'wallet' : 'rupee'} size={14} /></span>
                <span className="list-main"><b>{a.name}</b><small className="muted">{a.physical_cash ? 'Cash drawer' : 'Bank / online'}</small></span>
                <b className={num(a.balance) < 0 ? 'neg' : ''}>{fmt(a.balance)}</b>
              </div></li>
            ))}
          </ul>
        </section>

        <section className="panel">
          <div className="panel-head"><h3>Reports & stock</h3><Link to="/inventory" className="small">Inventory</Link></div>
          <ul className="list">
            <li><div className="list-row"><span className="avatar sm"><Icon name="file" size={14} /></span>
              <span className="list-main"><b>Latest Item Sales report</b><small className="muted">{d.latest_item_sales ? `${fmtDate(d.latest_item_sales.report_date)} · ${d.latest_item_sales.qty} items` : 'None imported yet'}</small></span>
              <b>{d.latest_item_sales ? fmt(d.latest_item_sales.amount) : '—'}</b></div></li>
            <li><div className="list-row"><span className="avatar sm"><Icon name="box" size={14} /></span>
              <span className="list-main"><b>Catalogue items to review</b><small className="muted">From imported reports</small></span><b>{d.pending_catalogue_items}</b></div></li>
            <li><div className="list-row"><span className={`avatar sm ${d.low_stock_items.length ? 'bad' : ''}`}><Icon name="alert" size={14} /></span>
              <span className="list-main"><b>Low stock</b><small className="muted">{d.low_stock_items.slice(0, 3).map((s: any) => s.name).join(', ') || 'All above threshold'}</small></span><b>{d.low_stock_items.length}</b></div></li>
          </ul>
        </section>

        <section className="panel span-2">
          <div className="panel-head"><h3>Recent activity</h3>{ins?.last_closed_day && <span className="muted small">Last day closed {fmtDate(ins.last_closed_day)}</span>}</div>
          {!ins ? <div className="skeleton" style={{ height: 160 }} /> : ins.recent_activity.length === 0 ? <div className="empty-mini">No activity yet</div> : (
            <ul className="timeline">
              {ins.recent_activity.map((a: any, i: number) => (
                <li key={i}><span className="tl-dot" /><div><b>{a.label}</b>{a.amount != null && <span className="mono"> · {fmt(a.amount)}</span>}
                  <small className="muted"> — {a.user} · {timeAgo(a.ts)}</small>{a.reason && <div className="muted small">{a.reason}</div>}</div></li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  )
}

function greeting() {
  const h = Number(new Date().toLocaleString('en-US', { timeZone: 'Asia/Kolkata', hour: 'numeric', hour12: false }))
  return h < 12 ? 'morning' : h < 17 ? 'afternoon' : 'evening'
}

function timeAgo(isoUtc: string) {
  const t = Date.parse(isoUtc.endsWith('Z') ? isoUtc : isoUtc + 'Z')
  const s = Math.max(0, (Date.now() - t) / 1000)
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.floor(s / 60)} min ago`
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`
  return new Date(t).toLocaleDateString('en-IN', { day: '2-digit', month: 'short' })
}

function DashboardSkeleton() {
  return (
    <div className="dash">
      <div className="skeleton" style={{ height: 48, width: 320, marginBottom: 20 }} />
      <div className="kpi-grid">{[1, 2, 3, 4, 5].map(i => <div key={i} className="skeleton" style={{ height: 110 }} />)}</div>
      <div className="skeleton" style={{ height: 260 }} />
    </div>
  )
}
