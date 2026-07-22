# Deploy Ferrum Engineering Services on your VPS

Sets up `sololedger.ferrumeng.com` and `poolsplat.ferrumeng.com` with Docker Compose + Caddy (auto TLS).

## 1. DNS

Add A records at your DNS provider:

| Type | Name | Value |
|------|------|-------|
| A | `sololedger` | `<your-vps-ip>` |
| A | `poolsplat` | `<your-vps-ip>` |

## 2. On the VPS

```bash
# Install Docker if needed
curl -fsSL https://get.docker.com | sh

# Clone the repos
git clone https://github.com/dilljens/sololedger /opt/sololedger
git clone https://github.com/dilljens/poolsplat /opt/poolsplat

# Configure SoloLedger
cp /opt/sololedger/config.toml /opt/sololedger/config.toml
nano /opt/sololedger/config.toml
#   → set business name, EIN, address, etc.
mkdir -p /opt/sololedger/{ledger,output,imports}

# Set up secrets
cp /opt/sololedger/deploy/.env.example /opt/sololedger/deploy/.env
nano /opt/sololedger/deploy/.env
#   → add Stripe, Plaid, Toggl, FAL_KEY as needed

# Start everything
cd /opt/sololedger/deploy
docker compose up -d
```

## 3. Verify

### SoloLedger
- `https://sololedger.ferrumeng.com/app/` → SoloLedger dashboard
- `https://sololedger.ferrumeng.com/docs` → API docs
- `https://sololedger.ferrumeng.com/api/v1/health` → API health check

### PoolSplat
- `https://poolsplat.ferrumeng.com/` → 3D viewer

### First-run SoloLedger setup
```bash
docker exec sololedger-api python3 -m app.main init
docker exec sololedger-api python3 -m app.main demo
docker exec sololedger-api python3 -m app.main doctor
```

## 4. Maintenance

```bash
# Update all services
cd /opt/sololedger && git pull
cd /opt/poolsplat && git pull
docker compose -f /opt/sololedger/deploy/docker-compose.yml up -d --build

# View logs
docker compose -f /opt/sololedger/deploy/docker-compose.yml logs -f sololedger-api
docker compose -f /opt/sololedger/deploy/docker-compose.yml logs -f poolsplat

# Stop
docker compose -f /opt/sololedger/deploy/docker-compose.yml down
```
