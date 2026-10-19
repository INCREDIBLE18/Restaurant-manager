import { useEffect } from 'react'

export type KeyCombo = {
  key: string
  ctrl?: boolean
  alt?: boolean
  shift?: boolean
  description: string
  category: 'Navigation' | 'Actions' | 'Billing' | 'System'
  action: () => void
}

/** Check if active element is an input or textarea */
export function isTypingActive(): boolean {
  const el = document.activeElement
  if (!el) return false
  const tag = el.tagName.toLowerCase()
  return tag === 'input' || tag === 'textarea' || tag === 'select' || (el as HTMLElement).isContentEditable
}

/** Theme storage helper */
export function getStoredTheme(): 'dark' | 'light' {
  const t = localStorage.getItem('rom-theme')
  if (t === 'light' || t === 'dark') return t
  return 'dark'
}

export function setStoredTheme(theme: 'dark' | 'light') {
  localStorage.setItem('rom-theme', theme)
  document.documentElement.setAttribute('data-theme', theme)
}

/** Hook for listening to key combos */
export function useKeyboardShortcut(combo: {
  key: string
  ctrl?: boolean
  alt?: boolean
  shift?: boolean
  allowInInputs?: boolean
  onTrigger: (e: KeyboardEvent) => void
}) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (!combo.allowInInputs && isTypingActive()) return

      const matchKey = e.key.toLowerCase() === combo.key.toLowerCase()
      const matchCtrl = combo.ctrl ? e.ctrlKey || e.metaKey : true
      const matchAlt = combo.alt ? e.altKey : true
      const matchShift = combo.shift ? e.shiftKey : true

      if (matchKey && matchCtrl && matchAlt && matchShift) {
        e.preventDefault()
        combo.onTrigger(e)
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [combo])
}
