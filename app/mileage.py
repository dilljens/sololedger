"""Mileage tracking for business driving deductions.

Logs trips and calculates the IRS standard mileage deduction.
Stores entries in a JSON file appended to the Beancount ledger as
transactions on Expenses:Travel (or a designated mileage account).

IRS standard mileage rate (updated annually):
    2025: $0.70/mile  (effective Jan 1, 2025)
    2024: $0.67/mile

Usage:
    from app.mileage import MileageTracker
    mt = MileageTracker(cfg, ledger)
    mt.add_trip(date="2026-07-17", purpose="Client meeting", miles=42)
    report = mt.yearly_report(2026)
"""

from __future__ import annotations

import csv
import datetime
import json
from dataclasses import dataclass, field, asdict
from decimal import Decimal
from pathlib import Path
from typing import Optional

from .config import Config
from .ledger import Ledger


# IRS standard mileage rates (per business mile)
# Update this each year
IRS_MILEAGE_RATES: dict[int, Decimal] = {
    2025: Decimal("0.70"),
    2024: Decimal("0.67"),
    2023: Decimal("0.655"),
    2022: Decimal("0.585"),  # H2 2022 rate
}


def get_irs_rate(year: int) -> Decimal:
    """Get the IRS standard mileage rate for a given year."""
    return IRS_MILEAGE_RATES.get(year, IRS_MILEAGE_RATES.get(2025, Decimal("0.70")))


@dataclass
class Trip:
    """A single business driving trip."""
    date: str          # YYYY-MM-DD
    miles: float       # total miles driven
    purpose: str       # business purpose description
    client: str = ""   # optional client name
    start_odo: float = 0.0  # optional odometer start
    end_odo: float = 0.0    # optional odometer end
    notes: str = ""    # optional notes
    route: str = ""    # optional start → end description
    id: str = ""       # auto-generated

    def __post_init__(self):
        if not self.id:
            self.id = f"trip_{self.date}_{abs(hash(self.date + self.purpose + str(self.miles)) % 1000000)}"

    @property
    def deduction(self) -> Decimal:
        """Calculate IRS standard deduction for this trip."""
        rate = get_irs_rate(int(self.date[:4]))
        return rate * Decimal(str(self.miles))


class MileageTracker:
    """Track business mileage and calculate deductions.

    Data stored in `.mileage_log.json` at the project root.
    Trips can optionally be posted to Beancount ledger as transactions.
    """

    LOG_FILE = ".mileage_log.json"

    def __init__(self, cfg: Config, ledger: Ledger):
        self.cfg = cfg
        self.ledger = ledger
        self._log_path = Path(cfg.project_root) / self.LOG_FILE
        self._trips: list[Trip] = []
        self._load()

    def _load(self):
        """Load trips from JSON log."""
        if self._log_path.exists():
            try:
                data = json.loads(self._log_path.read_text())
                self._trips = [Trip(**t) for t in data]
            except (json.JSONDecodeError, Exception):
                self._trips = []
        else:
            self._trips = []

    def _save(self):
        """Persist trips to JSON log."""
        self._log_path.write_text(
            json.dumps([asdict(t) for t in self._trips], indent=2)
        )

    def add_trip(
        self,
        date: str,
        miles: float,
        purpose: str,
        client: str = "",
        start_odo: float = 0.0,
        end_odo: float = 0.0,
        notes: str = "",
        route: str = "",
        post_to_ledger: bool = True,
    ) -> Trip:
        """Log a business trip and optionally post to the Beancount ledger.

        Args:
            date: Trip date (YYYY-MM-DD)
            miles: Miles driven
            purpose: Business purpose
            client: Optional client/project
            start_odo: Starting odometer
            end_odo: Ending odometer
            notes: Optional notes
            route: Start→end description
            post_to_ledger: If True, append a transaction to Beancount

        Returns:
            The Trip object.
        """
        # Auto-calculate miles if start/end odo provided
        if start_odo and end_odo and miles == 0:
            miles = end_odo - start_odo

        trip = Trip(
            date=date,
            miles=miles,
            purpose=purpose,
            client=client,
            start_odo=start_odo,
            end_odo=end_odo,
            notes=notes,
            route=route,
        )

        self._trips.append(trip)
        self._save()

        # Optionally post to Beancount
        if post_to_ledger:
            deduction = trip.deduction
            mileage_account = "Expenses:Travel"  # could be configurable

            # Split into medical vs business if needed
            # (currently all business)
            postings = [
                (mileage_account, f"{deduction:.2f} USD"),
                (self.cfg.checking_account, f"{-deduction:.2f} USD"),
            ]

            narration = f"Mileage: {purpose}"
            payee = purpose[:60]
            trip_date = datetime.date.fromisoformat(date)
            self.ledger.append(trip_date, payee, narration, postings)
            self.ledger.reload(force=True)

        return trip

    def add_trips_batch(self, trips: list[dict], post_to_ledger: bool = True) -> list[Trip]:
        """Add multiple trips at once.

        Args:
            trips: List of dicts with keys: date, miles, purpose[, client, notes, route]
            post_to_ledger: Post each trip to Beancount

        Returns:
            List of created Trip objects.
        """
        results = []
        for t in trips:
            trip = self.add_trip(
                date=t["date"],
                miles=t["miles"],
                purpose=t["purpose"],
                client=t.get("client", ""),
                notes=t.get("notes", ""),
                route=t.get("route", ""),
                post_to_ledger=post_to_ledger,
            )
            results.append(trip)
        return results

    def yearly_report(self, year: int) -> dict:
        """Generate a yearly mileage summary for tax purposes.

        Returns:
            dict with keys: year, total_miles, total_deduction, rate, trip_count,
                            trips_by_purpose, monthly_breakdown
        """
        yearly = [t for t in self._trips if t.date.startswith(str(year))]
        total_miles = sum(t.miles for t in yearly)
        rate = get_irs_rate(year)
        total_deduction = rate * Decimal(str(total_miles))

        # Group by purpose
        by_purpose: dict[str, float] = {}
        for t in yearly:
            by_purpose[t.purpose] = by_purpose.get(t.purpose, 0) + t.miles

        # Monthly breakdown
        monthly: dict[str, float] = {}
        for t in yearly:
            month = t.date[:7]  # YYYY-MM
            monthly[month] = monthly.get(month, 0) + t.miles

        return {
            "year": year,
            "total_miles": total_miles,
            "total_deduction": float(total_deduction),
            "rate_per_mile": float(rate),
            "trip_count": len(yearly),
            "trips_by_purpose": by_purpose,
            "monthly_breakdown": monthly,
        }

    def export_csv(self, path: str | Path, year: Optional[int] = None) -> str:
        """Export mileage log to CSV.

        Args:
            path: Output CSV path
            year: Optional year filter

        Returns:
            Path to the CSV file.
        """
        trips = self._trips
        if year:
            trips = [t for t in trips if t.date.startswith(str(year))]

        path = Path(path)
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "id", "date", "miles", "purpose", "client",
                "start_odo", "end_odo", "route", "notes", "deduction",
            ])
            writer.writeheader()
            for t in trips:
                row = asdict(t)
                row["deduction"] = float(t.deduction)
                writer.writerow(row)

        return str(path)

    def list_trips(
        self,
        year: Optional[int] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """List trips with optional filters.

        Args:
            year: Optional year filter
            limit: Max trips to return
            offset: Pagination offset

        Returns:
            List of trip dicts with computed deduction.
        """
        trips = self._trips
        if year:
            trips = [t for t in trips if t.date.startswith(str(year))]

        trips.sort(key=lambda t: t.date, reverse=True)
        trips = trips[offset:offset + limit]

        return [
            {
                "id": t.id,
                "date": t.date,
                "miles": t.miles,
                "purpose": t.purpose,
                "client": t.client,
                "deduction": float(t.deduction),
                "route": t.route,
                "notes": t.notes,
            }
            for t in trips
        ]

    def clear(self):
        """Clear all mileage entries (use with caution)."""
        self._trips = []
        self._save()

    @property
    def trip_count(self) -> int:
        return len(self._trips)
