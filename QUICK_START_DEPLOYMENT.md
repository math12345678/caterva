> **Note (2026-08-11):** the Local Development and Docker (single container) sections were verified accurate — `npm run web:start` is a real script (`package.json`), and `docker-compose.yml`/`Dockerfile` genuinely exist and match this doc's commands. The Kubernetes section below is aspirational: it's an inline `kubectl apply` heredoc with no backing manifest file in the repo, and there's no cluster config anywhere to apply it to.

# 🚀 Quick Start Deployment Guide

**Get Terrium running in 5 minutes**

---

## Local Development

### Easiest Way (5 seconds)
```bash
cd /Users/smyan/Desktop/Coding/Terrium
npm run web:start
```

Then visit **http://localhost:3000**

### With Docker Compose

```bash
# Build and start
docker-compose up -d

# View logs
docker-compose logs -f terrium

# Stop
docker-compose down
```

---

## Production Deployment

### Docker (Single Container)

```bash
# Build image
docker build -t terrium:latest .

# Run container
docker run -d \
  --name terrium \
  -p 3000:3000 \
  -v terrium-data:/app/data \
  --restart unless-stopped \
  terrium:latest

# Check status
docker logs terrium
curl http://localhost:3000/api/health
```

### Kubernetes

```bash
# Create namespace
kubectl create namespace terrium

# Create secret for environment
kubectl create secret generic terrium-env \
  --from-literal=NODE_ENV=production \
  -n terrium

# Deploy
kubectl apply -f - <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: terrium
  namespace: terrium
spec:
  replicas: 3
  selector:
    matchLabels:
      app: terrium
  template:
    metadata:
      labels:
        app: terrium
    spec:
      containers:
      - name: terrium
        image: terrium:latest
        ports:
        - containerPort: 3000
        env:
        - name: NODE_ENV
          value: "production"
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "1Gi"
            cpu: "1000m"
        livenessProbe:
          httpGet:
            path: /api/health
            port: 3000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /api/health
            port: 3000
          initialDelaySeconds: 10
          periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: terrium
  namespace: terrium
spec:
  selector:
    app: terrium
  ports:
  - protocol: TCP
    port: 80
    targetPort: 3000
  type: LoadBalancer
EOF

# Verify
kubectl get pods -n terrium
kubectl port-forward -n terrium svc/terrium 3000:80
```

### Cloud Platforms

#### AWS (EC2)
```bash
# Launch instance
aws ec2 run-instances \
  --image-id ami-0c55b159cbfafe1f0 \
  --instance-type t3.medium \
  --key-name your-key \
  --security-groups default

# SSH in and install
ssh ec2-user@instance
curl -fsSL https://nodejs.org/dist/v22.0.0/node-v22.0.0-linux-x64.tar.xz | tar xJ
export PATH=$PWD/node-v22.0.0-linux-x64/bin:$PATH

# Clone and run
git clone <repo>
cd Terrium
npm install
npm run build
npm run web:start &
```

#### Heroku
```bash
# Login
heroku login

# Create app
heroku create terrium-app

# Deploy
git push heroku main

# View logs
heroku logs --tail
```

#### Google Cloud Run
```bash
# Build and push image
gcloud builds submit --tag gcr.io/PROJECT/terrium

# Deploy
gcloud run deploy terrium \
  --image gcr.io/PROJECT/terrium \
  --platform managed \
  --port 3000 \
  --memory 512Mi \
  --timeout 3600

# Get URL
gcloud run describe terrium --platform managed
```

---

## Using the API

### Python Integration

```bash
# Install dependencies
pip install requests

# Run examples
python examples/python_integration.py
```

**Quick usage:**
```python
from examples.python_integration import TerriumClient

client = TerriumClient()

# Run simulation
job_id = client.simulate(
    query='michaelis-menten',
    parameters={'km': 5.2, 'vmax': 12.8, 's0': 10}
)

# Wait for results
job = client.wait_for_job(job_id)
print(f"Result: {job['result']['finalValue']}")

# Export data
csv = client.export_jobs_csv()
```

### Node.js Integration

```bash
# Run examples
node examples/nodejs_integration.js
```

**Quick usage:**
```javascript
const TerriumClient = require('./examples/nodejs_integration');

const client = new TerriumClient();

// Run simulation
const jobId = await client.simulate(
  'michaelis-menten',
  { km: 5.2, vmax: 12.8, s0: 10 }
);

// Get results
const job = await client.waitForJob(jobId);
console.log(`Result: ${job.result.finalValue}`);
```

### cURL

```bash
# Single simulation
curl -X POST http://localhost:3000/api/simulate \
  -H "Content-Type: application/json" \
  -d '{
    "query": "michaelis-menten",
    "parameters": {"km": 5.2, "vmax": 12.8, "s0": 10}
  }'

# Parameter sweep
curl -X POST http://localhost:3000/api/sweep \
  -H "Content-Type: application/json" \
  -d '{
    "query": "michaelis-menten",
    "baseParameters": {"vmax": 12.8, "s0": 10},
    "sweepParameters": [{"name": "km", "spec": "1:10:0.5"}]
  }'

# Batch processing
curl -X POST http://localhost:3000/api/batch \
  -H "Content-Type: application/json" \
  -d '{
    "query": "michaelis-menten",
    "parameterSets": [
      {"km": 1, "vmax": 10},
      {"km": 2, "vmax": 12},
      {"km": 3, "vmax": 14}
    ],
    "concurrency": 3
  }'

# Query jobs
curl "http://localhost:3000/api/jobs/query?status=complete&minConfidence=0.9"

# Export CSV
curl http://localhost:3000/api/export/jobs/csv > jobs.csv

# System health
curl http://localhost:3000/api/health
```

---

## Monitoring & Operations

### Health Check

```bash
# Check system status
curl http://localhost:3000/api/health

# Response:
{
  "status": "ok",
  "uptime": 123.45,
  "jobs": { "total": 42, "running": 2, "completed": 40, "failed": 0 },
  "sweeps": { "total": 5, "completed": 5 },
  "batches": { "total": 3, "completed": 3 }
}
```

### Statistics

```bash
# Get system statistics
curl http://localhost:3000/api/stats

# Response:
{
  "totalJobs": 150,
  "successful": 145,
  "failed": 5,
  "averageExecutionTimeMs": 78,
  "queryCounts": {
    "michaelis-menten": 100,
    "competitive-inhibition": 30,
    "non-competitive-inhibition": 15,
    "product-inhibition": 5
  }
}
```

### Logs

```bash
# Docker logs
docker logs terrium

# Kubernetes logs
kubectl logs -n terrium -l app=terrium -f

# Follow live
docker-compose logs -f terrium
```

---

## Scaling

### Horizontal Scaling (Multiple Instances)

```bash
# Start multiple instances
docker run -d --name terrium1 -p 3000:3000 terrium:latest
docker run -d --name terrium2 -p 3001:3000 terrium:latest
docker run -d --name terrium3 -p 3002:3000 terrium:latest

# Use load balancer (nginx)
# See DEPLOYMENT_AND_OPS.md for nginx config
```

### Vertical Scaling (Bigger Machine)

```bash
# Allocate more resources in docker-compose.yml
# or Kubernetes resource requests/limits
```

---

## Persistence & Backups

### Job Data

Jobs are saved to `terrium-jobs.jsonl`. This file:
- Persists across restarts
- Grows ~1KB per job
- Should be backed up regularly

```bash
# Backup
cp terrium-jobs.jsonl terrium-jobs.jsonl.backup.$(date +%Y%m%d)

# Or with Docker:
docker cp terrium:/app/data/terrium-jobs.jsonl ./backup/
```

### Upgrade Path to Database

To upgrade from file storage to PostgreSQL:

```bash
# 1. Add postgres service to docker-compose.yml
# (See docker-compose.yml for example)

# 2. Start postgres
docker-compose up -d postgres

# 3. Run migration (future feature)
# npm run migrate:file-to-postgres

# 4. Restart terrium
docker-compose restart terrium
```

---

## Troubleshooting

### Port Already in Use
```bash
# Find what's using port 3000
lsof -i :3000

# Use different port
PORT=3001 npm run web:start
```

### High Memory Usage
```bash
# Reduce job retention
# Edit src/storage/job-database.ts:
# clearOldJobs(days: 30)  # Keep last 30 days only

# Rebuild and restart
npm run build
npm run web:start
```

### Jobs Not Persisting
```bash
# Check file permissions
ls -la terrium-jobs.jsonl

# Check disk space
df -h

# Verify path in logs
docker logs terrium | grep -i "database\|storage"
```

---

## Next Steps

1. **Read the docs:** See `START_HERE.md` for complete feature overview
2. **Try the dashboard:** Visit http://localhost:3000
3. **Explore the API:** See `API_QUICK_REFERENCE.md`
4. **Integrate with Python/Node.js:** See examples/ directory
5. **Deploy to production:** Follow cloud platform guide above

---

**Questions? See the comprehensive guides:**
- `START_HERE.md` — Feature overview
- `VERIFIED_SYSTEM_STATUS.md` — All 19 endpoints
- `EXPORT_AND_ANALYSIS_GUIDE.md` — Data export and analysis
- `DEPLOYMENT_AND_OPS.md` — Production operations

🚀 **Ready to go. Start with local, scale with Docker, deploy to cloud.**
