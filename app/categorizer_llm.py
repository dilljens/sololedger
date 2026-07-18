"""LLM-assisted categorization — Level 3 of the cascade.

Sits between embedding similarity (Level 2) and human review (Level 4).
Only fires for transactions that both pattern rules and embedding
couldn't categorize with confidence.

Supports multiple backends:
  - Local: Ollama (gemma3:1b, phi4-mini, llama3.2)
  - Remote: OpenAI-compatible APIs (OpenAI, Anthropic, etc.)

No backend configured = gracefully disabled.

Usage:
    from app.categorizer_llm import LlmCategorizer
    llm = LlmCategorizer(cfg)

    # Check if available
    if llm.available:
        result = llm.suggest(
            merchant="AMAZON MKTPLACE PMTS $47.23",
            similar=[{"merchant": "...", "account": "..."}, ...],
            accounts=["Expenses:Software:SaaS", "Expenses:Supplies", ...],
        )
        # → {"account": "Expenses:Software:SaaS", "confidence": 0.85,
        #    "reasoning": "Amazon marketplace payments...", "model": "gemma3:1b"}
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from .config import Config


# ── Configuration ──────────────────────────────────────────────────────────

# Which LLM backends to try, in order
# Set via env var or app config
LLM_BACKEND = os.environ.get("SL_LLM_BACKEND", "")  # "ollama", "openai", "anthropic"
LLM_MODEL = os.environ.get("SL_LLM_MODEL", "gemma3:1b")
LLM_API_KEY = os.environ.get("SL_LLM_API_KEY", "")
LLM_API_URL = os.environ.get("SL_LLM_API_URL", "http://localhost:11434")  # Ollama default
LLM_TIMEOUT = int(os.environ.get("SL_LLM_TIMEOUT", "30"))


# ── Prompt Template ────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a categorization assistant for a solo consulting LLC's accounting system.
Your job is to categorize bank transactions into the correct expense or income account.

Rules:
1. Only return a category from the provided list of valid accounts
2. If uncertain, choose the closest match and explain why
3. Use past similar categorizations as guidance — consistency matters
4. For truly ambiguous transactions, flag them

Return your response as JSON: {{"account": "...", "confidence": 0.0-1.0, "reasoning": "..."}}
"""


def build_prompt(
    merchant: str,
    similar: Optional[list[dict]] = None,
    accounts: Optional[list[str]] = None,
    rules: Optional[list[dict]] = None,
) -> str:
    """Build the full prompt for LLM categorization.

    Args:
        merchant: The raw transaction merchant name + amount
        similar: Past similar transactions [{merchant, account, count}]
        accounts: All valid accounts in the chart
        rules: Active pattern rules [{pattern, account}]

    Returns:
        Formatted prompt string.
    """
    parts = [f"Categorize this transaction: {merchant}"]

    if accounts:
        parts.append(f"\nValid accounts:\n" + "\n".join(f"  - {a}" for a in sorted(accounts)))

    if similar:
        parts.append(f"\nPast similar transactions:")
        for s in similar[:5]:
            parts.append(f"  - {s.get('merchant', '?')[:50]} → {s.get('account', '?')}")
            if s.get("count", 0) > 1:
                parts[-1] += f" ({s['count']} times)"

    if rules:
        parts.append(f"\nActive rules that didn't match (for context):")
        for r in rules[:5]:
            parts.append(f"  - {r.get('pattern', '?')} → {r.get('account', '?')}")

    parts.append(
        "\n\nReturn ONLY valid JSON: "
        '{"account": "...", "confidence": 0.85, "reasoning": "..."}'
    )

    return "\n".join(parts)


# ── Backend Implementations ────────────────────────────────────────────────


def _call_ollama(model: str, prompt: str, system: str, timeout: int) -> Optional[dict]:
    """Call a local Ollama model."""
    try:
        import requests
        url = f"{LLM_API_URL}/api/chat"
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "options": {"temperature": 0.1},  # low temp for deterministic output
        }
        resp = requests.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        content = data.get("message", {}).get("content", "")
        return _parse_json_response(content)
    except ImportError:
        return None
    except Exception as e:
        return None


def _call_openai(model: str, prompt: str, system: str, timeout: int) -> Optional[dict]:
    """Call an OpenAI-compatible API."""
    try:
        import requests
        url = f"{LLM_API_URL}/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {LLM_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
        }
        resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        return _parse_json_response(content)
    except ImportError:
        return None
    except Exception as e:
        return None


def _call_anthropic(model: str, prompt: str, system: str, timeout: int) -> Optional[dict]:
    """Call Anthropic Claude API."""
    try:
        import requests
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": LLM_API_KEY,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "system": system,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 200,
            "temperature": 0.1,
        }
        resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        content = data.get("content", [{}])[0].get("text", "")
        return _parse_json_response(content)
    except ImportError:
        return None
    except Exception as e:
        return None


def _parse_json_response(content: str) -> Optional[dict]:
    """Extract JSON from LLM response (handles markdown-wrapped JSON)."""
    if not content:
        return None

    # Try direct parse first
    content = content.strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # Try extracting from ```json ... ``` blocks
    import re
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Try finding { } in the text
    match = re.search(r"\{[^{}]*\}", content, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    return None


# ── LLM Categorizer ────────────────────────────────────────────────────────


class LlmCategorizer:
    """LLM-assisted transaction categorization.

    Usage:
        llm = LlmCategorizer(cfg)
        if llm.available:
            result = llm.suggest(merchant="...")
    """

    def __init__(self, cfg: Optional[Config] = None):
        self.cfg = cfg
        self._backend = LLM_BACKEND
        self._model = LLM_MODEL
        self._available: Optional[bool] = None

    @property
    def available(self) -> bool:
        """Check if an LLM backend is configured and reachable."""
        if self._available is not None:
            return self._available

        # Check env config
        if not self._backend:
            self._available = False
            return False

        # Quick health check
        if self._backend == "ollama":
            self._available = self._check_ollama()
        elif self._backend in ("openai", "anthropic"):
            self._available = bool(LLM_API_KEY)
        else:
            self._available = False

        return self._available

    def _check_ollama(self) -> bool:
        """Check if Ollama is running and has the model."""
        try:
            import requests
            resp = requests.get(f"{LLM_API_URL}/api/tags", timeout=5)
            if resp.status_code != 200:
                return False
            models = resp.json().get("models", [])
            return any(m.get("name", "").startswith(self._model) for m in models)
        except Exception:
            return False

    def suggest(
        self,
        merchant: str,
        similar: Optional[list[dict]] = None,
        accounts: Optional[list[str]] = None,
        rules: Optional[list[dict]] = None,
    ) -> dict[str, Any]:
        """Suggest a category using the LLM.

        Args:
            merchant: Raw transaction description (e.g. "AMAZON MKTPLACE PMTS $47.23")
            similar: Past similar categorizations [{merchant, account, count}]
            accounts: List of valid account names (from chart of accounts)
            rules: Active pattern rules for context

        Returns:
            dict with keys:
                account: The suggested Beancount account
                confidence: 0.0-1.0
                reasoning: Explanation text
                model: Model name used
                backend: Backend used
            or {"account": None, "available": False} if unavailable.
        """
        if not self.available:
            return {"account": None, "confidence": 0.0, "reasoning": "",
                    "available": False, "model": self._model}

        prompt = build_prompt(merchant, similar, accounts, rules)

        result = None
        if self._backend == "ollama":
            result = _call_ollama(self._model, prompt, SYSTEM_PROMPT, LLM_TIMEOUT)
        elif self._backend == "openai":
            result = _call_openai(self._model, prompt, SYSTEM_PROMPT, LLM_TIMEOUT)
        elif self._backend == "anthropic":
            result = _call_anthropic(self._model, prompt, SYSTEM_PROMPT, LLM_TIMEOUT)

        if result and "account" in result:
            result["model"] = self._model
            result["backend"] = self._backend
            result["available"] = True
            return result

        return {"account": None, "confidence": 0.0, "reasoning": "LLM returned no valid response",
                "available": True, "model": self._model, "backend": self._backend}
