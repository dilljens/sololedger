"""Regression tests for the importer, backup, and LLM-categorizer fixes."""
import os
import subprocess
from pathlib import Path

import pytest


class TestImporterDedup:
    """Importer (Wave/QBO/generic CSV) must dedup via the metadata DB."""

    def test_generic_csv_dedup(self, sample_config, tmp_path):
        from app.db import TenantDB
        from app.importer import Importer
        from app.ledger import Ledger

        db = TenantDB(tmp_path)
        importer = Importer(sample_config, Ledger(sample_config))

        csv_path = tmp_path / "data.csv"
        csv_path.write_text(
            "Date,Description,Amount\n"
            "2026-02-01,Office Supplies,-25.00\n"
            "2026-02-02,Client Retainer,1000.00\n"
        )

        first = importer.import_csv(csv_path, db=db, source="csv")
        assert len(first) == 2, first

        second = importer.import_csv(csv_path, db=db, source="csv")
        assert len(second) == 0, f"generic CSV re-import double-posted: {len(second)}"

    def test_wave_csv_parses(self, sample_config, tmp_path):
        from app.importer import Importer
        from app.ledger import Ledger

        importer = Importer(sample_config, Ledger(sample_config))
        wave = tmp_path / "wave.csv"
        wave.write_text(
            "Date,Description,Amount,Account Type,Account Name\n"
            "2026-03-01,Software Subscription,-49.00,Expense,Banking\n"
            "2026-03-05,Consulting Income,2500.00,Income,Banking\n"
        )
        result = importer.import_wave_csv(wave, preview=True)
        assert len(result) == 2, result

    def test_qbo_csv_parses(self, sample_config, tmp_path):
        from app.importer import Importer
        from app.ledger import Ledger

        importer = Importer(sample_config, Ledger(sample_config))
        qbo = tmp_path / "qbo.csv"
        qbo.write_text(
            "Date,Description,Amount,Name,Account\n"
            "2026-04-01,Hosting,-15.00,Provider,Banking\n"
        )
        result = importer.import_qbo_csv(qbo, preview=True)
        assert len(result) == 1, result


class TestBackup:
    """Backup commits ledger changes and surfaces push failures."""

    @pytest.fixture
    def git_repo(self, tmp_path):
        """A throwaway git repo with a config + ledger."""
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "ledger").mkdir()
        (repo / "ledger" / "main.beancount").write_text(
            'option "title" "Backup test"\n'
            "1970-01-01 open Assets:Bank:BusinessChecking\n"
        )
        (repo / "ledger" / "transactions.beancount").write_text(";; txn\n")
        (repo / "config.toml").write_text(
            "[business]\nname = \"T\"\nowner = \"T\"\nstate = \"WY\"\nein = \"X\"\naddress = \"\"\nphone = \"\"\nemail = \"t@t.com\"\n"
            "[ledger]\npath = \"ledger/main.beancount\"\n"
            "[accounts]\nchecking = \"Assets:Bank:BusinessChecking\"\nar = \"Assets:AccountsReceivable\"\nincome = \"Income:Consulting\"\nowner_draws = \"Equity:OwnerDraws\"\n"
            "[tax]\nstate = \"WY\"\nstandard_deduction = 14600\n[[tax.brackets]]\nrate = 0.10\nfloor = 0\nceiling = 11925\n"
            "[tax.self_employment]\nrate_social_security = 0.124\nrate_medicare = 0.029\nss_wage_base = 184800\ndeduction_ratio = 0.9235\n"
        )
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=repo, check=True)
        return repo

    def test_commit_captures_changes(self, git_repo):
        from app.config import Config
        from app.backup import Backup

        cfg = Config(str(git_repo / "config.toml"))
        # Make a change
        (git_repo / "ledger" / "transactions.beancount").write_text(";; txn changed\n")

        b = Backup(cfg)
        assert b.has_changes() is True
        result = b.commit(message="test backup", quiet=True)
        assert result["committed"] is True, result

        # Committed: working tree clean for tracked paths
        stdout = subprocess.run(
            ["git", "status", "--porcelain"], cwd=git_repo, capture_output=True, text=True
        ).stdout.strip()
        assert stdout == "", f"dirty after commit: {stdout}"

    def test_no_changes_reports_not_committed(self, git_repo):
        from app.config import Config
        from app.backup import Backup
        cfg = Config(str(git_repo / "config.toml"))
        b = Backup(cfg)
        result = b.commit(message="nothing", quiet=True)
        assert result["committed"] is False
        assert "No changes" in result["message"]


class TestLlmConfig:
    """LLM categorizer config is read lazily and backend URLs are correct."""

    def test_config_reads_env_fresh(self, monkeypatch):
        from app.categorizer_llm import llm_config
        monkeypatch.setenv("SL_LLM_BACKEND", "openai")
        monkeypatch.setenv("SL_LLM_MODEL", "gpt-4o-mini")
        monkeypatch.setenv("SL_LLM_API_KEY", "sk-test-123")
        cfg = llm_config()
        assert cfg["backend"] == "openai"
        assert cfg["model"] == "gpt-4o-mini"
        assert cfg["api_key"] == "sk-test-123"

    def test_openai_uses_openai_endpoint_not_ollama(self, monkeypatch):
        """Without SL_LLM_API_URL, OpenAI calls must target api.openai.com,
        not silently post to the local Ollama URL."""
        from app.categorizer_llm import _call_openai
        # Monkeypatch requests so no network is hit — capture the URL used.
        captured = {}

        class FakeResp:
            def raise_for_status(self):
                pass

            def json(self):
                return {"choices": [{"message": {"content": '{"account": "Expenses:Miscellaneous"}'}}]}

        class FakeRequests:
            @staticmethod
            def post(url, **kwargs):
                captured["url"] = url
                return FakeResp()

        # _call_openai does `import requests` internally → patch sys.modules
        import sys
        import types
        fake_mod = types.ModuleType("requests")
        fake_mod.post = FakeRequests.post
        monkeypatch.setitem(sys.modules, "requests", fake_mod)
        monkeypatch.delenv("SL_LLM_API_URL", raising=False)
        result = _call_openai("gpt-4o-mini", "prompt", "system", 5, api_key="sk-x")
        assert result is not None
        assert captured["url"].startswith("https://api.openai.com"), captured["url"]

    def test_available_requires_backend(self, monkeypatch):
        from app.categorizer_llm import LlmCategorizer
        monkeypatch.delenv("SL_LLM_BACKEND", raising=False)
        llm = LlmCategorizer()
        assert llm.available is False
