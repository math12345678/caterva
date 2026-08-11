# Production Readiness: Critical Deep Review

**For:** Decision makers deploying to production  
**Scope:** Honest assessment of readiness, real risks, what could fail  
**Tone:** Not a checklist. Not cheerleading. Real analysis.  
**Last Updated:** August 9, 2026

---

## Executive Summary: The Honest Truth

This backend is **technically sound** and **production-capable**. Tests pass, architecture is solid, documentation is comprehensive.

But production readiness is not just technical. It's about:
- What happens when things fail?
- Do we have monitoring to catch failures?
- Are we prepared for real users?
- What edge cases haven't we seen?

This review explores what we **don't know we don't know**.

---

## Section 1: What Could Actually Go Wrong in Production

### 1.1 The Silent Result Divergence

**Scenario:** A researcher runs the same query twice and gets slightly different results.

**For deterministic domains (SIR, Lotka-Volterra):**
- Should be identical
- If different → solver bug
- If we don't detect this → published incorrect results

**Current monitoring:** None. We cache results but don't verify determinism.

**Real risk:** 
```
Query 1: SIR beta=0.5 gamma=0.1 → Result A
Query 2: SIR beta=0.5 gamma=0.1 → Result B (from cache)
A ≠ B (shouldn't happen for deterministic domain)
User publishes Results A as primary, Results B as verification
Results don't match
→ Retraction, wasted research time
```

**What we should do:**
1. Run identical deterministic queries multiple times
2. Alert if results differ
3. Quarantine divergent results
4. Investigate before serving

**Current state:** No implementation for this

**Severity:** HIGH - Could invalidate research

---

### 1.2 Parameter Value Drift

**Scenario:** We change a domain default, but cached results still use old default.

**Example:**
```
Old code: SIR defaults to end=100, points=1001
Researcher runs: "SIR beta=0.5 gamma=0.1"
Result cached with end=100, points=1001

Code upgrade: SIR defaults to end=200, points=2001
Same researcher runs: "SIR beta=0.5 gamma=0.1"
Result returned from cache: end=100, points=1001 (OLD)
User thinks result is for new defaults (WRONG)
```

**Current state:** Cache is NOT versioned by code. This is a real risk.

**Mitigation:** 
- Version cache by code commit hash
- Clear cache on deployment
- Log when old results returned

**Current implementation:** None

**Severity:** MEDIUM-HIGH - Silent incorrectness

---

### 1.3 LLM Provider Cascade Failure

**Scenario:** Primary LLM provider fails during production deployment.

**Flow:**
1. GROQ_API_KEY works fine in staging
2. Deploy to production
3. GROQ has regional outage
4. Fallback to OPENROUTER (different model, different quirks)
5. OPENROUTER also fails (rare but possible)
6. Fallback to keywords

**At keyword level:** Ambiguous query like "oscillator" could resolve to:
- `lotka_volterra` (predator-prey oscillates)
- `cell_cycle_oscillator` (cell cycle oscillates)
- `repressilator` (genetic circuit oscillates)

**Current behavior:** First match in keyword list wins (undefined order)

**Real scenario:**
```
User: "simulate oscillator dynamics with k=0.5"
LLMs down
→ Keyword fallback chooses "cell_cycle_oscillator" (deterministic, but not what user meant)
→ cell_cycle doesn't use parameter k
→ k goes unused silently
→ Result is complete but wrong
```

**Current state:** No priority ordering for ambiguous keywords

**Severity:** MEDIUM - Silent wrong domain selection

---

### 1.4 Database Transaction Isolation Bug

**Scenario:** PostgreSQL transaction isolation level mismatch.

```typescript
// In simulate.ts
const db = getDb();
if (db) {
  await db.insert(simulationsTable).values({...});
}
```

**Question:** What's the isolation level?

PostgreSQL defaults to READ_COMMITTED. This allows:

```
Transaction A: INSERT simulation X
Transaction B: SELECT COUNT(*) FROM simulations → sees X (dirty read)
Transaction A: ROLLBACK → X never happened
Transaction B: Count is wrong
```

**With READ_COMMITTED:** This is actually fine (we don't care about dirty reads for simulations).

**But:** If someone adds a constraint that depends on consistency:
```sql
ALTER TABLE simulations ADD CONSTRAINT check_not_duplicate
  CHECK (count_duplicates() = 0);
```

Suddenly dirty reads matter. This constraint breaks silently.

**Current state:** 
- No explicit isolation level set
- Relies on PostgreSQL defaults
- Could break if constraints added later

**Severity:** LOW (unlikely to trigger), HIGH (if it does)

---

### 1.5 Memory Pressure Under Sustained Load

**Scenario:** System runs for 72 hours with steady simulation requests.

```
Hour 1:  10 jobs in memory, 2 active
Hour 24: 1000 jobs in memory (capped), 2 active
Hour 48: Still 1000 jobs (pruning keeps max), 2 active
Hour 72: ???
```

**What happens to job listeners?**

```typescript
// src/lib/queue.ts
export function cleanupJob(jobId: string): void {
  listeners.delete(jobId);
}
```

This only runs after job completes. But:

```
Job 1 completes → cleanupJob(1) → listeners removed
Job 2 completes → cleanupJob(2) → listeners removed
...
Job 1000 completes → cleanupJob(1000) → listeners removed
Job 1001 created → Map size: 1001 listeners

But listeners map should only have 1000 max!
```

**The bug:** We prune jobs from `jobs` map but NOT from `listeners` map.

```typescript
// ❌ Current code in queue.ts
if (jobs.size > MAX_JOBS) {
  const oldest = Array.from(jobs.values())
    .filter((j) => j.status === "completed" || j.status === "failed")
    .sort((a, b) => ...)
    [0];
  if (oldest) {
    jobs.delete(oldest.jobId);
    listeners.delete(oldest.jobId);  // Good! We DO clean listeners
  }
}
```

Actually, re-reading the code: **we DO delete listeners**. This is correct.

**But:** Is there a path where listeners persist without jobs?

Yes:

```typescript
// Job completes
queue.setJobResult(jobId, result);  // Updates listeners

// Listeners are notified
// Job is now terminal

// Later, when 1001st job arrives:
if (jobs.size > MAX_JOBS) {
  // Delete oldest from jobs
  // Delete oldest from listeners
  // But what if listeners were added AFTER jobs were added?
}
```

**Real risk:** A subtle timing bug where listeners leak. Under 72 hours of load, listeners map grows unbounded.

**Current state:** Code looks correct, but requires testing to verify

**Severity:** MEDIUM - Only manifests under sustained load, hard to diagnose

---

### 1.6 Python Process Crash Not Detected

**Scenario:** Python bridge crashes mid-simulation.

```python
# src/lib/tellurium_runner.py
def run_sir(parameters):
    # Simulation running
    # ...
    # CRASH: numpy array access out of bounds
    # Segmentation fault
    # Process exits with code -11
```

**What happens in TypeScript:**

```typescript
const result = await spawnSync(pythonExe, ['-c', code]);
if (result.status === 0) {
  // Success
} else if (result.status === -11) {
  // CRASH
  // What do we do?
}
```

**Current code (simulate.ts):**

```typescript
catch (err) {
  if (abort.signal.aborted || queue.isCancelled(jobId)) {
    queue.setJobCancelled(jobId);
  } else if (err instanceof RequiredParametersMissingError) {
    // ...
  } else {
    queue.setJobError(jobId, {
      error: "PIPELINE_ERROR",
      message: err instanceof Error ? err.message : "Unexpected pipeline failure"
    });
  }
}
```

**Issue:** Python segfault is caught as generic error, message says "Unexpected pipeline failure" (user-facing).

User sees: "Your query failed. Try again."

Operator sees: Nothing distinctive in logs (just generic error).

**Better behavior:**

```typescript
if (result.status === -11 || result.status === -6) {
  // Segfault or abort
  queue.setJobError(jobId, {
    error: "ENGINE_CRASH",
    message: "Simulation engine encountered a fatal error",
    internalMessage: `Python exited with code ${result.status}`
  });
  // Alert: Engine crashed
  logger.error("CRITICAL: Python engine crashed");
}
```

**Current state:** No special handling for segfaults

**Severity:** MEDIUM - Crashes are undetected, could cascade

---

## Section 2: What Monitoring Are We Missing?

### 2.1 Monitoring We Have

```
✅ Health check endpoint (/healthz)
✅ Metrics endpoint (/api/metrics)
✅ Structured logging
✅ Job status tracking
✅ Queue depth visibility
```

### 2.2 Monitoring We're Missing

```
❌ Determinism verification (same query → same result?)
❌ Cache coherence monitoring (divergence between cache and live)
❌ Python process health (crash detection, heartbeat)
❌ LLM provider status (is primary working? Fallback needed?)
❌ Parameter provenance validation (are we logging correctly?)
❌ Response size monitoring (trajectory size distribution)
❌ Latency by domain (which domains are slow?)
❌ Error attribution (LLM? Parameter? Engine?)
```

### 2.3 What This Means

**Without these metrics, we can't detect:**
- Silent result divergence (until user reports)
- Cache poisoning (until results diverge)
- Engine crashes (until jobs fail mysteriously)
- Provenance drift (until audit)

**How operators respond to incidents:**
```
"Jobs are failing"
Check: /healthz → OK
Check: /api/metrics → Queue depth: 500, error rate: 0.5%
Check: logs → "PIPELINE_ERROR" × 500
Try: "Is it the LLM?" 
Blind guess between 3 providers
Finally: "Let's look at the first failed job"
```

---

## Section 3: Questions We Haven't Answered

### 3.1 What's the minimum viable monitoring setup?

Current answer: Health check + metrics endpoint

Real answer: Unknown. We haven't run this in production.

### 3.2 How does the system behave under sustained load?

We know: MAX_CONCURRENT=2, queue is unbounded

We don't know:
- Response latency under 10k jobs queued?
- Memory usage over 7 days?
- Job listener leak under load?
- Database connection pool exhaustion?

### 3.3 How does the LLM fallback chain actually behave?

Theory: GROQ → OPENROUTER → MISTRAL → SILICONFLOW → OPENAI → keywords

Reality: Unknown. Each provider has different:
- Failure modes
- Latency distribution
- Domain classification accuracy
- Timeout behavior

We've never tested provider cascades.

### 3.4 What happens when the database is briefly unavailable?

Scenario: PostgreSQL goes down for 30 seconds

Expected: System continues with in-memory cache

Actual: Unknown. We haven't tested this.

### 3.5 What's the actual cost under production load?

Budgeted: ~$300/month (from DEPLOYMENT_GUIDE.md)

Actual: Unknown until we measure real usage

Questions:
- How many jobs/second are realistic?
- What's the compute-per-job on AWS/GCP?
- Does vertical or horizontal scaling work better?

---

## Section 4: Architectural Risks

### 4.1 The ADR 0007 Boundary Could Drift

**Risk:** Python adds a domain, TypeScript doesn't learn about it.

**Current safeguard:** Contract test in `llmProviders.test.ts`

**Gap:** Test only runs if you explicitly run tests. What if:
- Developer adds domain only to Python
- Commits without running tests
- CI/CD doesn't run because test suite is skipped
- Domain exists in Python but not TypeScript
- Queries for that domain silently fail

**Mitigation:** 
- Make contract test mandatory in CI/CD ✅ (we have this)
- Make failing deployment impossible ✅ (we have this)

**But:** We haven't tested whether CI/CD actually blocks this

---

### 4.2 The Cache Isn't Versioned by Code

**Current:** Cache is normalized query string only

**Gap:** Code changes (new solver version) don't invalidate cache

**Scenario:**
1. Deploy v1.0 (SIR solver)
2. Someone runs: "SIR beta=0.5 gamma=0.1"
3. Result cached
4. Deploy v2.0 (improved SIR solver)
5. Same query returns cached result from v1.0
6. User thinks they have v2.0 result

**Severity:** HIGH - Silent version mismatch

**Fix:** Version cache by code commit hash

**Current state:** Not implemented

---

### 4.3 The Provenance System Trusts LLM Output

**Current:** If LLM suggests parameters, we mark them `origin: "llm"` with NO citation

**Gap:** We trust the LLM without verification

**Example Scenario:**
```
Input: "enzyme kinetics for unknown enzyme"
LLM Output: "I'll guess km=5"
Flagging: origin: "llm", note: "LLM suggested"
Risk: User might not realize this is speculative and use it for publication
Reality: km=5 was not verified against any database
```

**Better:** Mark LLM values with "NOT VERIFIED" flag

**Current state:** We do flag them, but not prominently

---

## Section 5: Operational Readiness

### 5.1 Do We Have an Incident Response Plan?

**Answer:** Yes, OPERATIONS_RUNBOOK.md

**Gap:** Plan was never tested under real production conditions

**Unknown:**
- Can operators actually follow the runbook in a crisis?
- Do the diagnostic commands work?
- Are timing estimates accurate?
- Are escalation procedures actually correct?

**What should happen:** Run a fire drill where someone (not the author) follows the runbook to fix a simulated problem

**Current state:** Not done

---

### 5.2 Do We Have a Deployment Rollback Plan?

**Answer:** Partially. DEPLOYMENT_GUIDE.md covers deployment but not rollback clearly

**Gap:** What happens if v2.0 has a bug?

```
v2.0 deployed
Jobs start failing
Operator wants to rollback to v1.0
How? Exactly what commands?
What about jobs in progress?
What about cached results from v2.0?
```

**Current state:** Unclear

---

### 5.3 Do We Have Security Incident Response?

**Answer:** SECURITY_HARDENING.md covers security but incident response is vague

**Gap:** What if someone finds a SQL injection?

```
Vulnerability discovered
Patch written
But what about existing data?
Can we be sure injection didn't steal data?
How do we audit what was accessed?
```

**Current state:** Not documented

---

## Section 6: Testing Gaps

### 6.1 We Don't Test Real Failure Scenarios

```
✅ Unit tests: All pass (404/404)
✅ Integration tests: All pass
❌ Chaos engineering: Not done
❌ Load testing: Not done
❌ Failure injection testing: Not done
```

**Example missing test:**
```python
def test_python_process_crashes():
    """What happens if Python segfaults mid-simulation?"""
    # Inject segfault
    # Verify job is marked PIPELINE_ERROR
    # Verify subsequent jobs recover
    # Verify no listener leak
```

**Current state:** No chaos tests

---

### 6.2 We Don't Test Provider Cascades

```
Test: GROQ works → ✅
Test: OPENROUTER works → ✅
Test: What if GROQ fails and OPENROUTER is tried → ❌ (NOT TESTED)
```

**Current state:** Each provider tested in isolation, not cascade

---

### 6.3 We Don't Load Test

```
Test: 1 concurrent job → ✅
Test: 10 concurrent jobs → ❌ (NOT TESTED)
Test: 1000 jobs queued → ❌ (NOT TESTED)
Test: 24-hour sustained load → ❌ (NOT TESTED)
```

**Current state:** No load tests

---

## Section 7: Honest Assessment

### What We Know Works

- Domain classification (tested)
- Parameter validation (tested)
- Cache hit/miss (tested)
- Provenance tracking (tested)
- Single simulation execution (tested)
- Error classification (tested)

### What We Think Works But Haven't Verified

- Multiple simultaneous jobs
- Sustained load over days
- LLM provider fallback chain
- PostgreSQL transaction handling
- Job listener cleanup
- Cache under concurrent writes

### What We Don't Know

- Real production latency distribution
- Real production error rates
- Cost under real usage
- User satisfaction/friction
- Whether operators can follow runbooks
- Whether our monitoring catches real issues

---

## Section 8: Recommendations for Production

### Before Deploy

**Must Do:**
1. Load test with 10× expected peak load
2. Run chaos test: Kill Python process mid-job
3. Test LLM provider cascade: Mock GROQ failure, verify fallback
4. Test database unavailability: Stop PostgreSQL, verify behavior
5. Run 24-hour sustained load test
6. Dry-run incident response: Follow runbook to fix simulated problem
7. Code review by someone who hasn't touched this code
8. Security audit by actual security person

**Should Do:**
1. Monitor all "Missing" metrics from Section 2.2
2. Version cache by code commit hash
3. Add determinism verification for deterministic domains
4. Add Python crash detection with alerting
5. Write chaos engineering tests

**Nice to Do:**
1. Load testing harness in CI/CD
2. Monthly fire drill of incident response
3. Production staging environment (mirror of prod)

### After Deploy

**Week 1:**
- Daily operator check-in
- Monitor for unexpected patterns
- Track all errors by type
- Watch latency distribution

**Week 2-4:**
- Customer feedback collection
- Operator comfort assessment
- Adjust alerts based on real patterns
- Update runbooks with lessons learned

**Month 2+:**
- Quarterly load testing
- Quarterly security audit
- Quarterly chaos testing
- Six-month deep review

---

## Section 9: The Hard Truth

This system is **technically sound** but **operationally unproven**.

We can deploy it. It will probably work.

But we're deploying blind on several critical dimensions:
- We don't know how it behaves at scale
- We don't know if operators can actually respond to incidents
- We don't know if our monitoring is sufficient
- We don't know if provider fallbacks work correctly
- We don't know if cache remains coherent under load

**This is not unusual.** Most systems go to production in this state.

**But it means:** Be conservative in expectations. Have people watching. Be ready to rollback. Have a real incident commander.

---

## Conclusion

**Verdict:** Production-capable. Not production-proven.

**What to do:** Deploy, but with eyes wide open to the gaps.

**Timeline for confidence:**
- Week 1: Does it stay up?
- Month 1: Does it perform?
- Month 3: Do operators understand it?
- Month 6: Can we truly operate it?

Trust the tests. But don't trust only the tests.

---

**Date:** August 9, 2026  
**Author's confidence:** 70% (technical), 40% (operational)  
**Recommendation:** Deploy with caution and close monitoring
