import { Link, useNavigate } from 'react-router-dom'
import { api, fmt, fmtDate, num } from '../api'
import { Card, ErrorBox, Notice, useAsync } from '../ui'

export default function Dashboard() {
  const navigate = useNavigate()
  const { data: d, error, loading } = useAsync(() => api('/dashboard'))
  if (loading && !d) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: 30, color: 'var(--muted)' }}>
        <div className="status-pill-dot" />
        <span>Loading Operations Dashboard…</span>
      </div>
    )
  }
  if (!d) return <ErrorBox msg={error} />
  const src = Object.entries(d.expenses_today_by_source || {})

  return (
    <>
      <div className="row between">
        <h1>
          Dashboard <small className="muted" style={{ fontWeight: 400, fontSize: '0.92rem' }}>· {fmtDate(d.today)}</small>
        </h1>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <button className="btn small" onClick={() => navigate('/udhari/new-bill')}>
            <span>+ Bill</span> <kbd className="kbd-sm kbd-accent">F3</kbd>
          </button>
          <button className="btn small secondary" onClick={() => navigate('/receive')}>
            <span>Receive Pay</span> <kbd className="kbd-sm">F4</kbd>
          </button>
          <button className="btn small secondary" onClick={() => navigate('/cash')}>
            <span>Cash Closing</span> <kbd className="kbd-sm">F8</kbd>
          </button>
          <button className="btn small ghost" onClick={() => navigate('/expenses')}>
            <span>Expenses</span> <kbd className="kbd-sm">F9</kbd>
          </button>
        </div>
      </div>

      <ErrorBox msg={error} />

      {/* Primary KPI Grid */}
      <div className="grid">
        <Card
          title="Customer Udhari Outstanding"
          value={fmt(d.total_outstanding)}
          tone={num(d.total_outstanding) > 0 ? 'bad' : 'good'}
          sub={<Link to="/udhari">View customers <kbd className="kbd-sm" style={{ marginLeft: 4 }}>Alt+2</kbd></Link>}
        />
        <Card
          title="Collected Today (Old Udhari)"
          value={fmt(d.collected_today)}
          tone="good"
          sub="Receipts settled against ledger"
        />
        <Card
          title={`Overdue > ${d.overdue_days_setting} Days`}
          value={d.overdue_customers}
          sub={fmt(d.overdue_amount)}
          tone={d.overdue_customers ? 'warn' : undefined}
        />
        <Card
          title="Unpaid / Part-Paid Expenses"
          value={fmt(d.unpaid_expenses_amount)}
          sub={`${d.unpaid_expenses_count} vendor bill(s)`}
          tone={d.unpaid_expenses_count ? 'warn' : undefined}
        />
        <Card
          title="Owed to Owner"
          value={fmt(d.owner_due)}
          sub="Owner-paid, pending reimbursement"
        />
        <Card
          title="Expected Drawer Cash"
          value={fmt(d.expected_closing_cash)}
          sub={`Status: ${d.day_status}`}
        />
      </div>

      {/* Operational Breakdown Cards */}
      <div className="grid">
        <div className="card stat">
          <div className="stat-title">Expenses Paid Today by Source</div>
          {src.length === 0 ? (
            <div className="muted" style={{ padding: '8px 0' }}>No expense paid today yet</div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 8 }}>
              {src.map(([k, v]) => (
                <div key={k} style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.9rem' }}>
                  <span className="muted">{k}</span>
                  <b style={{ fontFamily: 'JetBrains Mono, monospace' }}>{fmt(v)}</b>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="card stat">
          <div className="stat-title">Latest Item Sales Report</div>
          {d.latest_item_sales ? (
            <div style={{ marginTop: 6 }}>
              <div><b>{fmtDate(d.latest_item_sales.report_date)}</b></div>
              <div style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '1.05rem', marginTop: 2 }}>
                {d.latest_item_sales.qty} items · {fmt(d.latest_item_sales.amount)}
              </div>
              <div className="stat-sub">{d.latest_item_sales.note}</div>
            </div>
          ) : (
            <div className="muted" style={{ padding: '8px 0' }}>
              No report imported yet. <Link to="/inventory">Import one</Link>
            </div>
          )}
        </div>

        <div className="card stat">
          <div className="stat-title">Imports Needing Attention</div>
          <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 4, fontSize: '0.88rem' }}>
            <div>
              <span className="badge warn" style={{ marginRight: 6 }}>{d.draft_imports} draft</span>
              <span>{d.unresolved_import_rows} unresolved rows</span>
            </div>
            {d.duplicate_warnings > 0 && <div className="neg">⚠️ {d.duplicate_warnings} duplicate warning(s)</div>}
            <div className="muted">{d.pending_catalogue_items} catalogue item(s) pending review</div>
          </div>
        </div>

        <div className="card stat">
          <div className="stat-title">Low Stock Alerts</div>
          {d.low_stock_items.length === 0 ? (
            <div className="muted" style={{ padding: '8px 0' }}>All stock levels above threshold</div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginTop: 6 }}>
              {d.low_stock_items.map((s: any) => (
                <div key={s.item_id} style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.86rem' }}>
                  <span>{s.name}</span>
                  <span className="badge bad">{s.estimated_stock}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="row between" style={{ marginTop: 18 }}>
        <h2>Account Balances</h2>
        <span className="muted" style={{ fontSize: '0.82rem' }}>Real-time verified book balance</span>
      </div>
      <div className="grid">
        {d.accounts.map((a: any) => (
          <Card
            key={a.name}
            title={a.name}
            value={fmt(a.balance)}
            sub={a.physical_cash ? 'Physical Cash Drawer' : 'Bank / Online Account'}
          />
        ))}
      </div>

      <Notice msg="Account balances reflect verified opening balances plus posted sales, udhari collections, and expense payouts." />
    </>
  )
}
