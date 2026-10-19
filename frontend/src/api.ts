const KEY = 'rom_token'

export const getToken = () => {
  try { return localStorage.getItem(KEY) } catch { return null }
}
export const setToken = (t: string | null) => {
  try { t ? localStorage.setItem(KEY, t) : localStorage.removeItem(KEY) } catch { /* ignore */ }
}

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) { super(message); this.status = status }
}

type Opts = { method?: string; body?: unknown; form?: FormData }

export async function api<T = any>(path: string, opts: Opts = {}): Promise<T> {
  const headers: Record<string, string> = {}
  const t = getToken()
  if (t) headers.Authorization = `Bearer ${t}`
  let body: BodyInit | undefined
  if (opts.form) body = opts.form
  else if (opts.body !== undefined) { headers['Content-Type'] = 'application/json'; body = JSON.stringify(opts.body) }
  let res: Response
  try {
    res = await fetch('/api/v1' + path, { method: opts.method || (body ? 'POST' : 'GET'), headers, body })
  } catch {
    throw new ApiError('Cannot reach the server. Check that the backend is running; your input has not been cleared.', 0)
  }
  if (res.status === 401 && !path.startsWith('/auth/')) {
    setToken(null)
    window.dispatchEvent(new Event('rom-logout'))
  }
  if (!res.ok) {
    let msg = `Request failed (${res.status})`
    try { const j = await res.json(); if (j.detail) msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail) } catch { /* ignore */ }
    throw new ApiError(msg, res.status)
  }
  return res.json()
}

export async function downloadCsv(path: string, filename: string) {
  const t = getToken()
  const res = await fetch('/api/v1' + path, { headers: t ? { Authorization: `Bearer ${t}` } : {} })
  if (!res.ok) throw new ApiError('Export failed', res.status)
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = filename; a.click()
  URL.revokeObjectURL(url)
}

const inr = new Intl.NumberFormat('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
/** Display only. All arithmetic happens on the backend with Decimal. */
export function fmt(v: unknown): string {
  if (v === null || v === undefined || v === '') return '—'
  const n = Number(v)
  return Number.isFinite(n) ? '₹' + inr.format(n) : String(v)
}
export const num = (v: unknown) => Number(v ?? 0)

export function fmtDate(d?: string | null) {
  if (!d) return '—'
  const [y, m, day] = d.slice(0, 10).split('-')
  return `${day}-${m}-${y}`
}
export const todayIso = () => new Date(new Date().toLocaleString('en-US', { timeZone: 'Asia/Kolkata' })).toLocaleDateString('en-CA')

/** Open an uploaded attachment (needs the auth header, so fetch as a blob). */
export async function openAttachment(name: string) {
  const t = getToken()
  const res = await fetch('/api/v1/attachments/' + name, { headers: t ? { Authorization: `Bearer ${t}` } : {} })
  if (!res.ok) throw new ApiError('Could not open attachment', res.status)
  window.open(URL.createObjectURL(await res.blob()), '_blank')
}
