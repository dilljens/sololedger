# Wyoming LLC Tools

A self-hosted accounting, invoicing, and tax estimation system for your single-member Wyoming consulting LLC.

**Stack**: [Beancount](https://beancount.github.io/) (double-entry accounting) + custom Python CLI + [Fava](https://beancount.github.io/fava/) (web dashboard).

## What It Does

| Command | What |
|---|---|
| `llc invoice create` | Creates an invoice (PDF + ledger entry) |
| `llc expense import bank.csv` | Imports bank CSV → auto-categorizes → records |
| `llc tax estimate` | Calculates quarterly estimated tax (1040-ES + Schedule SE) |
| `llc tax schedule-c` | Spits out Schedule C data at year-end |
| `llc tax deadlines` | Shows upcoming quarterly tax deadlines |
| `llc status` | Dashboard: cash, P&L, tax summary, deadlines |
| Fava (port 5000) | Web UI: balance sheets, P&L charts, budgets |

## Quick Start

### 1. Prerequisites

- Python 3.11+
- Docker + Docker Compose (for Fava web UI — optional)

### 2. Install

```bash
cd llc-tools
pip install -r requirements.txt
```

### 3. Configure

Edit `config.toml` with your business info, EIN, and tax parameters.

### 4. Initialize the ledger

```bash
# Verify the ledger is valid
python -m app.main check
```

### 5. Add your first transaction

```bash
# Record your initial bank deposit
# (edit ledger/transactions.beancount manually for the first entry)
```

### 6. Start Fava (web dashboard)

```bash
docker compose up -d
# Open http://localhost:5000
```

## Usage Examples

```bash
# Dashboard
python -m app.main status

# Create an invoice
python -m app.main invoice create \
    --client "Acme Corp" \
    --description "Q3 2026 Consulting" \
    --amount 5000

# Import bank statement
python -m app.main expense import ./imports/bank-statement-march.csv

# Preview an import (no writes)
python -m app.main expense import --preview ./imports/bank-statement-march.csv

# Tax estimate
python -m app.main tax estimate

# Tax estimate with custom projection
python -m app.main tax estimate --projected-income 120000

# Schedule C summary (at year-end)
python -m app.main tax schedule-c

# Tax deadlines
python -m app.main tax deadlines

# Shorter: use Makefile
make status
make tax-estimate
```

## Project Structure

```
llc-tools/
├── config.toml                  # Your business settings
├── ledger/
│   ├── main.beancount           # Entry point (includes all)
│   ├── accounts.beancount       # Chart of accounts
│   └── transactions.beancount   # Your transactions (appended)
├── app/
│   ├── main.py                  # CLI entry point
│   ├── config.py                # Config loader
│   ├── ledger.py                # Beancount wrapper
│   ├── invoice.py               # Invoice creation + PDF
│   ├── taxes.py                 # Tax estimation engine
│   └── expenses.py              # Bank CSV import
├── templates/
│   └── invoice.html             # Invoice PDF template
├── output/invoices/             # Generated PDFs
├── imports/                     # Drop bank CSVs here
├── docker-compose.yml           # Fava web UI
└── requirements.txt
```

## Tax Logic (Wyoming Single-Member LLC)

```
Net Profit = Revenue − Expenses

Self-Employment Tax = Net Profit × 92.35% × 15.3%
    (12.4% SS on first $184,800 + 2.9% Medicare, uncapped)
    Half of this is deductible above-the-line on Form 1040

Federal Income Tax = (Adjusted Net − Standard Deduction) × Brackets
    Standard deduction (2026): $14,600 (single)
    Brackets: 10% → 37%

Wyoming State Tax = $0  (no state income tax!)

Quarterly Payment = Total Estimated Tax ÷ 4
    Safe harbor: pay 100% of prior year's tax to avoid penalty
```

## Annual Workflow

1. **Weekly/monthly**: Drop bank CSVs in `imports/`, run `llc expense import`
2. **As needed**: `llc invoice create` when you send an invoice
3. **Quarterly**: `llc tax estimate` → pay suggested amount via IRS Direct Pay
4. **Year-end**: `llc tax schedule-c` → copy numbers into Form 1040 Schedule C
5. **File**: Submit Form 1040 (with Schedule C and Schedule SE) by April 15
