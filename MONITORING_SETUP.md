# Monitoring Setup Guide: Prometheus + Grafana

> **⚠️ CORRECTION (2026-08-12):** The "Metrics Reference" section below ("All metrics exposed at `/metrics`") lists `caterva_success_rate`, `caterva_execution_time_avg_ms`/`median_ms`/`min_ms`/`max_ms`/`stddev_ms`, `caterva_convergence_steps_avg`, `caterva_model_execution_time_avg_ms`, `caterva_model_convergence_steps_avg`, and `caterva_execution_time_percentile_ms{...}` as if unconditionally present. In the real `src/web/metrics-exporter.ts`, each of these is **omitted from the output** (not printed as `0`) whenever the underlying value has no data to report -- a fresh server (zero jobs), or a specific model where every recorded job failed. Before this session, six of these eight gauges (`caterva_success_rate` and `caterva_execution_time_percentile_ms` were already correct) instead printed a fabricated `0`, which would have shown as real 0ms/0-step measurements on the "Average Execution Time" and "Execution Time Distribution" Grafana panels below for a server with zero traffic. Fixed this session (`src/web/metrics-exporter.ts`); reproduced the before/after output directly by calling `generatePrometheusMetrics()` with an empty metrics collector.

Complete monitoring stack for Caterva with real-time dashboards, alerts, and metrics.

---

## Quick Start (5 minutes)

### 1. Start the Full Stack

```bash
docker-compose -f docker-compose-monitoring.yml up -d
```

This starts:
- **Caterva** at `http://localhost:3000`
- **Prometheus** at `http://localhost:9090`
- **Grafana** at `http://localhost:3001`

### 2. Access Grafana

```bash
open http://localhost:3001
# Username: admin
# Password: admin
```

### 3. View Dashboard

- Click **Dashboards** → **Caterva Performance Monitoring**
- Graphs update every 30 seconds

### 4. Stop Everything

```bash
docker-compose -f docker-compose-monitoring.yml down
```

---

## Architecture

```
Caterva (Port 3000)
    ↓ exposes /metrics in Prometheus format
Prometheus (Port 9090)
    ↓ scrapes every 15 seconds, stores time-series data
Grafana (Port 3001)
    ↓ queries Prometheus, renders dashboards
Browser
```

---

## What's Being Monitored

### System Metrics
- Total jobs (count)
- Successful jobs (count)
- Failed jobs (count)
- Success rate (%)

### Performance Metrics
- Average execution time (ms)
- Median execution time (ms)
- Min/max execution time (ms)
- Standard deviation (consistency)

### Model Metrics (per kinetic model)
- Jobs by model
- Execution time by model
- Success rate by model
- Convergence steps by model

### SLA Metrics
- p50, p75, p90, p95, p99 execution times
- Slow queries count (> 1s)
- Failed queries count

---

## Grafana Dashboard Panels

The imported dashboard includes:

| Panel | What it shows |
|-------|---------------|
| Average Execution Time | Trend of simulation speed over time |
| Success Rate | % of successful simulations (gauge) |
| Execution Time Distribution | Min/median/max comparison |
| Jobs by Model | Stacked bar chart of all models |
| Execution Time by Model | Performance comparison across models |
| Execution Time Percentiles | P50, P75, P90, P95, P99 trends |
| Slow Queries | Count of queries > 1s |
| Failed Queries | Count of failed simulations |
| Total Jobs | Overall job count (gauge) |

---

## Prometheus Alerts

Alerts are triggered when:

### Warning Level
- ✠ Success rate drops below 90%
- ✠ Average execution time exceeds 1 second
- ✠ More than 20 slow queries
- ✠ More than 10 failed queries
- ✠ A model's success rate drops below 85%

### Critical Level
- ✘ Success rate drops below 75%

### Info Level
- ℹ High performance variance detected (stdDev > 50% of mean)
- ℹ Median execution time exceeds 500ms

---

## Accessing Metrics Endpoints

### Prometheus Text Format

```bash
# Scraped by Prometheus every 15 seconds
curl http://localhost:3000/metrics
```

Output format:
```
# HELP caterva_jobs_total Total number of jobs
# TYPE caterva_jobs_total gauge
caterva_jobs_total 150 1628000000000

# HELP caterva_success_rate Success rate percentage
# TYPE caterva_success_rate gauge
caterva_success_rate 96.67 1628000000000
```

### JSON Format

```bash
# Query through Prometheus HTTP API
curl http://localhost:9090/api/v1/query?query=caterva_success_rate

# Or directly from Caterva API
curl http://localhost:3000/api/metrics
```

---

## Common Tasks

### View Real-time Metrics

```bash
# Prometheus UI - raw queries
open http://localhost:9090

# Query a metric
Query: caterva_success_rate
Graph: Shows live value
```

### Check Alert Status

```bash
# Prometheus alerts page
open http://localhost:9090/alerts

# Shows which alerts are firing
```

### Export Metrics

```bash
# Download raw metrics as CSV/JSON
# Through Grafana export button on any panel

# Or query Prometheus API
curl 'http://localhost:9090/api/v1/query_range?query=caterva_success_rate&start=START&end=END&step=60s'
```

### Debug Scraping Issues

```bash
# Check if Prometheus can reach Caterva
curl http://caterva:3000/metrics

# View scrape status in Prometheus
open http://localhost:9090/targets

# Should show "caterva" job as UP (green)
```

---

## Configuration Files

### prometheus.yml
- **What:** Tells Prometheus where to scrape metrics
- **Edit:** Add more scrape targets here
- **Location:** `/prometheus.yml`

### prometheus-rules.yml
- **What:** Alert rules (thresholds, durations, notifications)
- **Edit:** Customize alert conditions here
- **Location:** `/prometheus-rules.yml`

### grafana-dashboard.json
- **What:** Dashboard layout and panels
- **Edit:** Customize visualization here (or in Grafana UI)
- **Location:** `/grafana-dashboard.json`

### docker-compose-monitoring.yml
- **What:** Container configuration and networking
- **Edit:** Add more services, change ports, adjust resources
- **Location:** `/docker-compose-monitoring.yml`

---

## Advanced Usage

### Add Custom Alert Notification

Edit `prometheus-rules.yml`:

```yaml
- alert: CustomAlert
  expr: caterva_execution_time_avg_ms > 2000
  for: 5m
  labels:
    severity: warning
    team: research
  annotations:
    summary: "Very slow execution detected"
```

### Add New Grafana Panel

1. In Grafana: **+** → **Create** → **Graph**
2. Data source: `Prometheus`
3. Metrics: `caterva_*`
4. Customize visualization
5. Save to dashboard

### Export Grafana Dashboard

1. Click dashboard title
2. → **Share** → **Export as JSON**
3. Save to file
4. Share with team

### Query Prometheus Programmatically

```python
import requests

# Query current value
response = requests.get('http://localhost:9090/api/v1/query', 
  params={'query': 'caterva_success_rate'})
data = response.json()
print(data['data']['result'][0]['value'])

# Query time range
response = requests.get('http://localhost:9090/api/v1/query_range',
  params={
    'query': 'caterva_success_rate',
    'start': '1640000000',
    'end': '1640086400',
    'step': '300'
  })
```

### Set Up Slack Alerts

1. Create Slack webhook
2. Add Alertmanager config:

```yaml
# alertmanager.yml
global:
  resolve_timeout: 5m

route:
  receiver: 'slack'

receivers:
  - name: 'slack'
    slack_configs:
      - api_url: 'YOUR_SLACK_WEBHOOK_URL'
        channel: '#alerts'
```

3. Mount in docker-compose and enable

---

## Troubleshooting

### Prometheus says "DOWN" for caterva

```bash
# Check if Caterva is running
docker ps | grep caterva

# Check if /metrics endpoint works
curl http://localhost:3000/metrics

# Check Prometheus logs
docker logs caterva
```

### No data in Grafana

```bash
# Wait 30 seconds (dashboard refresh interval)
# Then refresh browser

# Check if Prometheus has scraped data
curl http://localhost:9090/api/v1/query?query=caterva_jobs_total

# If empty, Prometheus hasn't scraped yet (wait 15s for scrape interval)
```

### Grafana can't connect to Prometheus

```bash
# Check if Prometheus container is running
docker ps | grep prometheus

# Check docker network
docker network inspect docker_default

# Both should be on same network
```

### High memory usage

```bash
# Prometheus stores ~2GB per year of metrics
# Reduce retention in prometheus.yml:
# Add: --storage.tsdb.retention.time=7d

# Or clean up old data:
curl -X POST http://localhost:9090/api/v1/admin/tsdb/clean_tombstones
```

---

## Production Setup

For production deployments:

### 1. Use External Prometheus
- Don't run in Docker
- Use managed service (AWS, Grafana Cloud, etc.)
- Better performance and uptime

### 2. Configure Backups
```bash
# Backup Prometheus data
tar -czf prometheus-backup-$(date +%s).tar.gz prometheus_data/

# Backup Grafana dashboards
docker exec grafana grafana-cli admin export-dashboard > dashboard-backup.json
```

### 3. Set Up Alerting
- Configure Alertmanager
- Add Slack/PagerDuty/email webhooks
- Test alerts work

### 4. Enable Authentication
- Change Grafana password (beyond default)
- Use network policies
- Put behind reverse proxy (nginx)

### 5. Monitor the Monitor
- Set up monitoring for Prometheus itself
- Alert if Prometheus goes down
- Alert if scraping fails

---

## Grafana Features

### Annotations
```
Click on graph → Add annotation
Save notes about deployments, incidents, changes
Appears as vertical line on all panels
```

### Dashboard Variables
```
Settings → Variables → Add variable
Create dropdowns for filtering
Example: ${model} to filter by kinetic model
```

### Export/Share
```
Share button → Export JSON
Share dashboard links
Make read-only or edit links
```

### Alerts in Grafana
```
Panel → Alert tab
Set threshold conditions
Trigger notifications
```

---

## Metrics Reference

All metrics exposed at `/metrics`:

```
caterva_jobs_total                           # Total jobs
caterva_jobs_successful                      # Successful jobs
caterva_jobs_failed                          # Failed jobs
caterva_success_rate                         # Success % (0-100)
caterva_execution_time_avg_ms                # Average time
caterva_execution_time_median_ms             # Median time
caterva_execution_time_min_ms                # Min time
caterva_execution_time_max_ms                # Max time
caterva_execution_time_stddev_ms             # Standard deviation
caterva_convergence_steps_avg                # Avg convergence
caterva_model_jobs_total{model="..."}        # Jobs per model
caterva_model_execution_time_avg_ms{...}     # Time per model
caterva_model_success_rate{model="..."}      # Rate per model
caterva_model_convergence_steps_avg{...}     # Convergence per model
caterva_execution_time_percentile_ms{...}    # P50, P75, P90, P95, P99
caterva_slow_queries_total                   # Slow queries (>1s)
caterva_failed_queries_total                 # Failed queries
```

---

## Next Steps

1. ✅ Run docker-compose setup
2. ✅ Access Grafana dashboard
3. ✅ Run some simulations
4. ✅ Watch metrics populate
5. → Customize alerts/thresholds
6. → Integrate with team alerting
7. → Add more panels/visualizations
8. → Export metrics to BI tools

---

## Getting Help

- **Prometheus docs:** https://prometheus.io/docs/
- **Grafana docs:** https://grafana.com/docs/
- **Docker Compose:** https://docs.docker.com/compose/
- **Caterva API:** See `/OPENAPI_GUIDE.md`

---

**Status:** ✅ Ready to monitor  
**Uptime target:** 99.9% (Prometheus + Grafana should stay up)  
**Data retention:** 30 days (configurable)  
**Alert response:** Real-time
