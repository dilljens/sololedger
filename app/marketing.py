"""Marketing automation — generate changelog, blog posts, and social media
content from git history using any LLM API (OpenAI, Anthropic, or local).

Usage:
    llc marketing generate           # Generate all marketing content
    llc marketing changelog          # Just the changelog
    llc marketing blog               # Just the blog post draft
    llc marketing social             # Just the social media posts

Requires:
    - OPENAI_API_KEY or ANTHROPIC_API_KEY env var
    - Or set LLM_PROVIDER=local for local models
"""

import datetime
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Optional


class MarketingGenerator:
    """Generate marketing content from git history using an LLM."""

    def __init__(self, repo_path: Optional[str] = None):
        self.repo_path = repo_path or str(Path.cwd())
        self.api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY") or ""
        self.provider = self._detect_provider()

    def _detect_provider(self) -> str:
        """Detect which LLM provider to use."""
        if os.environ.get("OPENAI_API_KEY"):
            return "openai"
        if os.environ.get("ANTHROPIC_API_KEY"):
            return "anthropic"
        return "none"

    def _git_log(self, days: int = 30) -> list[dict]:
        """Get git commits from the last N days."""
        since = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
        try:
            result = subprocess.run(
                ["git", "log", f"--since={since}", "--oneline", "--format=%H|%ai|%s"],
                capture_output=True, text=True, timeout=15,
                cwd=self.repo_path,
            )
            commits = []
            for line in result.stdout.strip().split("\n"):
                if not line.strip():
                    continue
                parts = line.split("|", 2)
                if len(parts) == 3:
                    commits.append({"hash": parts[0], "date": parts[1], "message": parts[2]})
            return commits
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return []

    def _git_diff(self, days: int = 30) -> str:
        """Get git diff stat for recent changes."""
        since = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
        try:
            result = subprocess.run(
                ["git", "diff", f"--since={since}", "--stat"],
                capture_output=True, text=True, timeout=15,
                cwd=self.repo_path,
            )
            return result.stdout.strip()[:2000]  # truncate for LLM
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return ""

    def _llm_call(self, prompt: str, system: str = "") -> str:
        """Call the configured LLM API."""
        if not self.api_key:
            return self._local_fallback(prompt)

        if self.provider == "openai":
            return self._call_openai(prompt, system)
        elif self.provider == "anthropic":
            return self._call_anthropic(prompt, system)
        return self._local_fallback(prompt)

    def _call_openai(self, prompt: str, system: str) -> str:
        """Call OpenAI API."""
        import requests
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        try:
            r = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json={
                    "model": "gpt-4o-mini",
                    "messages": messages,
                    "max_tokens": 1500,
                    "temperature": 0.7,
                },
                timeout=30,
            )
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            return f"Error calling OpenAI: {e}"

    def _call_anthropic(self, prompt: str, system: str) -> str:
        """Call Anthropic API."""
        import requests
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        messages = [{"role": "user", "content": prompt}]
        body = {
            "model": "claude-3-haiku-20240307",
            "max_tokens": 1500,
            "messages": messages,
        }

        try:
            r = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=body,
                timeout=30,
            )
            r.raise_for_status()
            return r.json()["content"][0]["text"].strip()
        except Exception as e:
            return f"Error calling Anthropic: {e}"

    def _local_fallback(self, prompt: str) -> str:
        """Fallback when no LLM is configured — returns a template."""
        return (
            "⚠  No LLM API key set. Set OPENAI_API_KEY or ANTHROPIC_API_KEY.\n\n"
            "Without an API key, the marketing generator provides templates.\n"
            "Fill in the details below and post manually.\n\n"
            "---\n\n"
            + prompt
        )

    def generate_changelog(self, days: int = 30) -> str:
        """Generate a human-readable changelog from git commits."""
        commits = self._git_log(days)
        if not commits:
            return "No recent changes found."

        commit_text = "\n".join([
            f"- {c['date'][:10]}: {c['message']}" for c in commits
        ])
        diff_stats = self._git_diff(days)

        prompt = f"""You are a technical writer for SoloLedger, an open-source accounting tool.
Write a concise, user-friendly changelog for the latest release.

Recent commits:
{commit_text}

Files changed:
{diff_stats}

Write a changelog in markdown format with:
1. Version header with date
2. "New" section for new features
3. "Changed" section for improvements
4. "Fixed" section for bug fixes (if any)
5. Keep it short — developers scan changelogs"""

        result = self._llm_call(prompt, "You write concise changelogs for developer tools.")

        # If LLM didn't work, fallback to manual template
        if result.startswith("Error") or result.startswith("⚠"):
            result = f"""# Changelog — {datetime.date.today().isoformat()}

## New
- {commits[0]['message'] if commits else 'See git log'}

## Installation
```bash
git pull
pip install -r requirements.txt
```
"""
        return result

    def generate_blog_post(self, days: int = 30) -> str:
        """Generate a blog post draft about recent changes."""
        commits = self._git_log(days)
        commit_text = "\n".join([
            f"- {c['message']}" for c in commits
        ])

        prompt = f"""You are the founder of SoloLedger, an open-source accounting tool for solo consultants.
Write a short blog post (300-500 words) about the latest updates.

Recent changes:
{commit_text}

The blog post should:
1. Start with a hook about the problem SoloLedger solves
2. Describe the newest features naturally
3. End with a call to action (try it on GitHub, star the repo)
4. Be authentic and technical — developer audience
5. Include a link to https://github.com/dillonj/solo-ledger

Write in first person as the founder."""

        result = self._llm_call(prompt, "You write authentic technical blog posts for developer tools.")

        if result.startswith("Error") or result.startswith("⚠"):
            result = f"""# SoloLedger Update — {datetime.date.today().isoformat()}

I've been working on SoloLedger, an open-source accounting tool for solo consulting LLCs.
Here's what's new:

{chr(10).join([f'- {c["message"]}' for c in commits[:5]])}

Try it out: https://github.com/dillonj/solo-ledger
"""
        return result

    def generate_social_posts(self, days: int = 30) -> dict:
        """Generate social media posts for Twitter/X, LinkedIn, and Reddit."""
        commits = self._git_log(days)
        top_features = "\n".join([c["message"] for c in commits[:5]])

        prompt = f"""You are marketing SoloLedger, an open-source accounting tool.
Generate 3 social media posts based on these recent changes:

{top_features}

Product: SoloLedger — open-source accounting/invoicing/tax for solo consulting LLCs
URL: https://github.com/dillonj/solo-ledger

Generate:
1. A Twitter/X thread (5 tweets max)
2. A LinkedIn post (professional tone)
3. A Reddit post for r/plaintextaccounting"""

        result = self._llm_call(prompt, "You write concise, engaging social media content for developer tools.")

        if result.startswith("Error") or result.startswith("⚠"):
            result = f"""## Twitter/X Thread

1/ SoloLedger just shipped new features:
{chr(10).join([f'{i+1}. {c["message"]}' for i, c in enumerate(commits[:4])])}

5/ Open source, self-hosted, $0 to start. GitHub: https://github.com/dillonj/solo-ledger

## LinkedIn

Just shipped updates to SoloLedger — my open-source accounting tool for solo consulting LLCs.

New: {commits[0]['message'] if commits else 'See changelog'}

Self-host your own accounting. https://github.com/dillonj/solo-ledger

## Reddit (r/plaintextaccounting)

Just updated SoloLedger, my open-source Beancount-based accounting tool. New features:
{chr(10).join([f'- {c["message"]}' for c in commits[:5]])}

https://github.com/dillonj/solo-ledger
"""
        return result

    def generate_all(self, days: int = 30) -> dict:
        """Generate all marketing content."""
        return {
            "changelog": self.generate_changelog(days),
            "blog_post": self.generate_blog_post(days),
            "social_posts": self.generate_social_posts(days),
            "generated_at": datetime.datetime.now().isoformat(),
        }

    def save_to_files(self, days: int = 30, output_dir: Optional[str] = None):
        """Generate and save all marketing content to files."""
        out = Path(output_dir or (Path(self.repo_path) / "marketing"))
        out.mkdir(parents=True, exist_ok=True)

        content = self.generate_all(days)

        # Save each piece to a markdown file
        (out / "CHANGELOG.md").write_text(content["changelog"])
        (out / "blog-post.md").write_text(content["blog_post"])

        social = content["social_posts"]
        if isinstance(social, str):
            (out / "social-posts.md").write_text(social)
        elif isinstance(social, dict):
            (out / "social-posts.md").write_text(
                "\n\n---\n\n".join(f"## {k}\n\n{v}" for k, v in social.items())
            )

        (out / "generated.txt").write_text(f"Generated: {content['generated_at']}\n")

        return {
            "output_dir": str(out),
            "files": ["CHANGELOG.md", "blog-post.md", "social-posts.md"],
        }
