# Invoicing

Invoice generation with PDF downloads, Stripe payment links, and receivables tracking.

## Key Functions

- `app.invoice.Invoicer` — invoice creation (13 callers, core domain)
- `app.invoice.Invoicer.create` — generate invoice + PDF
- `app.payments` — Stripe payment processing and checkout
- `app.reports` — AR aging, P&L, expense reports
- `templates/invoice.html` — invoice PDF template (Jinja2)
- `templates/voucher.html` — 1040-ES voucher template

## Dependencies

- `stripe` — payment processing
- `jinja2` — PDF template rendering

## Testing

`tests/test_invoice.py` — 15 calls into invoice module (top tested domain).
