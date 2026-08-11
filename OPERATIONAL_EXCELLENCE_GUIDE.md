# Operational Excellence Guide

> **⚠️ Nothing here is deployed -- read before treating this as real.**
> This describes monitoring, Grafana dashboards, alert routing, on-call
> escalation, and cost breakdowns for an Express HTTP service. No such
> service exists: `src/` (package `terrium-scientific-backend`) is a
> library/CLI with no `express()`/`app.listen()`/`createServer()` anywhere
> (confirmed by grep, 2026-08-10), no Prometheus/Grafana/PagerDuty config
> exists anywhere in this repo, and the repo's only `Dockerfile` builds a
> Python dev/CI sandbox (`CMD ["bash"]`, no `EXPOSE`, no server start) --
> unrelated to deploying this TS tree. There is nothing running to monitor,
> no on-call rotation, and no real cost to report. Kept below as a
> specification for operational work that would be needed if this tree were
> ever exposed as a deployed service, not a description of current state.

## Production Deployment Checklist

### Pre-Deployment (48 hours before)

#### Code Quality
- [ ] All tests passing (`npm test`)
- [ ] Zero TypeScript errors (`npm run type-check`)
- [ ] Linting passes (`npm run lint`)
- [ ] No outstanding security warnings
- [ ] All PRs reviewed and approved
- [ ] CHANGELOG.md updated
- [ ] Version bumped in package.json

#### Testing
- [ ] Unit tests cover >90% critical paths
- [ ] Integration tests pass on staging
- [ ] E2E tests pass on staging
- [ ] Load testing completed
- [ ] Security scanning completed
- [ ] Dependency audit clean

#### Documentation
- [ ] API docs current
- [ ] Runbooks updated
- [ ] Recovery procedures tested
- [ ] Team trained on new features

### Deployment Day

#### Pre-Deployment (2 hours before)
- [ ] Database backups verified
- [ ] Rollback procedure tested
- [ ] Team on standby
- [ ] Monitoring dashboards active
- [ ] Alerts configured
- [ ] Communication channels open (Slack, etc.)

#### During Deployment
- [ ] Deploy to canary environment first
- [ ] Monitor metrics for 15 minutes
- [ ] Verify no errors in canary
- [ ] Deploy to production
- [ ] Monitor error rates
- [ ] Monitor latency
- [ ] Monitor throughput
- [ ] Check logs for warnings

#### Post-Deployment (1 hour after)
- [ ] Verify all endpoints responding
- [ ] Check database health
- [ ] Verify cache operations
- [ ] Confirm no increase in errors
- [ ] Document any issues
- [ ] Update team on status

### Post-Deployment (24 hours)

- [ ] Review metrics over 24-hour period
- [ ] Check for any slow memory leaks
- [ ] Verify background jobs completed
- [ ] Review user feedback
- [ ] Document lessons learned
- [ ] Archive logs

## Monitoring & Observability

### Key Metrics to Track

```typescript
interface ProductionMetrics {
  // Availability
  uptime_percentage: number;           // Target: >99.9%
  error_rate: number;                  // Target: <0.1%
  
  // Performance
  p50_latency_ms: number;              // Target: <200ms
  p95_latency_ms: number;              // Target: <500ms
  p99_latency_ms: number;              // Target: <1000ms
  
  // Capacity
  active_jobs: number;                 // Monitor trending
  queue_depth: number;                 // Alert if >1000
  memory_usage_mb: number;             // Alert if >1000
  
  // Correctness
  cache_hit_rate: number;              // Target: >75%
  parameter_resolution_rate: number;   // Target: >95%
  literature_hit_rate: number;         // Target: >70%
}
```

### Alert Rules

```yaml
alerts:
  - name: HighErrorRate
    condition: error_rate > 1%
    duration: 5m
    action: page_oncall
    
  - name: HighLatency
    condition: p95_latency_ms > 1000
    duration: 10m
    action: page_oncall
    
  - name: HighMemory
    condition: memory_usage_mb > 2000
    duration: 15m
    action: notify_team
    
  - name: QueueBacklog
    condition: queue_depth > 5000
    duration: 5m
    action: page_oncall
    
  - name: CacheMiss
    condition: cache_hit_rate < 50%
    duration: 30m
    action: notify_team
```

### Grafana Dashboard Layout

```
┌─────────────────────────────────────┐
│ Service Health                      │
├──────────────────┬──────────────────┤
│ Error Rate (1h)  │ Uptime (30d)     │
├──────────────────┼──────────────────┤
│ Latency P50/P95  │ Queue Depth      │
├──────────────────┼──────────────────┤
│ Memory Usage     │ Cache Hit Rate   │
├──────────────────┼──────────────────┤
│ CPU Usage        │ Requests/sec     │
├──────────────────┼──────────────────┤
│ Domain Usage     │ Resolution Rate  │
└──────────────────┴──────────────────┘
```

## Incident Response

### P1 (Critical) Response

```
ALERT → notify_oncall immediately
  ↓
CONTEXT: Assess scope
  - What's broken?
  - How many users affected?
  - Business impact?
  ↓
DECISION: Fix or Rollback?
  - Can fix <15 minutes? → Implement fix
  - Otherwise → Rollback
  ↓
ACTION: Fix or Rollback (max 5 minutes)
  ↓
VERIFY: Healthy metrics
  - Error rate normal
  - Latency normal
  - Users can operate
  ↓
COMMUNICATE: Status updates every 5 minutes
  ↓
POST-INCIDENT: Write RCA within 24 hours
```

### Root Cause Analysis (RCA) Template

```markdown
# Incident RCA: [Title]

## Timeline
- HH:MM - Alert fired
- HH:MM - Investigation started
- HH:MM - Root cause identified
- HH:MM - Fix deployed
- HH:MM - Verified healthy

## Impact
- Duration: X minutes
- Users affected: X
- Transactions lost: X
- Revenue impact: $X

## Root Cause
[Describe the underlying cause]

## Contributing Factors
- [Factor 1]
- [Factor 2]

## Detection
- Detection time: X minutes
- Could we have detected earlier? How?

## Resolution
- What was done to fix it?
- Why does this fix work?

## Prevention
1. [Action 1] - Owner: X - By: Date
2. [Action 2] - Owner: X - By: Date

## Process Improvement
- What process failed?
- How do we improve it?
```

## Runbooks

### Runbook: High Error Rate

```
SYMPTOM: Error rate >1% for >5 minutes

INITIAL TRIAGE:
1. Check error type distribution
   - Are all domains affected or specific ones?
   - Are errors in resolution, simulation, or both?

2. Check infrastructure
   - CPU usage normal? (<80%)
   - Memory normal? (<2000MB)
   - Disk space available?
   - Database responsive?

3. Check recent changes
   - Any deployments in last 30 minutes?
   - Any config changes?
   - Any database migrations?

DIAGNOSIS:
Case 1: Errors in specific domain
  → Check DOMAIN_DEFAULTS for that domain
  → Check literature resolver for that domain
  → Review recent changes to resolver
  
Case 2: Errors in Python bridge
  → Check Python process status
  → Review python logs
  → Check Tellurium availability
  
Case 3: Widespread errors
  → Check cache health
  → Check database connections
  → Check LLM provider status
  → Check rate limiter state

RECOVERY:
Option A: Fix the issue
  1. Identify fix
  2. Deploy fix
  3. Monitor error rate
  4. Alert subsides

Option B: Rollback
  1. Verify previous version stable
  2. Revert to previous version
  3. Deploy rollback
  4. Monitor error rate
  5. Investigate issue in dev environment

POST-INCIDENT:
- [ ] Write RCA
- [ ] Implement prevention
- [ ] Update monitoring
- [ ] Test recovery procedure
```

### Runbook: High Memory Usage

```
SYMPTOM: Memory >2000MB for >15 minutes

DIAGNOSIS:
1. Check memory trend
   - Gradual increase? → Memory leak
   - Sudden spike? → Load spike or new job
   
2. Identify high-memory operation
   - Large parameter resolution?
   - Large simulation output?
   - Unbounded cache growth?

3. Check cache state
   - How many entries cached?
   - Cache size distribution?
   - When was cache last reset?

RECOVERY:
Option A: Find root cause
  1. Enable detailed memory profiling
  2. Identify leak source
  3. Deploy fix
  
Option B: Reset cache
  1. Verify cache can be reset safely
  2. Call cache reset endpoint
  3. Monitor memory
  
Option C: Scale up
  1. Increase memory allocation
  2. Monitor for continued growth
  3. Investigate root cause separately

FOLLOW-UP:
- [ ] Identify memory leak source
- [ ] Implement fix or mitigation
- [ ] Add memory limits
- [ ] Improve cache eviction
```

## Scaling Guide

### Horizontal Scaling (Add Instances)

```
When to scale:
- Queue depth > 5000
- Error rate increasing with load
- Latency degrading

Steps:
1. Deploy new instance with same config
2. Update load balancer with new instance
3. Warm up for 5 minutes
4. Monitor for stability
5. Gradually shift traffic
```

### Vertical Scaling (Increase Resources)

```
When to scale:
- CPU >85% sustained
- Memory >2000MB sustained
- Single instance bottleneck

Steps:
1. Increase memory allocation
2. Increase CPU allocation
3. Restart service (during maintenance window)
4. Monitor for improvement
5. Consider horizontal scaling instead
```

## Maintenance Windows

### Weekly (Tuesday 2-3 AM UTC)
- Database maintenance
- Log rotation
- Cache cleanup
- Metrics aggregation

### Monthly (First Sunday of month, 3-4 AM UTC)
- Dependency updates
- Security patches
- Configuration review
- Performance analysis

### Quarterly
- Database optimization
- Index analysis
- Capacity planning
- Architecture review

## Capacity Planning

### Metrics to Track

```
Daily:
- Peak concurrent jobs
- Peak requests/sec
- Peak memory usage
- Peak CPU usage

Weekly:
- Growth rate (requests/sec)
- Growth rate (concurrent jobs)
- Growth rate (data volume)

Monthly:
- Trend analysis
- Forecast for next 3 months
- Resource utilization
- Cost trend
```

### Scaling Triggers

| Metric | Threshold | Action |
|--------|-----------|--------|
| Requests/sec | >500 | Horizontal scale |
| Concurrent jobs | >1000 | Horizontal scale |
| Memory/instance | >1500MB | Vertical scale |
| CPU utilization | >85% | Horizontal scale |
| Cache hit rate | <50% | Review cache strategy |
| Error rate | >1% | Investigate + remediate |

## Security Hardening

### Regular Security Checks

```bash
# Weekly
npm audit
npm outdated

# Monthly
npm audit fix --force  # (after testing)
Review rate limiter effectiveness
Review error logs for data leaks

# Quarterly
Security scanning tool
Penetration testing
Dependency vulnerability scanning
```

### Security Headers

```typescript
app.use((req, res, next) => {
  // Prevent info disclosure
  res.set('X-Content-Type-Options', 'nosniff');
  res.set('X-Frame-Options', 'DENY');
  res.set('X-XSS-Protection', '1; mode=block');
  
  // Rate limiting headers
  res.set('X-RateLimit-Limit', process.env.RATE_LIMIT_MAX);
  res.set('X-RateLimit-Remaining', String(remaining));
  res.set('X-RateLimit-Reset', String(resetTime));
  
  next();
});
```

## Disaster Recovery

### Backup Strategy

```
Database backups:
- Hourly: Last 24 hours
- Daily: Last 30 days
- Weekly: Last 3 months

Cache backups:
- None required (can be rebuilt)

Configuration:
- Git version control (immutable)
- Environment variables in secure vault
- Encrypted during transit
```

### Recovery Time Objectives (RTO)

| Component | RTO | Procedure |
|-----------|-----|-----------|
| Cache layer | 5 min | Reset and rebuild |
| API servers | 10 min | Redeploy from image |
| Database | 30 min | Restore from backup |
| Full system | 60 min | Full disaster recovery |

### Testing

```
Monthly disaster recovery drill:
1. Create test environment
2. Restore from latest backup
3. Verify all endpoints work
4. Verify data integrity
5. Document any issues
6. Update recovery procedures
```

## Performance Tuning

### Baseline Metrics

Measure these before and after changes:

```
API Latency:
- /healthz: <50ms
- /resolve: <500ms
- /simulate: <100ms (initial response)
- /simulate/:jobId: <100ms

Throughput:
- /simulate: >100 requests/sec
- /resolve: >500 requests/sec
- /healthz: >1000 requests/sec

Resource Usage:
- Memory: <1000MB idle
- CPU: <10% idle
- Connections: <500 open

Cache:
- Hit rate: >75%
- Eviction rate: <10%
```

### Profiling

```bash
# Enable detailed profiling
NODE_OPTIONS=--prof npm start

# Generate report
node --prof-process isolate-*.log > report.txt

# Analyze:
# - Memory allocation patterns
# - CPU hotspots
# - GC pauses
# - Heap growth
```

## Team Runbook

### On-Call Responsibilities

```
Primary On-Call:
- Monitor alerts 24/7
- First responder to incidents
- Escalate to secondary if needed
- Document resolution

Secondary On-Call:
- Backup for primary
- Sleep until called
- Take over if primary unavailable
- Join post-incident review

Manager On-Call:
- Override decisions if needed
- Resource allocation
- Customer communication
- Incident declarations
```

### Escalation Path

```
Incident severity:
- P4: Silent alerts (no page)
- P3: Email alert within 1 hour
- P2: Page within 15 minutes
- P1: Page immediately

Escalation:
- 5 min no response → Page secondary
- 15 min no progress → Page manager
- 30 min critical issue → All hands
```

## Cost Monitoring

### Monthly Cost Breakdown

Track spending by:
- Compute (instances)
- Storage (database)
- Network (egress)
- Services (LLM API, etc.)

Alert on:
- Unusual spike (>10% daily increase)
- Projected month over budget
- Unused resources

## Conclusion

Operations excellence requires consistent discipline:
- Monitoring shows what's happening
- Runbooks enable fast response
- Drills test recovery procedures
- Documentation prevents knowledge loss

Review and update this guide quarterly.
