# Deployment Guide

**For:** Operators deploying Terrium backend  
**Status:** August 2026  
**Audience:** DevOps, SRE, deployment engineers

---

## Deployment Options

### Option 1: Single Server (Development/Small Scale)

**Best for:** <100 queries/day, single team  
**Setup time:** ~15 minutes  
**Maintenance:** Minimal

```bash
# 1. Prerequisites
Node.js 18+
Python 3.10–3.13
npm/pnpm

# 2. Clone and install
git clone <repo>
cd Science-Agent-Pipeline/artifacts/api-server
npm install

# 3. Configure environment
cp .env.example .env
# Edit .env with your values:
# - PORT=5000
# - NODE_ENV=production
# - LOG_LEVEL=info
# - TERRIUM_PYTHON=/usr/bin/python3.12

# 4. Build
npm run build

# 5. Start
npm start
# Or use systemd (see below)
```

### Option 2: Docker Container (Recommended)

**Best for:** <1000 queries/day, staging/production  
**Setup time:** ~30 minutes  
**Maintenance:** Moderate

**Dockerfile:**
```dockerfile
FROM node:18-bullseye

# Install Python
RUN apt-get update && apt-get install -y \
    python3.12 \
    python3.12-venv \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy package files
COPY package.json package-lock.json ./
RUN npm ci --omit=dev

# Copy application
COPY . .

# Build TypeScript
RUN npm run build

# Expose port
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD node -e "require('http').get('http://localhost:5000/healthz', (r) => {if (r.statusCode !== 200) throw new Error(r.statusCode)})"

# Start
CMD ["node", "dist/index.js"]
```

**Build and run:**
```bash
docker build -t terrium-api:latest .

docker run -d \
  --name terrium-api \
  -p 5000:5000 \
  -e PORT=5000 \
  -e NODE_ENV=production \
  -e DATABASE_URL="postgresql://..." \
  -e GROQ_API_KEY="..." \
  terrium-api:latest
```

### Option 3: Kubernetes (Scale)

**Best for:** >1000 queries/day, multi-region  
**Setup time:** ~2 hours  
**Maintenance:** High (but automated)

**k8s Deployment:**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: terrium-api
  labels:
    app: terrium-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: terrium-api
  template:
    metadata:
      labels:
        app: terrium-api
    spec:
      containers:
      - name: api
        image: terrium-api:latest
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
              name: terrium-secrets
              key: database-url
        - name: GROQ_API_KEY
          valueFrom:
            secretKeyRef:
              name: terrium-secrets
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
            path: /healthz
            port: 5000
          initialDelaySeconds: 10
          periodSeconds: 30
        readinessProbe:
          httpGet:
            path: /healthz
            port: 5000
          initialDelaySeconds: 5
          periodSeconds: 10

---
apiVersion: v1
kind: Service
metadata:
  name: terrium-api
spec:
  selector:
    app: terrium-api
  type: LoadBalancer
  ports:
  - protocol: TCP
    port: 80
    targetPort: 5000
```

**Deploy:**
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
TERRIUM_PYTHON=/usr/bin/python3.12 # Python interpreter path
VIRTUAL_ENV=/path/to/venv          # Optional: virtual environment

# Logging
LOG_LEVEL=info                      # trace|debug|info|warn|error

# Data Persistence
CACHE_FILE=./data/cache.json        # In-memory cache file (optional)
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

# LLM timeout (default 30000ms)
LLM_TIMEOUT_MS=30000
```

### Security Variables

```bash
# Rate limiting
RATE_LIMIT=1000                    # Requests per window
RATE_WINDOW_MS=900000              # 15 minutes

# Metrics access
METRICS_ADMIN_TOKEN=your-secret    # Protect /metrics endpoints
```

### Example .env File

```bash
# Server Configuration
PORT=5000
NODE_ENV=production
LOG_LEVEL=info

# Python Bridge
TERRIUM_PYTHON=/usr/bin/python3.12
VIRTUAL_ENV=/opt/terrium-venv

# Persistence (optional)
DATABASE_URL=postgresql://user:password@localhost:5432/terrium
CACHE_FILE=/var/cache/terrium/cache.json

# LLM Configuration (optional - falls back to keywords if not set)
GROQ_API_KEY=gsk_your_key_here
LLM_TIMEOUT_MS=30000

# Security
METRICS_ADMIN_TOKEN=your-secret-admin-token
RATE_LIMIT=1000
RATE_WINDOW_MS=900000
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
  --name terrium-db \
  -e POSTGRES_DB=terrium \
  -e POSTGRES_USER=terrium \
  -e POSTGRES_PASSWORD=secure_password \
  -p 5432:5432 \
  postgres:15-alpine
```

### Create Database & User

```sql
CREATE DATABASE terrium;
CREATE USER terrium WITH PASSWORD 'secure_password';
ALTER ROLE terrium SET client_encoding TO 'utf8';
ALTER ROLE terrium SET default_transaction_isolation TO 'read committed';
ALTER ROLE terrium SET timezone TO 'UTC';
GRANT ALL PRIVILEGES ON DATABASE terrium TO terrium;
```

### Run Migrations

```bash
# If using Drizzle migrations
npm run db:migrate

# Verify
psql -U terrium -d terrium -c "\d"
# Should show: simulations table
```

### Connection String

```
postgresql://terrium:secure_password@localhost:5432/terrium
```

---

## System Service Setup (systemd)

### Service File

```ini
# /etc/systemd/system/terrium-api.service
[Unit]
Description=Terrium Science Agent API
After=network.target

[Service]
Type=simple
User=terrium
WorkingDirectory=/opt/terrium-api
EnvironmentFile=/opt/terrium-api/.env
ExecStart=/usr/bin/node dist/index.js
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
sudo systemctl enable terrium-api
sudo systemctl start terrium-api

# Check status
sudo systemctl status terrium-api

# View logs
sudo journalctl -u terrium-api -f
```

---

## Health Checks & Monitoring

### Built-in Health Endpoint

```bash
curl http://localhost:5000/healthz
# Returns: {"status":"ok"}
```

### Metrics Endpoint

```bash
curl http://localhost:5000/api/metrics \
  -H "Authorization: Bearer your-secret-admin-token"

# Returns detailed metrics
```

### Prometheus Scrape Config

```yaml
# prometheus.yml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'terrium-api'
    static_configs:
      - targets: ['localhost:5000']
    metrics_path: '/api/metrics'
    bearer_token: 'your-secret-admin-token'
```

### Grafana Dashboards

**Key metrics to graph:**
- HTTP request latency (p50, p95, p99)
- Queue depth (active jobs)
- Cache hit rate
- Error rate by type
- Python execution time
- LLM API latency

---

## Load Balancer Setup

### Nginx (Reverse Proxy)

```nginx
upstream terrium_backend {
    server localhost:5000;
    server localhost:5001;
    server localhost:5002;
}

server {
    listen 80;
    server_name api.terrium.example.com;
    
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
        proxy_pass http://terrium_backend;
    }
    
    location /api/metrics {
        auth_request /auth;
        proxy_pass http://terrium_backend;
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
CACHE_FILE=/var/cache/terrium/cache.json
BACKUP_DIR=/backups/terrium

cp $CACHE_FILE $BACKUP_DIR/cache-$(date +%s).json

# Keep only last 7 days
find $BACKUP_DIR -name "cache-*.json" -mtime +7 -delete
```

**Tier 2: Database** (daily)
```bash
#!/bin/bash
# backup-db.sh
BACKUP_DIR=/backups/terrium

pg_dump -U terrium terrium > \
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
gunzip < /backups/terrium/db-20260809.sql.gz | \
    psql -U terrium terrium
```

**Restore cache:**
```bash
cp /backups/terrium/cache-1691596800.json \
    /var/cache/terrium/cache.json
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

1. **Add shared cache:** Redis
   ```bash
   redis-server --bind 0.0.0.0 --port 6379
   # Update app to use Redis instead of file cache
   ```

2. **Add shared database:** PostgreSQL (already scalable)

3. **Add load balancer:** Nginx or AWS ALB

4. **Add job queue:** Bull, RabbitMQ, or AWS SQS (optional)

**Result:** 100+ queries/sec possible

---

## Log Rotation

### Logrotate Configuration

```bash
# /etc/logrotate.d/terrium
/var/log/terrium/*.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
    create 0640 terrium terrium
    postrotate
        systemctl reload terrium-api > /dev/null 2>&1 || true
    endscript
}
```

### Apply

```bash
sudo logrotate -f /etc/logrotate.d/terrium
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
sudo useradd -m -s /bin/bash terrium
sudo chown -R terrium:terrium /opt/terrium-api
```

### Secret Management

**Use a secrets manager:**
```bash
# Option 1: AWS Secrets Manager
aws secretsmanager create-secret \
  --name terrium/groq-api-key \
  --secret-string "gsk_..."

# Option 2: HashiCorp Vault
vault kv put secret/terrium groq_api_key="gsk_..."

# Option 3: Sealed Secrets (Kubernetes)
kubectl create secret generic terrium-secrets \
  --from-literal=groq-api-key="gsk_..."
```

---

## Monitoring & Alerts

### Prometheus Alert Rules

```yaml
# alerts.yml
groups:
  - name: terrium
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
        expr: up{job="terrium-api"} == 0
        annotations:
          summary: "API process is down"
```

### Alert Channels

```yaml
# alertmanager config
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
- [ ] Health check returns 200
- [ ] Logs written to stdout (journalctl)
- [ ] Metrics endpoint accessible
- [ ] Database connected (if using)
- [ ] LLM API key working (if using)
- [ ] Cache file being created
- [ ] Rate limiting working
- [ ] HTTPS configured (if public)
- [ ] Backups scheduled
- [ ] Monitoring connected
- [ ] Alerting configured

---

## Troubleshooting Deployment Issues

### Port Already in Use

```bash
lsof -i :5000
kill -9 <PID>
```

### Python Not Found

```bash
export TERRIUM_PYTHON=$(which python3.12)
# Verify:
python3.12 --version
```

### Database Connection Refused

```bash
# Test connection
psql -U terrium -d terrium -c "SELECT 1"

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

- Environment setup: See `.env.example`
- Docker building: See root Dockerfile
- Database schema: See `lib/db/src/schema/`
- Monitoring: `PERFORMANCE_GUIDE.md`
- Architecture: `BACKEND_ARCHITECTURE.md`

---

**Ready to deploy?** Follow the checklist above, review logs for errors, and monitor the health endpoint.

**Questions?** See DEVELOPER_QUICK_START.md or BACKEND_ARCHITECTURE.md.
