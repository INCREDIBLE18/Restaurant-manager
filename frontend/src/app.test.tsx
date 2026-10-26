import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { fmt, fmtDate } from './api'
import { AccountSelect } from './shared'
import { AddBill } from './pages/Udhari'

const accounts = [
  { id: 1, name: 'Cash Drawer', type: 'cash', is_physical_cash: true, active: true, balance: '0' },
  { id: 2, name: 'UPI', type: 'upi', is_physical_cash: false, active: true, balance: '0' },
]

describe('formatting', () => {
  it('formats rupees with Indian digit grouping', () => {
    expect(fmt('1234567.5')).toBe('₹12,34,567.50')
    expect(fmt(null)).toBe('—')
  })
  it('formats dates as dd-mm-yyyy', () => expect(fmtDate('2026-09-30')).toBe('30-09-2026'))
})

describe('AccountSelect', () => {
  it('offers only the cash drawer for cash payments', () => {
    render(<AccountSelect accounts={accounts} method="cash" value={1} onChange={() => {}} />)
    expect(screen.getByRole('option', { name: 'Cash Drawer' })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: 'UPI' })).toBeNull()
  })
  it('offers only non-cash accounts for UPI', () => {
    render(<AccountSelect accounts={accounts} method="upi" value={2} onChange={() => {}} />)
    expect(screen.queryByRole('option', { name: 'Cash Drawer' })).toBeNull()
    expect(screen.getByRole('option', { name: 'UPI' })).toBeInTheDocument()
  })
})

describe('AddBill form', () => {
  it('calculates the udhari balance instead of letting it be typed', () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(new Response('[]', { status: 200 }))))
    render(<MemoryRouter><AddBill /></MemoryRouter>)
    fireEvent.change(screen.getByLabelText(/Bill total/), { target: { value: '1200' } })
    fireEvent.change(screen.getByLabelText(/Received now/), { target: { value: '500' } })
    expect(screen.getByText('₹700.00')).toBeInTheDocument()
  })
  it('shows a server error and keeps the typed input', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(new Response(JSON.stringify({ detail: 'Bill number already exists' }), { status: 409 }))))
    render(<MemoryRouter><AddBill /></MemoryRouter>)
    fireEvent.change(screen.getByLabelText(/Bill number/), { target: { value: 'B-77' } })
    fireEvent.click(screen.getByText('Save udhari bill'))
    expect(await screen.findByText(/Select or create the customer first/)).toBeInTheDocument()
    expect(screen.getByLabelText(/Bill number/)).toHaveValue('B-77')
  })
})

describe('POS Keyboard enhancements', () => {
  it('renders ShortcutsModal with hotkeys cheat sheet', async () => {
    const { ShortcutsModal } = await import('./ShortcutsModal')
    render(<ShortcutsModal onClose={() => {}} />)
    expect(screen.getByText(/POS Keyboard Shortcuts Cheat-Sheet/)).toBeInTheDocument()
    expect(screen.getByText(/Add Udhari \(Credit\) Bill/)).toBeInTheDocument()
    expect(screen.getByText(/Quick Save \/ Submit active bill or form/i)).toBeInTheDocument()
  })

  it('renders CommandPalette and searches commands', async () => {
    const { CommandPalette } = await import('./CommandPalette')
    render(
      <MemoryRouter>
        <CommandPalette isOpen={true} onClose={() => {}} onToggleTheme={() => {}} onOpenHelp={() => {}} />
      </MemoryRouter>
    )
    expect(screen.getByLabelText('Search')).toBeInTheDocument()
    expect(screen.getByText('New udhari bill')).toBeInTheDocument()
    expect(screen.getByText('Receive payment')).toBeInTheDocument()
  })

  it('shows server search results grouped by type', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(new Response(JSON.stringify({ results: [
      { type: 'bill', id: 4, title: 'Bill GX-77', subtitle: 'Ganesh · ₹500', url: '/udhari/2' },
      { type: 'customer', id: 2, title: 'Ganesh Traders', subtitle: '98765', url: '/udhari/2' },
    ] }), { status: 200 }))))
    const { CommandPalette } = await import('./CommandPalette')
    render(<MemoryRouter><CommandPalette isOpen={true} onClose={() => {}} onToggleTheme={() => {}} onOpenHelp={() => {}} /></MemoryRouter>)
    fireEvent.change(screen.getByLabelText('Search'), { target: { value: 'GX' } })
    expect(await screen.findByText('Bill GX-77')).toBeInTheDocument()
    expect(screen.getByText('Bills')).toBeInTheDocument()
    expect(screen.getByText('Ganesh Traders')).toBeInTheDocument()
  })
})

describe('Dashboard', () => {
  it('renders KPIs, alerts and top debtors from the API', async () => {
    const dash = { total_outstanding: '1200.00', collected_today: '0', overdue_customers: 1, overdue_amount: '1200.00', overdue_days_setting: 30,
      unpaid_expenses_count: 0, unpaid_expenses_amount: '0', owner_due: '0', expenses_today_by_source: {}, expected_closing_cash: '500.00',
      day_status: 'open', latest_item_sales: null, low_stock_items: [], unresolved_import_rows: 0, duplicate_warnings: 0, draft_imports: 0,
      pending_catalogue_items: 0, accounts: [{ name: 'Cash Drawer', balance: '500.00', physical_cash: true }], today: '2026-10-26' }
    const ins = { aging: [{ bucket: '0-30', amount: '0' }, { bucket: '31-60', amount: '0' }, { bucket: '61-90', amount: '0' }, { bucket: '90+', amount: '1200.00' }],
      top_debtors: [{ customer_id: 7, name: 'Ramesh', phone: '', outstanding: '1200.00', oldest_days: 120 }],
      trend: [{ date: '2026-10-26', collections: '0', expenses: '0', credit_given: '0', item_sales: '0' }],
      recent_activity: [], unclosed_days: ['2026-10-20'], last_closed_day: null, payables_due_soon: [] }
    vi.stubGlobal('fetch', vi.fn((url: string) => Promise.resolve(new Response(JSON.stringify(url.includes('insights') ? ins : dash), { status: 200 }))))
    const { default: Dashboard } = await import('./pages/Dashboard')
    render(<MemoryRouter><Dashboard /></MemoryRouter>)
    expect(await screen.findByText('Udhari outstanding')).toBeInTheDocument()
    expect(await screen.findByText('Ramesh')).toBeInTheDocument()
    expect(screen.getByText(/never finalized/)).toBeInTheDocument()
    expect(screen.getAllByText('₹1,200.00').length).toBeGreaterThan(0)
  })
})

