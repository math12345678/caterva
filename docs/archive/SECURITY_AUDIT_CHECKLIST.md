# Security Audit Checklist & Hardening Guide

> **⚠️ No audit was performed -- every "✅ IMPLEMENTED" below needs to be
> read as a specification, not a result.** This describes security controls
> (Zod input validation, an Express rate limiter, CORS/security headers)
> for an HTTP service that does not exist in this codebase: `src/` (package
> `caterva-scientific-backend`) has no `dependencies` in `package.json` at
> all (only `devDependencies` -- jest, ts-node, eslint, typescript), `zod`
> is not installed, and no `express()`/`app.use()`/`createServer()` exists
> anywhere in `src/` (confirmed by grep, 2026-08-10). A security checklist
> marking controls "implemented" for a service that was never built is the
> same failure mode this repo has already caught and corrected once, in
> `Science-Agent-Pipeline/artifacts/api-server/SECURITY_HARDENING.md` (that
> project's real security posture, since corrected, is genuinely worth
> reading -- it documents an actual running server). Kept below as a
> specification for security work that would be needed if/when this tree is
> exposed as a network service, not an audit finding.

## Executive Summary

This document provides a comprehensive security audit checklist for the Caterva backend. It covers:
- Input validation & output encoding
- Authentication & authorization
- Data protection & encryption
- Infrastructure security
- Dependency management
- Incident response capabilities

**Current Status:** Ready for first security audit  
**Last Updated:** 2026-08-09  
**Next Review:** Quarterly

---

## Input Validation & Sanitization

### API Input Validation

```typescript
// ✅ IMPLEMENTED: Zod schema validation
const RunSimulationBody = z.object({
  query: z.string().min(1).max(1000)
});

// ✅ IMPLEMENTED: Query parameter validation
router.get("/simulate/:jobId", (req, res) => {
  const schema = z.object({
    jobId: z.string().uuid()
  });
  const result = schema.safeParse(req.params);
  if (!result.success) {
    return res.status(400).json({ error: result.error });
  }
});
```

**Audit Items:**
- [ ] All route parameters validated with Zod
- [ ] All query parameters validated with Zod
- [ ] All request bodies validated with Zod
- [ ] No string concatenation in SQL/database queries
- [ ] No direct use of user input in file paths
- [ ] No command injection possible in Python bridge

### Parameter Validation

```typescript
// ✅ IMPLEMENTED: Numeric validators
function isValidFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

// ✅ IMPLEMENTED: Array validators
function isValidNumberArray(value: unknown): value is number[] {
  return Array.isArray(value) && value.every(isValidFiniteNumber);
}
```

**Audit Items:**
- [ ] All parameter values validated before use
- [ ] No negative values where not allowed
- [ ] No extremely large values (potential memory bomb)
- [ ] Scientific notation handled correctly
- [ ] NaN and Infinity rejected

### Error Messages

```typescript
// ✅ IMPLEMENTED: Safe error messages
function createAppError(statusCode: number, userMessage: string) {
  return {
    statusCode,
    error: 'AppError',
    message: userMessage  // User-safe, no implementation details
    // Stack trace never included in response
  };
}

// ❌ DO NOT: Leak implementation details
res.status(500).json({
  error: err.stack,  // DANGER: Exposes file paths and code
  query: rawUserInput  // DANGER: Echo user input
});
```

**Audit Items:**
- [ ] No stack traces in production responses
- [ ] No database error details exposed
- [ ] No file paths exposed
- [ ] No SQL queries exposed
- [ ] No Python command exposure

---

## Authentication & Authorization

### API Key Management

```typescript
// ✅ IMPLEMENTED: Environment variable storage
const apiKey = process.env.LLM_API_KEY;

// ✅ IMPLEMENTED: No logging of secrets
logger.info({ query });  // ✅ Safe
logger.info({ apiKey });  // ❌ DANGER

// ✅ IMPLEMENTED: Timeout for external API calls
const timeout = 30000;  // 30 seconds maximum per request
```

**Audit Items:**
- [ ] All secrets in environment variables
- [ ] Secrets never logged
- [ ] Secrets never in git history
- [ ] Rotation policy documented
- [ ] Secrets rotation implemented
- [ ] Multiple environment secrets supported (dev/staging/prod)

### Rate Limiting

```typescript
// ✅ IMPLEMENTED: Global rate limiter
class GlobalRateLimiter {
  private limit = 1000;
  private windowMs = 15 * 60 * 1000;  // 15 minutes
}

// ✅ IMPLEMENTED: Per-endpoint rate limiting
const simulateLimiter = rateLimit({
  windowMs: 60_000,
  max: 10
});
```

**Audit Items:**
- [ ] Rate limiter active on all endpoints
- [ ] Rate limits prevent brute force attacks
- [ ] Rate limit headers included in responses
- [ ] Bypass logic impossible
- [ ] Rate limit storage protected
- [ ] DDoS mitigation in place (WAF, etc.)

### Authorization

```typescript
// ✅ IMPLEMENTED: Jobs isolated by ID
export function getJob(jobId: string): Job | undefined {
  // No user context, but jobs require valid UUID format
}

// TODO: Implement user-based authorization
interface UserContext {
  userId: string;
  permissions: string[];
}

function authorizeJobAccess(jobId: string, user: UserContext): boolean {
  const job = getJob(jobId);
  // Verify user owns job or has read permission
  return job?.userId === user.userId || user.permissions.includes('read:all_jobs');
}
```

**Audit Items:**
- [ ] Resource ownership verified
- [ ] Permission checks before resource access
- [ ] No privilege escalation possible
- [ ] Admin vs. user roles enforced
- [ ] Cross-account access prevented

---

## Data Protection & Encryption

### Data in Transit

```typescript
// ✅ IMPLEMENTED: HTTPS enforced (at infrastructure level)
// ✅ IMPLEMENTED: Secure headers
app.use((req, res, next) => {
  res.set('X-Content-Type-Options', 'nosniff');
  res.set('X-Frame-Options', 'DENY');
  res.set('X-XSS-Protection', '1; mode=block');
  res.set('Strict-Transport-Security', 'max-age=31536000; includeSubDomains');
});

// ✅ IMPLEMENTED: CORS configuration
app.use(cors({
  origin: process.env.ALLOWED_ORIGINS?.split(',') || [],
  credentials: true
}));
```

**Audit Items:**
- [ ] HTTPS enforced (no HTTP)
- [ ] TLS 1.2+ required
- [ ] Certificate validation works
- [ ] CORS properly configured
- [ ] No overly permissive CORS
- [ ] CSP headers set
- [ ] HSTS header present

### Data at Rest

```typescript
// TODO: Encryption implementation
interface EncryptedData {
  iv: string;           // Initialization vector
  ciphertext: string;   // Encrypted data
  tag: string;         // Authentication tag
}

function encryptSensitiveData(data: string, key: string): EncryptedData {
  // Use AES-256-GCM for authenticated encryption
  // Never use simple encryption without authentication
}
```

**Audit Items:**
- [ ] Sensitive parameters encrypted in cache
- [ ] Encryption key management secure
- [ ] Database encryption enabled
- [ ] Backups encrypted
- [ ] Key rotation policy exists

### Sensitive Data Handling

```typescript
// ✅ IMPLEMENTED: No credential logging
logger.info({ query });  // ✅ Safe
logger.info({ apiKey: process.env.LLM_API_KEY });  // ❌ DANGER

// ✅ IMPLEMENTED: Error messages don't leak data
catch (err) {
  res.status(500).json({
    error: 'InternalError',
    message: 'Failed to process request'  // Generic, safe message
  });
}
```

**Audit Items:**
- [ ] No API keys in logs
- [ ] No passwords in logs
- [ ] No user PII in logs
- [ ] No database connection strings in logs
- [ ] Log retention policy enforced
- [ ] Audit logs protected

---

## Infrastructure Security

### Service Isolation

```typescript
// ✅ IMPLEMENTED: Python process isolation
const proc = spawn(pythonExecutable, [SCRIPT_PATH], {
  cwd: REPO_ROOT,
  env: buildCatervaEnvironment(process.env, REPO_ROOT)
});

// Timeout prevents hanging processes
const timeoutId = setTimeout(() => abortController.abort(), 30_000);
```

**Audit Items:**
- [ ] Python processes timeout after 30 seconds
- [ ] Resource limits enforced (memory, CPU)
- [ ] File access restricted to intended paths
- [ ] Network access restricted
- [ ] No privilege escalation possible

### Dependency Management

```json
{
  "scripts": {
    "audit": "npm audit",
    "audit:fix": "npm audit fix",
    "outdated": "npm outdated"
  }
}
```

**Audit Items:**
- [ ] `npm audit` runs clean (zero vulnerabilities)
- [ ] No known vulnerabilities in dependencies
- [ ] Dependency updates automated (Dependabot)
- [ ] Security patches prioritized
- [ ] Major versions reviewed before upgrade
- [ ] Python dependencies similarly audited

### Database Security

```typescript
// ✅ IMPLEMENTED: Parameterized queries
// Using ORMs/query builders that prevent SQL injection

// ❌ NEVER DO THIS:
const query = `SELECT * FROM jobs WHERE jobId = '${jobId}'`;  // SQL injection risk

// ✅ ALWAYS DO THIS:
const result = db.query('SELECT * FROM jobs WHERE jobId = ?', [jobId]);
```

**Audit Items:**
- [ ] All queries use parameterized statements
- [ ] No string concatenation in queries
- [ ] Database user has minimal permissions
- [ ] Backups encrypted and secured
- [ ] Database audit logging enabled
- [ ] Password policies enforced

---

## Monitoring & Logging

### Security Logging

```typescript
// Log security-relevant events
logger.info({ path: req.path, method: req.method }, 'Request received');
logger.warn({ path: req.path, status: 429 }, 'Rate limit exceeded');
logger.error({ error: 'AUTH_FAILED', userId }, 'Authentication failed');
```

**Audit Items:**
- [ ] All authentication attempts logged
- [ ] All rate limit violations logged
- [ ] All errors with code >400 logged
- [ ] All admin actions logged
- [ ] Login failures tracked (for brute force detection)
- [ ] Unusual patterns detected

### Security Monitoring

```typescript
// Alert on suspicious patterns
const alerts = {
  failedAuthAttempts: (count) => count > 5 && 'Brute force detected',
  rateLimitViolations: (count) => count > 100 && 'DDoS suspected',
  errorRate: (rate) => rate > 1% && 'Error spike - possible attack',
  unusualLatency: (latency) => latency > 5000 && 'Performance degradation'
};
```

**Audit Items:**
- [ ] Failed authentication attempts monitored
- [ ] Rate limit violations monitored
- [ ] Unusual error patterns detected
- [ ] Performance degradation detected
- [ ] Alerts sent to security team
- [ ] Response procedures documented

---

## Incident Response

### Security Incident Types

```
CRITICAL (Page immediately):
- Active exploitation
- Data breach in progress
- Ransomware detected
- Unauthorized access

HIGH (Page within 15 min):
- Multiple failed auth attempts (>10 in 5min)
- Unusual data access patterns
- Rate limit bypass
- Service unavailability

MEDIUM (Alert within 1 hour):
- Single failed auth attempt
- Unusual but not critical pattern
- Minor vulnerability discovered

LOW (Email):
- Informational security events
- Routine security updates
- Policy reminders
```

**Audit Items:**
- [ ] Security incident types defined
- [ ] Response procedures documented
- [ ] Escalation paths clear
- [ ] Communication templates ready
- [ ] Incident drills scheduled quarterly

### Breach Response Checklist

```
Upon discovering potential breach:
[ ] Assess scope (what data exposed?)
[ ] Estimate duration (how long was it exposed?)
[ ] Preserve evidence (logs, database snapshots)
[ ] Isolate affected systems (if needed)
[ ] Notify security team
[ ] Begin investigation
[ ] Contact affected users (if required)
[ ] Update breach notice
[ ] Implement remediation
[ ] Document lessons learned
[ ] Update security measures
[ ] Audit for other breaches
```

---

## Compliance & Audit

### Required Audits

```
ANNUAL:
- [ ] Full security audit by third party
- [ ] Penetration testing
- [ ] Code review for security issues
- [ ] Dependency vulnerability scan

QUARTERLY:
- [ ] Internal security review
- [ ] Access control audit
- [ ] Backup verification
- [ ] Disaster recovery drill

MONTHLY:
- [ ] Security patch review
- [ ] Dependency updates
- [ ] Log review for anomalies
- [ ] Rate limiter effectiveness review

WEEKLY:
- [ ] npm audit
- [ ] Error rate monitoring
- [ ] Rate limit monitoring
- [ ] Failed auth attempt monitoring

DAILY:
- [ ] Automated security scanning
- [ ] Log aggregation review
- [ ] Alert response review
```

### Audit Trail

```typescript
// Maintain audit trail for compliance
interface AuditEntry {
  timestamp: Date;
  userId?: string;
  action: string;
  resource: string;
  result: 'success' | 'failure';
  details?: Record<string, any>;
}

function logAudit(entry: AuditEntry) {
  // Store in immutable audit log
  // Cannot be deleted, only archived
}
```

---

## Security Checklist Summary

### Before Production Deployment

```
Code Security:
- [ ] No hardcoded secrets
- [ ] No debug code
- [ ] All input validated
- [ ] Error messages safe
- [ ] Logging secure
- [ ] Dependencies audited
- [ ] No dangerous imports
- [ ] Rate limiting active

Infrastructure:
- [ ] HTTPS enforced
- [ ] Database secured
- [ ] Backups encrypted
- [ ] Access logs enabled
- [ ] Monitoring active
- [ ] Alerts configured
- [ ] Incident response ready

Compliance:
- [ ] Privacy policy current
- [ ] Data retention policy set
- [ ] User consent collected
- [ ] Breach response plan ready
- [ ] Audit trail in place
- [ ] Terms of service updated
```

### Ongoing Security

```
Monthly:
- [ ] Security patch review
- [ ] Audit report review
- [ ] Compliance verification

Quarterly:
- [ ] Full security audit
- [ ] Penetration testing
- [ ] Policy review
- [ ] Disaster recovery drill

Annually:
- [ ] Third-party audit
- [ ] Compliance certification
- [ ] Security training
- [ ] Policy overhaul
```

---

## Contact & Escalation

**Security Team Lead:** [Name] ([email])  
**Incident Response:** [Hotline or email]  
**Bug Bounty Program:** [URL or email]  
**Privacy Officer:** [Name] ([email])  

For security vulnerabilities, please report privately through https://github.com/math12345678/caterva/security/advisories/new (not public issues).

---

## Document Control

**Version:** 1.0  
**Last Updated:** 2026-08-09  
**Next Review:** 2026-11-09  
**Owner:** Security Team  
**Classification:** Internal
