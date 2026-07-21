# Time Tracking

Sync billable hours from Toggl and Clockify to generate invoices.

## Key Functions

- `app.time_tracking` — time data sync and processing (6 callers)
- `app.time_tracking.fetch_entries` — pull time entries from providers
- `app.time_tracking.time_to_invoice` — convert tracked time to invoice lines
- `app.time_tracking.list` — list projects and workspaces

## External APIs

| Provider | Endpoint | Auth |
|----------|----------|------|
| Toggl | `api.track.toggl.com/api/v9` | API token |
| Clockify | `api.clockify.me/api/v1` | API key |
