# Operations Runbook

**For:** On-call operators, SREs  
**Status:** August 2026  
**Response Time:** P1 incidents ≤15 min, P2 ≤1 hour, P3 ≤24 hours

---

> **Note on infrastructure assumptions in this runbook.** This runbook was written assuming a systemd-managed deployment (`systemctl`/`journalctl` against a `caterva-api` service) and PagerDuty/Slack alerting. **None of that exists in this repository** — there is no systemd unit file, install script, or `caterva-api` service reference anywhere in the codebase, and no PagerDuty/Slack integration or webhook config either. Treat every `systemctl`/`journalctl -u caterva-api` command below as a **proposed** convention for operators who choose to run the built server under systemd, not as something this repo ships or configures today. If you're running the server directly (`pnpm run start`) or under Docker, substitute your process manager's equivalent commands (e.g. `docker logs`, `docker restart`, or your own process supervisor). Endpoint paths below have been corrected to match the real router in `src/app.ts` (`app.use("/api", router)`), where `/healthz` is mounted at `/api/healthz`, not `/healthz`.

---

## Incident Severity Levels

| Level | Impact | Response |
|-------|--------|----------|
| **P1 (Critical)** | Service down, all users affected | Page on-call, respond <5 min |
| **P2 (High)** | Partial degradation, some users affected | Respond <15 min |
| **P3 (Medium)** | Non-critical feature broken, workaround exists | Respond <1 hour |
| **P4 (Low)** | Minor issue, cosmetic, no workaround needed | Address during business hours |

---

## Quick Diagnostics

### Step 1: Check If Service Is Running

```bash
curl http://localhost:5000/api/healthz
# Expected: {"status":"ok"}
```

**If timeout or refused:**
- Service is down → Go to "Service Down" section


**If 5xx error:**
- Service is running but unhealthy → Check logs

### Step 2: Check Logs

```bash
# systemd
sudo journalctl -u caterva-api -n 50 -f

# Docker
docker logs -f caterva-api --tail 50

# File logs
tail -f /var/log/caterva/app.log
```

**Look for:**
- Error messages (ERROR in logs)
- Stack traces (thrown exceptions)
- Connection errors (DATABASE, LLM, Python)
- Resource exhaustion (OOM, CPU maxed)

### Step 3: Check Resource Usage

```bash
# CPU & Memory (real entry point is dist/index.mjs, see package.json "start" script)
ps aux | grep "node dist/index.mjs"

# Disk space
df -h

# Network connections
netstat -an | grep ESTABLISHED | grep 5000 | wc -l
```

---

## Common Incidents & Fixes

### Incident: "Service Slow" (P2)

**Symptoms:**
- Requests taking >2 seconds
- Queue depth increasing
- CPU/memory normal

**Diagnosis:**
```bash
# Check queue
curl http://localhost:5000/api/simulate | jq '.[] | .status' | sort | uniq -c

# Check LLM/resolution latency — there is no `.llmLatency` field anywhere
# in the real responses. The closest real signal is the "Parameter
# Resolution" stage duration (which includes LLM calls) from the detailed
# snapshot endpoint (src/routes/metrics.ts, real path /api/snapshot):
curl http://localhost:5000/api/snapshot | \
  jq '.data.stages[] | select(.name == "Parameter Resolution")'
```

**Probable Causes & Fixes:**

1. **LLM API is slow**
   - Wait (temporary) or
   - Disable LLM: remove GROQ_API_KEY from .env, restart
   - Fall back to keyword resolution (~10ms instead of 500ms)

2. **Python simulation queue backed up**
   - Check job queue: `curl http://localhost:5000/api/simulate`
   - MAX_CONCURRENT=2 is limiting throughput
   - This is expected under load
   - Scale horizontally (add more instances)

3. **Database queries slow**
   - Check PostgreSQL: `ps aux | grep postgres`
   - Run: `SELECT query, count FROM pg_stat_statements ORDER BY mean_time DESC LIMIT 5;`
   - Add index if cache lookup slow (see DEPLOYMENT_GUIDE.md)

**Mitigation:**
```bash
# Restart service (clears in-memory state)
sudo systemctl restart caterva-api

# Or scale horizontally
docker run -d --name caterva-api-2 -p 5001:5000 ... caterva-api
```

---

### Incident: "Service Down" (P1)

**Symptoms:**
- `curl http://localhost:5000/api/healthz` → Connection refused
- `systemctl status caterva-api` → Inactive (dead) — assumes the proposed systemd setup; substitute your process manager's status command otherwise

**Immediate Actions:**
```bash
# 1. Restart
sudo systemctl restart caterva-api

# 2. Check if it stays up
sleep 5 && systemctl status caterva-api

# 3. Verify health
curl http://localhost:5000/api/healthz
```

**If still down, check logs:**
```bash
sudo journalctl -u caterva-api -n 100
```

**Common Root Causes:**

1. **Port in use**
   ```bash
   lsof -i :5000
   kill -9 <PID>
   sudo systemctl restart caterva-api
   ```

2. **Python not found**
   ```bash
   # Check if Python exists
   which python3.12
   # or
   ls -la /usr/bin/python3*
   
   # Fix: update CATERVA_PYTHON in .env
   export CATERVA_PYTHON=/usr/bin/python3.12
   sudo systemctl restart caterva-api
   ```

3. **Out of memory (OOM)**
   ```bash
   dmesg | tail -20 | grep -i "killed"
   # Shows if kernel killed the process
   
   # Fix: restart to clear memory
   sudo systemctl restart caterva-api
   
   # Monitor going forward
   while true; do
     free -h | grep Mem
     sleep 5
   done
   ```

4. **Database connection refused**
   ```bash
   # Check if DB is running
   sudo systemctl status postgresql
   
   # Test connection
   psql -U caterva -d caterva -c "SELECT 1"
   
   # If not running: start it
   sudo systemctl start postgresql
   
   # Then restart API
   sudo systemctl restart caterva-api
   ```

5. **Corrupted cache file**
   ```bash
   # Check cache file
   cat /var/cache/caterva/cache.json | jq . > /dev/null
   # If parse error:
   
   # Backup and remove
   mv /var/cache/caterva/cache.json /tmp/cache-corrupt.json
   
   # Restart (will create new cache)
   sudo systemctl restart caterva-api
   ```

---

### Incident: "High Error Rate" (P2)

**Symptoms:**
- Error rate >1% (normally <0.1%)
- Elevated `failedSimulations` in `curl http://localhost:5000/api/metrics`, or elevated `failureCount` per stage in `curl http://localhost:5000/api/snapshot`

**Diagnosis:**
```bash
# Check error types — note: there is no `.errorsByType` field in any real
# response. Job-level failure counts are in `failedSimulations`
# (GET /api/metrics) and per-stage failure counts are in
# `data.stages[].failureCount` (GET /api/snapshot). For actual error
# messages/types you need to grep the logs (see below), not the metrics API.
curl http://localhost:5000/api/snapshot | jq '.data.stages'

# Sample errors from logs
sudo journalctl -u caterva-api -n 50 | grep ERROR
```

**Common Errors & Fixes:**

| Error | Cause | Fix |
|-------|-------|-----|
| `MISSING_REQUIRED_INPUT` | User didn't provide parameters | User education, improve defaults |
| `PIPELINE_ERROR` | Engine failure | Check Python logs, restart Python |
| *(no distinct error code)* | DB connection failed | There is no `DATABASE_ERROR` code in the source — DB unavailability is handled silently: the service falls back to in-memory/file storage rather than surfacing a request-level error (see "Fallback Mode" below and `isDbAvailable()` used in `src/routes/pipeline.ts`). Check PostgreSQL and restart it if persistence is expected. |
| `INTERNAL_SERVER_ERROR` | Unexpected exception | Check logs for stack trace, report bug |
| `TOO_MANY_REQUESTS` (HTTP 429) | Too many `POST /api/simulate` requests — the only endpoint with real, enforced rate limiting (hardcoded 10 req/60s via `src/lib/rateLimit.ts`; the global per-app limit in `src/app.ts` is headers-only and never actually rejects requests) | Inform user; changing the limit requires editing `rateLimit.ts` and redeploying, it is not env-configurable |

**Recovery:**
```bash
# Most errors are user-caused, not service-caused
# Service should auto-recover

# If errors persist:
sudo systemctl restart caterva-api
```

---

### Incident: "High Memory Usage" (P2)

**Symptoms:**
- `free -h` shows <500MB available
- `ps aux | grep node` shows memory climbing
- Service becomes slow then crashes

**Diagnosis:**
```bash
# Check memory over time
for i in {1..10}; do
  date
  ps aux | grep "node dist" | grep -v grep | awk '{print $6 " KB"}'
  sleep 10
done

# Check cache size
ls -lh /var/cache/caterva/cache.json
```

**Probable Causes:**

1. **Cache growing too large**
   - Cache is append-only; trajectories accumulate
   - MAX_JOBS=1000 is the in-memory limit
   - But disk cache file keeps growing

   **Fix:**
   ```bash
   # Rotate/archive cache
   mv /var/cache/caterva/cache.json \
      /backups/cache-$(date +%Y%m%d).json
   # Restart to create fresh cache
   sudo systemctl restart caterva-api
   ```

2. **Trajectory data is huge**
   - Some domains (Gillespie with 10k steps) create big trajectories
   - Each stored in memory

   **Fix:**
   ```bash
   # Monitor cache size
   du -sh /var/cache/caterva/cache.json
   
   # If >100MB, rotate it
   ```

3. **Job listeners not being cleaned up**
   - Implies a code bug (should not happen)

   **Fix:**
   ```bash
   # Restart (clears in-memory state)
   sudo systemctl restart caterva-api
   
   # Report to dev team
   ```

**Prevention:**
```bash
# Monitor in production
watch -n 5 'free -h && ps aux | grep node'

# Set up alerts (see DEPLOYMENT_GUIDE.md)
```

---

### Incident: "Database Connection Failed" (P2)

**Symptoms:**
- Logs show `connect ECONNREFUSED 127.0.0.1:5432`
- Health check passes (no DB required)
- But data not persisting to database

**Diagnosis:**
```bash
# Test PostgreSQL
psql -U caterva -d caterva -c "SELECT 1"

# If connection refused:
sudo systemctl status postgresql

# Check PostgreSQL logs
sudo tail -f /var/log/postgresql/postgresql-*.log
```

**Fixes:**

1. **PostgreSQL not running**
   ```bash
   sudo systemctl start postgresql
   sudo systemctl status postgresql
   sudo systemctl restart caterva-api
   ```

2. **Connection string wrong**
   ```bash
   # Check .env
   grep DATABASE_URL /opt/caterva-api/.env
   
   # Test manually
   psql $DATABASE_URL -c "SELECT 1"
   
   # If error, fix the URL and restart
   ```

3. **PostgreSQL crashed**
   ```bash
   sudo systemctl status postgresql
   sudo systemctl restart postgresql
   
   # Check for corruption
   sudo -u postgres pg_dumpall > /tmp/backup.sql
   ```

4. **Network issue (if DB on different host)**
   ```bash
   # Test connectivity
   telnet db.example.com 5432
   
   # Check firewall
   sudo ufw allow from this_host to db_host port 5432
   ```

**Fallback Mode:**
- If DATABASE_URL not set or DB unavailable
- System falls back to in-memory + file cache
- Data is still persisted (just not in DB)
- This is expected behavior

---

### Incident: "LLM API Not Responding" (P3)

**Symptoms:**
- Queries taking 30+ seconds (hitting timeout)
- Some queries failing with "LLM timeout"
- Logs show repeated timeouts

**Diagnosis:**
```bash
# Check LLM connectivity
curl https://api.groq.com/status

# Check API key is valid
curl https://api.groq.com/openapi/v1/models \
  -H "Authorization: Bearer $GROQ_API_KEY"
```

**Fixes:**

1. **LLM API is down**
   - This is external; nothing we can do
   - Queries automatically fall back to keyword resolution
   - System continues working (slower)
   - Inform users

2. **API key invalid or expired**
   ```bash
   # Update .env
   export GROQ_API_KEY="new-key"
   sudo systemctl restart caterva-api
   ```

3. **Network connectivity issue**
   ```bash
   # Test from server
   curl https://api.groq.com/status
   
   # If blocked, check firewall
   sudo ufw status
   sudo ufw allow out to any port 443
   ```

**Workaround:**
```bash
# Disable LLM temporarily (remove API key)
# System will use keyword fallback instead
# Queries will be slower but still work
```

---

### Incident: "Python Process Crash" (P1)

**Symptoms:**
- Simulations timeout after waiting indefinitely
- Logs show "Python process exited with code -9" or "-11"
- Process keeps respawning

**Diagnosis:**
```bash
# Check exit codes in logs
sudo journalctl -u caterva-api | grep -i "exit\|signal"

# Check if Python is running
ps aux | grep python3

# Check system logs for crashes
dmesg | tail -20
```

**Probable Causes:**

| Exit Code | Meaning |
|-----------|---------|
| -9 | Killed (OOM or user kill) |
| -11 | Segmentation fault (memory corruption) |
| -15 | SIGTERM (killed gracefully) |
| 1 | Python exception |

**Fixes:**

1. **Out of memory (exit -9)**
   ```bash
   # Check available memory
   free -h
   
   # Reduce cache size
   # Or increase server memory
   
   # Restart
   sudo systemctl restart caterva-api
   ```

2. **Segmentation fault (exit -11)**
   - Likely a bug in Python code
   ```bash
   # Report to dev team with:
   # - Input query that caused crash
   # - Full logs
   # - Python version: python3 --version
   # - Exact domain and parameters
   
   # Workaround: disable that domain
   # Or fallback to keyword resolution only
   ```

3. **Killed by user or OOM killer**
   ```bash
   # See if OOM killer did it
   grep "Out of memory" /var/log/syslog
   
   # Scale up resources or add swap
   sudo fallocate -l 2G /swapfile
   sudo chmod 600 /swapfile
   sudo mkswap /swapfile
   sudo swapon /swapfile
   ```

---

## Maintenance Tasks

### Daily (Automated)

```bash
# Health check (every 5 min) — the systemctl restart line below assumes
# the proposed systemd setup from DEPLOYMENT_GUIDE.md; substitute your
# actual process manager's restart command if you're not using systemd.
curl -s http://localhost:5000/api/healthz || \
  systemctl restart caterva-api

# Log rotation (daily)
/usr/sbin/logrotate /etc/logrotate.d/caterva

# Backup cache (hourly)
0 * * * * /opt/caterva-api/backup-cache.sh
```

### Weekly (Manual)

```bash
# Disk usage review
df -h
du -sh /var/cache/caterva/

# Log review for trends
sudo journalctl -u caterva-api -S "1 week ago" | \
  grep ERROR | wc -l

# Cache rotation if needed
if [ $(du -s /var/cache/caterva/cache.json | cut -f1) -gt 100000 ]; then
  mv /var/cache/caterva/cache.json \
     /backups/cache-$(date +%Y%m%d).json
fi
```

### Monthly (Scheduled)

```bash
# Database maintenance
sudo -u postgres vacuumdb caterva
sudo -u postgres reindexdb caterva

# Backup verification
# Restore latest backup to test DB
# Verify can load and query
```

### Quarterly (Planned)

```bash
# Performance review
# Check if caching strategy is effective
# Monitor LLM vs. keyword resolution ratio
# Review error logs for patterns

# Dependency updates (this is a pnpm workspace — see note at top of this doc)
pnpm audit
pnpm update

# Load testing
# Verify system can handle expected peak load
```

---

## Escalation Procedures

### Tier 1 (On-Call Engineer)

**Responsibilities:**
- Respond to alerts within 5 minutes
- Triage severity
- Apply immediate fixes (restart, failover, rollback)
- Communicate status to stakeholders

**If cannot resolve in 15 minutes → Escalate to Tier 2**

### Tier 2 (Backend Lead)

**Responsibilities:**
- Deep diagnosis (logs, code review, profiling)
- Fix or deploy hotfix
- Post-mortem if incident >1 hour

**If code change needed → Deploy through normal process**

### Tier 3 (Architecture/On-Call)

**Responsibilities:**
- Multi-region issues
- Architecture changes needed
- Major outages

---

## Post-Incident Actions

After resolving any P1 or P2 incident:

1. **Document**
   ```bash
   # Create incident report with:
   # - What happened
   # - Root cause
   # - Resolution taken
   # - Time to resolution
   # - Prevention going forward
   ```

2. **Communicate**
   ```bash
   # Notify stakeholders
   # Post to #incidents channel
   # Include timeline
   ```

3. **Fix Prevention**
   ```bash
   # Add monitoring/alerting for this issue
   # Update runbook if procedure was unclear
   # Create ticket for permanent fix if needed
   ```

4. **Schedule Postmortem**
   ```bash
   # Within 48 hours
   # Team review of what went wrong
   # Action items to prevent recurrence
   ```

---

## On-Call Schedule

### Handoff Procedure

**Outgoing on-call (end of shift):**
1. Update on-call log with summary
2. List any known issues or monitoring
3. Review alert dashboard with incoming
4. Hand off phone/pager

**Incoming on-call (start of shift):**
1. Review on-call log
2. Check alert dashboard
3. Review open incidents
4. Test alert path (call self to verify)

---

## Contact Information

> **Proposed — not implemented in this repo yet.** There is no PagerDuty or Slack integration anywhere in this repository (no webhook config, no `#incidents` reference outside this doc). The fields below are placeholders for a team to fill in if/when such tooling is adopted.

**On-Call Phone:** [Configured in PagerDuty — once PagerDuty is actually set up]

**Slack Channel:** #incidents (proposed — no Slack integration exists in this repo today)

**Escalation:**
- Backend Lead: [Contact info]
- DevOps Lead: [Contact info]
- VP Engineering: [Contact info]

---

## Useful Commands Reference

```bash
# Service management — proposed; assumes the systemd unit from
# DEPLOYMENT_GUIDE.md, which is not installed by anything in this repo.
# If you're not running under systemd, use your process manager's
# equivalents (e.g. `docker start/stop/restart caterva-api`, or `pnpm run start`).
sudo systemctl start caterva-api
sudo systemctl stop caterva-api
sudo systemctl restart caterva-api
sudo systemctl status caterva-api
sudo systemctl enable caterva-api

# Logging — Note: the app itself logs to stdout via pino. Systemd journal
# entries appear only when the app is run under a systemd unit.
sudo journalctl -u caterva-api -f
sudo journalctl -u caterva-api -S "1 hour ago"
sudo journalctl -u caterva-api -u postgresql -f

# Monitoring — real, verified paths (src/app.ts mounts the router at /api;
# src/routes/health.ts, src/routes/pipeline.ts, src/routes/metrics.ts)
curl http://localhost:5000/api/healthz
curl http://localhost:5000/api/metrics
curl http://localhost:5000/api/snapshot
curl http://localhost:5000/api/simulate | jq '.[] | .status'

# Database
psql -U caterva -d caterva -c "SELECT COUNT(*) FROM simulations"
sudo systemctl status postgresql
sudo -u postgres psql caterva

# Performance
ps aux | grep node
top -b -n 1 | head
free -h
df -h
```

---

## References

- **Deployment:** DEPLOYMENT_GUIDE.md
- **Architecture:** BACKEND_ARCHITECTURE.md
- **Performance:** PERFORMANCE_GUIDE.md
- **Development:** DEVELOPER_QUICK_START.md
- **Monitoring:** DEPLOYMENT_GUIDE.md → Monitoring section

---

**Status:** Last updated August 9, 2026  
**Next review:** August 23, 2026  
**Owner:** SRE team
