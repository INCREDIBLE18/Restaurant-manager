import { ReactNode, useCallback, useEffect, useState } from 'react'
import { ApiError } from './api'
import { toast } from './toast'

export function useAsync<T>(fn: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const run = useCallback(() => {
    setLoading(true)
    return fn().then(d => { setData(d); setError('') }).catch(e => setError(e.message)).finally(() => setLoading(false))
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
  useEffect(() => { run() }, [run])
  return { data, error, loading, reload: run, setData }
}

export function ErrorBox({ msg }: { msg?: string }) {
  return msg ? <div className="alert error" role="alert"><span>⚠️</span> {msg}</div> : null
}

export function Notice({ msg, kind = 'info' }: { msg?: string; kind?: 'info' | 'warn' | 'ok' }) {
  const icon = kind === 'ok' ? '✓' : kind === 'warn' ? '⚠️' : 'ℹ️'
  return msg ? <div className={`alert ${kind}`}><span>{icon}</span> {msg}</div> : null
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
      {hint && <small>{hint}</small>}
    </label>
  )
}

export function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation()
        onClose()
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  return (
    <div className="modal-back" role="dialog" aria-modal="true" aria-label={title} onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <div className="modal-head">
          <h3>{title}</h3>
          <button className="btn small ghost" onClick={onClose} aria-label="Close">
            ✕ <kbd className="kbd-sm" style={{ marginLeft: 4 }}>Esc</kbd>
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}

export function Card({ title, value, sub, tone }: { title: string; value: ReactNode; sub?: ReactNode; tone?: 'bad' | 'good' | 'warn' }) {
  return (
    <div className={`card stat ${tone || ''}`}>
      <div className="stat-title">{title}</div>
      <div className="stat-value">{value}</div>
      {sub && <div className="stat-sub">{sub}</div>}
    </div>
  )
}

export function Badge({ status }: { status: string }) {
  const tone = ['paid', 'finalized', 'confirmed', 'mapped', 'posted'].includes(status) ? 'good'
    : ['partial', 'draft', 'reopened', 'new_item', 'open'].includes(status) ? 'warn'
    : ['unpaid', 'voided', 'unmapped', 'rejected', 'reversed'].includes(status) ? 'bad' : ''
  return <span className={`badge ${tone}`}>{status.replace(/_/g, ' ')}</span>
}

/** Submit helper: keeps form input on failure and shows the error. */
export function useSubmit() {
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  /** submit(fn) or submit('Saved', fn) — the message is shown as a toast on success. */
  const submit = async (a: string | (() => Promise<unknown>), b?: () => Promise<unknown>) => {
    const fn = (typeof a === 'string' ? b : a) as () => Promise<unknown>
    setBusy(true); setError('')
    try { await fn(); if (typeof a === 'string') toast(a); return true }
    catch (e) { setError(e instanceof ApiError ? e.message : String(e)); return false }
    finally { setBusy(false) }
  }
  return { error, busy, submit, setError }
}

export function Pager({ children }: { children: ReactNode }) {
  return <div className="table-wrap">{children}</div>
}

export function PrintButton() {
  return (
    <button className="btn ghost no-print" onClick={() => window.print()}>
      Print
    </button>
  )
}
