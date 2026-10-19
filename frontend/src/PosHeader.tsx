import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

export function PosHeader({
  shopName,
  theme,
  onToggleTheme,
  onOpenCommandPalette,
  onOpenShortcuts,
}: {
  shopName: string
  theme: 'dark' | 'light'
  onToggleTheme: () => void
  onOpenCommandPalette: () => void
  onOpenShortcuts: () => void
}) {
  const navigate = useNavigate()
  const [timeStr, setTimeStr] = useState('')

  useEffect(() => {
    const update = () => {
      const now = new Date()
      const time = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
      const date = now.toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' })
      setTimeStr(`${date} · ${time}`)
    }
    update()
    const timer = setInterval(update, 1000)
    return () => clearInterval(timer)
  }, [])

  return (
    <header className="pos-header">
      <div className="pos-header-left">
        <div className="status-pill">
          <span className="status-pill-dot" />
          <span>Register Online</span>
        </div>
        <div className="pos-clock" title="Current POS Terminal Time">
          <span>🕒</span>
          <span>{timeStr}</span>
        </div>
      </div>

      <div
        className="pos-omni-bar"
        onClick={onOpenCommandPalette}
        title="Open command palette & customer search (Ctrl+K or F2)"
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span>🔍</span>
          <span>Quick search customer or jump to…</span>
        </div>
        <div style={{ display: 'flex', gap: 4 }}>
          <kbd className="kbd-sm">Ctrl</kbd>
          <kbd className="kbd-sm">K</kbd>
        </div>
      </div>

      <div className="pos-header-actions">
        <button
          className="btn small"
          onClick={() => navigate('/udhari/new-bill')}
          title="Add udhari credit bill (F3)"
        >
          <span>+ Bill</span>
          <kbd className="kbd-sm kbd-accent">F3</kbd>
        </button>

        <button
          className="btn small secondary"
          onClick={() => navigate('/receive')}
          title="Receive payment (F4)"
        >
          <span>Receive</span>
          <kbd className="kbd-sm">F4</kbd>
        </button>

        <button
          className="btn small ghost"
          onClick={onToggleTheme}
          title="Toggle Dark / Light Theme (Alt+T)"
          aria-label="Toggle Theme"
        >
          <span>{theme === 'dark' ? '☀️ Light' : '🌙 Dark'}</span>
          <kbd className="kbd-sm">Alt+T</kbd>
        </button>

        <button
          className="btn small ghost"
          onClick={onOpenShortcuts}
          title="Keyboard shortcuts help (F1 or ?)"
          aria-label="Shortcuts"
        >
          <span>⌨️</span>
          <kbd className="kbd-sm">?</kbd>
        </button>
      </div>
    </header>
  )
}
