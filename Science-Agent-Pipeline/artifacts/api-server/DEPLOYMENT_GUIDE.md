# Deployment Guide

**For:** Operators deploying Caterva backend  
**Status:** August 2026  
**Audience:** DevOps, SRE, deployment engineers

---

## Deployment Options

### Option 1: Single Server (Development/Small Scale)

**Best for:** <100 queries/day, single team  
**Setup time:** ~15 minutes  
**Maintenance:** Minimal

> **Package manager note:** this is a pnpm workspace (root `Science-Agent-Pipeline/package.json` declares `"packageManager": "pnpm@11.20.0"` and its `preinstall` script deletes any `package-lock.json`/`yarn.lock` that shows up). Workspace packages like `@workspace/api-zod` and `@workspace/db` use the `workspace:*` protocol, which plain `npm install` cannot resolve. Use `pnpm`, not `npm`, for every step below.

```bash
# 1. Prerequisites
Node.js 18+
Python 3.10–3.13
pnpm (see packageManager field in Science-Agent-Pipeline/package.json for the exact version)

# 2. Clone and install (install from the workspace root, not the api-server dir)
git clone <repo>
cd Science-Agent-Pipeline
pnpm install

# 3. Configure environment
cd artifacts/api-server
cp .env.example .env
# Edit .env with your values (see .env.example for the full list):
# - PORT=5000            (required — server will not start without it)
# - NODE_ENV=production
# - LOG_LEVEL=info
# - CATERVA_PYTHON=/usr/bin/python3.12

# 4. Build (from artifacts/api-server, or use the workspace-root filter)
pnpm run build
# equivalent from the workspace root: pnpm --filter @workspace/api-server run build

# 5. Start
pnpm run start
# Or use systemd — see "System Service Setup" below, which is a proposed
# setup, not something this repo ships or installs today.
```

### Option 2: Docker Container

> **Proposed — not implemented in this repo yet.** The repo's one real `Dockerfile` lives at the git root (`/Dockerfile`). It is `FROM python:3.12-slim` and builds a sandbox/CI-parity image for the Caterva simulation engine (installs `requirements-dev.txt`, runs `scripts/check_env.py`, and drops into `CMD ["bash"]`). It has no Node.js, no `EXPOSE`, and nothing to do with the Express API server. There is no Dockerfile anywhere under `Science-Agent-Pipeline/artifacts/api-server`. The Node Dockerfile below is a proposal for containerizing the API server, not something that exists or has been built/tested in this repo — treat it as a starting point, not a verified artifact.
>
> The earlier version of this section also used `npm ci` against a `package-lock.json`, which does not exist and would not work here: this is a pnpm workspace (`Science-Agent-Pipeline/package.json` declares `"packageManager": "pnpm@11.20.0"` and its `preinstall` script deletes `package-lock.json`/`yarn.lock` if either appears), and the API server's own dependencies (`@workspace/api-zod`, `@workspace/db`) use the `workspace:*` protocol that plain `npm`/`npm ci` cannot resolve at all. The Dockerfile below has been corrected to use `pnpm` and to build from the workspace root so the `workspace:*` deps resolve.

**Proposed Dockerfile** (place at the `Science-Agent-Pipeline` workspace root, not written to the repo today):
```dockerfile
FROM node:20-bullseye

# Install Python (only needed if the container also runs the simulation
# engine in-process; if Python runs in a separate service/container, drop this).
RUN apt-get update && apt-get install -y \
    python3.12 \
    python3.12-venv \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

# Enable pnpm via corepack, pinned to the version this workspace declares.
RUN corepack enable && corepack prepare pnpm@11.20.0 --activate

WORKDIR /app

# Copy the whole workspace so `workspace:*` deps (e.g. @workspace/api-zod,
# @workspace/db) resolve correctly -- a single package's package.json is
# not enough in a pnpm workspace.
COPY Science-Agent-Pipeline/ ./Science-Agent-Pipeline/
WORKDIR /app/Science-Agent-Pipeline
RUN pnpm install --frozen-lockfile

# Build only the api-server package
RUN pnpm --filter @workspace/api-server run build

WORKDIR /app/Science-Agent-Pipeline/artifacts/api-server

# Expose port (must match the PORT env var passed at runtime)
EXPOSE 5000

# Health check — the real route is /api/healthz (health.ts is mounted
# under the /api prefix in src/app.ts), not /healthz.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD node -e "require('http').get('http://localhost:5000/api/healthz', (r) => {if (r.statusCode !== 200) throw new Error(r.statusCode)})"

# Real entry point per package.json's "start" script: node --enable-source-maps ./dist/index.mjs
# (build.mjs/esbuild emits an ESM bundle at dist/index.mjs, not dist/index.js)
CMD ["node", "--enable-source-maps", "dist/index.mjs"]
```

**Build and run (once such a Dockerfile is added):**
```bash
docker build -t caterva-api:latest -f Dockerfile.api .

docker run -d \
  --name caterva-api \
  -p 5000:5000 \
  -e PORT=5000 \
  -e NODE_ENV=production \
  -e DATABASE_URL="postgresql://..." \
  -e GROQ_API_KEY="..." \
  caterva-api:latest
```

### Option 3: Kubernetes (Scale)

> **Proposed — not implemented in this repo yet.** There are no Kubernetes manifests anywhere in this repository (no `k8s/` or `kubernetes/` directory, no `*.yaml`/`*.yml` file with `apiVersion:`/`kind:`, no `kubectl` usage in any script). The YAML and commands below are an illustrative proposal for a future k8s deployment, not a deployment target this repo currently supports or has tested. It also depends on the proposed Docker image from Option 2, which does not exist yet either.

**Best for:** >1000 queries/day, multi-region  
**Setup time:** ~2 hours  
**Maintenance:** High (but automated)

**k8s Deployment (proposed):**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: caterva-api
  labels:
    app: caterva-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: caterva-api
  template:
    metadata:
      labels:
        app: caterva-api
    spec:
      containers:
      - name: api
        image: caterva-api:latest
        ports:
        - containerPort: 5000
        env:
        - name: PORT
          value: "5000"
        - name: NODE_ENV
          value: "production"
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: caterva-secrets
              key: database-url
        - name: GROQ_API_KEY
          valueFrom:
            secretKeyRef:
              name: caterva-secrets
              key: groq-api-key
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"
        livenessProbe:
          httpGet:
            path: /api/healthz
            port: 5000
          initialDelaySeconds: 10
          periodSeconds: 30
        readinessProbe:
          httpGet:
            path: /api/healthz
            port: 5000
          initialDelaySeconds: 5
          periodSeconds: 10

---
apiVersion: v1
kind: Service
metadata:
  name: caterva-api
spec:
  selector:
    app: caterva-api
  type: LoadBalancer
  ports:
  - protocol: TCP
    port: 80
    targetPort: 5000
```

**Deploy (once these manifests are actually added to the repo):**
```bash
kubectl apply -f deployment.yaml
kubectl apply -f secrets.yaml  # Contains API keys
```

---

## Environment Configuration

### Required Variables

```bash
# Server
PORT=5000                           # Listening port
NODE_ENV=production                 # development|production

# Python
CATERVA_PYTHON=/usr/bin/python3.12 # Python interpreter path
VIRTUAL_ENV=/path/to/venv          # Optional: virtual environment

# Logging
LOG_LEVEL=info                      # trace|debug|info|warn|error

# Data Persistence
CACHE_FILE=./data/cache.json        # In-memory cache file (optional)
WAITLIST_FILE=./data/waitlist.json  # Waitlist JSON file (optional; read in
                                     # src/routes/waitlist.ts and src/routes/pipeline.ts)
DATABASE_URL=                       # PostgreSQL URL (optional)
```

### Optional LLM Configuration

```bash
# Groq (recommended, free tier available)
GROQ_API_KEY=gsk_...

# Or: OpenRouter
OPENROUTER_API_KEY=sk_...

# Or: Mistral
MISTRAL_API_KEY=...

# Or: SiliconFlow
SILICONFLOW_API_KEY=...

# Or: Generic OpenAI-compatible
OPENAI_API_KEY=...
OPENAI_BASE_URL=https://your-endpoint.com/v1

# LLM timeout: NOT an env var. src/lib/llmResolver.ts hardcodes 30_000ms
# directly in the AbortController timeout (`setTimeout(() => abortController.abort(), 30_000)`).
# There is no LLM_TIMEOUT_MS env var read anywhere in the code. To change
# this value you must edit llmResolver.ts and rebuild/redeploy.
```

### Security Variables

```bash
# Rate limiting: NOT env-configurable, and there are actually two separate,
# unrelated mechanisms in the codebase, neither reads process.env for these values:
#
# 1. Global middleware (src/app.ts): `const RATE_LIMIT = 1000;
#    const RATE_WINDOW_MS = 15 * 60 * 1000;`. This only sets
#    X-RateLimit-* response headers on every request -- it tracks a
#    counter but never actually rejects a request (no 429 branch exists).
#    In practice this is informational only, not enforcement.
# 2. Real enforcement (src/lib/rateLimit.ts, via express-rate-limit),
#    applied only to `POST /api/simulate`: hardcoded 10 requests per 60
#    seconds. Exceeding it returns HTTP 429 with
#    `{"error":"TOO_MANY_REQUESTS","message":"..."}` -- not "RATE_LIMITED".
#
# To change either, edit the relevant source file and rebuild/redeploy;
# setting RATE_LIMIT or RATE_WINDOW_MS in the environment has no effect
# on either mechanism.

# Metrics access
METRICS_ADMIN_TOKEN=your-secret    # Protects POST /api/metrics/reset (real; see src/routes/metrics.ts)
```

### Example .env File

```bash
# Server Configuration
PORT=5000
NODE_ENV=production
LOG_LEVEL=info

# Python Bridge
CATERVA_PYTHON=/usr/bin/python3.12
VIRTUAL_ENV=/opt/caterva-venv

# Persistence (optional)
DATABASE_URL=postgresql://user:password@localhost:5432/caterva
CACHE_FILE=/var/cache/caterva/cache.json
WAITLIST_FILE=/var/lib/caterva/waitlist.json

# LLM Configuration (optional - falls back to keywords if not set)
GROQ_API_KEY=gsk_your_key_here
# NOTE: LLM_TIMEOUT_MS is not a real env var — the 30s LLM timeout is
# hardcoded in src/lib/llmResolver.ts. Setting it here does nothing.

# Security
METRICS_ADMIN_TOKEN=your-secret-admin-token
# NOTE: RATE_LIMIT and RATE_WINDOW_MS are not real env vars — both are
# hardcoded constants in src/app.ts. Setting them here does nothing;
# changing the rate limit requires editing app.ts and redeploying.
```

---

## Database Setup (Optional)

### PostgreSQL Installation

```bash
# macOS
brew install postgresql@15
brew services start postgresql@15

# Ubuntu
sudo apt-get install postgresql-15
sudo systemctl start postgresql

# Docker
docker run -d \
  --name caterva-db \
  -e POSTGRES_DB=caterva \
  -e POSTGRES_USER=caterva \
  -e POSTGRES_PASSWORD=secure_password \
  -p 5432:5432 \
  postgres:15-alpine
```

### Create Database & User

```sql
CREATE DATABASE caterva;
CREATE USER caterva WITH PASSWORD 'secure_password';
ALTER ROLE caterva SET client_encoding TO 'utf8';
ALTER ROLE caterva SET default_transaction_isolation TO 'read committed';
ALTER ROLE caterva SET timezone TO 'UTC';
GRANT ALL PRIVILEGES ON DATABASE caterva TO caterva;
```

### Push Schema (Drizzle)

There is no `db:migrate` script anywhere in this repo, and the DB package
(`Science-Agent-Pipeline/lib/db`, package name `@workspace/db`) does not use
migration files at all — it uses Drizzle's push-based workflow. The real
scripts, per `Science-Agent-Pipeline/lib/db/package.json`, are `build`,
`push`, and `push-force`:

```bash
# From the workspace root (Science-Agent-Pipeline/)
pnpm --filter @workspace/db run push
# Force push (accepts data-loss warnings non-interactively):
pnpm --filter @workspace/db run push-force

# Verify
psql -U caterva -d caterva -c "\d"
# Should show: simulations table
```

### Connection String

```
postgresql://caterva:secure_password@localhost:5432/caterva
```

---

## System Service Setup (systemd)

> **Proposed — not implemented in this repo yet.** There is no systemd unit file, install script, or any reference to `caterva-api` as a service anywhere in this repository. Nothing here installs, enables, or manages a systemd service today. The unit file below is a proposal for operators who choose to run the built server directly on a Linux host with systemd — it has not been tested against this repo.

### Service File (proposed)

```ini
# /etc/systemd/system/caterva-api.service
[Unit]
Description=Caterva Science Agent API
After=network.target

[Service]
Type=simple
User=caterva
WorkingDirectory=/opt/caterva-api
EnvironmentFile=/opt/caterva-api/.env
# Real entry point per package.json's "start" script:
ExecStart=/usr/bin/node --enable-source-maps dist/index.mjs
Restart=on-failure
RestartSec=10s
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

### Enable & Start

```bash
sudo systemctl daemon-reload
sudo systemctl enable caterva-api
sudo systemctl start caterva-api

# Check status
sudo systemctl status caterva-api

# View logs
sudo journalctl -u caterva-api -f
```

---

## Health Checks & Monitoring

### Built-in Health Endpoint

The router is mounted at `/api` in `src/app.ts` (`app.use("/api", router)`), and `/healthz` is defined inside that router (`src/routes/health.ts`) — so the real path is `/api/healthz`, not `/healthz`:

```bash
curl http://localhost:5000/api/healthz
# Returns: {"status":"ok"}
```

### Metrics Endpoints

There are several real, distinct metrics-related endpoints, all mounted under `/api` — none of them require a bearer token except the reset endpoint. Re-verified directly against `src/routes/pipeline.ts` and `src/routes/metrics.ts`:

```bash
# Basic aggregate counts (src/routes/pipeline.ts) — no auth required.
# Confirmed by src/__tests__/routes.test.ts ("GET /api/metrics").
curl http://localhost:5000/api/metrics
# Returns: {totalSimulations, completedSimulations, enqueuedSimulations,
#           failedSimulations, waitlistSignups, uptime}

# Detailed snapshot (src/routes/metrics.ts) — no auth required.
# NOTE: despite living in metrics.ts and the file's own header comment
# claiming "GET /api/metrics/snapshot", the route is registered as
# router.get("/snapshot", ...) on a router mounted with no "/metrics"
# prefix, so the real, working path is /api/snapshot, NOT /api/metrics/snapshot.
# This looks like a real bug/inconsistency in the source, documented here
# as-is rather than as the aspirational path the code comment describes.
curl http://localhost:5000/api/snapshot

# Lightweight health check for monitoring systems — no auth required.
curl http://localhost:5000/api/metrics/health

# Admin-only reset — the only metrics endpoint that actually checks
# METRICS_ADMIN_TOKEN (returns 501 if the token isn't configured).
curl -X POST http://localhost:5000/api/metrics/reset \
  -H "Authorization: Bearer your-secret-admin-token"
```

There is no `GET /api/metrics/history` endpoint in this repo (it's mentioned only in a stale comment in `src/routes/metrics.ts`, not implemented as a route).

### Prometheus Scrape Config

> **Proposed — not implemented in this repo yet.** There is no `prometheus.yml`, scrape config, or Prometheus integration anywhere in this repository — no `/metrics` endpoint in Prometheus exposition format exists either (the JSON endpoints above are not Prometheus-format). The config below is illustrative only and would need a real Prometheus-format metrics endpoint to be added before it could work.

```yaml
# prometheus.yml (proposed)
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'caterva-api'
    static_configs:
      - targets: ['localhost:5000']
    metrics_path: '/api/metrics'
```

### Grafana Dashboards

> **Proposed — not implemented in this repo yet.** No Grafana dashboards, provisioning config, or references exist in this repository.

**Key metrics to graph (proposed, contingent on the Prometheus integration above existing):**
- HTTP request latency (p50, p95, p99)
- Queue depth (active jobs)
- Cache hit rate
- Error rate by type
- Python execution time
- LLM API latency

---

## Load Balancer Setup

### Nginx (Reverse Proxy)

> **Proposed — not implemented in this repo yet.** There is no nginx config, `.conf` file, or reverse-proxy setup anywhere in this repository. The config below is illustrative only.

```nginx
# proposed nginx config — not present in this repo
upstream caterva_backend {
    server localhost:5000;
    server localhost:5001;
    server localhost:5002;
}

server {
    listen 80;
    server_name api.caterva.example.com;
    
    # Rate limiting
    limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s;
    limit_req zone=api_limit burst=20 nodelay;
    
    # Proxy settings
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    
    # Timeouts
    proxy_connect_timeout 60s;
    proxy_send_timeout 60s;
    proxy_read_timeout 60s;
    
    location / {
        proxy_pass http://caterva_backend;
    }
    
    # GET /api/metrics is a real, unauthenticated endpoint (see
    # src/routes/pipeline.ts) — it does not require the admin token.
    # The endpoint that actually checks METRICS_ADMIN_TOKEN is
    # POST /api/metrics/reset (see src/routes/metrics.ts); if you want to
    # additionally gate it at the proxy layer, scope the auth_request to
    # that specific path instead of all of /api/metrics.
    location /api/metrics/reset {
        auth_request /auth;
        proxy_pass http://caterva_backend;
    }
    
    location /auth {
        # Verify admin token
        return 200;
    }
}
```

### Start Nginx

```bash
nginx -t
sudo systemctl start nginx
```

---

## Backup & Disaster Recovery

### Backup Strategy

**Tier 1: Cache File** (hourly)
```bash
#!/bin/bash
# backup-cache.sh
CACHE_FILE=/var/cache/caterva/cache.json
BACKUP_DIR=/backups/caterva

cp $CACHE_FILE $BACKUP_DIR/cache-$(date +%s).json

# Keep only last 7 days
find $BACKUP_DIR -name "cache-*.json" -mtime +7 -delete
```

**Tier 2: Database** (daily)
```bash
#!/bin/bash
# backup-db.sh
BACKUP_DIR=/backups/caterva

pg_dump -U caterva caterva > \
    $BACKUP_DIR/db-$(date +%Y%m%d).sql.gz

# Keep only last 30 days
find $BACKUP_DIR -name "db-*.sql.gz" -mtime +30 -delete
```

**Tier 3: Code** (version control)
```bash
git push origin main  # Automated via CI/CD
```

### Restore Procedure

**Restore from database backup:**
```bash
gunzip < /backups/caterva/db-20260809.sql.gz | \
    psql -U caterva caterva
```

**Restore cache:**
```bash
cp /backups/caterva/cache-1691596800.json \
    /var/cache/caterva/cache.json
```

---

## Scaling Considerations

### Vertical Scaling (Single Server)

Increase resources on existing server:
- CPU: TypeScript is single-threaded; limited by Python
- Memory: Cache stores trajectories; scale to ~2GB for 10k results
- Disk: Log rotation recommended (see below)

**Limits:**
- Python concurrency: MAX_CONCURRENT=2 (GIL limited)
- ~20 queries/sec max throughput

### Horizontal Scaling (Multiple Servers)

> **Proposed — not implemented in this repo yet.** The current job queue (`src/lib/queue.ts`) is in-memory, with a comment in the source acknowledging this directly: "demo guard; a production deployment would use Redis or a database." There is no Redis client, config, or dependency anywhere in this repo (`redis`/`ioredis` are not in any `package.json`), no message broker (Bull/RabbitMQ/SQS), and no load balancer config. The items below are proposals for scaling out, not existing capabilities.

1. **Add shared cache:** Redis
   ```bash
   redis-server --bind 0.0.0.0 --port 6379
   # Would require adding a redis client dependency and rewriting the
   # in-memory cache in src/lib/queue.ts / src/lib/cache to use it —
   # this is a code change, not a config change.
   ```

2. **Add shared database:** PostgreSQL (already scalable, and already a real optional dependency via `DATABASE_URL` / `@workspace/db`)

3. **Add load balancer:** Nginx or AWS ALB (see the "Proposed" Nginx section above)

4. **Add job queue:** Bull, RabbitMQ, or AWS SQS (optional; none currently integrated)

**Result (projected, not measured against a real deployment):** 100+ queries/sec possible

---

## Log Rotation

> **Proposed — not implemented in this repo yet.** There is no logrotate config, `/etc/logrotate.d/caterva` file, or any log-rotation setup anywhere in this repository. The app logs via `pino`/`pino-http` to stdout (see `src/app.ts`, `src/lib/logger`) — it does not write to `/var/log/caterva/*.log` on its own. The config below assumes an operator has separately redirected stdout to that path.

### Logrotate Configuration (proposed)

```bash
# /etc/logrotate.d/caterva
/var/log/caterva/*.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
    create 0640 caterva caterva
    postrotate
        systemctl reload caterva-api > /dev/null 2>&1 || true
    endscript
}
```

### Apply

```bash
sudo logrotate -f /etc/logrotate.d/caterva
```

---

## Security Hardening

### Network Security

```bash
# Firewall: Only allow port 5000 from load balancer
sudo ufw allow from 10.0.1.0/24 to any port 5000

# API key protection
export METRICS_ADMIN_TOKEN=$(openssl rand -base64 32)
```

### Environment Isolation

```bash
# Run as non-root user
sudo useradd -m -s /bin/bash caterva
sudo chown -R caterva:caterva /opt/caterva-api
```

### Secret Management

> **Proposed — not implemented in this repo yet.** There is no AWS Secrets Manager, HashiCorp Vault, or Kubernetes Sealed Secrets integration anywhere in this repository. (`@aws-sdk/*` appears only as a generic "never bundle this if present" entry in `build.mjs`'s esbuild externals list — alongside dozens of unrelated packages like `@azure/*`, `firebase-admin`, and `oracledb` — not as an actual dependency or code path.) Today, secrets are read directly from process env vars / a `.env` file (see `.env.example`). The options below are proposals for a more hardened secret-management setup.

**Use a secrets manager (proposed):**
```bash
# Option 1: AWS Secrets Manager
aws secretsmanager create-secret \
  --name caterva/groq-api-key \
  --secret-string "gsk_..."

# Option 2: HashiCorp Vault
vault kv put secret/caterva groq_api_key="gsk_..."

# Option 3: Sealed Secrets (Kubernetes) — depends on the proposed
# Kubernetes deployment in Option 3 above, which also does not exist yet.
kubectl create secret generic caterva-secrets \
  --from-literal=groq-api-key="gsk_..."
```

---

## Monitoring & Alerts

> **Proposed — not implemented in this repo yet.** There is no Prometheus, Alertmanager, PagerDuty, or Slack integration anywhere in this repository — no alert-rule files, no webhook config, no `PagerDuty`/`pagerduty` or `hooks.slack.com` references outside this doc. This whole section is a proposal for a future alerting setup, contingent on the (also proposed) Prometheus scrape config above actually existing.

### Prometheus Alert Rules (proposed)

```yaml
# alerts.yml
groups:
  - name: caterva
    rules:
      - alert: HighErrorRate
        expr: rate(http_requests_total{status=~"5.."}[5m]) > 0.05
        annotations:
          summary: "High error rate detected"
      
      - alert: QueueBacklog
        expr: queue_depth > 100
        annotations:
          summary: "Queue depth exceeding threshold"
      
      - alert: LowCacheHitRate
        expr: cache_hit_ratio < 0.5
        annotations:
          summary: "Cache hit rate below 50%"
      
      - alert: PythonProcessDown
        expr: up{job="caterva-api"} == 0
        annotations:
          summary: "API process is down"
```

### Alert Channels (proposed)

```yaml
# alertmanager config — proposed, not present in this repo
route:
  receiver: 'default'
  group_wait: 10s
  group_interval: 10s
  repeat_interval: 12h

receivers:
  - name: 'default'
    slack_configs:
      - api_url: 'https://hooks.slack.com/services/YOUR/WEBHOOK/URL'
    pagerduty_configs:
      - service_key: 'YOUR-PAGERDUTY-KEY'
```

---

## Post-Deployment Checklist

- [ ] Server accessible on PORT
- [ ] Health check returns 200 (`GET /api/healthz`)
- [ ] Logs written to stdout (the app logs via pino/pino-http to stdout by default; `journalctl` only applies if you've set up the proposed systemd service above)
- [ ] Metrics endpoints accessible (`GET /api/metrics`, `GET /api/snapshot`, `GET /api/metrics/health`)
- [ ] Database connected (if using)
- [ ] LLM API key working (if using)
- [ ] Cache file being created
- [ ] Rate limiting working (the global 1000-req/15min "limit" in `src/app.ts` is headers-only and never rejects requests; the real, enforced limit is 10 req/60s on `POST /api/simulate` via `src/lib/rateLimit.ts` — neither is configurable without a code change; see Environment Configuration above)
- [ ] HTTPS configured (if public)
- [ ] Backups scheduled
- [ ] Monitoring connected (only applicable if you've built the proposed Prometheus/Grafana setup above)
- [ ] Alerting configured (only applicable if you've built the proposed Alertmanager/PagerDuty/Slack setup above)

---

## Troubleshooting Deployment Issues

### Port Already in Use

```bash
lsof -i :5000
kill -9 <PID>
```

### Python Not Found

```bash
export CATERVA_PYTHON=$(which python3.12)
# Verify:
python3.12 --version
```

### Database Connection Refused

```bash
# Test connection
psql -U caterva -d caterva -c "SELECT 1"

# Check PostgreSQL is running
sudo systemctl status postgresql
```

### Memory Leak

```bash
# Monitor memory
ps aux | grep node
# If growing, check:
# 1. Cache size (see cache.ts limit)
# 2. Open file descriptors (lsof)
# 3. Memory profiling (node --inspect)
```

### High CPU Usage

```bash
# Check top processes
top -b -n 1 | head -n 15

# Python process running slow?
# Profile with: python -m cProfile
```

---

## Cost Estimation

> **Illustrative / estimated only — not the cost of any real deployed system.** Nothing in this repository is currently deployed to AWS, GCP, or any cloud provider (there is no Terraform/CloudFormation/Pulumi config, no GKE/EKS setup, no AWS resource definitions). The figures below are rough, unverified public-pricing estimates for the hypothetical deployment options described above (several of which — Kubernetes, multi-server AWS — are themselves proposed/not-implemented per the sections above), not measured costs of anything running today.

### Single Server

| Component | Est. Cost/Month |
|-----------|-----------------|
| VM (2 CPU, 4GB RAM) | $30–50 |
| PostgreSQL | $15–30 |
| Storage (100GB) | $5–10 |
| Bandwidth | $5–20 |
| **Total** | **$55–110** |

### Multi-Server (AWS)

| Component | Est. Cost/Month |
|-----------|-----------------|
| EC2 (3x t3.medium) | $90–120 |
| RDS PostgreSQL | $50–100 |
| ALB | $20 |
| CloudWatch | $10–20 |
| Storage (S3 backups) | $5–10 |
| **Total** | **$175–270** |

### Kubernetes (GKE/EKS)

| Component | Est. Cost/Month |
|-----------|-----------------|
| Managed K8s | $30–75 |
| Node pool (3x) | $60–120 |
| Managed PostgreSQL | $50–100 |
| Load balancer | $20 |
| Storage | $10–20 |
| **Total** | **$170–335** |

---

## References

- Environment setup: See `.env.example` (in this directory)
- Docker: the repo's root `Dockerfile` builds a Python/Caterva sandbox & CI-parity image — it is not a Docker build for this API server. See "Option 2: Docker Container" above for a proposed (not implemented) Node/pnpm Dockerfile for the API server itself.
- Database schema: See `Science-Agent-Pipeline/lib/db/src/schema/`
- Monitoring: `PERFORMANCE_GUIDE.md`
- Architecture: `BACKEND_ARCHITECTURE.md`

---

**Ready to deploy?** Follow the checklist above, review logs for errors, and monitor the health endpoint.

**Questions?** See DEVELOPER_QUICK_START.md or BACKEND_ARCHITECTURE.md.
