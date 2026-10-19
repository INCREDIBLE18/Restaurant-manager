# Restaurant Operations Manager — Claude Code Build Specification

**Purpose:** Build a simple, reliable internal web application for a restaurant to track customer *udhari* (credit), collections, expenses, payment sources, daily cash reconciliation, purchases, and item sales/inventory movements.

**Primary outcome:** The owner should be able to answer these questions without checking piles of paper:
1. Who owes us money, how much do they owe, and which bill(s) make up the balance?
2. When a customer pays later, which outstanding bill(s) did that payment settle, how was it received, and who received it?
3. How much cash should be in the drawer at closing, how much was physically counted, and why is there a difference?
4. Which expenses are unpaid or partially paid? Who paid each one and from which source/account?
5. What items were purchased, what items sold according to the daily Item Sales report, and what stock movement can be calculated reliably?
6. Can we import the restaurant software's scanned PDF reports without trusting its negative Stock Position figures?

> **Important input-report rule:** The reference PDFs are scanned images, not reliably machine-readable text. Use them to build and test a human-reviewed import process. In `Stock Position.PDF.pdf`, use the item names and displayed unit labels only as a starting catalogue. Ignore all quantities and values in that report, including Open, Purchase, Issued/Sale, Damage, Wastage, Variance, Return, Closing, and Closing Stock Value. Those figures are not a trustworthy stock balance for this application. In `Item Sales.PDF.pdf`, extract sellable item rows, Qty Sold, and Total Amount; do not create products from Department/Category headings, subtotal rows, grand total rows, or ditto marks (`"`). The Item Sales report does not establish how much was collected in cash/UPI/card or which sales were on credit.

---

## 1. Instructions to Claude Code

You are the lead product engineer. Build the application in the current project directory. Treat this specification as the product source of truth.

### Before coding
- Inspect the current working directory, existing code, installed tools, and runtime. Do not overwrite or modify an unrelated project.
- If the repository is empty, scaffold the project using the stack in Section 13. If a sensible stack already exists in this new project, document it and adapt without unnecessary rewrites.
- Look for the reference files `Stock Position.PDF.pdf` and `Item Sales.PDF.pdf` in `./reference_pdfs/`, `./docs/reference_pdfs/`, and the project root. If they are not present, keep the PDF import feature configurable and document that the owner must place the reference files in `reference_pdfs/`. Do not halt the whole application because the sample PDFs are absent.
- The sample report header appears to identify the outlet as **AARAVALI, TITWALA**. Use that only as an editable initial setting, not as a hard-coded brand name.
- Create a short `IMPLEMENTATION_PLAN.md`, then start implementing. Do not stop after writing a plan or producing mock-ups. Work in small, testable steps and run tests after each major module.
- Record material assumptions in `docs/ASSUMPTIONS.md`. Do not silently invent financial or inventory values.

### Required engineering behavior
- Deliver a working application, not just wireframes. Every visible button, form, filter, upload, export, and action must work or clearly state that it is not yet implemented.
- Validate business rules in the backend as well as in the UI. Frontend-only validation is insufficient.
- Use database migrations; never rely on manually editing production tables.
- Use decimal-safe monetary values (database decimal/numeric and Python `Decimal`), not binary floating-point arithmetic for money.
- Store timestamps consistently and display local dates/times in `Asia/Kolkata`. Store money in INR (₹), use Indian number formatting where practical, and make the restaurant name, contact details, and receipt format editable settings.
- Never permanently delete posted financial transactions. Use void/reversal/adjustment flows with a reason and audit trail.
- No test/demo data should silently appear in the live database. Provide a clearly marked demo seed command only.
- Do not hard-code API keys, passwords, or database credentials. Provide `.env.example`; keep `.env` ignored by Git.
- The app must remain usable if Gemini is not configured or unavailable. AI must be optional, and no transaction may be committed from an AI result without explicit user review and confirmation.
- Do not ask the owner to decide routine implementation details. Choose reasonable defaults, record them, and continue. Ask only if an unresolved choice would cause data loss, security risk, or a major change in scope.

---

## 2. Product scope and priorities

### MVP — must work end to end
1. Customer directory with name, phone, optional address/notes, and a complete ledger.
2. Manual credit/udhari bill entry with bill number, date, amount, customer, and optional line items/photo of paper bill.
3. Receive full or partial customer payments later; allocate each receipt to one or more bills; show remaining balance immediately.
4. Expense register with paid/unpaid/partially paid state, category, vendor/person paid, payment date, payment method, and payment source/account.
5. Cashbook/account ledger and daily cash closing reconciliation.
6. Daily Item Sales PDF upload with preview, correction/mapping, duplicate detection, and confirmation before any data is saved.
7. Purchases/stock-in entry and item movement ledger. Stock tracking must clearly state when a starting count is unknown.
8. Basic reports and CSV exports.
9. Backups, audit trail, login, and a responsive interface that works on a desktop and mobile browser.

### Later enhancements (do not block the MVP)
- WhatsApp reminder text/copy link for overdue customers; do not send messages automatically without a future explicit feature and consent.
- Supplier payment reminders, recurring expenses, recipe/BOM ingredients, staff attendance/payroll, GST invoicing, POS integration, multi-branch support, and online/cloud hosting.
- Optional Gemini-assisted PDF parsing if local text extraction/OCR is not sufficient.

Do not expand this into a full restaurant POS/order-taking system for the first release. The restaurant's existing billing software remains the sales/POS system. This app is the operational ledger and reconciliation tool beside it.

---

## 3. Core concepts and terminology

- **Credit/Udhari bill:** A sale that has already been made but whose amount is not fully collected. It creates a receivable from a named customer.
- **Receipt/collection:** Money actually received from a customer later or at the time of a bill. A receipt is not a new sale.
- **Outstanding balance:** Total posted credit bills minus amounts allocated from receipts minus approved credit notes/write-offs. Derive it from the ledger; do not let users manually edit the balance.
- **Expense:** A business cost/obligation. An expense can exist before it is paid.
- **Expense payment:** A payment against an expense, with the payee, date, method, payer, and account/source.
- **Account/source:** Where money moved: restaurant cash drawer, bank account, UPI settlement/account, card settlement, owner's personal funds, staff advance, or another configurable account. Payment method (cash/UPI/card/bank transfer) and money source/account are separate fields.
- **Daily POS sales report:** Aggregated item sales from the existing billing software. It is used for sales-item analysis and approved stock-out movements only. It is not a cash receipt report.
- **Stock movement:** A quantity change caused by a confirmed purchase, confirmed sale report, wastage, return, or explicit adjustment. Do not confuse a legacy POS stock-position figure with a verified count.

### Avoid double counting
This rule is critical:
- Importing `Item Sales.PDF.pdf` produces a dated aggregate of sold items/revenue and, for mapped stock-tracked products, the approved sales-side stock movements.
- Entering an existing POS udhari bill creates the customer receivable and its bill detail. By default it is marked **Already included in the POS daily report**. It must not add that bill's revenue or stock consumption a second time.
- An app-created sale that is not included in the external POS report may be treated as a new sale only through an explicit option, and that option must be off by default.
- The same PDF/import batch must never be posted twice without an explicit administrator override and a warning.

---

## 4. Main user journeys

### Journey A — record a new udhari bill
1. Open **Udhari → Add Bill**.
2. Search for an existing customer by name or phone. If new, create a customer. For a credit bill, customer name is required; phone is strongly recommended and should be configurable as mandatory.
3. Enter the POS/paper bill number, bill date/time, amount, optional item lines, note, and attach a photo/PDF if useful.
4. Enter the total bill amount and any amount already received now. Select payment method and account for the amount received now.
5. Set the unpaid balance as credit/udhari. The system calculates it; never type a separate conflicting value.
6. Confirm the bill. Show a printable/shareable ledger entry with bill ID, total, paid now, and outstanding.
7. Show this bill in the customer's history and in the outstanding/aging report.

**Formula:** `new_outstanding = bill_total - payment_received_at_bill_time - other_allocated_receipts - approved_credit_notes_or_writeoffs`.

Validation: bill total must be greater than zero; paid-now amount cannot be negative or greater than bill total; a credit bill cannot be saved without a customer; bill number duplication should warn and require confirmation/unique internal ID.

### Journey B — receive old udhari later
1. Open **Udhari → Receive Payment** or open the customer's ledger and click **Collect Payment**.
2. Search/select the customer and show all open bills, bill dates, original totals, collected-to-date, outstanding amounts, and age.
3. Enter amount actually received, date/time, method (cash/UPI/bank/card/other), account receiving the money, receipt/reference number, and the person who received it.
4. Allocate payment to selected bills. Provide **oldest bill first** as a convenient suggested allocation, but allow the user to edit it.
5. If the customer pays less than total due, leave the remaining balances open. If they overpay, retain the extra amount as an unallocated customer advance/credit; do not silently discard or apply it to a different customer.
6. Save one receipt plus one or more receipt-allocation records in a single database transaction.
7. Print/share a receipt if needed. Update the customer's balance, collection report, and relevant cash/bank account movement immediately.

Examples of required behavior:
- Bill ₹1,200; customer pays ₹500: bill still shows ₹700 due.
- Customer has bills ₹600 and ₹900; pays ₹1,000: allocate ₹600 to the first and ₹400 to the second by default; ₹500 remains due on the second.
- A customer gives ₹1,500 when only ₹1,200 is due: ₹1,200 is allocated and ₹300 remains as a customer advance/unallocated credit.
- A UPI receipt increases the appropriate UPI/bank account ledger but must not increase physical cash in the drawer.
- A cash receipt against old udhari increases today's physical cash even though it is not today's sales revenue.

### Journey C — add an expense
1. Open **Expenses → Add Expense**.
2. Enter date, category, description, amount, vendor/payee, optional vendor bill number/due date, and attach a bill/photo/PDF.
3. Set status based on actual payments: Unpaid, Partially Paid, or Paid. The status should be derived from payments made versus amount due, not chosen arbitrarily.
4. If unpaid, save the obligation with no cash movement.
5. If paid now or partly paid, add a payment record with amount, date/time, payment method, account/source, paid-by person, and reference/note.
6. Permit multiple payment records from different sources. Example: a ₹2,000 expense can be paid ₹1,000 from the drawer and ₹1,000 personally by the owner.
7. Display the expense under the relevant category and in the appropriate account cashbook.

**Expense source/payee distinction:** Record both (a) *who/what received the money* (vendor/payee) and (b) *where the money came from / who funded it* (cash drawer, restaurant bank, UPI account, owner personally, staff advance). These are not the same field.

**Owner-paid expense rule:** If the owner pays a business expense from personal money, record the expense once and record the payment source as the owner's personal funds. By default create an **amount owed to owner/reimbursement due** balance. This payment must not reduce the restaurant's physical cash. If the restaurant later reimburses the owner, reduce the owner-reimbursement balance and the restaurant's cash/bank account; do not record the reimbursement as a second expense. Allow an admin to mark the owner-funded amount as a non-reimbursable contribution if that is the actual arrangement.

### Journey D — close the day and tally cash
1. Open **Daily Closing** for the business date.
2. Enter/count opening cash float (normally carry forward the prior day's verified closing cash, with any adjustment explained).
3. Enter the totals from the POS/tender/closing report separately where available: POS sales total, cash sales collected, UPI, card, other modes, and udhari/credit sales. The Item Sales PDF alone does not provide these tender totals, so do not infer them from it.
4. Pull cash receipts, including collections against previous udhari, from the app's receipt ledger. Pull cash-paid expenses and other cash-in/out transactions from the cashbook. Permit correction only through a logged adjustment, not by silently changing an existing receipt/expense.
5. Calculate expected closing cash:

   `expected_closing_cash = opening_cash + cash_sales_collected + cash_udhari_collections + other_cash_in - cash_paid_expenses - cash_refunds - cash_withdrawals - other_cash_out`

6. Enter the physical cash counted by the user. Calculate `difference = physical_cash_counted - expected_closing_cash`.
7. If the difference is not zero, show a prominent but neutral variance with an optional reason and a required note above a configurable threshold. Do not auto-create an expense to force the numbers to match.
8. Finalize the day. The closing is locked against casual editing; corrections use an admin reopen/reversal flow with reason and audit log.

Do not subtract old-credit collections from current sales, and do not classify a credit collection as a new sale. The cashbook uses actual movement, so the user doesn't have to manually subtract udhari twice.

### Journey E — upload the daily Item Sales PDF
1. Open **Inventory & Imports → Import Item Sales PDF**.
2. Choose the business/report date. If a date can be read from the report, prefill it and ask the user to confirm. Prefer the report's business date over the print timestamp.
3. Parse the scanned document using the order: native PDF text extraction → local OCR → optional Gemini-assisted structuring as a fallback.
4. Display a review table before writing anything: source item text, normalized item, Qty Sold, Total Amount, any cancel/no-charge/free indicators available, mapping status, extraction confidence, and notes.
5. Treat department/category headings and `Sub Total`, `Grand Total`, `Summary`, `End Of Report`, and ditto (`"`) rows as structural rows, not new products. A ditto-marked product row may inherit the previous product name only when the table structure makes that interpretation clear; flag uncertain rows for review.
6. Do not blindly add quantities across product-detail rows, subtotals, department totals, and grand totals. Only import individual product rows. Use subtotals/grand total for reconciliation checks, not as sale lines.
7. Preserve separate concepts for `Qty Sold`, `Total Amount`, cancellation count, free/no-charge items, void bills, complimentary bills, guest bills, staff bills, and any stock quantity column. Never use a blank or untrusted Stock Qty field as stock-on-hand.
8. Match source names against the item catalogue using normalized exact matching and saved aliases first. Fuzzy/AI matches are suggestions only. The user must confirm unknown or ambiguous mappings.
9. Show a duplicate warning if the file hash was already imported, or a report of the same type/date exists. Make the admin choose whether to cancel or perform a deliberate replacement/reversal.
10. Show summary checks: row count, sum of accepted Qty Sold, sum of accepted Total Amount, count of unresolved lines, rows excluded as headings/subtotals, and variance against the report's printed totals if detected.
11. Only after the user clicks **Confirm Import** save the batch and inventory movements. Save source filename/hash, report date, imported by, timestamp, mapping decisions, exclusions, and review notes.
12. Keep the original file attached to the import batch so the user can audit a number later.

### Journey F — record a supplier purchase/bill and stock-in
1. Open **Purchases → Add Purchase** or upload a supplier bill PDF/photo.
2. Enter supplier, supplier invoice number/date, line items, purchase units, quantities, unit price, discount/tax if used, total bill amount, due date, payment status, and optional attachment.
3. For each line, map to an existing item or create a draft new item. Show pack size/unit conversion explicitly (e.g. a case may contain several bottles). Do not assume a conversion from the text in the product name without confirmation.
4. Confirming the purchase posts its quantity as an inbound stock movement only for items marked **Track stock**. Record the supplier liability/payment separately.
5. Purchase payment may be unpaid, partial, or paid from one or more accounts; payment must not create a second purchase/expense for the same cost.
6. If a vendor invoice is paid directly by the owner, use the owner-paid rule described under expenses/payables.

---

## 5. PDF-specific rules for the current sample reports

### `Item Sales.PDF.pdf`
The sample is a scanned, 2-page report. Its visible columns include:
- Item Name
- Qty Sold
- Total Amount
- Cancel Orders
- No Charge
- Free Items
- Void Bills
- Compl Bills
- Guest Bills
- Staff Bills
- Stock Qty

It also contains Department and Category headings, subtotals, and a grand total. Example visible item rows include food/menu items such as `Manchow Soup`, `Chana Koliwada With Garlic Fry`, and `Chicken Lollipop`, as well as packaged beverage/liquor items such as `DSP Black 180ml` and `Imperial Blue 180ml`. Use the actual source spelling as an alias, but let the owner correct names. The visible sample's date is **30-Sep-2026**; the print time is separate. Do not hard-code this date into logic or demo data.

### `Stock Position.PDF.pdf`
The sample is a scanned, 4-page report. It contains an Item Name and UOM column, plus Open, Purchase, Issued/Sale, Damage, Wastage, Variance, Return, Closing, and closing-stock-value-style columns. Some displayed balances are negative or mix number/volume representations. This is expected for the way the existing restaurant software is used and is **not usable inventory truth** for this application.

Allowed from this report:
- Propose item names for the catalogue.
- Propose a displayed UOM label as an editable hint.

Not allowed from this report:
- Opening-stock import.
- Purchase quantity import.
- Sales quantity import.
- Closing-stock import.
- Cost/value import.
- Any auto-adjustment intended to fix a negative value.

### Catalogue reconciliation
- Merge candidate names from the Stock Position and Item Sales reports into a **pending item catalogue**.
- Preserve `source_name` and `source_report` for traceability.
- Do not merge similarly named items solely because a fuzzy match is high. For example, different bottle sizes, brands, or prefix forms (such as `P ... 90ml`) may represent different sellable items. Ask for confirmation on the mapping screen.
- An item must be explicitly marked `Track stock = yes` before purchases/sales can affect the quantity-on-hand view.
- Sale item quantities can directly reduce stock only when the sold item corresponds to the tracked stock item or the user has configured a consumption mapping. A prepared dish such as a chicken starter is not automatically a measured quantity of chicken, oil, spices, etc.
- If ingredient-level stock deduction is desired later, add a recipe/BOM feature in a future phase. Do not invent recipes in the MVP.

---

## 6. Inventory rules and limitations

Maintain a stock-movement ledger rather than allowing users to type the current balance directly.

For each stock-tracked item:

`estimated_stock = manually_confirmed_opening_stock + confirmed_purchase_in - confirmed_sale_out + sale_returns - supplier_returns - wastage - other_out + other_in`

- A starting count must be entered by a user with permission. Never populate it from Stock Position figures.
- If no starting stock count was entered, show **Opening baseline unknown** and do not present a misleading absolute stock-on-hand. The user can start tracking from a chosen date; show the quantity of movements since that date.
- Quantity conversions must be explicit and editable per item: purchase unit, base unit, and conversion factor. Examples: case → bottles; bottle → ml; packet → pieces. Never apply a name-based conversion silently.
- Use an item movement history for every stock quantity: timestamp, business date, item, movement type, quantity in base unit, source record/import batch, user, and reason.
- Corrections must be inventory adjustments with reason and audit trail, not edits to an old movement.
- The stock view can show estimated quantity, last movement, low-stock threshold, and baseline status. Low-stock alerts should be disabled for items with an unknown baseline unless the item is being tracked in movement-only mode with a clearly defined warning.
- A purchase may include food materials while the Item Sales report lists prepared dishes. Do not automatically subtract dish quantities from ingredient stock. Support explicit item mappings now and recipe/BOM later.

---

## 7. Screens and navigation

Build a clean, fast, mobile-responsive web UI optimized for use during a busy service. Use readable labels, touch-friendly controls, clear dates, and minimal typing. Prefer quick-add actions, searchable tables, keyboard-friendly forms, and confirmation dialogs for destructive/reversal actions.

### Main navigation
1. **Dashboard**
2. **Udhari / Customers**
3. **Receive Payment**
4. **Expenses & Payables**
5. **Purchases**
6. **Inventory & PDF Imports**
7. **Daily Closing / Cashbook**
8. **Reports**
9. **Settings / Users / Backup** (admin only)

### Dashboard cards
- Total outstanding customer udhari.
- Amount collected today against old udhari.
- Number/value of overdue customer balances.
- Unpaid and partially paid expenses/vendor bills.
- Owner reimbursement due.
- Expenses paid today, grouped by source/account.
- Expected closing cash (if opening balance/day close is entered).
- Latest Item Sales report date and import status.
- Imported item sales total/quantity (clearly labelled as report data, not cash collected).
- Inventory items whose baseline is set and are below their threshold.
- Unresolved import rows/duplicate warnings.

### Customer directory and ledger
- Search by name/phone; filter by balance, overdue state, and recent activity.
- Details: name, phone, optional address/notes, active/inactive state, created date.
- Ledger rows: date, bill/receipt/reference, debit (credit bill), credit (receipt or credit note), allocated-to bill(s), and running balance.
- Customer statement with opening balance, dated bills, receipts, outstanding per bill, and closing balance. CSV export and print-friendly view.
- Phone number is not a unique customer ID; detect likely duplicate phone/name and ask before merging. Never silently merge customers.

### Expenses page
- Filters: date range, category, paid/unpaid/partial, vendor/person, paid-from source/account, paid-by, and due/overdue.
- Show expense amount, payments made, remaining payable, payee, source, last payment date, and attachment.
- A detailed view with all payment splits. Separate **Reimburse owner** from **Add new expense**.

### Daily closing page
- Date selector and closing status (Open / Finalized / Reopened with reason).
- Opening float and POS tender inputs.
- Ledger-derived receipts by collection method/account; cash sales totals entered from POS tender report; other cash in/out; cash expenses and cash refunds.
- Expected cash, physical cash counted, variance, reason, closed by/time.
- Warn if imported item sales report is missing or if POS tender numbers do not reconcile. Do not block cash closing only because the item sales PDF is missing; make the missing-report warning clear.

### Import review page
- Upload/drop area for scanned PDF, image, CSV, or Excel where supported.
- Report type: Item Sales, Stock Position (catalogue names only), or Supplier Purchase (separate workflow).
- Rendered original preview or accessible file link; detected report date; table of parsed rows; source image/row/page metadata where available.
- Editable mapping for item/customer/vendor names.
- Exclusion reason for headings/subtotals and row-level validation errors.
- Duplicate batch warning and confirm/reject buttons.
- Never make **Import** the default action; require the explicit final confirmation.

---

## 8. Data model requirements

Use normalized relational tables. Exact table names can vary if documented, but the relationships and invariants below must be implemented.

### Core entities
- `User`: username/email, password hash, role, active state, created/last-login times.
- `Customer`: name, phone, address, notes, active state, timestamps.
- `Vendor`: name, phone/contact, address, notes, active state.
- `Item`: canonical name, category/department, source name(s), base unit, default selling unit, default purchase unit, purchase-to-base conversion, selling-to-base conversion, stock tracking flag, low-stock threshold, active state.
- `ItemAlias`: alias text, item ID, source report, confirmed by, timestamps; uniqueness rules that prevent an alias pointing to two conflicting items.
- `Account`: display name, type (cash/bank/UPI/card settlement/owner-personal/staff-advance/other), active state, whether it is physical cash, and optional opening balance/effective date.
- `SaleBill`: internal unique ID, bill number, optional POS bill number, business date/time, customer ID where relevant, total, amount collected at bill time, source, credit status, POS inclusion flag, notes, attachment, status (posted/voided/reversed), created by.
- `SaleBillLine` (optional in simple credit ledger entry): item ID or free-text item name, quantity, unit, unit price, discount, line total.
- `Receipt`: unique receipt number, customer ID, receipt date/time, amount, payment method, receiving account, reference/transaction ID, received by, notes, status, created by.
- `ReceiptAllocation`: receipt ID, sale bill ID, allocated amount. Enforce that active allocations do not exceed the receipt amount or a bill's outstanding amount, except explicitly modelled customer advance/unallocated money.
- `Expense`: date, category, description, vendor/payee, bill/reference number, total amount, due date, attachment, notes, status derived from payments, created by.
- `ExpensePayment`: expense ID, amount, paid date/time, method, source account, paid-by person, payee, reference, notes, status. Owner-personal payments must link to owner reimbursement/contribution accounting as appropriate.
- `PurchaseBill` and `PurchaseBillLine`: supplier/invoice details, item IDs/free-text items, quantities/units/conversions, price, taxes/discounts, total and payment state. Link purchase payments to the supplier bill without creating duplicate expenses.
- `CashMovement` or a unified account-ledger table: account, date/time, business date, signed amount, movement type, source entity/reference, note, user, reversal reference. All actual money inflows/outflows must be posted exactly once.
- `InventoryMovement`: item, date/time/business date, movement type, positive quantity plus direction or signed base-unit quantity, source record, import batch, user, reason. The stored balance is derived from opening movement plus ledger movements.
- `ImportBatch`: report type, filename, hash, report date, print date/time if found, extraction method, status (draft/reviewed/confirmed/rejected/reversed), totals, warnings, uploaded by/time, confirmed by/time, file attachment/storage reference.
- `ImportRow`: raw row data, page/row locator, raw item name, parsed quantity/amount, match suggestion, confidence, accepted/rejected state, review notes, final item mapping.
- `DayClose`: business date, opening cash, POS totals/tender amounts, ledger-derived cash movements, expected closing cash, actual cash counted, variance/reason, finalized by/time, reopen information.
- `OwnerBalance` or explicit owner ledger entries: reimbursements owed/paid and non-reimbursable capital/contribution entries. Do not store a manually editable balance without ledger entries.
- `AuditLog`: user, action, entity type/ID, timestamp, before/after summary, reason, request/correlation ID where useful.
- `AppSetting`: restaurant/outlet name, currency, timezone, invoice/receipt prefixes, phone rules, variance thresholds, AI enabled/disabled, and other safe configuration.

### Ledger principles
- Calculate customer balances and expense payment status from posted transaction rows.
- A receipt can be allocated to multiple bills; a bill can be paid through multiple receipts.
- A transaction cannot have two cash movements for the same amount. Creating the receipt/expense payment and posting the linked account movement must be atomic.
- Voids/reversals must create reversal records and retain the original record. Reports should exclude the reversed economic effect while preserving history.
- Keep event/business date separate from database creation timestamp so a late-entered bill can be recorded with its true date and still show who entered it later.
- Apply database constraints and backend validation for positive values, references, unique IDs, and allowed transitions.

---

## 9. Accounting and reconciliation calculations

### Customer receivables
For each bill:

`bill_outstanding = posted_bill_total - sum(active_receipt_allocations) - approved_credit_notes - approved_writeoffs`

For a customer:

`customer_outstanding = sum(max(0, bill_outstanding)) - valid_unallocated_customer_credit`

The UI should still show unallocated credit explicitly instead of hiding it in a negative balance. Avoid negative per-bill due unless the system explicitly records a credit note/refund.

### Expense payable
`expense_due = expense_total - sum(active_expense_payments) - approved_expense_adjustments`

Status is derived:
- Unpaid: paid amount = 0
- Partially paid: paid amount > 0 and due > 0
- Paid: due = 0 (within the currency's defined precision)
- Reversed/voided: no active payable impact but visible in audit history

### Accounts and cash
For each account, derive balance from opening balance plus its posted movements. Distinguish account transfer from income/expense: a transfer from cash to bank reduces cash and increases bank, without recording revenue or expense.

`expected_closing_cash = opening_physical_cash + cash_sales_collected + cash_customer_collections + other_cash_in - cash_expense_payments - cash_refunds - cash_withdrawals - other_cash_out`

Only movements in accounts marked `physical cash` affect the physical drawer closing formula. UPI or bank receipts never count as physical cash. Owner-paid expenses never reduce the drawer unless a later reimbursement is actually paid from it.

### POS total vs tender totals
- Allow the operator to enter the POS close report's total sales and payment-mode/tender totals.
- If `Item Sales.PDF.pdf` is used, its grand total is an item report cross-check only. Do not pretend it is a cash collection total.
- Show a variance such as `POS sales total - (cash sales + UPI + card + other tender + credit sales - properly represented refunds/adjustments)` only when the components use comparable definitions; label assumptions and do not silently reconcile away differences.
- Customer credit bills recorded from existing POS bills may be part of the POS reported total. Use the `Already included in POS report` flag to prevent revenue double counting.
- Collections against prior-day udhari are receipts/cash movements on the collection date; do not add them to POS sales for that date.

---

## 10. Reporting and exports

Build at least these reports with date filters, search, totals, and CSV export:
1. **Customer Outstanding:** customer, phone, total due, oldest open bill date, days overdue, last collection.
2. **Customer Statement:** chronological bills, payments, allocations, adjustments, and running balance.
3. **Udhari Collections:** receipt date, customer, amount, method, account received into, received by, bill allocations, reference.
4. **Bill Outstanding Detail:** original bill total, allocated payments, remaining due, age, POS bill number.
5. **Expense Summary:** expense category, total incurred, total paid, unpaid, and period.
6. **Unpaid/Part-paid Expenses:** vendor/payee, due date, amount due, last payment, source/payment split.
7. **Paid By / Source Report:** group expenses by who funded them and source account, including owner-funded amounts.
8. **Owner Reimbursement Ledger:** owner-paid expenses due to owner, reimbursements paid, contributions/non-reimbursable items, balance.
9. **Cashbook:** opening balance, all in/out movements, reference, account, and running balance.
10. **Daily Closing:** POS totals/tenders, cash inflows/outflows, expected vs actual drawer cash, variance/reason, finalized by.
11. **Item Sales Summary:** product-level quantities/amounts from confirmed Item Sales imports, filters by day/range and category.
12. **Purchase Summary:** supplier bills, items/quantities, amount, payment state.
13. **Stock Movement Ledger:** item, movement source, in/out quantity, running estimated quantity, baseline status, reason.
14. **Import History:** report date, import date, filename, user, row count, warnings, confirmed/reversed state.

Exports should use UTF-8, stable column headers, and human-readable date/time and currency. Provide print CSS for customer statements, payment receipts, and day-close summaries. Do not silently include reversed transactions as current balances.

---

## 11. Optional AI/Gemini and PDF processing

The first preference should be deterministic local parsing and review. The current samples appear to be image-scanned reports, so design a fallback chain:
1. Try PDF text/table extraction.
2. If usable text is absent, render pages and run local OCR (such as Tesseract) when installed.
3. Normalize extracted rows with deterministic parsing rules for the known report layout.
4. If enabled and configured, use Gemini as a fallback to turn selected page images/OCR text into structured JSON with item name, quantity, amount, report date, category, and page/row references.
5. Validate the output against a strict schema and display it to the user for review. The model must not decide that negative Stock Position balances are inventory truth.

### AI safety and cost controls
- Make the model provider optional behind a service interface; support Gemini only after checking its currently available API limits/pricing and document any limitations. Never promise the API will remain free.
- Read `GEMINI_API_KEY` from environment configuration; never hard-code it or expose it to frontend code.
- Do not send customer phone numbers, names, credit ledgers, or financial account details to a model for PDF import. PDF parsing usually only needs the scanned report page and extracted table text.
- Provide timeout, bounded retries, error messages, and a way to complete import manually without AI.
- Model outputs are untrusted suggestions. Require a human review screen before import confirmation.
- Log which extraction mode was used and the schema-validation/import warnings, but avoid logging secret keys or unnecessary sensitive values.
- Do not call Gemini for routine ledger calculations. All balances, allocations, expected cash, and stock calculations must be deterministic backend code.

Suggested JSON schema for item sales import:

```json
{
  "report_type": "item_sales",
  "business_date": "YYYY-MM-DD",
  "outlet_name": "string or null",
  "rows": [
    {
      "raw_item_name": "string",
      "category": "string or null",
      "department": "string or null",
      "qty_sold": "decimal string or null",
      "total_amount_inr": "decimal string or null",
      "cancel_orders": "integer or null",
      "no_charge": "decimal string or null",
      "free_items": "decimal string or null",
      "void_bills": "integer or null",
      "complimentary_bills": "integer or null",
      "guest_bills": "integer or null",
      "staff_bills": "integer or null",
      "page_number": "integer",
      "confidence": "0..1",
      "row_type": "item|heading|subtotal|grand_total|unknown"
    }
  ],
  "printed_grand_total_inr": "decimal string or null",
  "warnings": ["string"]
}
```

Use strings/decimal-safe parsing for amounts and quantities. The backend must validate numeric strings and reject invalid or absurd values rather than trusting model-generated JSON.

---

## 12. Authentication, audit, privacy, backups

- Require login for the owner-facing application. At minimum support `Admin/Owner` and `Staff/Cashier` roles. Admin manages users/settings, confirms/reverses imports, reopens a finalized day, and performs high-risk adjustments. Staff can enter permitted bills, receipts, expenses, and import drafts according to configured permissions.
- Hash passwords using a recognised password-hashing scheme. Do not store plaintext credentials. Add session/token expiry and safe CORS settings.
- Do not expose database admin endpoints or Gemini keys through the frontend.
- Log who created, changed, voided, reversed, imported, confirmed, reopened, and exported material financial data. Include an explanation field for material corrections.
- Backup: provide a documented one-click/command backup that includes the database and uploaded bill/report attachments. Provide restore instructions and verify that backup files are created successfully. Do not claim a backup succeeded until the file was written and checked.
- Store attachments with safe filenames; prevent path traversal; limit file size/type; keep references in the database. Use local filesystem storage for a local deployment unless another storage choice is documented.
- Use environment variables for secrets and provide example values only. Add sensible upload limits and backend validation.
- For optional LAN access from a phone, bind only as intended, document the local URL, and explain that the PC/server must remain running. Do not expose the app to the public internet by default.

---

## 13. Recommended technical architecture

Use this stack unless the repository already provides an equally suitable, working alternative:

- **Frontend:** React + TypeScript + Vite; a consistent responsive component library or Tailwind-based design system; forms with proper validation and accessible labels.
- **Backend:** Python FastAPI, Pydantic schemas, SQLAlchemy 2.x, Alembic migrations.
- **Database:** PostgreSQL for a multi-user/LAN-capable setup. Use Docker Compose for local development where practical. If the chosen environment cannot run Docker and a single-device-only first version is explicitly documented, SQLite may be used behind the same data-access patterns; do not promise safe concurrent multi-user operation on SQLite.
- **PDF/import:** a reliable PDF text extractor, local OCR fallback when available, file/page preview, strict parsing/validation, and optional Gemini provider.
- **Tests:** pytest for backend, frontend unit/component tests for important forms, and API integration tests using an isolated test database.
- **Docs/scripts:** `README.md`, `.env.example`, `IMPLEMENTATION_PLAN.md`, `docs/ASSUMPTIONS.md`, database migration instructions, Windows-friendly PowerShell setup/start/backup scripts, and `docker-compose.yml` if PostgreSQL is used.
- **API:** version the API under `/api/v1/`. Keep the UI, business rules, and database concerns separated. Do not put ledger formulas only in React components.

Potential API resource groups (adapt as needed):
- `/api/v1/auth`, `/api/v1/users`, `/api/v1/settings`
- `/api/v1/customers`, `/api/v1/credit-bills`, `/api/v1/receipts`, `/api/v1/receipts/{id}/allocations`
- `/api/v1/expenses`, `/api/v1/expenses/{id}/payments`, `/api/v1/vendors`, `/api/v1/purchases`
- `/api/v1/items`, `/api/v1/item-aliases`, `/api/v1/inventory/movements`, `/api/v1/inventory/opening-counts`
- `/api/v1/imports/item-sales/preview`, `/api/v1/imports/stock-position/preview`, `/api/v1/imports/{id}/confirm`, `/api/v1/imports/{id}/reverse`
- `/api/v1/day-closes`, `/api/v1/accounts`, `/api/v1/cash-movements`
- `/api/v1/reports/...`, `/api/v1/backups`

---

## 14. Suggested build phases and completion gates

### Phase 0 — inspect, plan, and scaffold
- Inspect the repository and the two reference PDFs when available.
- Write the plan, architecture note, data model, and import assumptions.
- Scaffold application, configuration, migrations, test infrastructure, and health-check endpoint.
- **Gate:** app can start locally, database migration runs, health check returns success, and README explains setup.

### Phase 1 — udhari/customer ledger
- Login/roles, settings, customer search/add/edit, new credit bill, customer ledger, receipt entry, partial/multiple allocations, customer statement.
- **Gate:** the acceptance tests in Section 15 for customer balances pass; refreshing/restarting the app does not lose data.

### Phase 2 — expenses, accounts, cashbook, and day closing
- Expense register, expense payment splits, owner-paid expenses/reimbursement ledger, accounts, cash movements, daily close, variance and audit trail.
- **Gate:** cash expected/actual calculation and owner-payment examples in Section 15 pass, with no double-counted account movements.

### Phase 3 — item catalogue, purchases, and PDF imports
- Item catalogue/aliases, manual opening counts, purchase bills, scanned Item Sales PDF preview/import, Stock Position catalogue-name import, duplicate controls, stock movement ledger.
- **Gate:** the source PDFs' headings/subtotals are not created as products; Stock Position numbers never post inventory; duplicate imports do not duplicate stock movements; unknown stock baseline is labelled.

### Phase 4 — dashboard, reports, export, backups, and hardening
- Dashboard, reports, CSV/print outputs, backup/restore, role checks, usability and security review.
- **Gate:** all financial/inventory tests pass, critical workflows work on desktop and mobile layout, and setup/backup/restore are documented and exercised.

### Phase 5 — optional AI enhancement
- Add optional Gemini-assisted extraction behind an interface, after local extraction/review works.
- **Gate:** if AI is disabled, all core features work; if AI returns malformed or uncertain data, it is shown as an error/review item and never auto-posted.

Do not claim a phase is complete based only on generated code. Run the application and tests, inspect error logs, and fix failures before proceeding.

---

## 15. Required acceptance tests and example scenarios

Implement tests for at least the following scenarios. Use isolated test data and never depend on production records.

### Credit ledger
1. Add customer A and bill ₹1,200. Outstanding = ₹1,200.
2. Record a ₹500 receipt allocated to the bill. Outstanding = ₹700; cash/bank account increases by ₹500 in the selected receiving account.
3. Record another ₹700 receipt. Outstanding = ₹0; bill shows paid; receipts remain separately visible.
4. Customer has bill A ₹600 and bill B ₹900 and pays ₹1,000. Default oldest-first allocation is ₹600 to A and ₹400 to B; B outstanding = ₹500.
5. Customer owes ₹1,200 and pays ₹1,500. ₹1,200 is allocated and ₹300 remains explicitly unallocated/customer advance.
6. Reject allocation to another customer's bill.
7. Reject an allocation that exceeds a bill's open balance unless the extra amount is explicitly recorded as unallocated customer advance.
8. Voiding/reversing a receipt restores the bill balance through a reversal record and audit log, not silent deletion.
9. An existing POS udhari bill marked as already included in POS reports does not double count daily sales revenue or stock movement.

### Expenses and owner funding
10. Add unpaid expense ₹2,000. Payable = ₹2,000; physical cash/bank does not change.
11. Add ₹1,000 cash payment to the expense. Payable = ₹1,000; physical cash decreases by ₹1,000.
12. Pay remaining ₹1,000 personally by the owner. Payable = ₹0; restaurant cash does not decrease for the owner-funded payment; owner reimbursement due increases by ₹1,000 by default.
13. Reimburse owner ₹1,000 from restaurant cash later. Cash decreases by ₹1,000 and owner reimbursement due decreases by ₹1,000; no new expense is created.
14. Reject negative expense/payment amounts and invalid overpayments.
15. Expense paid by UPI/bank must not decrease physical drawer cash.

### Cash closing
16. Opening cash ₹2,000 + cash sales ₹5,000 + cash udhari collections ₹700 + other cash in ₹100 - cash expenses ₹1,200 - cash refund ₹100 = expected closing cash ₹6,500.
17. Enter physical count ₹6,400; variance = -₹100. Show variance and reason flow; do not auto-create a balancing expense.
18. UPI udhari collection increases the selected non-cash account but not the cash drawer expected closing cash.
19. Transfers between cash and bank must not become sales or expenses.
20. Finalized day cannot be casually overwritten; an admin reopen requires reason and audit record.

### Imports and inventory
21. Item Sales import extracts a known item row's name, sold quantity, and total amount into preview.
22. Department/category headings, subtotals, grand total, and `End Of Report` are not added as products or stock movements.
23. `"` ditto-marked rows are either confidently normalized to the intended item or flagged for review; never become a literal item named `"`.
24. Stock Position import may add candidate item names/UOM labels to a pending catalogue, but no stock quantities/values from that report affect inventory.
25. Importing the same PDF twice does not duplicate item sales or inventory movements.
26. Unmapped sale item rows appear in the review queue and do not silently affect a different product's stock.
27. Unknown opening baseline shows **Opening baseline unknown** rather than presenting an authoritative stock balance.
28. A product configured as a prepared dish does not consume raw ingredient stock unless an explicit mapping/recipe exists.
29. Purchase bill quantity increases stock only for a confirmed stock-tracked item and uses a user-confirmed conversion factor.
30. Wrong or malformed AI output cannot pass validation or be committed without a human-confirmed import.

### Security and usability
31. Staff cannot perform admin-only import reversal, day reopen, or user administration actions.
32. Financial changes create audit history, including actor and timestamp.
33. CSV export totals agree with the screen totals for the same filters.
34. Backup file is created, has non-zero size, and restore instructions are tested against a throwaway test database.

---

## 16. Definition of done

The first release is done only when:
- The app starts using the documented setup steps on Windows.
- The backend and frontend run end to end and persist data through a restart.
- Credit bills, partial collections, multi-bill allocations, expenses, payment sources, owner-funded expenses, cashbook, daily closing, purchase entry, and PDF preview/import have working flows.
- The two sample report formats have a human-reviewed import path; the Stock Position quantity columns are explicitly ignored.
- All acceptance tests above pass, plus lint/type checks where configured.
- Critical UI forms show validation errors clearly, handle network/server errors, and do not clear user input after a failed save.
- Database migrations, `.env.example`, backup/restore instructions, and project README are complete.
- At least one realistic local demo sequence is documented: create customer → enter udhari bill → collect partial payment → settle remaining balance → add expense unpaid → pay from two sources → upload/review Item Sales report → enter purchase → close cash → export reports.
- State exactly what was tested and any remaining limitation. Never claim the app is fully tested if only static analysis was run.

---

## 17. Final execution instruction

Start by inspecting the workspace and available reference PDFs. Then build the application in the phases above, keeping each phase runnable. Prioritize correctness of ledgers and reconciliation over visual effects. Use a clean, professional, restaurant-friendly interface, but do not sacrifice accounting invariants for convenience. At the end of each phase, report what was implemented, the commands to run it, tests executed and their actual results, migration status, and any known limitations. Continue to the next phase without waiting for approval unless you encounter a genuine blocking decision.
