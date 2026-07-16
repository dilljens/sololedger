"""Auto-backup — commit and push ledger changes to git.

Usage:
    from app.backup import Backup
    b = Backup(cfg)
    b.commit()        # Commit any changes
    b.status()        # Show uncommitted changes
"""

import datetime
import subprocess
import sys
from pathlib import Path

from .config import Config


class Backup:
    """Git-based backup for the ledger."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.repo_path = cfg.project_root

    def _git(self, *args: str) -> tuple[str, str]:
        """Run a git command and return (stdout, stderr)."""
        try:
            result = subprocess.run(
                ["git"] + list(args),
                capture_output=True, text=True, timeout=30,
                cwd=self.repo_path,
            )
            return result.stdout.strip(), result.stderr.strip()
        except FileNotFoundError:
            return "", "git not found"
        except subprocess.TimeoutExpired:
            return "", "timeout"

    def has_changes(self) -> bool:
        """Check if there are uncommitted changes in the ledger dirs."""
        stdout, _ = self._git("status", "--porcelain", "--", "ledger/", "config.toml")
        return bool(stdout.strip())

    def status(self) -> list[dict]:
        """Get uncommitted changes."""
        stdout, _ = self._git("status", "--porcelain", "--", "ledger/", "config.toml")
        changes = []
        for line in stdout.strip().split("\n"):
            if not line.strip():
                continue
            status = line[:2].strip()
            path = line[3:].strip()
            changes.append({"status": status, "path": path})
        return changes

    def commit(self, message: str = "", quiet: bool = False) -> dict:
        """Commit any uncommitted ledger changes.

        Returns dict with committed, message, files_changed.
        """
        if not self.has_changes():
            return {"committed": False, "message": "No changes to commit"}

        if not message:
            date_str = datetime.date.today().isoformat()
            message = f"Auto-backup {date_str}"

        # Add only ledger and config files
        self._git("add", "--", "ledger/", "config.toml")
        stdout, stderr = self._git("commit", "-m", message)

        committed = bool(stdout.strip())
        files = self.status()  # should be empty now

        if not quiet:
            if committed:
                print(f"✓ Backup: {message}")
            else:
                print(f"  Backup: nothing to commit")

        # Try to push if remote exists
        remote_stdout, _ = self._git("remote", "-v")
        if remote_stdout.strip():
            push_out, push_err = self._git("push")
            if not quiet and push_out:
                print(f"  Pushed to remote")

        return {
            "committed": committed,
            "message": message,
            "stdout": stdout,
        }
