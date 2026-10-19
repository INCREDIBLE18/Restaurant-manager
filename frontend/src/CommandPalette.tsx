import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, fmt } from './api'

export type PaletteAction = {
  id: string
  title: string
  sub?: string
  shortcut?: string[]
  icon: string
  category: string
  run: () => void
}

export function CommandPalette({
  isOpen,
  onClose,
  onToggleTheme,
  onOpenHelp,
}: {
  isOpen: boolean
  onClose: () => void
  onToggleTheme: () => void
  onOpenHelp: () => void
}) {
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [customers, setCustomers] = useState<any[]>([])
  const [selectedIndex, setSelectedIndex] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (isOpen) {
      setQuery('')
      setCustomers([])
      setSelectedIndex(0)
      setTimeout(() => inputRef.current?.focus(), 30)
    }
  }, [isOpen])

  // Search customers when typing
  useEffect(() => {
    if (!query.trim()) {
      setCustomers([])
      return
    }
    const t = setTimeout(() => {
      api(`/customers?q=${encodeURIComponent(query)}`)
        .then(list => setCustomers(list.slice(0, 5)))
        .catch(() => {})
    }, 150)
    return () => clearTimeout(t)
  }, [query])

  if (!isOpen) return null

  const staticActions: PaletteAction[] = [
    {
      id: 'nav-add-bill',
      title: '+ Add Udhari (Credit) Bill',
      sub: 'Record customer bill on credit',
      shortcut: ['F3'],
      icon: '📝',
      category: 'Billing & Cashier',
      run: () => { navigate('/udhari/new-bill'); onClose() },
    },
    {
      id: 'nav-receive-payment',
      title: 'Receive Payment',
      sub: 'Collect cash/UPI against open bills',
      shortcut: ['F4'],
      icon: '💵',
      category: 'Billing & Cashier',
      run: () => { navigate('/receive'); onClose() },
    },
    {
      id: 'nav-cash-closing',
      title: 'Daily Closing & Cash Drawer',
      sub: 'Physical cash count and day finalize',
      shortcut: ['F8'],
      icon: '🔒',
      category: 'Operations',
      run: () => { navigate('/cash'); onClose() },
    },
    {
      id: 'nav-expenses',
      title: 'Expenses & Vendor Payables',
      sub: 'Record bills, gas, ingredients, salary',
      shortcut: ['F9'],
      icon: '🧾',
      category: 'Operations',
      run: () => { navigate('/expenses'); onClose() },
    },
    {
      id: 'nav-dashboard',
      title: 'Dashboard Overview',
      sub: 'Today metrics, balances, alerts',
      shortcut: ['Alt', '1'],
      icon: '📊',
      category: 'Navigation',
      run: () => { navigate('/'); onClose() },
    },
    {
      id: 'nav-udhari',
      title: 'Udhari / Customer Directory',
      sub: 'View all balances, send reminders',
      shortcut: ['Alt', '2'],
      icon: '👥',
      category: 'Navigation',
      run: () => { navigate('/udhari'); onClose() },
    },
    {
      id: 'nav-purchases',
      title: 'Purchases',
      sub: 'Supplier invoices & stock entries',
      shortcut: ['Alt', '7'],
      icon: '🛒',
      category: 'Navigation',
      run: () => { navigate('/purchases'); onClose() },
    },
    {
      id: 'nav-inventory',
      title: 'Inventory & POS PDF Imports',
      sub: 'Import Item Sales & Sales Summary',
      shortcut: ['Alt', '8'],
      icon: '📦',
      category: 'Navigation',
      run: () => { navigate('/inventory'); onClose() },
    },
    {
      id: 'nav-reports',
      title: 'Reports & P&L',
      sub: 'Daybook, customer statement, item sales',
      shortcut: ['Alt', '9'],
      icon: '📈',
      category: 'Navigation',
      run: () => { navigate('/reports'); onClose() },
    },
    {
      id: 'nav-settings',
      title: 'Settings / Users / Backup',
      sub: 'Admin config, database backup',
      shortcut: ['Alt', '0'],
      icon: '⚙️',
      category: 'Navigation',
      run: () => { navigate('/settings'); onClose() },
    },
    {
      id: 'act-theme',
      title: 'Toggle Dark / Light Theme',
      sub: 'Switch POS display mode',
      shortcut: ['Alt', 'T'],
      icon: '🌓',
      category: 'Appearance',
      run: () => { onToggleTheme(); onClose() },
    },
    {
      id: 'act-shortcuts',
      title: 'Keyboard Shortcuts Help',
      sub: 'Interactive keybindings cheat-sheet',
      shortcut: ['F1', '?'],
      icon: '⌨️',
      category: 'Help',
      run: () => { onClose(); onOpenHelp() },
    },
  ]

  // Filter static actions based on query
  const filteredActions = staticActions.filter(a => {
    if (!query.trim()) return true
    const q = query.toLowerCase()
    return a.title.toLowerCase().includes(q) || (a.sub && a.sub.toLowerCase().includes(q)) || a.category.toLowerCase().includes(q)
  })

  // Customer actions from search
  const customerActions: PaletteAction[] = customers.map(c => ({
    id: `cust-${c.id}`,
    title: c.name,
    sub: `Phone: ${c.phone} · Outstanding: ${fmt(c.outstanding)}`,
    icon: '👤',
    category: 'Customers (Direct Jump)',
    run: () => { navigate(`/udhari/${c.id}`); onClose() },
  }))

  const allItems: PaletteAction[] = [...customerActions, ...filteredActions]

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setSelectedIndex(prev => (prev + 1) % (allItems.length || 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setSelectedIndex(prev => (prev - 1 + allItems.length) % (allItems.length || 1))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      if (allItems[selectedIndex]) {
        allItems[selectedIndex].run()
      }
    } else if (e.key === 'Escape') {
      e.preventDefault()
      onClose()
    }
  }

  return (
    <div className="modal-back" onClick={onClose}>
      <div className="cmd-palette" onClick={e => e.stopPropagation()}>
        <div className="cmd-input-wrap">
          <span className="cmd-search-icon">🔍</span>
          <input
            ref={inputRef}
            className="cmd-input"
            placeholder="Search customer, jump to page, or run command… (↑↓ to select, ↵ to run)"
            value={query}
            onChange={e => { setQuery(e.target.value); setSelectedIndex(0) }}
            onKeyDown={handleKeyDown}
          />
          <kbd>Esc</kbd>
        </div>

        <div className="cmd-list">
          {allItems.length === 0 ? (
            <div style={{ padding: '24px 16px', textAlign: 'center', color: 'var(--muted)' }}>
              No matches found for "{query}"
            </div>
          ) : (
            allItems.map((item, idx) => {
              const isSelected = idx === selectedIndex
              return (
                <div
                  key={item.id}
                  className={`cmd-item ${isSelected ? 'selected' : ''}`}
                  onClick={item.run}
                  onMouseEnter={() => setSelectedIndex(idx)}
                >
                  <div className="cmd-item-left">
                    <span style={{ fontSize: '1.1rem' }}>{item.icon}</span>
                    <div>
                      <span style={{ fontWeight: 600 }}>{item.title}</span>
                      {item.sub && <span className="cmd-item-sub">— {item.sub}</span>}
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
                    {item.shortcut?.map((k, kIdx) => <kbd key={kIdx} className="kbd-sm">{k}</kbd>)}
                  </div>
                </div>
              )
            })
          )}
        </div>
      </div>
    </div>
  )
}
