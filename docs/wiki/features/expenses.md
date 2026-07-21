# Expenses

Bank CSV import, auto-categorization, receipt OCR scanning, and bank feed sync.

## Key Functions

- `app.importer.Importer` — CSV import pipeline (5 callers)
- `app.importer.import_csv` / `import_transactions` — file ingestion
- `app.categorizer.Categorizer` — rule-based + LLM categorization
- `app.categorizer_llm` — OpenAI/Anthropic LLM categorization
- `app.categorizer_embed` — embedding-based similarity matching
- `app.receipts.ReceiptScanner` — Tesseract OCR receipt scanning
- `app.bank_feed` — Plaid bank feed integration
- `app.reconciliation` — bank transaction matching
- `app.ofx_import` — OFX/QFX file import
- `app.mileage` — mileage tracking and deduction
