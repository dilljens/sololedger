"""SoloLedger Cloud — Stripe-driven customer provisioning.

When a customer pays for SoloLedger Cloud, this module:
1. Generates a unique API key
2. Provisions a Docker container with their ledger
3. Emails them their URL + API key
4. Registers the instance in a local registry

Usage (manual test):
    python -m app.provision provision "customer@example.com" cloud-monthly

Usage (via Stripe webhook):
    POST /api/v1/stripe-webhook  (handled in api.py → calls provision_customer)
"""

import json
import os
import secrets
import subprocess
import smtplib
import string
import sys
from datetime import datetime
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

# ── Config ──────────────────────────────────────────────────────────────────

# Where customer instances live on the host machine
INSTANCES_DIR = Path(os.environ.get("SL_INSTANCES_DIR", "/opt/sololedger/instances"))
# Registry of all provisioned customers
REGISTRY_PATH = Path(os.environ.get("SL_REGISTRY_PATH", "/opt/sololedger/registry.json"))
# The domain/IP where instances are served
HOST_DOMAIN = os.environ.get("SL_HOST_DOMAIN", "sololedger.ferrumeng.com")
# Docker image tag for the API
DOCKER_IMAGE = os.environ.get("SL_DOCKER_IMAGE", "sololedger-api:latest")
# SMTP config for welcome emails
SMTP_HOST = os.environ.get("SL_SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SL_SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SL_SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SL_SMTP_PASSWORD", "")
SMTP_FROM = os.environ.get("SL_SMTP_FROM", "dillon@ferrumengineeringllc.com")


def generate_api_key() -> str:
    """Generate a cryptographically random API key."""
    return "sl_" + secrets.token_hex(24)


def generate_instance_name(email: str) -> str:
    """Derive a filesystem-safe instance name from the customer email."""
    safe = email.split("@")[0].lower()
    safe = "".join(c for c in safe if c in string.ascii_lowercase + string.digits + "-_")
    safe = safe[:32] or "customer"
    return f"{safe}-{secrets.token_hex(4)}"


def provision_customer(email: str, plan: str = "cloud-monthly") -> dict:
    """Provision a SoloLedger Cloud instance for a paying customer.

    Steps:
    1. Generate API key + instance name
    2. Create instance directory with config + ledger
    3. Start Docker container
    4. Register in the registry
    5. Send welcome email

    Returns dict with instance details.
    """
    api_key = generate_api_key()
    inst_name = generate_instance_name(email)
    inst_dir = INSTANCES_DIR / inst_name
    port = _allocate_port()

    print(f"  Provisioning {email} → {inst_name} (port {port})")
    print(f"  API key: {api_key}")

    # ── 1. Create instance directory ──────────────────────────────
    inst_dir.mkdir(parents=True, exist_ok=True)

    # Copy base ledger template
    _write_default_ledger(inst_dir, email)

    # Write instance config.toml
    _write_instance_config(inst_dir, inst_name)

    # ── 2. Start Docker container ─────────────────────────────────
    container_name = f"sololedger-{inst_name}"
    host_config_dir = str(inst_dir)

    try:
        subprocess.run(
            ["docker", "run", "-d",
             "--name", container_name,
             "--restart", "unless-stopped",
             "-p", f"{port}:8100",
             "-e", f"API_KEYS={api_key}",
             "-e", f"API_CONFIG=/app/config.toml",
             "-v", f"{host_config_dir}:/app/config.toml:ro",
             "-v", f"{host_config_dir}/ledger:/app/ledger",
             "-v", f"{host_config_dir}/output:/app/output",
             DOCKER_IMAGE],
            check=True, capture_output=True, text=True, timeout=60,
        )
        container_id = container_name
        print(f"  ✓ Container started: {container_name}")
    except subprocess.CalledProcessError as e:
        print(f"  ✗ Docker run failed: {e.stderr}")
        # Fall back to running on host via systemd
        container_id = _fallback_host_run(inst_name, inst_dir, api_key, port)
    except FileNotFoundError:
        print(f"  ⚠ Docker not found, falling back to host run")
        container_id = _fallback_host_run(inst_name, inst_dir, api_key, port)

    # ── 3. Register ───────────────────────────────────────────────
    registry = _load_registry()
    registry[email] = {
        "email": email,
        "plan": plan,
        "instance": inst_name,
        "api_key": api_key,
        "port": port,
        "url": f"https://{HOST_DOMAIN}:{port}",
        "container": container_id,
        "provisioned_at": datetime.utcnow().isoformat(),
        "status": "active",
    }
    _save_registry(registry)

    # ── 4. Send welcome email ─────────────────────────────────────
    _send_welcome_email(email, inst_name, api_key, port)

    return registry[email]


def deprovision_customer(email: str):
    """Stop and remove a customer's instance."""
    registry = _load_registry()
    info = registry.get(email)
    if not info:
        print(f"  ✗ No instance found for {email}")
        return

    inst_name = info["instance"]
    container_name = f"sololedger-{inst_name}"

    # Stop Docker container
    try:
        subprocess.run(["docker", "stop", container_name], capture_output=True, timeout=15)
        subprocess.run(["docker", "rm", container_name], capture_output=True, timeout=15)
        print(f"  ✓ Removed container: {container_name}")
    except Exception:
        pass

    # Clean up instance directory
    inst_dir = INSTANCES_DIR / inst_name
    if inst_dir.exists():
        import shutil
        shutil.rmtree(inst_dir)

    # Mark as inactive
    info["status"] = "inactive"
    info["deprovisioned_at"] = datetime.utcnow().isoformat()
    _save_registry(registry)
    print(f"  ✓ Deprovisioned {email}")


def list_instances() -> list[dict]:
    """List all provisioned instances."""
    return list(_load_registry().values())


# ── Internal helpers ────────────────────────────────────────────────────────


def _allocate_port() -> int:
    """Allocate the next available port for a new instance."""
    base = int(os.environ.get("SL_PORT_BASE", "8400"))
    registry = _load_registry()
    used = {info["port"] for info in registry.values() if info.get("status") == "active"}
    port = base
    while port in used:
        port += 1
    return port


def _load_registry() -> dict:
    if REGISTRY_PATH.exists():
        try:
            return json.loads(REGISTRY_PATH.read_text())
        except (json.JSONDecodeError, Exception):
            return {}
    return {}


def _save_registry(registry: dict):
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY_PATH.write_text(json.dumps(registry, indent=2))


def _write_default_ledger(inst_dir: Path, email: str):
    """Write a minimal Beancount ledger for the new customer."""
    ledger_dir = inst_dir / "ledger"
    ledger_dir.mkdir(parents=True, exist_ok=True)

    (ledger_dir / "main.beancount").write_text(f''';; SoloLedger — {email}
;; Auto-provisioned {datetime.utcnow().strftime("%Y-%m-%d")}

2026-01-01 open Assets:Bank:BusinessChecking
2026-01-01 open Assets:AccountsReceivable
2026-01-01 open Equity:OwnerDraws
2026-01-01 open Income:Consulting
2026-01-01 open Expenses:Software:SaaS
2026-01-01 open Expenses:BankFees
2026-01-01 open Liabilities:CreditCard
''')

    (ledger_dir / "transactions.beancount").write_text(";; Transactions will be added here\n")
    (ledger_dir / "accounts.beancount").write_text(";; Account tree — customize as needed\n")


def _write_instance_config(inst_dir: Path, inst_name: str):
    """Write a minimal config.toml for the new instance."""
    config_path = inst_dir / "config.toml"
    config_path.write_text(f"""# SoloLedger Cloud — {inst_name}
# Auto-generated. Customer-specific settings.

[business]
name = "My LLC"
owner = "Business Owner"
state = "WY"
ein = "XX-XXXXXXX"
address = ""
phone = ""
email = ""

[ledger]
path = "ledger/main.beancount"

[accounts]
checking = "Assets:Bank:BusinessChecking"
ar = "Assets:AccountsReceivable"
income = "Income:Consulting"
owner_draws = "Equity:OwnerDraws"

[notifications]
desktop_enabled = false
email_enabled = false

[banking]
plaid_enabled = false
""")


def _fallback_host_run(inst_name: str, inst_dir: Path, api_key: str, port: int) -> str:
    """Fallback: run the API directly on the host via systemd."""
    import shutil
    has_systemd = shutil.which("systemctl")

    if has_systemd:
        service_name = f"sololedger-{inst_name}"
        service_file = f"/etc/systemd/system/{service_name}.service"
        try:
            subprocess.run(
                ["sudo", "tee", service_file],
                input=f"""[Unit]
Description=SoloLedger Cloud — {inst_name}
After=network.target

[Service]
Type=simple
User={os.environ.get("USER", "root")}
WorkingDirectory={inst_dir}
ExecStart={shutil.which("uvicorn") or "uvicorn"} app.api:app --host 0.0.0.0 --port {port}
Restart=always
Environment=API_KEYS={api_key}
Environment=API_CONFIG={inst_dir / "config.toml"}

[Install]
WantedBy=multi-user.target
""",
                check=True, capture_output=True, text=True, timeout=15,
            )
            subprocess.run(["sudo", "systemctl", "daemon-reload"], check=True, timeout=15)
            subprocess.run(["sudo", "systemctl", "enable", service_name], check=True, timeout=15)
            subprocess.run(["sudo", "systemctl", "start", service_name], check=True, timeout=15)
            print(f"  ✓ systemd service started: {service_name}")
            return service_name
        except Exception as e:
            print(f"  ⚠ systemd fallback failed: {e}")

    return "unknown"


def _send_welcome_email(email: str, inst_name: str, api_key: str, port: int):
    """Send a welcome email with connection details."""
    if not SMTP_HOST:
        print(f"  ⚠ SMTP not configured; skipping welcome email for {email}")
        return

    body = f"""Welcome to SoloLedger Cloud!

Your instance is ready. Here are your connection details:

  URL:     https://{HOST_DOMAIN}:{port}/app/
  API:     https://{HOST_DOMAIN}:{port}/api/v1/
  API Key: {api_key}

Getting started:

1. Open the URL in your browser
2. When prompted, enter your API key
3. Run llc init on your local machine to set up your business details

Your dashboard:  https://{HOST_DOMAIN}:{port}/app/
API docs:       https://{HOST_DOMAIN}:{port}/docs

Need help? Reply to this email.

—
SoloLedger Cloud
https://sololedger.ferrumeng.com
"""

    msg = MIMEText(body)
    msg["Subject"] = "Welcome to SoloLedger Cloud — Your Instance Is Ready"
    msg["From"] = SMTP_FROM
    msg["To"] = email

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            if SMTP_USER and SMTP_PASSWORD:
                server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        print(f"  ✓ Welcome email sent to {email}")
    except Exception as e:
        print(f"  ⚠ Failed to send welcome email: {e}")


# ── CLI entry point ─────────────────────────────────────────────────────────


def main():
    """CLI for managing cloud instances."""
    import argparse
    parser = argparse.ArgumentParser(description="SoloLedger Cloud Provisioning")
    sub = parser.add_subparsers(dest="command")

    p_prov = sub.add_parser("provision", help="Provision a new customer")
    p_prov.add_argument("email", help="Customer email")
    p_prov.add_argument("--plan", default="cloud-monthly", help="Subscription plan")
    p_prov.add_argument("--docker-image", help="Override Docker image tag")

    p_deprov = sub.add_parser("deprovision", help="Remove a customer instance")
    p_deprov.add_argument("email", help="Customer email")

    sub.add_parser("list", help="List all instances")

    args = parser.parse_args()
    global DOCKER_IMAGE
    if getattr(args, "docker_image", None):
        DOCKER_IMAGE = args.docker_image

    if args.command == "provision":
        result = provision_customer(args.email, args.plan)
        print(json.dumps(result, indent=2, default=str))
    elif args.command == "deprovision":
        deprovision_customer(args.email)
    elif args.command == "list":
        instances = list_instances()
        print(json.dumps(instances, indent=2, default=str))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
