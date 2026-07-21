# Core Ledger

The accounting engine built on Beancount double-entry bookkeeping.

## Key Functions

- `app.ledger.Ledger` — ledger operations, append transactions, account balances
- `app.ledger.Ledger.account_balance` — get balance for any account
- `ledger/main.beancount` — primary ledger file
- `ledger/accounts.beancount` — chart of accounts
- `ledger/transactions.beancount` — transaction journal
- `app.api` — REST API endpoints for ledger queries

## Call Graph Hotspots

- `Ledger.append` — 17 callers (most-used mutation)
- `Ledger.account_balance` — 8 callers (most-used query)

## Testing

Run via `python -m pytest tests/test_ledger.py`.
