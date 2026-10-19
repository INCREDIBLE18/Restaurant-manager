import { useEffect, useState } from 'react'
import { NavLink, Navigate, Route, Routes, useNavigate } from 'react-router-dom'
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
import { PosHeader } from './PosHeader'
import { PosHud } from './PosHud'
import { CommandPalette } from './CommandPalette'
import { ShortcutsModal } from './ShortcutsModal'
import { getStoredTheme, isTypingActive, setStoredTheme } from './keyboard'

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
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '85vh', padding: 16 }}>
      <form className="card login" onSubmit={go}>
        <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 16 }}>
          <div style={{ width: 52, height: 52, borderRadius: 14, background: 'linear-gradient(135deg, var(--brand), #ea580c)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 26, boxShadow: '0 4px 16px var(--brand-glow)' }}>
            🍽️
          </div>
        </div>
        <h1 style={{ fontSize: '1.45rem', textAlign: 'center', margin: '0 0 4px' }}>Restaurant Operations</h1>
        <p className="muted" style={{ textAlign: 'center', fontSize: '0.86rem', margin: '0 0 20px' }}>
          POS Ledger & Operations Terminal
        </p>
        {needsSetup && <p className="alert info">First run: create the owner (admin) account. Password must be at least 8 characters.</p>}
        <ErrorBox msg={error} />
        <div className="form-grid" style={{ gridTemplateColumns: '1fr', gap: 14 }}>
          {needsSetup && (
            <Field label="Your name">
              <input value={fullName} onChange={e => setFullName(e.target.value)} placeholder="e.g. Ramesh Sharma" />
            </Field>
          )}
          <Field label="Username">
            <input value={username} onChange={e => setUsername(e.target.value)} autoFocus autoComplete="username" placeholder="cashier / admin" />
          </Field>
          <Field label="Password">
            <input type="password" value={password} onChange={e => setPassword(e.target.value)} autoComplete="current-password" placeholder="••••••••" />
          </Field>
        </div>
        <p style={{ marginTop: 20 }}>
          <button className="btn" style={{ width: '100%' }} disabled={busy || needsSetup === null}>
            {needsSetup ? 'Create Owner Account' : 'Sign In to Terminal'}
          </button>
        </p>
        <div style={{ textAlign: 'center', marginTop: 14 }}>
          <span style={{ fontSize: '0.78rem', color: 'var(--muted)' }}>
            Press <kbd className="kbd-sm">↵</kbd> to sign in · <kbd className="kbd-sm">Tab</kbd> to next field
          </span>
        </div>
      </form>
    </div>
  )
}

const NAV: [string, string, string, string][] = [
  ['/', 'Dashboard', '📊', 'Alt+1'],
  ['/udhari', 'Udhari / Customers', '👥', 'Alt+2'],
  ['/receive', 'Receive Payment', '💵', 'F4'],
  ['/expenses', 'Expenses & Payables', '🧾', 'F9'],
  ['/purchases', 'Purchases', '🛒', 'Alt+7'],
  ['/inventory', 'Inventory & Imports', '📦', 'Alt+8'],
  ['/cash', 'Daily Closing / Cash', '🔒', 'F8'],
  ['/reports', 'Reports & P&L', '📈', 'Alt+9'],
]

export default function App() {
  const navigate = useNavigate()
  const [user, setUser] = useState<User | null>(null)
  const [ready, setReady] = useState(false)
  const [open, setOpen] = useState(false)
  const [shopName, setShopName] = useState('')
  const [theme, setTheme] = useState<'dark' | 'light'>('dark')
  const [cmdOpen, setCmdOpen] = useState(false)
  const [shortcutsOpen, setShortcutsOpen] = useState(false)

  // Initialize theme
  useEffect(() => {
    const t = getStoredTheme()
    setTheme(t)
    setStoredTheme(t)
  }, [])

  const toggleTheme = () => {
    const next = theme === 'dark' ? 'light' : 'dark'
    setTheme(next)
    setStoredTheme(next)
  }

  useEffect(() => {
    const out = () => setUser(null)
    window.addEventListener('rom-logout', out)
    if (getToken()) {
      api('/auth/me').then(setUser).catch(() => setToken(null)).finally(() => setReady(true))
    } else {
      setReady(true)
    }
    return () => window.removeEventListener('rom-logout', out)
  }, [])

  useEffect(() => {
    if (user) {
      api('/settings').then(s => setShopName(s.restaurant_name)).catch(() => {})
    }
  }, [user])

  // Global Keyboard Shortcuts
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      // Escape closes modals/palettes
      if (e.key === 'Escape') {
        if (cmdOpen) {
          e.preventDefault()
          setCmdOpen(false)
          return
        }
        if (shortcutsOpen) {
          e.preventDefault()
          setShortcutsOpen(false)
          return
        }
      }

      // F1 or ? for Help / Shortcuts
      if (e.key === 'F1' || (e.key === '?' && !isTypingActive())) {
        e.preventDefault()
        setShortcutsOpen(true)
        return
      }

      // Ctrl+K or F2 for Command Palette
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setCmdOpen(prev => !prev)
        return
      }
      if (e.key === 'F2') {
        e.preventDefault()
        setCmdOpen(prev => !prev)
        return
      }

      // Alt+T for Theme toggle
      if (e.altKey && e.key.toLowerCase() === 't') {
        e.preventDefault()
        toggleTheme()
        return
      }

      // POS Hotkeys
      if (e.key === 'F3') {
        e.preventDefault()
        navigate('/udhari/new-bill')
        return
      }
      if (e.key === 'F4') {
        e.preventDefault()
        navigate('/receive')
        return
      }
      if (e.key === 'F8') {
        e.preventDefault()
        navigate('/cash')
        return
      }
      if (e.key === 'F9') {
        e.preventDefault()
        navigate('/expenses')
        return
      }

      // Alt + number page jumps
      if (e.altKey && !e.ctrlKey && !e.shiftKey) {
        if (e.key === '1') { e.preventDefault(); navigate('/') }
        else if (e.key === '2') { e.preventDefault(); navigate('/udhari') }
        else if (e.key === '3') { e.preventDefault(); navigate('/udhari/new-bill') }
        else if (e.key === '4') { e.preventDefault(); navigate('/receive') }
        else if (e.key === '5') { e.preventDefault(); navigate('/cash') }
        else if (e.key === '6') { e.preventDefault(); navigate('/expenses') }
        else if (e.key === '7') { e.preventDefault(); navigate('/purchases') }
        else if (e.key === '8') { e.preventDefault(); navigate('/inventory') }
        else if (e.key === '9') { e.preventDefault(); navigate('/reports') }
        else if (e.key === '0') { e.preventDefault(); navigate('/settings') }
      }

      // Universal Form Save: Ctrl+Enter or F10
      if (((e.ctrlKey || e.metaKey) && e.key === 'Enter') || e.key === 'F10') {
        const active = document.activeElement as HTMLElement | null
        const form = active?.closest('form')
        if (form) {
          e.preventDefault()
          const submitBtn = form.querySelector('button[type="submit"]') as HTMLButtonElement | null
          if (submitBtn) {
            submitBtn.click()
            return
          }
        }
        // If not in a form or form has no type=submit, click primary save button
        const saveBtn = document.querySelector('.card .btn:not(.secondary):not(.ghost):not(.danger)') as HTMLButtonElement | null
        if (saveBtn && !saveBtn.disabled) {
          e.preventDefault()
          saveBtn.click()
        }
      }
    }

    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [cmdOpen, shortcutsOpen, navigate, theme])

  if (!ready) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh', gap: 12, color: 'var(--muted)' }}>
        <div className="status-pill-dot" />
        <span>Initializing POS Terminal…</span>
      </div>
    )
  }

  if (!user) return <Login onLogin={setUser} />

  const logout = () => {
    setToken(null)
    setUser(null)
  }
  const admin = user.role === 'admin'

  return (
    <div className="layout">
      {/* Mobile Topbar */}
      <div className="topbar">
        <button className="btn small secondary" onClick={() => setOpen(!open)} aria-label="Menu">☰ Menu</button>
        <b>{shopName || 'Restaurant POS'}</b>
        <button className="btn small ghost" onClick={toggleTheme} aria-label="Toggle Theme">{theme === 'dark' ? '☀️' : '🌙'}</button>
      </div>

      {/* POS Desktop Sidebar */}
      <nav className={`sidebar ${open ? 'open' : ''}`} onClick={() => setOpen(false)}>
        <div className="brand">
          <div className="brand-title">
            <div className="brand-icon">🍽️</div>
            <span>{shopName || 'Restaurant POS'}</span>
          </div>
          <small>Operations & Cash Ledger</small>
        </div>

        <div className="sidebar-nav-list">
          {NAV.map(([to, label, icon, shortcut]) => (
            <NavLink key={to} to={to} end={to === '/'}>
              <div className="nav-label-wrap">
                <span className="nav-icon">{icon}</span>
                <span>{label}</span>
              </div>
              <kbd className="kbd-sm">{shortcut}</kbd>
            </NavLink>
          ))}
          {admin && (
            <NavLink to="/settings">
              <div className="nav-label-wrap">
                <span className="nav-icon">⚙️</span>
                <span>Settings & Admin</span>
              </div>
              <kbd className="kbd-sm">Alt+0</kbd>
            </NavLink>
          )}
        </div>

        <div className="user">
          <div className="user-info">
            <span className="user-name">{user.full_name || user.username}</span>
            <span className="user-role">{user.role}</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 8 }}>
            <span style={{ fontSize: '0.74rem', color: 'var(--muted)' }}>Register Active</span>
            <a href="#" style={{ color: 'var(--bad)', fontSize: '0.78rem', fontWeight: 600 }} onClick={e => { e.preventDefault(); logout() }}>
              Sign out
            </a>
          </div>
        </div>
      </nav>

      {/* Mobile sidebar overlay — close when tapped */}
      {open && <div className="sidebar-overlay visible" onClick={() => setOpen(false)} />}

      {/* Main Container */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        {/* Modern POS HUD Header */}
        <PosHeader
          shopName={shopName}
          theme={theme}
          onToggleTheme={toggleTheme}
          onOpenCommandPalette={() => setCmdOpen(true)}
          onOpenShortcuts={() => setShortcutsOpen(true)}
        />

        <main className="main">
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

        {/* Bottom Hotkey HUD / Ticker */}
        <PosHud
          onOpenCommandPalette={() => setCmdOpen(true)}
          onOpenShortcuts={() => setShortcutsOpen(true)}
          onToggleTheme={toggleTheme}
        />
      </div>

      {/* Global Command Palette */}
      <CommandPalette
        isOpen={cmdOpen}
        onClose={() => setCmdOpen(false)}
        onToggleTheme={toggleTheme}
        onOpenHelp={() => setShortcutsOpen(true)}
      />

      {/* Global Keyboard Shortcuts Modal */}
      {shortcutsOpen && <ShortcutsModal onClose={() => setShortcutsOpen(false)} />}
    </div>
  )
}
