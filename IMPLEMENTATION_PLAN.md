# Implementation plan & status

Source of truth: `RESTAURANT_MANAGEMENT_CLAUDE_BUILD_SPEC.md`. Assumptions: `docs/ASSUMPTIONS.md`.

## Architecture
```
backend/app
  models.py       SQLAlchemy 2 models (24 tables) – Alembic migration 0001
  core.py         money/qty validation, auth tokens, audit, settings, day-lock helper
  ledger.py       receivables, receipts/allocations, bills, expenses, owner funding, voids  (pure business rules)
  cash.py         daily-close maths, transfers, manual cash movements
  inventory.py    item catalogue/aliases, movement ledger, stock view (baseline-aware)
  parsing.py      Item Sales / Stock Position extraction (pdf text → local OCR → CSV) + AI payload validator
  reports.py      14 reports shared by screen + CSV;  backup.py verified zip backup/restore;  ai.py optional Gemini provider
  routers/        auth, udhari, money, stock, reporting   (all under /api/v1)
frontend/src      React + TS + Vite SPA (login, dashboard, udhari, receive payment, expenses, purchases, inventory/imports, cash, reports, settings)
```

## Phases (spec §14) — status
| Phase | Scope | Status |
|---|---|---|
| 0 | scaffold, config, migrations, health, README | **Done** |
| 1 | login/roles, settings, customers, credit bills, receipts + multi-bill allocation, advance, statement, voids | **Done** |
| 2 | expenses + split payments, owner funding/reimbursement, accounts, cashbook, transfers, daily close, variance, reopen, audit | **Done** |
| 3 | item catalogue/aliases, opening counts, purchases, Item Sales + Stock Position import review, duplicate controls, stock ledger | **Done** (OCR needs human review by design) |
| 4 | dashboard, 14 reports + CSV + print CSS, verified backups + restore CLI, role checks | **Done** |
| 5 | optional Gemini provider | **Partial**: `app/ai.py` + strict validator + tests of the validator; not wired into upload UI, never run against the live API |

See README "Test results" for what was actually executed.
