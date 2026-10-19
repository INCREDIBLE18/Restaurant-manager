import { Modal } from './ui'

export function ShortcutsModal({ onClose }: { onClose: () => void }) {
  const categories = [
    {
      title: 'Global Hotkeys & Operations',
      items: [
        { keys: ['F1', 'or', '?'], desc: 'Open this Keyboard Shortcuts cheat-sheet' },
        { keys: ['Ctrl', 'K'], desc: 'Open Command Palette & Omni-Search' },
        { keys: ['F2'], desc: 'Alternative quick search shortcut' },
        { keys: ['F3'], desc: 'Jump to + Add Udhari (Credit) Bill' },
        { keys: ['F4'], desc: 'Jump to Receive Payment / Settle Bill' },
        { keys: ['F8'], desc: 'Jump to Daily Closing & Cash Drawer' },
        { keys: ['F9'], desc: 'Jump to Expenses & Vendor Payables' },
        { keys: ['Alt', 'T'], desc: 'Toggle Dark / Light POS Theme' },
        { keys: ['Esc'], desc: 'Close any active modal or search' },
      ],
    },
    {
      title: 'Form & Cashier Rapid Entry',
      items: [
        { keys: ['Ctrl', 'Enter'], desc: 'Quick Save / Submit active bill or form' },
        { keys: ['F10'], desc: 'POS Quick Save from anywhere in a form' },
        { keys: ['Enter'], desc: 'Advance to the next input in form grids' },
        { keys: ['Alt', 'N'], desc: 'Create new customer inline in picker' },
        { keys: ['↑', '↓'], desc: 'Navigate search suggestions or customer list' },
      ],
    },
    {
      title: 'Module Navigation',
      items: [
        { keys: ['Alt', '1'], desc: 'Dashboard Overview' },
        { keys: ['Alt', '2'], desc: 'Udhari / Customer Directory' },
        { keys: ['Alt', '3'], desc: 'Add Udhari Bill' },
        { keys: ['Alt', '4'], desc: 'Receive Payment' },
        { keys: ['Alt', '5'], desc: 'Daily Cash Closing / Cashbook' },
        { keys: ['Alt', '6'], desc: 'Expenses & Payables' },
        { keys: ['Alt', '7'], desc: 'Purchases' },
        { keys: ['Alt', '8'], desc: 'Inventory & POS PDF Imports' },
        { keys: ['Alt', '9'], desc: 'Reports & P&L' },
        { keys: ['Alt', '0'], desc: 'Settings / Admin' },
      ],
    },
  ]

  return (
    <Modal title="⌨️ POS Keyboard Shortcuts Cheat-Sheet" onClose={onClose}>
      <p className="muted" style={{ marginTop: -8, marginBottom: 16 }}>
        Designed for high-speed cashier and billing desk operations without needing a mouse.
      </p>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
        {categories.map(cat => (
          <div key={cat.title}>
            <div style={{ fontSize: '0.85rem', fontWeight: 700, textTransform: 'uppercase', color: 'var(--brand)', letterSpacing: '0.05em', marginBottom: 8 }}>
              {cat.title}
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '8px 16px' }}>
              {cat.items.map((item, idx) => (
                <div key={idx} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '6px 8px', background: 'var(--panel-elevated)', borderRadius: 8, border: '1px solid var(--line)' }}>
                  <span style={{ fontSize: '0.86rem', color: 'var(--ink)' }}>{item.desc}</span>
                  <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
                    {item.keys.map((k, kIdx) => (
                      k === 'or' ? <span key={kIdx} style={{ fontSize: '0.72rem', color: 'var(--muted)' }}>or</span> : <kbd key={kIdx}>{k}</kbd>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      <div style={{ marginTop: 20, textAlign: 'right' }}>
        <button className="btn" onClick={onClose}>Got it <kbd style={{ marginLeft: 6 }}>Esc</kbd></button>
      </div>
    </Modal>
  )
}
