"""Notifications — desktop alerts, email reminders, and CLI status checks.

Supports:
  - Desktop notifications (Linux notify-send)
  - Email alerts via SMTP
  - Aggregated daily/weekly status summaries

Config (in config.toml):
  [notifications]
  email_enabled = false
  smtp_host = "smtp.gmail.com"
  smtp_port = 587
  smtp_user = "you@gmail.com"
  smtp_password = "app-password"   # Or set NOTIFY_SMTP_PASSWORD env var
  alert_email = "you@gmail.com"
  desktop_enabled = true
  remind_days_before = 7
"""

import datetime
import os
import smtplib
import subprocess
import sys
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

from .config import Config
from .ledger import Ledger
from .taxes import TaxEstimator


class Notifier:
    """Send notifications about tax deadlines, unpaid invoices, and ledger health."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._load_config()

    def _load_config(self):
        """Load notification settings from config."""
        raw = getattr(self.cfg, "_raw", {})
        n = raw.get("notifications", {})

        self.desktop_enabled = n.get("desktop_enabled", True)
        self.email_enabled = n.get("email_enabled", False)
        self.remind_days = n.get("remind_days_before", 7)

        self.smtp_host = n.get("smtp_host", "smtp.gmail.com")
        self.smtp_port = n.get("smtp_port", 587)
        self.smtp_user = n.get("smtp_user", "")
        self.smtp_password = n.get("smtp_password", "") or os.environ.get("NOTIFY_SMTP_PASSWORD", "")
        self.alert_email = n.get("alert_email", self.smtp_user)

    def desktop(self, title: str, message: str, urgency: str = "normal") -> bool:
        """Send a desktop notification via notify-send.

        Returns True if notification was sent.
        """
        if not self.desktop_enabled:
            return False

        try:
            subprocess.run(
                ["notify-send", f"--urgency={urgency}", title, message],
                timeout=5,
                capture_output=True,
            )
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
            return False

    def email(self, subject: str, body: str) -> bool:
        """Send an email notification.

        Returns True if sent successfully.
        """
        if not self.email_enabled or not self.smtp_user or not self.smtp_password:
            return False

        try:
            msg = MIMEText(body)
            msg["Subject"] = subject
            msg["From"] = self.smtp_user
            msg["To"] = self.alert_email or self.smtp_user

            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)

            return True
        except Exception as e:
            print(f"⚠  Email send failed: {e}", file=sys.stderr)
            return False

    # ── specific alert builders ────────────────────────────────────────────

    def alert_tax_deadlines(self, ledger: Ledger) -> list[str]:
        """Check upcoming tax deadlines and send alerts if needed.

        Returns list of alert messages sent.
        """
        taxer = TaxEstimator(self.cfg, ledger, state_code=self.cfg.state_code)
        info = taxer.deadline_info()
        alerts = []

        for d in info["deadlines"]:
            days = d["days_until"]

            if days < 0:
                # Overdue!
                msg = f"⚠  {d['label']} tax deadline is OVERDUE ({d['due']})!"
                self.desktop("Tax Deadline Overdue!", msg, urgency="critical")
                self.email("Tax Deadline Overdue!", msg)
                alerts.append(msg)

            elif 0 <= days <= self.remind_days:
                # Approaching
                msg = f"📅 {d['label']} tax deadline: {d['due']} ({days} days away)"
                self.desktop("Upcoming Tax Deadline", msg)
                alerts.append(msg)

        # Add payment amount info if possible
        if alerts:
            net = ledger.net_income()
            if net > 0:
                est = taxer.quarterly_estimate(net)
                amt_msg = (
                    f"Suggested next payment: ${est['suggested_payment']:,.2f}\n"
                    f"{est['note']}"
                )
                alerts.append(amt_msg)
                self.desktop("Estimated Tax Due", amt_msg)

        return alerts

    def alert_unpaid_invoices(self, ledger: Ledger) -> list[str]:
        """Check for overdue accounts receivable and alert.

        Returns list of alert messages.
        """
        # Query AccountsReceivable balance
        ar_balance = ledger.account_balance(self.cfg.ar_account)
        alerts = []

        if ar_balance > 0:
            msg = (
                f"Unpaid invoices: ${ar_balance:,.2f} in Accounts Receivable\n"
                f"Run 'llc invoice list' to see details."
            )
            self.desktop("Unpaid Invoices", msg, urgency="normal")
            alerts.append(msg)

        return alerts

    def alert_ledger_health(self, ledger: Ledger) -> list[str]:
        """Alert if the ledger has errors."""
        errors = ledger.check()
        if errors:
            msg = f"Ledger has {len(errors)} error(s)! Run 'llc check' for details."
            self.desktop("Ledger Error", msg, urgency="critical")
            self.email("Ledger Error", msg + "\n\n" + "\n".join(errors[:10]))
            return [msg]
        return []

    def send_digest(self, ledger: Ledger) -> dict:
        """Send a full status digest — combines all alerts.

        Returns summary dict with counts of each alert type.
        """
        results = {
            "tax_deadlines": self.alert_tax_deadlines(ledger),
            "unpaid_invoices": self.alert_unpaid_invoices(ledger),
            "ledger_health": self.alert_ledger_health(ledger),
        }

        # If email is enabled, send a digest email
        if self.email_enabled:
            parts = []
            for key, alerts in results.items():
                if alerts:
                    parts.append(f"=== {key.upper()} ===")
                    parts.extend(alerts)
                    parts.append("")

            if parts:
                body = "\n".join(parts)
                self.email(
                    f"LLC Daily Digest — {datetime.date.today().isoformat()}",
                    body,
                )

        return results
