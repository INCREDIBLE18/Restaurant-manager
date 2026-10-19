# Assumptions & decisions

Recorded per the build spec (§1). None of these invent financial or inventory values.

## Environment / stack
- **Database: SQLite by default** (single PC). Docker and a known PostgreSQL password were not available, so PostgreSQL support is provided
  (`DATABASE_URL`, `docker-compose.yml`, a `Dec` column type that is NUMERIC on PostgreSQL) but **was not tested**. SQLite is not safe for concurrent
  multi-PC use; use one server PC and open the app from other devices over the LAN.
- Money is stored as exact decimals (strings on SQLite, `NUMERIC` on PostgreSQL), computed with Python `Decimal`, and sent to the browser as decimal
  strings. The browser only formats them for display.
- The API serializes everything aggregated in Python (not SQL `SUM`) so SQLite and PostgreSQL behave identically.
- OCR: **RapidOCR (ONNX, local)** because Tesseract is not installed. Scanned PDFs take ~1–2 minutes on this PC. Gemini support (`app/ai.py`) is an
  optional provider that is not wired into the UI flow and was not run against the live API (no key).
- Auth: signed (HMAC-SHA256) expiring bearer token, bcrypt password hashes. First-run `bootstrap` creates the initial admin only while no user exists.

## Ledger rules
- A **receipt** is separate from a **bill**. Amount "received now" on a bill is stored as a *bill-time receipt* allocated to that bill.
- **Bills marked "already in POS report"** (default): the bill is a receivable only. Its "received now" part is **not** posted to the cashbook
  by default because it is assumed to be inside the POS tender totals the owner types into Daily Closing (otherwise cash would be counted twice).
  The bill form can post it explicitly (`post_paid_now_to_cashbook`). Bills *not* in the POS report post their paid-now amount.
- A bill flagged "already in POS report" can never also be "count as new sale". The app never derives revenue/stock from udhari bills; revenue
  comes only from confirmed Item Sales imports and operator-entered POS totals.
- Overpayment is kept as an **unallocated customer advance** on the receipt; it can later be applied to new bills (no new cash movement).
- Customer outstanding = Σ open bill balances; advance is shown separately (net = outstanding − advance).
- Payment method vs account: `cash` must use a physical-cash account; every other method must use a non-cash account (prevents UPI inflating the drawer).
- Voids are **admin-only**, need a reason, keep the original row and post reversal movements dated **today** (the date money actually moves).
  Staff can create entries but cannot void, reopen, reverse imports, write off, enter opening stock counts, or administer users/settings.
- Posting new cash movements into a **finalized** business day is blocked (409). Reverse today or ask an admin to reopen (reason + audit).
- Owner-paid expense payments create **no** account movement; they create an owner-ledger "funded" entry (reimbursable by default; can be marked a
  non-reimbursable contribution). Reimbursing the owner posts one outflow and one owner-ledger entry; no expense is created.
- Purchase bills create exactly **one linked expense** (category "Purchases"); payments are expense payments. Stock-in happens only for lines whose
  item has **Track stock** on, with a **user-entered** conversion factor when the unit differs from the base unit.

## Daily closing
- Expected cash = opening + POS cash sales (typed) + ledger cash movements on physical-cash accounts for that business date (udhari collections,
  other in, transfers in) − (expense payments, owner reimbursements, refunds, withdrawals, other out, transfers out).
  A cash→bank deposit therefore lowers the drawer without being a sale or an expense.
- Opening cash defaults to the previous *finalized* day's counted cash; changing it requires a note when finalizing.
- Variance reasons are mandatory at/above a configurable threshold (default ₹50). No balancing entry is ever auto-created.
- POS tender consistency (`POS total − Σ tenders`) is displayed only as a warning; it is not "reconciled away".

## Imports
- Item Sales rows: `Department:`/`Category:` headings (their printed totals are used only to cross-check the rows beneath them), `Sub Total`,
  `GrandTotal`, `End Of Report`, and unreadable rows are never products or stock movements.
- **Ditto rows** (`"`, or an empty/garbled name with numbers): in the sample they are the same product at a different price. They inherit the name of
  the item row directly above *within the same group*; with no clear predecessor they are left unaccepted and flagged. Same-name rows are summed in
  item-sales reports (e.g. Imperial Blue 180ml: 3 + 2).
- OCR drops spaces and confuses digits/letters. Names are re-spaced heuristically and **matched on a compact key** (letters/digits only). Typos
  (e.g. "Roval Staq") are left for the reviewer; fuzzy matches are *suggestions only*. Sub-total/category/grand-total mismatches flag exactly the
  rows that probably were misread (the sample's `Tuborg Strong 650ml 9→6` and `Sub Total 90→6` are caught this way).
- **Stock Position**: only names and UOM labels are read; quantity/value columns are never extracted or stored (rows have `qty = amount = NULL`).
  The "Summary" repeat section is skipped. Imported names become *pending* catalogue items with `Track stock = off`; no inventory movement is created.
- Duplicate protection: same file hash or same report type+date already confirmed → import blocked; only an admin can override, with a reason.
- Confirming requires: zero unmapped accepted rows, report date set, and an explicit "acknowledge warnings" tick when rows are flagged or the totals
  do not reconcile with the printed grand total.
- Confirmed Item Sales create `item_sale_lines` (report data, not cash). Stock-out is posted only for items with `Track stock` on and kind = product;
  prepared dishes never consume ingredient stock (no recipes in this version).
- The root-level PDFs supplied in the project folder were 0-byte files; the real documents were in `Restaurant_Operations_Manager_Claude_Pack/reference_pdfs/`
  and were copied to `reference_pdfs/` (the location the spec searches).

## Not built (documented limitations)
Recipes/BOM, WhatsApp reminders, payroll, GST invoicing, multi-branch, Excel (.xlsx) import (PDF/image/CSV supported), supplier-bill PDF import
(manual purchase entry works), per-user granular permissions beyond admin/staff, bulk restore UI (restore is a CLI), editing a posted bill's amount
(void and re-enter), Gemini wiring into the upload screen.
