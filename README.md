# Restaurant Operations Manager

Internal web app for a restaurant: customer **udhari (credit) ledger** with bill-wise payment tracking, **expenses & payables** (incl. owner-paid
and reimbursement), **cashbook & daily cash reconciliation**, **purchases/stock movements**, and **human-reviewed PDF imports** of the POS
*Item Sales* and *Stock Position* reports. Spec: [`RESTAURANT_MANAGEMENT_CLAUDE_BUILD_SPEC.md`](RESTAURANT_MANAGEMENT_CLAUDE_BUILD_SPEC.md) ·
Assumptions: [`docs/ASSUMPTIONS.md`](docs/ASSUMPTIONS.md) · Plan/status: [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md)

Stack: FastAPI + SQLAlchemy 2 + Alembic (SQLite by default, PostgreSQL-capable) · React + TypeScript + Vite · local OCR (RapidOCR/ONNX).

## Run with Docker (Fastest Deployment)
Run the entire stack (FastAPI backend + built React POS frontend + SQLite persistence) with a single command:
```bash
docker compose up -d --build
```
Open **http://127.0.0.1:8000** in your browser. All database and attachments are safely stored in `./data`.

## Run Locally (Windows, PowerShell)
Requirements: Python 3.11+, Node 20+.
```powershell
.\scripts\setup.ps1     # once: .env with random secret, pip install, DB migrations, frontend build
.\scripts\start.ps1     # http://127.0.0.1:8000   (use -Lan to reach it from phones/tablets on the same Wi-Fi)
```
Open the URL; the first screen creates the **owner (admin)** account. Add staff users in *Settings → Users*.
Development with hot reload: `cd backend; python -m uvicorn app.main:app --reload` and `cd frontend; npm run dev` (http://127.0.0.1:5173).
Health check: `GET /api/v1/health`. API docs: `/docs`.

## ⌨️ POS Keyboard-First Navigation
Designed for rapid cashier desk operation without lifting hands to the mouse:
* **`Ctrl + K` or `F2`**: Omni-search command palette (instant customer search by phone/name, jump to any page)
* **`F1` or `?`**: Interactive keyboard shortcuts reference
* **`F3` / `Alt + 3`**: + Add Udhari Bill
* **`F4` / `Alt + 4`**: Receive Payment / Settle bills with quick tender presets
* **`F8` / `Alt + 5`**: Daily Closing & Cash Drawer with Denomination Calculator
* **`F9` / `Alt + 6`**: Expenses & Payables
* **`Ctrl + Enter` or `F10`**: Universal Quick-Save for any active form
* **`Alt + T`**: Toggle Dark POS Theme / Light Mode
* **`Esc`**: Dismiss modals and search palettes

Everything is in this folder: database `data/restaurant.db`, uploads `data/attachments/`, backups `data/backups/`. Copy `.env.example` → `.env` if you
want to change settings (the setup script generates one). Never commit `.env`.

## Backup & restore
* App: *Settings → Backups → Create backup now*, or `.\scripts\backup.ps1`. A zip (database snapshot + attachments + manifest) is written to
  `data\backups\` and **verified** (non-empty, zip integrity, DB present) before it is reported as successful.
* Restore (SQLite) — never overwrites an existing DB:
```powershell
cd backend
python -m app.cli restore ..\data\backups\backup-YYYYMMDD-HHMMSS.zip --db ..\data\restored\restaurant.db --attachments ..\data\restored\attachments
# stop the app, move the old data\restaurant.db aside, copy the restored file over it (and attachments into data\attachments), start the app
```
PostgreSQL backups use `pg_dump` (must be on PATH); restore with `psql -f database.sql`. *(PostgreSQL path not exercised in this build.)*

## How the main flows work
* **Udhari → Add bill**: customer + bill no + total (+ amount received now). Outstanding is calculated, never typed.
  *“Already included in the POS daily report”* is on by default so the bill never double counts sales or stock.
* **Go-live onboarding**: *Udhari → Import old udhari (CSV)* loads existing unpaid bills (customer, phone, bill_no, date, amount, paid) with a check-first step; all-or-nothing, no cash posted. Set account opening balances in *Settings*.
* **Customers**: edit details, bill details (items, attachment, payments), printable payment receipts, and a *Copy reminder text* button (nothing is sent automatically).
* **Receive Payment**: pick customer → open bills with age → enter amount/method/account → *Suggest oldest bill first* (editable) → save.
  Part payments leave balances open; extra money is kept as **customer advance** (explicitly shown, applicable later).
* **Expenses**: status is derived from payments. Split payments across accounts; **Funded by = Owner personal money** records the expense once,
  leaves the drawer alone and increases *Owed to owner*; **Reimburse owner** reduces both the account and the owed balance (no new expense).
* **Daily Closing**: opening cash + POS cash sales (typed from your POS closing report) + ledger movements → expected cash; enter the physical count;
  variance shown (note required above a threshold); *Finalize* locks the day; only an admin can reopen (reason + audit).
* **PDF imports** (Inventory & PDF Imports → upload): a preview table is built; headings/sub totals/grand total are shown greyed and **never imported**;
  ditto rows inherit the item above; flagged rows are highlighted; totals are cross-checked against the printed ones. Map or create items
  (*bulk buttons available*), tick the review box, then **Confirm import**. Nothing is saved before that. Stock Position imports read **item names +
  UOM only** and create *pending* catalogue items — quantities and values are ignored by design.
* **Demo sequence** (customer → udhari → partial → settle → unpaid expense → two sources → upload Item Sales → purchase → close cash → export):
  `python scripts/demo_flow.py --username … --password … --i-understand-this-adds-demo-data` against a **throw-away** database
  (it labels records `DEMO`). It is the only demo-data command; the live database never receives demo data automatically.

## Tests
```powershell
.\scripts\test.ps1          # backend (fast) + frontend typecheck + unit tests
.\scripts\test.ps1 -Slow    # also runs OCR on the two reference PDFs (~2–4 min)
```
See the bottom of this file for the results recorded when this version was built.

## PostgreSQL
Set `DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/restaurant` in `.env`, run `python -m alembic upgrade head`, start normally. The role must have
`LOGIN` and own the database. To run the test-suite on PostgreSQL create a **separate** database whose name ends in `_test` and set
`TEST_DATABASE_URL` (the suite refuses any other name because it drops all tables).

## AI-assisted reading (optional, experimental)
`GEMINI_ENABLED=true` + `GEMINI_API_KEY` (model `GEMINI_MODEL`, default `gemini-2.5-flash`) adds a *Read with AI* tick-box on Item Sales uploads. Only page images are
sent. On the bundled sample it misread the date (2023) and totals (₹76,341 vs printed ₹26,690), so local OCR + reconciliation remains the default and AI rows are
always flagged for review.

## Security notes
bcrypt password hashes; HMAC-signed 12 h tokens; admin-only voids/reopen/reversal/users/settings/backups; uploads limited by type and size with
generated filenames (no path traversal); CORS limited to the dev origins; secrets only via `.env`; Gemini key never reaches the browser and
customer data is never sent to any model. Bind to `127.0.0.1` unless you deliberately use `-Lan`; do not expose the port to the internet.

## Known limitations
* OCR output must be reviewed: it misreads some digits/letters (the bundled sample has a `9→6` and a `90→6` misread; the reconciliation checks
  flag both). Spaces in names are re-inserted heuristically.
* PostgreSQL, Docker, and the Gemini provider were not exercised. Excel import, supplier-bill PDF import, recipes/BOM, WhatsApp reminders are not built.
* Posted bills cannot be edited; void and re-enter. Staff cannot void.
* Money is shown/typed in ₹ with 2 decimals; the browser does display-only formatting.

## Test results recorded for this build (2026-10-19, Windows 11, Python 3.11, Node 24)
| Suite | Result |
|---|---|
| Backend `pytest` (all, incl. 2 real-OCR tests on the reference PDFs) | **40 passed** in 5m30s |
| Frontend `tsc --noEmit` | clean |
| Frontend `vitest` | **6 passed** |
| Alembic `upgrade head` on a fresh SQLite DB | OK (covered by a test) |
| Manual end-to-end (real server, throw-away DB): demo sequence, restart persistence, verified backup, import review page loads | OK |

Covered: spec acceptance scenarios 1-34 (credit ledger, owner funding, cash closing, imports/inventory, permissions, audit, CSV=screen, backup + restore to a throw-away DB).
Not covered / not run: PostgreSQL, Docker, Gemini live API, mobile-layout visual check (browser pane was hidden), clicking through every form in a browser
(forms were verified through the API and 6 component tests), load/concurrency testing, login rate-limiting (now implemented: 5 failures lock a user+IP for 5 minutes).

