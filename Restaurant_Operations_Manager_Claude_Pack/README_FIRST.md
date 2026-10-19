# Start here — Restaurant Operations Manager

1. Extract this package into a new project folder, for example `D:\Personal Projects\Restaurant Manager`.
2. Open Claude Code in that folder.
3. Paste the instruction below:

> Read `RESTAURANT_MANAGEMENT_CLAUDE_BUILD_SPEC.md` completely and treat it as the single source of truth for the product. Inspect both PDFs in `reference_pdfs/` before implementing the import workflow. First inspect the workspace and write `IMPLEMENTATION_PLAN.md` and `docs/ASSUMPTIONS.md`, then implement the phases in the specification, testing each phase and continuing until the application is working. Do not stop at a plan or UI mock-up. Do not modify files outside this project folder. Follow the financial-ledger, no-double-counting, and Stock Position PDF rules exactly. At the end, report the commands to run the app and the actual tests/results.

## Package contents

- `RESTAURANT_MANAGEMENT_CLAUDE_BUILD_SPEC.md` — detailed product and implementation brief.
- `reference_pdfs/Stock Position.PDF.pdf` — item names/UOM reference only; ignore its stock quantities and values.
- `reference_pdfs/Item Sales.PDF.pdf` — scanned aggregate item-sales report for import design/testing; not a payment-mode report.
