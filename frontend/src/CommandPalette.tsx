import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from './api'
import { Icon } from './icons'

type Item = { id: string; title: string; sub?: string; icon: string; group: string; hint?: string; run: () => void }

const TYPE_ICON: Record<string, string> = { customer: 'users', bill: 'file', receipt: 'wallet', expense: 'receipt', vendor: 'truck' }
const TYPE_GROUP: Record<string, string> = { customer: 'Customers', bill: 'Bills', receipt: 'Receipts', expense: 'Expenses', vendor: 'Suppliers' }

export function CommandPalette({ isOpen, onClose, onToggleTheme, onOpenHelp, isAdmin = false }: {
  isOpen: boolean; onClose: () => void; onToggleTheme: () => void; onOpenHelp: () => void; isAdmin?: boolean
}) {
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [sel, setSel] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (isOpen) { setQuery(''); setResults([]); setSel(0); setTimeout(() => inputRef.current?.focus(), 20) }
  }, [isOpen])

  useEffect(() => {
    if (query.trim().length < 2) { setResults([]); return }
    setLoading(true)
    const t = setTimeout(() => {
      api(`/search?q=${encodeURIComponent(query.trim())}`).then(r => setResults(r.results)).catch(() => setResults([])).finally(() => setLoading(false))
    }, 160)
    return () => clearTimeout(t)
  }, [query])

  useEffect(() => { (listRef.current?.querySelector('.cmd-item.selected') as HTMLElement | null)?.scrollIntoView?.({ block: 'nearest' }) }, [sel])

  if (!isOpen) return null
  const go = (path: string) => () => { navigate(path); onClose() }

  const actions: Item[] = [
    { id: 'a-bill', title: 'New udhari bill', sub: 'Record a credit bill', icon: 'plus', group: 'Actions', hint: 'F3', run: go('/udhari/new-bill') },
    { id: 'a-receive', title: 'Receive payment', sub: 'Collect against open bills', icon: 'wallet', group: 'Actions', hint: 'F4', run: go('/receive') },
    { id: 'a-close', title: 'Cash closing', sub: 'Count the drawer and close the day', icon: 'lock', group: 'Actions', hint: 'F8', run: go('/cash') },
    { id: 'a-exp', title: 'Expenses & payables', sub: 'Add or pay an expense', icon: 'receipt', group: 'Actions', hint: 'F9', run: go('/expenses') },
    { id: 'n-dash', title: 'Dashboard', icon: 'dashboard', group: 'Go to', hint: 'Alt+1', run: go('/') },
    { id: 'n-cust', title: 'Customers & Udhari', icon: 'users', group: 'Go to', hint: 'Alt+2', run: go('/udhari') },
    { id: 'n-pur', title: 'Purchases', icon: 'cart', group: 'Go to', hint: 'Alt+7', run: go('/purchases') },
    { id: 'n-inv', title: 'Inventory & imports', icon: 'box', group: 'Go to', hint: 'Alt+8', run: go('/inventory') },
    { id: 'n-rep', title: 'Reports', icon: 'chart', group: 'Go to', hint: 'Alt+9', run: go('/reports') },
    ...(isAdmin ? [{ id: 'n-set', title: 'Settings, users & backup', icon: 'settings', group: 'Go to', hint: 'Alt+0', run: go('/settings') }] : []),
    { id: 's-theme', title: 'Toggle light / dark theme', icon: 'sun', group: 'System', hint: 'Alt+T', run: () => { onToggleTheme(); onClose() } },
    { id: 's-help', title: 'Keyboard shortcuts', icon: 'keyboard', group: 'System', hint: 'F1', run: () => { onClose(); onOpenHelp() } },
  ]
  const q = query.trim().toLowerCase()
  const found: Item[] = results.map(r => ({ id: `${r.type}-${r.id}`, title: r.title, sub: r.subtitle, icon: TYPE_ICON[r.type] || 'file',
    group: TYPE_GROUP[r.type] || 'Results', run: go(r.url) }))
  const items = [...found, ...actions.filter(a => !q || `${a.title} ${a.sub || ''}`.toLowerCase().includes(q))]

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setSel(s => (s + 1) % Math.max(items.length, 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setSel(s => (s - 1 + items.length) % Math.max(items.length, 1)) }
    else if (e.key === 'Enter') { e.preventDefault(); items[sel]?.run() }
    else if (e.key === 'Escape') { e.preventDefault(); onClose() }
  }

  let lastGroup = ''
  return (
    <div className="modal-back palette-back" onClick={onClose}>
      <div className="cmd-palette" onClick={e => e.stopPropagation()} role="dialog" aria-label="Search and commands">
        <div className="cmd-input-wrap">
          <Icon name="search" size={18} />
          <input ref={inputRef} className="cmd-input" placeholder="Search customers, bill or receipt numbers, expenses… or type a command"
            value={query} onChange={e => { setQuery(e.target.value); setSel(0) }} onKeyDown={onKey} aria-label="Search" />
          {loading ? <div className="spinner sm" /> : <kbd className="kbd-sm">Esc</kbd>}
        </div>
        <div className="cmd-list" ref={listRef}>
          {items.length === 0 && <div className="empty-mini">No matches for “{query}”</div>}
          {items.map((it, idx) => {
            const head = it.group !== lastGroup ? (lastGroup = it.group) : null
            return (
              <div key={it.id}>
                {head && <div className="cmd-group">{head}</div>}
                <div className={`cmd-item ${idx === sel ? 'selected' : ''}`} onClick={it.run} onMouseEnter={() => setSel(idx)}>
                  <div className="cmd-item-left">
                    <span className="cmd-ico"><Icon name={it.icon} size={16} /></span>
                    <div className="cmd-text"><span className="cmd-title">{it.title}</span>{it.sub && <span className="cmd-item-sub">{it.sub}</span>}</div>
                  </div>
                  {it.hint && <kbd className="kbd-sm">{it.hint}</kbd>}
                </div>
              </div>
            )
          })}
        </div>
        <div className="cmd-foot"><span><kbd className="kbd-sm">↑</kbd><kbd className="kbd-sm">↓</kbd> navigate</span><span><kbd className="kbd-sm">↵</kbd> open</span><span><kbd className="kbd-sm">/</kbd> or <kbd className="kbd-sm">Ctrl K</kbd> anywhere</span></div>
      </div>
    </div>
  )
}
