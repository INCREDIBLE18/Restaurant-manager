import { useEffect, useState } from 'react'
import { api, fmt } from '../api'
import { Badge, ErrorBox, Field, Notice, useAsync, useSubmit } from '../ui'

const SETTING_LABELS: Record<string, string> = {
  restaurant_name: 'Restaurant / outlet name', address: 'Address', phone: 'Phone', receipt_prefix: 'Receipt number prefix', bill_prefix: 'Bill prefix',
  phone_mandatory: 'Customer phone mandatory (true/false)', variance_note_threshold: 'Variance note required at ₹ (cash closing)', overdue_days: 'Overdue after (days)',
}

export default function Settings() {
  const { data: s, reload } = useAsync(() => api('/settings'))
  const { data: healthData } = useAsync(() => api('/health'))
  const [f, setF] = useState<Record<string, string>>({})
  useEffect(() => { if (s) setF(s) }, [s])
  const { data: users, reload: ru } = useAsync(() => api('/users'))
  const { data: accounts, reload: ra } = useAsync(() => api('/accounts'))
  const { data: backups, reload: rb } = useAsync(() => api('/backups'))
  const { data: audit } = useAsync(() => api('/audit?limit=100'))
  const [u, setU] = useState({ username: '', password: '', full_name: '', role: 'staff' })
  const [a, setA] = useState({ name: '', type: 'bank', opening_balance: '' })
  const { error, submit } = useSubmit()
  const [msg, setMsg] = useState('')
  const [pw, setPw] = useState({ old_password: '', new_password: '' })
  return (
    <>
      <h1>Settings / Users / Backup</h1>
      <ErrorBox msg={error} />{msg && <Notice kind="ok" msg={msg} />}
      <div className="card" style={{ borderLeft: '4px solid #10b981' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
          <h3 style={{ margin: 0, display: 'flex', alignItems: 'center', gap: 8 }}>
            <span>⚡ Neon Cloud Architecture</span>
            <span style={{ fontSize: '0.75rem', background: 'rgba(16, 185, 129, 0.15)', color: '#10b981', padding: '2px 8px', borderRadius: 12, fontWeight: 600 }}>Active</span>
          </h3>
          <span className="muted" style={{ fontSize: '0.85rem' }}>Branch: <strong>{healthData?.neon_branch || 'production'}</strong></span>
        </div>
        <div className="form-grid" style={{ marginTop: 12, gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 12 }}>
          <div>
            <div className="muted" style={{ fontSize: '0.78rem' }}>Database Service</div>
            <div style={{ fontWeight: 600, fontSize: '0.9rem' }}>Neon Lakebase PostgreSQL</div>
          </div>
          <div>
            <div className="muted" style={{ fontSize: '0.78rem' }}>Auth Service</div>
            <div style={{ fontWeight: 600, fontSize: '0.9rem' }}>{healthData?.neon_auth ? 'Neon Managed Auth' : 'Ready'}</div>
          </div>
          <div>
            <div className="muted" style={{ fontSize: '0.78rem' }}>Database Status</div>
            <div style={{ fontWeight: 600, fontSize: '0.9rem', color: '#10b981' }}>{healthData?.database ? `Connected (${healthData.database})` : 'Connected'}</div>
          </div>
        </div>
      </div>
      <div className="card"><h3>Restaurant settings</h3>
        <div className="form-grid">{Object.keys(SETTING_LABELS).map(k => <Field key={k} label={SETTING_LABELS[k]}><input value={f[k] ?? ''} onChange={e => setF({ ...f, [k]: e.target.value })} /></Field>)}</div>
        <button className="btn" onClick={() => submit(async () => { const body: any = {}; Object.keys(SETTING_LABELS).forEach(k => body[k] = f[k]); await api('/settings', { method: 'PUT', body }); setMsg('Settings saved'); reload() })}>Save settings</button>
        <p className="muted">AI-assisted PDF reading (Gemini) is {s?.gemini_enabled === 'true' ? 'enabled' : 'disabled'}; it is controlled by environment variables on the server (see .env.example) and its output always requires human review.</p></div>
      <div className="card"><h3>Accounts</h3>
        <div className="table-wrap"><table><thead><tr><th>Name</th><th>Type</th><th>Physical cash</th><th className="n">Opening balance</th><th className="n">Balance</th><th>Active</th></tr></thead>
          <tbody>{(accounts || []).map((x: any) => <tr key={x.id}><td>{x.name}</td><td>{x.type}</td><td>{x.is_physical_cash ? 'yes' : 'no'}</td>
            <td className="n"><input className="inp" style={{ width: 110, textAlign: 'right' }} defaultValue={x.opening_balance} onBlur={e => e.target.value !== String(x.opening_balance) && submit(async () => { await api(`/accounts/${x.id}`, { method: 'PATCH', body: { opening_balance: e.target.value } }); setMsg('Opening balance saved'); ra() })} aria-label={`Opening balance ${x.name}`} /></td><td className="n">{fmt(x.balance)}</td>
            <td><input type="checkbox" checked={x.active} onChange={e => submit(async () => { await api(`/accounts/${x.id}`, { method: 'PATCH', body: { active: e.target.checked } }); ra() })} /></td></tr>)}</tbody></table></div>
        <div className="form-grid"><Field label="New account name"><input value={a.name} onChange={e => setA({ ...a, name: e.target.value })} /></Field>
          <Field label="Type"><select value={a.type} onChange={e => setA({ ...a, type: e.target.value })}>{['cash', 'bank', 'upi', 'card', 'owner_personal', 'staff_advance', 'other'].map(t => <option key={t}>{t}</option>)}</select></Field>
          <Field label="Opening balance"><input value={a.opening_balance} onChange={e => setA({ ...a, opening_balance: e.target.value })} /></Field></div>
        <button className="btn secondary" onClick={() => submit(async () => { await api('/accounts', { body: a }); setA({ name: '', type: 'bank', opening_balance: '' }); ra() })}>Add account</button></div>
      <div className="card"><h3>Users</h3>
        <div className="table-wrap"><table><thead><tr><th>User</th><th>Role</th><th>Active</th><th>Last login</th></tr></thead>
          <tbody>{(users || []).map((x: any) => <tr key={x.id}><td>{x.username} <span className="muted">{x.full_name}</span></td><td>{x.role}</td>
            <td><input type="checkbox" checked={x.active} onChange={e => submit(async () => { await api(`/users/${x.id}`, { method: 'PATCH', body: { active: e.target.checked } }); ru() })} /></td><td>{x.last_login || '—'}</td></tr>)}</tbody></table></div>
        <div className="form-grid"><Field label="Username"><input value={u.username} onChange={e => setU({ ...u, username: e.target.value })} /></Field>
          <Field label="Full name"><input value={u.full_name} onChange={e => setU({ ...u, full_name: e.target.value })} /></Field>
          <Field label="Password (min 8)"><input type="password" value={u.password} onChange={e => setU({ ...u, password: e.target.value })} /></Field>
          <Field label="Role"><select value={u.role} onChange={e => setU({ ...u, role: e.target.value })}><option value="staff">Staff / Cashier</option><option value="admin">Admin / Owner</option></select></Field></div>
        <button className="btn secondary" onClick={() => submit(async () => { await api('/users', { body: u }); setU({ username: '', password: '', full_name: '', role: 'staff' }); ru() })}>Add user</button></div>
      <div className="card"><h3>Change my password</h3><div className="form-grid">
        <Field label="Current password"><input type="password" value={pw.old_password} onChange={e => setPw({ ...pw, old_password: e.target.value })} /></Field>
        <Field label="New password (min 8)"><input type="password" value={pw.new_password} onChange={e => setPw({ ...pw, new_password: e.target.value })} /></Field></div>
        <button className="btn secondary" onClick={() => submit(async () => { await api('/auth/change-password', { body: pw }); setPw({ old_password: '', new_password: '' }); setMsg('Password changed') })}>Change password</button></div>
      <div className="card"><h3>Backups</h3>
        <button className="btn" onClick={() => submit(async () => { const r = await api('/backups', { body: {} }); setMsg(`Backup created and verified: ${r.name} (${(r.size / 1024).toFixed(0)} KB, ${r.attachments} attachment(s))`); rb() })}>Create backup now</button>
        <div className="table-wrap" style={{ marginTop: 10 }}><table><thead><tr><th>File</th><th>Size</th><th>Created</th></tr></thead>
          <tbody>{(backups || []).map((b: any) => <tr key={b.name}><td>{b.name}</td><td>{(b.size / 1024).toFixed(0)} KB</td><td>{b.modified}</td></tr>)}{!(backups || []).length && <tr><td colSpan={3} className="muted">No backups yet.</td></tr>}</tbody></table></div>
        <p className="muted">Backups are stored in the server's data/backups folder. See README for restore instructions.</p></div>
      <div className="card"><h3>Audit trail (latest 100)</h3>
        <div className="table-wrap" style={{ maxHeight: 320 }}><table><thead><tr><th>When (UTC)</th><th>User</th><th>Action</th><th>Entity</th><th>Reason</th></tr></thead>
          <tbody>{(audit || []).map((x: any) => <tr key={x.id}><td>{x.ts.slice(0, 19).replace('T', ' ')}</td><td>{x.user}</td><td><Badge status={x.action} /></td><td>{x.entity_type} {x.entity_id}</td><td>{x.reason}</td></tr>)}</tbody></table></div></div>
    </>
  )
}
