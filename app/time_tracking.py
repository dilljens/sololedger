"""Time tracking integration — Toggl Track & Clockify API.

Fetches time entries and generates invoice-ready summaries.

Requires (pick one):
  - TOGGL_API_TOKEN env var (Toggl Track)
  - CLOCKIFY_API_KEY env var (Clockify)

Usage:
    from app.time_tracking import TimeTracker
    tt = TimeTracker(source="toggl")
    entries = tt.fetch_entries(days_back=7)
    summary = tt.summarize_by_client(entries)
"""

import base64
import datetime
import os
import sys
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

import requests


@dataclass
class TimeEntry:
    """Normalized time entry from any time tracking service."""
    id: str
    description: str
    project: str
    client: str = ""
    start: Optional[datetime.datetime] = None
    end: Optional[datetime.datetime] = None
    duration_seconds: int = 0
    billable: bool = True
    hourly_rate: Optional[Decimal] = None
    tags: list[str] = None

    def __post_init__(self):
        if self.tags is None:
            self.tags = []

    @property
    def hours(self) -> float:
        return self.duration_seconds / 3600

    @property
    def amount(self) -> Optional[Decimal]:
        if self.hourly_rate and self.billable:
            return (Decimal(str(self.hours)) * self.hourly_rate).quantize(Decimal("0.01"))
        return None


class TimeTracker:
    """Fetch time entries from Toggl Track or Clockify."""

    def __init__(self, source: str = "toggl", hourly_rate: Optional[Decimal] = None):
        """
        Args:
            source: 'toggl' or 'clockify'
            hourly_rate: Default hourly rate (overridden by project rate)
        """
        self.source = source
        self.default_rate = hourly_rate or Decimal("150")  # Default $150/hr

    def fetch_entries(self, days_back: int = 7, billable_only: bool = True) -> list[TimeEntry]:
        """Fetch time entries from the configured source.

        Args:
            days_back: How many days to look back
            billable_only: Skip non-billable entries

        Returns:
            List of TimeEntry objects
        """
        if self.source == "toggl":
            return self._fetch_toggl(days_back, billable_only)
        elif self.source == "clockify":
            return self._fetch_clockify(days_back, billable_only)
        else:
            print(f"⚠  Unknown time tracking source: {self.source}")
            return []

    def _fetch_toggl(self, days_back: int, billable_only: bool) -> list[TimeEntry]:
        """Fetch time entries from Toggl Track v9 API."""
        api_token = os.environ.get("TOGGL_API_TOKEN", "")
        if not api_token:
            print("⚠  TOGGL_API_TOKEN not set", file=sys.stderr)
            return []

        # Toggl Track API v9 — basic auth with API token
        auth = base64.b64encode(f"{api_token}:api_token".encode()).decode()
        headers = {
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/json",
        }

        # Get workspace ID first
        try:
            r = requests.get("https://api.track.toggl.com/api/v9/me", headers=headers, timeout=10)
            r.raise_for_status()
            me = r.json()
            default_wid = me.get("default_workspace_id")
        except Exception as e:
            print(f"⚠  Toggl auth error: {e}", file=sys.stderr)
            return []

        # Calculate date range
        end_date = datetime.datetime.now(datetime.timezone.utc)
        start_date = end_date - datetime.timedelta(days=days_back)

        params = {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        }

        try:
            r = requests.get(
                f"https://api.track.toggl.com/api/v9/me/time_entries",
                headers=headers,
                params=params,
                timeout=15,
            )
            r.raise_for_status()
            raw_entries = r.json()
        except Exception as e:
            print(f"⚠  Toggl API error: {e}", file=sys.stderr)
            return []

        # Get projects map for project/client names
        projects = {}
        try:
            r = requests.get(
                f"https://api.track.toggl.com/api/v9/workspaces/{default_wid}/projects",
                headers=headers,
                timeout=10,
            )
            if r.ok:
                for p in r.json():
                    projects[p["id"]] = p["name"]
        except Exception:
            pass

        entries = []
        for raw in raw_entries:
            if billable_only and not raw.get("billable", False):
                continue

            duration = raw.get("duration", 0)
            if duration < 0:
                continue  # Still running

            entries.append(TimeEntry(
                id=str(raw["id"]),
                description=raw.get("description") or "(no description)",
                project=projects.get(raw.get("project_id", 0), "General"),
                start=self._parse_iso(raw.get("start")),
                end=self._parse_iso(raw.get("stop")),
                duration_seconds=duration,
                billable=raw.get("billable", False),
                tags=raw.get("tags", []),
            ))

        return entries

    def _fetch_clockify(self, days_back: int, billable_only: bool) -> list[TimeEntry]:
        """Fetch time entries from Clockify API."""
        api_key = os.environ.get("CLOCKIFY_API_KEY", "")
        if not api_key:
            print("⚠  CLOCKIFY_API_KEY not set", file=sys.stderr)
            return []

        headers = {"X-Api-Key": api_key, "Content-Type": "application/json"}

        # Get workspace ID
        try:
            r = requests.get("https://api.clockify.me/api/v1/workspaces", headers=headers, timeout=10)
            r.raise_for_status()
            workspaces = r.json()
            if not workspaces:
                print("⚠  No Clockify workspaces found")
                return []
            workspace_id = workspaces[0]["id"]
        except Exception as e:
            print(f"⚠  Clockify auth error: {e}", file=sys.stderr)
            return []

        end_date = datetime.datetime.now(datetime.timezone.utc)
        start_date = end_date - datetime.timedelta(days=days_back)

        params = {
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
            "page-size": 500,
        }

        try:
            r = requests.get(
                f"https://api.clockify.me/api/v1/workspaces/{workspace_id}/time-entries",
                headers=headers,
                params=params,
                timeout=15,
            )
            r.raise_for_status()
            raw_entries = r.json()
        except Exception as e:
            print(f"⚠  Clockify API error: {e}", file=sys.stderr)
            return []

        # Get projects
        projects = {}
        try:
            r = requests.get(
                f"https://api.clockify.me/api/v1/workspaces/{workspace_id}/projects",
                headers=headers,
                params={"page-size": 200},
                timeout=10,
            )
            if r.ok:
                for p in r.json():
                    projects[p["id"]] = p.get("name", "Unknown")
        except Exception:
            pass

        entries = []
        for raw in raw_entries:
            if billable_only and not raw.get("billable", False):
                continue

            duration_ms = raw.get("timeInterval", {}).get("duration", 0)
            duration_sec = int(duration_ms / 1000) if duration_ms else 0

            if duration_sec <= 0:
                continue

            project_id = raw.get("projectId", "")
            entries.append(TimeEntry(
                id=raw["id"],
                description=raw.get("description") or "(no description)",
                project=projects.get(project_id, "General"),
                start=self._parse_iso(raw.get("timeInterval", {}).get("start")),
                end=self._parse_iso(raw.get("timeInterval", {}).get("end")),
                duration_seconds=duration_sec,
                billable=raw.get("billable", False),
                tags=raw.get("tags", []),
            ))

        return entries

    def _parse_iso(self, iso_str: Optional[str]) -> Optional[datetime.datetime]:
        """Parse ISO 8601 datetime string."""
        if not iso_str:
            return None
        try:
            return datetime.datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        except Exception:
            return None

    @staticmethod
    def summarize_by_client(entries: list[TimeEntry], hourly_rate: Optional[Decimal] = None) -> dict:
        """Group time entries by client/project and summarize.

        Returns:
            dict with total_hours, total_amount, and by_client breakdown
        """
        by_client = defaultdict(lambda: {
            "hours": 0.0,
            "amount": Decimal("0"),
            "projects": defaultdict(lambda: {"hours": 0.0, "amount": Decimal("0")}),
            "entries": [],
        })

        for entry in entries:
            rate = hourly_rate or entry.hourly_rate or None
            amt = entry.amount if entry.amount and rate else Decimal("0")
            client = entry.client or entry.project or "General"

            by_client[client]["hours"] += entry.hours
            by_client[client]["amount"] += amt
            by_client[client]["projects"][entry.project]["hours"] += entry.hours
            by_client[client]["projects"][entry.project]["amount"] += amt
            by_client[client]["entries"].append(entry)

        total_hours = sum(e.hours for e in entries)
        total_amount = sum(e.amount for e in entries if e.amount)

        # Convert defaultdicts to regular dicts
        result = {
            "total_hours": round(total_hours, 2),
            "total_amount": total_amount,
            "entry_count": len(entries),
            "by_client": {},
        }

        for client, data in sorted(by_client.items()):
            result["by_client"][client] = {
                "hours": round(data["hours"], 2),
                "amount": data["amount"],
                "projects": dict(data["projects"]),
            }

        return result

    def generate_invoice_data(self, entries: list[TimeEntry], client_filter: Optional[str] = None) -> Optional[dict]:
        """Generate invoice-ready data from time entries.

        Returns dict suitable for passing to Invoicer.create().
        """
        if client_filter:
            entries = [e for e in entries if client_filter.lower() in e.client.lower() or client_filter.lower() in e.project.lower()]

        if not entries:
            return None

        summary = self.summarize_by_client(entries)
        client = client_filter or list(summary["by_client"].keys())[0]
        total = summary["total_amount"] or Decimal(str(summary["total_hours"] * 150)).quantize(Decimal("0.01"))

        desc_parts = []
        for client_name, data in summary["by_client"].items():
            for project, pdata in data["projects"].items():
                desc_parts.append(f"{project}: {pdata['hours']}h")

        return {
            "client": client,
            "description": "Time tracking: " + ", ".join(desc_parts[:3]),
            "amount": total,
            "entries": summary,
        }
