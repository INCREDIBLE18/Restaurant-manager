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
    expect(screen.getByPlaceholderText(/Search customer, jump to page/)).toBeInTheDocument()
    expect(screen.getByText('+ Add Udhari (Credit) Bill')).toBeInTheDocument()
    expect(screen.getByText('Receive Payment')).toBeInTheDocument()
  })
})

