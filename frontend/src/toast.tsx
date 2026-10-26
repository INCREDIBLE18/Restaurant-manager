import { useEffect, useState } from 'react'
import { Icon } from './icons'

type Toast = { id: number; msg: string; kind: 'ok' | 'error' | 'info' }
let seq = 0

/** Fire-and-forget notification from anywhere: toast('Receipt saved'). */
export function toast(msg: string, kind: Toast['kind'] = 'ok') {
  window.dispatchEvent(new CustomEvent<Toast>('rom-toast', { detail: { id: ++seq, msg, kind } }))
}

export function Toaster() {
  const [items, setItems] = useState<Toast[]>([])
  useEffect(() => {
    const on = (e: Event) => {
      const t = (e as CustomEvent<Toast>).detail
      setItems(p => [...p.slice(-3), t])
      setTimeout(() => setItems(p => p.filter(x => x.id !== t.id)), t.kind === 'error' ? 6000 : 3500)
    }
    window.addEventListener('rom-toast', on)
    return () => window.removeEventListener('rom-toast', on)
  }, [])
  return (
    <div className="toaster" role="status" aria-live="polite">
      {items.map(t => (
        <div key={t.id} className={`toast toast-${t.kind}`}>
          <Icon name={t.kind === 'ok' ? 'check' : t.kind === 'error' ? 'alert' : 'info'} size={16} />
          <span>{t.msg}</span>
          <button className="toast-x" aria-label="Dismiss" onClick={() => setItems(p => p.filter(x => x.id !== t.id))}><Icon name="x" size={14} /></button>
        </div>
      ))}
    </div>
  )
}
