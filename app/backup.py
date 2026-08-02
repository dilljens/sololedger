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

    def _backup_paths(self) -> list[str]:
        """Paths to back up: the repo ledger + config, plus tenant ledger
        data (data/ledgers/) so per-tenant ledgers aren't lost. Auth stores
        (sessions/users/tenants) are deliberately excluded — they contain
        bearer tokens and are gitignored as secrets."""
        paths = ["ledger/", "config.toml"]
        data_ledgers = self.repo_path / "data" / "ledgers"
        if data_ledgers.exists():
            paths.append("data/ledgers/")
        return paths

    def has_changes(self) -> bool:
        """Check if there are uncommitted changes in the ledger dirs."""
        stdout, _ = self._git("status", "--porcelain", "--", *self._backup_paths())
        return bool(stdout.strip())

    def status(self) -> list[dict]:
        """Get uncommitted changes."""
        stdout, _ = self._git("status", "--porcelain", "--", *self._backup_paths())
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

        # Add only ledger and config files (plus tenant ledger data when
        # present). Force-add: tenant data/ledgers is gitignored but must be
        # backed up off-site.
        self._git("add", "-f", "--", *self._backup_paths())
        stdout, stderr = self._git("commit", "-m", message)

        committed = bool(stdout.strip())
        files = self.status()  # should be empty now

        if not quiet:
            if committed:
                print(f"✓ Backup: {message}")
            else:
                print(f"  Backup: nothing to commit")

        # Try to push if remote exists — surface failures instead of
        # silently dropping them (a failed push means no off-site copy).
        push_result = ""
        remote_stdout, _ = self._git("remote", "-v")
        if remote_stdout.strip():
            push_out, push_err = self._git("push")
            if push_err:
                push_result = push_err
                print(f"⚠  Backup push failed: {push_err}", file=sys.stderr)
            elif not quiet and push_out:
                print(f"  Pushed to remote")

        return {
            "committed": committed,
            "message": message,
            "stdout": stdout,
            "push": push_result or ("ok" if remote_stdout.strip() else "no-remote"),
        }
