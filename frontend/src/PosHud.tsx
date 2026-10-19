import { useNavigate } from 'react-router-dom'

export function PosHud({
  onOpenCommandPalette,
  onOpenShortcuts,
  onToggleTheme,
}: {
  onOpenCommandPalette: () => void
  onOpenShortcuts: () => void
  onToggleTheme: () => void
}) {
  const navigate = useNavigate()

  return (
    <footer className="pos-hud no-print">
      <div className="pos-hud-shortcuts">
        <span className="pos-hud-item" onClick={onOpenShortcuts} title="Open keyboard cheat-sheet">
          <kbd className="kbd-sm">F1</kbd> <span>Help</span>
        </span>

        <span className="pos-hud-item" onClick={onOpenCommandPalette} title="Omni-search">
          <kbd className="kbd-sm">Ctrl+K</kbd> <span>Search</span>
        </span>

        <span className="pos-hud-item" onClick={() => navigate('/udhari/new-bill')} title="Add Udhari Bill">
          <kbd className="kbd-sm kbd-accent">F3</kbd> <span>+Bill</span>
        </span>

        <span className="pos-hud-item" onClick={() => navigate('/receive')} title="Receive Payment">
          <kbd className="kbd-sm">F4</kbd> <span>Receive</span>
        </span>

        <span className="pos-hud-item" onClick={() => navigate('/cash')} title="Cash Drawer Closing">
          <kbd className="kbd-sm">F8</kbd> <span>Cash Close</span>
        </span>

        <span className="pos-hud-item" onClick={() => navigate('/expenses')} title="Expenses">
          <kbd className="kbd-sm">F9</kbd> <span>Expenses</span>
        </span>

        <span className="pos-hud-item" title="Universal form save shortcut">
          <kbd className="kbd-sm">Ctrl+↵</kbd> <span>Quick Save</span>
        </span>

        <span className="pos-hud-item" onClick={onToggleTheme} title="Switch theme">
          <kbd className="kbd-sm">Alt+T</kbd> <span>Theme</span>
        </span>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <span style={{ opacity: 0.8, fontSize: '0.74rem' }}>POS Keyboard Mode Active</span>
        <kbd className="kbd-sm">Esc</kbd> <span style={{ opacity: 0.8, fontSize: '0.74rem' }}>Dismiss</span>
      </div>
    </footer>
  )
}
