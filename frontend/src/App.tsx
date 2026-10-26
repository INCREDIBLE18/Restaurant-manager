import { useCallback, useEffect, useRef, useState } from 'react'
import { NavLink, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { api, getToken, setToken } from './api'
import { ErrorBox, Field, useSubmit } from './ui'
import Dashboard from './pages/Dashboard'
import { Customers, CustomerDetail, AddBill } from './pages/Udhari'
import ReceivePayment from './pages/ReceivePayment'
import Expenses from './pages/Expenses'
import Purchases from './pages/Purchases'
import Inventory from './pages/Inventory'
import Cash from './pages/Cash'
import Reports from './pages/Reports'
import Settings from './pages/Settings'
import { CommandPalette } from './CommandPalette'
import { ShortcutsModal } from './ShortcutsModal'
import { getStoredTheme, isTypingActive, setStoredTheme } from './keyboard'
import { Icon } from './icons'
import { Toaster } from './toast'

export type User = { id: number; username: string; full_name: string; role: 'admin' | 'staff' }

function Login({ onLogin }: { onLogin: (u: User) => void }) {
  const [needsSetup, setNeedsSetup] = useState<boolean | null>(null)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [fullName, setFullName] = useState('')
  const { error, busy, submit } = useSubmit()

  useEffect(() => {
    api('/auth/status').then(s => setNeedsSetup(s.needs_setup)).catch(() => setNeedsSetup(false))
  }, [])

  const go = (e: React.FormEvent) => {
    e.preventDefault()
    submit(async () => {
      const r = await api(needsSetup ? '/auth/bootstrap' : '/auth/login', { body: { username, password, full_name: fullName } })
      setToken(r.token)
      onLogin(r.user)
    })
  }

  return (
    <div className="auth-screen">
      <div className="auth-side">
        <div className="auth-brand"><span className="brand-mark"><Icon name="receipt" size={22} /></span> Restaurant Ops</div>
        <h2>Udhari, cash and expenses — reconciled every day.</h2>
        <ul>
          <li><Icon name="check" size={16} /> Bill-wise credit ledger with part payments</li>
          <li><Icon name="check" size={16} /> Daily cash closing with variance tracking</li>
          <li><Icon name="check" size={16} /> Expenses, owner funding and supplier dues</li>
          <li><Icon name="check" size={16} /> Reviewed imports of your POS PDF reports</li>
        </ul>
      </div>
      <form className="auth-card" onSubmit={go}>
        <h1>{needsSetup ? 'Set up your workspace' : 'Sign in'}</h1>
        <p className="muted">{needsSetup ? 'Create the owner (admin) account. You can add staff later.' : 'Welcome back. Enter your credentials to continue.'}</p>
        <ErrorBox msg={error} />
        <div className="form-stack">
          {needsSetup && (
            <Field label="Your name">
              <input value={fullName} onChange={e => setFullName(e.target.value)} placeholder="e.g. Ramesh Sharma" />
            </Field>
          )}
          <Field label="Username">
            <input value={username} onChange={e => setUsername(e.target.value)} autoFocus autoComplete="username" />
          </Field>
          <Field label="Password" hint={needsSetup ? 'At least 8 characters' : undefined}>
            <input type="password" value={password} onChange={e => setPassword(e.target.value)} autoComplete={needsSetup ? 'new-password' : 'current-password'} />
          </Field>
        </div>
        <button className="btn block" disabled={busy || needsSetup === null || !username || !password}>
          {busy ? 'Please wait…' : needsSetup ? 'Create owner account' : 'Sign in'}
        </button>
      </form>
    </div>
  )
}

type NavItem = { to: string; label: string; icon: string; hint: string; admin?: boolean }
const NAV_GROUPS: { title: string; items: NavItem[] }[] = [
  { title: 'Overview', items: [{ to: '/', label: 'Dashboard', icon: 'dashboard', hint: 'Alt+1' }] },
  { title: 'Daily operations', items: [
    { to: '/udhari', label: 'Customers & Udhari', icon: 'users', hint: 'Alt+2' },
    { to: '/receive', label: 'Receive payment', icon: 'wallet', hint: 'F4' },
    { to: '/cash', label: 'Cash closing', icon: 'lock', hint: 'F8' },
  ] },
  { title: 'Money out', items: [
    { to: '/expenses', label: 'Expenses & payables', icon: 'receipt', hint: 'F9' },
    { to: '/purchases', label: 'Purchases', icon: 'cart', hint: 'Alt+7' },
  ] },
  { title: 'Stock & insights', items: [
    { to: '/inventory', label: 'Inventory & imports', icon: 'box', hint: 'Alt+8' },
    { to: '/reports', label: 'Reports', icon: 'chart', hint: 'Alt+9' },
  ] },
  { title: 'Admin', items: [{ to: '/settings', label: 'Settings', icon: 'settings', hint: 'Alt+0', admin: true }] },
]

const TITLES: [RegExp, string][] = [
  [/^\/$/, 'Dashboard'], [/^\/udhari\/new-bill/, 'New udhari bill'], [/^\/udhari\/\d+/, 'Customer ledger'], [/^\/udhari/, 'Customers & Udhari'],
  [/^\/receive/, 'Receive payment'], [/^\/cash/, 'Cash closing'], [/^\/expenses/, 'Expenses & payables'], [/^\/purchases/, 'Purchases'],
  [/^\/inventory/, 'Inventory & imports'], [/^\/reports/, 'Reports'], [/^\/settings/, 'Settings'],
]

function UserMenu({ user, onLogout }: { user: User; onLogout: () => void }) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const close = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])
  const initials = (user.full_name || user.username).split(/\s+/).map(s => s[0]).join('').slice(0, 2).toUpperCase()
  return (
    <div className="user-menu" ref={ref}>
      <button className="avatar-btn" onClick={() => setOpen(!open)} aria-haspopup="menu" aria-expanded={open} aria-label="Account menu">
        <span className="avatar">{initials}</span>
      </button>
      {open && (
        <div className="menu" role="menu">
          <div className="menu-head"><b>{user.full_name || user.username}</b><span className="muted">@{user.username} · {user.role}</span></div>
          <button role="menuitem" className="menu-item danger" onClick={onLogout}><Icon name="logout" size={16} /> Sign out</button>
        </div>
      )}
    </div>
  )
}

export default function App() {
  const navigate = useNavigate()
  const location = useLocation()
  const [user, setUser] = useState<User | null>(null)
  const [ready, setReady] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const [collapsed, setCollapsed] = useState(() => { try { return localStorage.getItem('rom-nav-collapsed') === '1' } catch { return false } })
  const [shopName, setShopName] = useState('')
  const [db, setDb] = useState<'ok' | 'down' | ''>('')
  const [theme, setTheme] = useState<'dark' | 'light'>(getStoredTheme())
  const [cmdOpen, setCmdOpen] = useState(false)
  const [shortcutsOpen, setShortcutsOpen] = useState(false)

  useEffect(() => { setStoredTheme(theme) }, [theme])
  const toggleTheme = useCallback(() => setTheme(t => (t === 'dark' ? 'light' : 'dark')), [])
  const toggleCollapsed = () => setCollapsed(c => { try { localStorage.setItem('rom-nav-collapsed', c ? '0' : '1') } catch { /* ignore */ } return !c })

  useEffect(() => {
    const out = () => setUser(null)
    window.addEventListener('rom-logout', out)
    if (getToken()) api('/auth/me').then(setUser).catch(() => setToken(null)).finally(() => setReady(true))
    else setReady(true)
    return () => window.removeEventListener('rom-logout', out)
  }, [])

  useEffect(() => {
    if (!user) return
    api('/settings').then(s => setShopName(s.restaurant_name)).catch(() => {})
    const ping = () => api('/health').then(() => setDb('ok')).catch(() => setDb('down'))
    ping()
    const t = setInterval(ping, 60000)
    return () => clearInterval(t)
  }, [user])

  useEffect(() => { setMobileOpen(false) }, [location.pathname])

  useEffect(() => {
    const go = (e: KeyboardEvent, path: string) => { e.preventDefault(); navigate(path) }
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'F1' || (e.key === '?' && !isTypingActive())) { e.preventDefault(); setShortcutsOpen(true); return }
      if (((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') || e.key === 'F2') { e.preventDefault(); setCmdOpen(p => !p); return }
      if (e.key === '/' && !isTypingActive()) { e.preventDefault(); setCmdOpen(true); return }
      if (e.altKey && e.key.toLowerCase() === 't') { e.preventDefault(); toggleTheme(); return }
      if (e.key === 'F3') return go(e, '/udhari/new-bill')
      if (e.key === 'F4') return go(e, '/receive')
      if (e.key === 'F8') return go(e, '/cash')
      if (e.key === 'F9') return go(e, '/expenses')
      if (e.altKey && !e.ctrlKey && !e.shiftKey) {
        const map: Record<string, string> = { '1': '/', '2': '/udhari', '3': '/udhari/new-bill', '4': '/receive', '5': '/cash', '6': '/expenses', '7': '/purchases', '8': '/inventory', '9': '/reports', '0': '/settings' }
        if (map[e.key]) return go(e, map[e.key])
      }
      if (((e.ctrlKey || e.metaKey) && e.key === 'Enter') || e.key === 'F10') {
        const form = (document.activeElement as HTMLElement | null)?.closest('form')
        const btn = (form?.querySelector('button[type="submit"]') || document.querySelector('[data-primary-action]')) as HTMLButtonElement | null
        if (btn && !btn.disabled) { e.preventDefault(); btn.click() }
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [navigate, toggleTheme])

  if (!ready) return <div className="boot"><div className="spinner" /> Loading…</div>
  if (!user) return <><Login onLogin={setUser} /><Toaster /></>

  const logout = () => { setToken(null); setUser(null) }
  const admin = user.role === 'admin'
  const title = TITLES.find(([re]) => re.test(location.pathname))?.[1] || ''

  return (
    <div className={`app-shell ${collapsed ? 'nav-collapsed' : ''}`}>
      <aside className={`side ${mobileOpen ? 'open' : ''}`} aria-label="Main navigation">
        <div className="side-brand">
          <span className="brand-mark"><Icon name="receipt" size={18} /></span>
          <div className="side-brand-text"><b title={shopName}>{shopName || 'Restaurant'}</b><small>Operations ledger</small></div>
        </div>
        <nav className="side-nav">
          {NAV_GROUPS.map(g => {
            const items = g.items.filter(i => !i.admin || admin)
            if (!items.length) return null
            return (
              <div className="side-group" key={g.title}>
                <div className="side-group-title">{g.title}</div>
                {items.map(i => (
                  <NavLink key={i.to} to={i.to} end={i.to === '/'} className="side-link" title={`${i.label} (${i.hint})`}>
                    <Icon name={i.icon} size={18} />
                    <span className="side-label">{i.label}</span>
                  </NavLink>
                ))}
              </div>
            )
          })}
        </nav>
        <button className="side-collapse" onClick={toggleCollapsed} aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}>
          <Icon name={collapsed ? 'chevronRight' : 'chevronLeft'} size={16} /><span className="side-label">Collapse</span>
        </button>
      </aside>
      {mobileOpen && <div className="scrim" onClick={() => setMobileOpen(false)} />}

      <div className="shell-main">
        <header className="topbar-x">
          <button className="icon-btn mobile-only" onClick={() => setMobileOpen(true)} aria-label="Open menu"><Icon name="menu" /></button>
          <div className="topbar-title">{title}</div>
          <button className="search-trigger" onClick={() => setCmdOpen(true)} aria-label="Search">
            <Icon name="search" size={16} /><span>Search customers, bills, receipts…</span><kbd className="kbd-sm">Ctrl K</kbd>
          </button>
          <div className="topbar-actions">
            <button className="btn small" onClick={() => navigate('/udhari/new-bill')} title="New udhari bill (F3)"><Icon name="plus" size={16} /><span className="hide-sm">New bill</span></button>
            <button className="btn small secondary hide-xs" onClick={() => navigate('/receive')} title="Receive payment (F4)"><Icon name="wallet" size={16} /><span className="hide-sm">Receive</span></button>
            {db && <span className={`db-dot ${db}`} title={db === 'ok' ? 'Server and database reachable' : 'Cannot reach the server — changes will not save'} />}
            <button className="icon-btn" onClick={() => setShortcutsOpen(true)} aria-label="Keyboard shortcuts" title="Keyboard shortcuts (F1)"><Icon name="keyboard" /></button>
            <button className="icon-btn" onClick={toggleTheme} aria-label="Toggle theme" title="Toggle theme (Alt+T)"><Icon name={theme === 'dark' ? 'sun' : 'moon'} /></button>
            <UserMenu user={user} onLogout={logout} />
          </div>
        </header>
        {db === 'down' && <div className="offline-bar"><Icon name="alert" size={16} /> Cannot reach the server. Check your connection — nothing you save now will be stored.</div>}

        <main className="main page-in" key={location.pathname}>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/udhari" element={<Customers />} />
            <Route path="/udhari/new-bill" element={<AddBill />} />
            <Route path="/udhari/:id" element={<CustomerDetail user={user} />} />
            <Route path="/receive" element={<ReceivePayment />} />
            <Route path="/expenses" element={<Expenses user={user} />} />
            <Route path="/purchases" element={<Purchases />} />
            <Route path="/inventory" element={<Inventory user={user} />} />
            <Route path="/cash" element={<Cash user={user} />} />
            <Route path="/reports" element={<Reports />} />
            <Route path="/settings" element={admin ? <Settings /> : <Navigate to="/" />} />
            <Route path="*" element={<Navigate to="/" />} />
          </Routes>
        </main>
      </div>

      <CommandPalette isOpen={cmdOpen} onClose={() => setCmdOpen(false)} onToggleTheme={toggleTheme} onOpenHelp={() => setShortcutsOpen(true)} isAdmin={admin} />
      {shortcutsOpen && <ShortcutsModal onClose={() => setShortcutsOpen(false)} />}
      <Toaster />
    </div>
  )
}
