# Security Hardening Guide

**For:** Security engineers, DevOps, compliance teams  
**Status:** August 2026  
**Classification:** For internal use  
**Last Review:** August 9, 2026

---

## Security Architecture

### Threat Model

**Assets to Protect:**
1. Simulation results (research data)
2. API availability (service continuity)
3. Server resources (compute, memory)
4. Database contents (persistent data)
5. LLM API keys (external credentials)

**Threat Categories:**

| Threat | Impact | Mitigation |
|--------|--------|-----------|
| DDoS / resource exhaustion | Service unavailable | Rate limiting, resource quotas |
| Parameter injection | Code execution | Input validation, sandboxing |
| SQL injection | Data breach | Prepared statements (Drizzle ORM) |
| Data exfiltration | Confidentiality loss | Encryption in transit/rest |
| Unauthorized access | Data/service compromise | Authentication, authorization |
| Supply chain attacks | Code compromise | Dependency scanning, pinning |

### Security Layers

```
                    User
                     ↓
        [Rate Limiting & DDoS Protection]
                     ↓
        [Input Validation & Sanitization]
                     ↓
        [Authentication/Authorization]
                     ↓
        [Business Logic]
                     ↓
        [Database Encryption & Access Control]
```

---

## 1. Input Validation & Injection Prevention

### Query Parameter Validation

**Current Implementation:**

```typescript
// src/lib/schemas.ts
export const ResolveBody = z.object({
  query: z
    .string()
    .min(1, "query is required")
    .max(500, "query must be 500 characters or fewer")
    .transform((s) => s.trim()),
});
```

**Security Properties:**
- ✅ String type enforced
- ✅ Length bounded (prevents buffer overflow)
- ✅ Trimmed (removes leading/trailing whitespace)
- ✅ Zod ensures validation

**Validation Coverage:**

```typescript
// Every parameter has type validation
const SimulationParameterSchemas: Record<SimulationDomain, ZodType> = {
  mm: z.object({
    km: numeric,              // Must be number, not string
    vmax: optionalNumeric,
    s0: numeric,
    // ...
  }),
  // ... all 16 domains
};
```

**Additional Protections:**

```typescript
// src/lib/queryResolver.ts - Parameter extraction
const value = Number.parseFloat(rawValue);
if (Number.isFinite(value)) {  // Rejects NaN, Infinity
  overrides[key] = value;
}
```

### SQL Injection Prevention

**Technology:** Drizzle ORM with prepared statements

```typescript
// Safe: Uses parameterized query
const rows = await db
  .select()
  .from(simulationsTable)
  .where(
    sql`lower(trim(regexp_replace(${simulationsTable.query}, '\\s+', ' ', 'g'))) = ${query}`
  );
// Parameters are bound separately, not concatenated
```

**Never do this:**
```typescript
// ❌ WRONG - Direct string concatenation
const query = `SELECT * FROM simulations WHERE query = '${userInput}'`;
```

**Verify in code review:** All database operations use Drizzle ORM, never raw SQL strings.

### Command Injection Prevention

**Risk:** User input passed to shell commands

**Current Implementation:** No shell commands used

```typescript
// ✅ Safe - Parameters passed to spawnSync
const result = spawnSync(pythonExe, [
  "-c",
  importChecks,  // Not user-controlled
], { stdio: "ignore" });
```

**If adding shell commands:**
```typescript
// ❌ WRONG
exec(`python ${userQuery}`);

// ✅ RIGHT
spawn("python", [userQuery], { shell: false });
```

### Expression Language Injection

**Risk:** User query contains template literals or expressions

**Current Implementation:** Query is treated as data, not code

```typescript
// ✅ Safe - Just a string
const query = "SIR with beta=0.5";
// No eval, no template evaluation, no code execution
```

**Never do this:**
```typescript
// ❌ WRONG - Query as code
eval(`simulateDomain('${userQuery}')`);
```

---

## 2. Rate Limiting & DDoS Prevention

### Global Rate Limiter

**Configuration:** `src/app.ts`

```typescript
const RATE_LIMIT = 1000;              // Requests per window
const RATE_WINDOW_MS = 15 * 60 * 1000; // 15 minutes
```

**Enforcement:**
```typescript
// Per global IP bucket
const bucket = REQUEST_COUNTS.get("global");
if (bucket.count > RATE_LIMIT) {
  res.status(429).json({ error: "RATE_LIMIT_EXCEEDED" });
  return;
}
```

**Response Headers:**
```
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 950
X-RateLimit-Reset: 1691596800
```

### Resource Quotas

**Concurrency:** Limited to 2 Python processes
```typescript
const MAX_CONCURRENT = 2;
```

**Job Queue:** Limited to 1000 in-memory jobs
```typescript
const MAX_JOBS = 1000;
```

**Request Size:** Limited to 1MB (Express default)
```typescript
app.use(express.json({ limit: '1mb' }));
```

### Nginx Rate Limiting (Production)

```nginx
# /etc/nginx/sites-enabled/terrium

# Rate limit: 10 requests/second, burst 20
limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s;

server {
    location / {
        limit_req zone=api_limit burst=20 nodelay;
        proxy_pass http://backend;
    }
}
```

### DDoS Mitigation Strategy

1. **Rate limiting** (application layer)
2. **Nginx rate limiting** (reverse proxy layer)
3. **WAF rules** (optional, Cloudflare/AWS WAF)
4. **Geo-blocking** (if needed)
5. **Anycast CDN** (absorb traffic spikes)

---

## 3. Authentication & Authorization

### Current State

**Status:** No authentication required (public API)

**Rationale:**
- Scientific research should be open access
- No user data stored per query
- Simulations are stateless
- Rate limiting provides fair access

### If Authentication Needed (Future)

```typescript
// src/lib/auth.ts
export interface User {
  id: string;
  email: string;
  apiKey: string;
  quotaPerDay: number;
}

// Middleware
function authenticateApiKey(req: Request, res: Response, next: NextFunction) {
  const apiKey = req.headers['x-api-key'] as string;
  if (!apiKey) {
    return res.status(401).json({ error: "UNAUTHORIZED" });
  }
  
  const user = getUser(apiKey);
  if (!user) {
    return res.status(403).json({ error: "FORBIDDEN" });
  }
  
  req.user = user;
  next();
}

// Per-user rate limiting
function applyUserQuota(req: Request, res: Response, next: NextFunction) {
  const user = req.user;
  const used = getUsageToday(user.id);
  
  if (used >= user.quotaPerDay) {
    return res.status(429).json({ error: "QUOTA_EXCEEDED" });
  }
  
  next();
}
```

### Metrics Admin Token

**Current:** Protects only `POST /metrics/reset` (i.e. `POST /api/metrics/reset`). The other
metrics routes — `GET /snapshot` and `GET /metrics/health` — are unauthenticated and readable
by anyone; the token only gates the destructive reset action.

```typescript
// src/routes/metrics.ts (POST /metrics/reset, lines ~123-146)
const adminToken = process.env.METRICS_ADMIN_TOKEN;
if (!adminToken) {
  // Token not configured in this environment: the endpoint is disabled, not open.
  res.status(501).json({ status: "error", error: "Metrics reset not configured" });
  return;
}

const authHeader = req.headers.authorization || "";
const [scheme, token] = authHeader.split(" ");

if (scheme !== "Bearer" || token !== adminToken) {
  res.status(403).json({ status: "error", error: "Unauthorized" });
  return;
}
```

Note the real response shape is `{ status: "error", error: "Unauthorized" }` on a 403, not
`{ error: "FORBIDDEN" }`, and if `METRICS_ADMIN_TOKEN` is unset the endpoint returns `501`
rather than allowing the reset.

**Generate Secure Token:**
```bash
openssl rand -base64 32
# Store in .env as METRICS_ADMIN_TOKEN
```

---

## 4. Data Protection

### Encryption in Transit

**HTTPS Required (Production)**

```nginx
server {
    listen 443 ssl http2;
    
    ssl_certificate /etc/ssl/certs/cert.pem;
    ssl_certificate_key /etc/ssl/private/key.pem;
    
    # Strong cipher suite
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_protocols TLSv1.2 TLSv1.3;
    
    # HSTS
    add_header Strict-Transport-Security "max-age=31536000" always;
}
```

**Generate Certificate:**
```bash
# Let's Encrypt (free)
certbot certonly --standalone -d api.example.com

# Or self-signed (testing only)
openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365
```

### Encryption at Rest

**Cache File** (optional, contains only simulation results)

```bash
# Encrypt cache file
openssl enc -aes-256-cbc -in cache.json -out cache.json.enc
```

**Database** (PostgreSQL encryption)

```sql
-- Enable pg_crypto extension
CREATE EXTENSION pgcrypto;

-- Encrypt sensitive columns
ALTER TABLE simulations ADD COLUMN encrypted_query TEXT;
UPDATE simulations 
SET encrypted_query = pgp_sym_encrypt(query, 'secret_key');
```

### Secret Management

**Current implementation: plain environment variables, no secrets manager.**

There is no `src/lib/secrets.ts` file and `aws-sdk` is not a dependency (confirmed absent from
`package.json`). Secrets are read directly from `process.env` wherever they're needed, e.g.:

```typescript
// src/lib/llmResolver.ts
return process.env[provider.apiKeyEnvVar] || process.env.LLM_API_KEY;
// ...
return process.env.OPENAI_API_KEY || process.env.LLM_API_KEY;

// src/routes/metrics.ts
const adminToken = process.env.METRICS_ADMIN_TOKEN;
```

The full list of expected environment variables (`GROQ_API_KEY`, `OPENROUTER_API_KEY`,
`MISTRAL_API_KEY`, `SILICONFLOW_API_KEY`, `TOKENROUTER_API_KEY`, `LLM_API_KEY`,
`OPENAI_API_KEY`, `METRICS_ADMIN_TOKEN`, etc.) is documented in `.env.example`. In
production these are set as plain process environment variables by whatever deploys the
container/process (e.g. platform env config); nothing in this codebase fetches them from
AWS Secrets Manager, Vault, or any other secrets store.

**Proposed — not yet implemented:** if/when a secrets manager is adopted, the following
is a reasonable shape for it. Treat this as forward guidance, not a description of the
running server.

```bash
# ❌ Never commit secrets
GROQ_API_KEY=gsk_...  # Git will find this!

# ✅ Use secrets manager
aws secretsmanager create-secret --name terrium/groq-api-key
```

```typescript
// PROPOSED — src/lib/secrets.ts does not exist yet; this file and the
// aws-sdk dependency it uses are not part of the codebase today.
import AWS from 'aws-sdk';

const secretsManager = new AWS.SecretsManager();

export async function getSecret(name: string): Promise<string> {
  const result = await secretsManager.getSecretValue({ SecretId: name }).promise();
  return result.SecretString;
}

export async function loadEnv() {
  if (process.env.NODE_ENV === 'production') {
    const groqKey = await getSecret('terrium/groq-api-key');
    process.env.GROQ_API_KEY = groqKey;
  }
}
```

---

## 5. Dependency Security

**Note on package manager:** this workspace uses **pnpm** (`packageManager: "pnpm@11.20.0"`
in the root `package.json`, `pnpm-lock.yaml` committed), not npm — there is no
`package-lock.json` (the root `preinstall` script actively deletes one if it appears).
Commands below are given as `pnpm` equivalents; the `npm audit`/`npm ci` spelling used in
older drafts of this doc would not work correctly against this repo's lockfile.

### Vulnerability Scanning

**Built-in (pnpm audit):**
```bash
pnpm audit
# Shows vulnerabilities and fixes

pnpm audit --fix
# Auto-fixes when possible

pnpm audit --audit-level moderate --prod
# Fail if moderate or higher severity found
```

**CI/CD Integration — not currently implemented.** There is no `.github/workflows/security.yml`
in this repo; the only workflow that runs is `.github/workflows/tests.yml` (see
`TESTING_AND_CI_CD.md`), which does not run a dependency audit step. Adding a dedicated
audit step/workflow is a reasonable proposal, not a description of current CI:

```yaml
# PROPOSED — .github/workflows/security.yml does not exist today
- name: Dependency Audit
  run: pnpm audit --audit-level moderate --prod
```

### Dependency Pinning

**Lock File (pnpm-lock.yaml)**
```bash
# Commit to version control
git add pnpm-lock.yaml
```

**Patch Updates Only (in CI) — proposed, not currently wired into any workflow:**
```yaml
- name: Update Dependencies
  run: pnpm update --latest=false  # Only patch/minor versions per pnpm's default range
```

### Supply Chain Security

**Verify Package Integrity:**
```bash
pnpm install --frozen-lockfile  # Clean install using lock file (used by the real CI's api-server job)
```

**Signed Commits (Optional):**
```bash
git config --global user.signingkey GPG_KEY_ID
git commit -S -m "Security update"
```

---

## 6. Error Handling & Information Disclosure

### Error Message Classification

**User-Safe Errors** (reveal safe info):
```typescript
// ✅ User sees this
{
  "error": "MISSING_REQUIRED_INPUT",
  "message": "Cannot simulate 'sir': beta, gamma could not be resolved..."
}
```

**Internal Errors** (hide implementation details):
```typescript
// ❌ User sees:
{
  "error": "INTERNAL_SERVER_ERROR",
  "message": "An unexpected error occurred"
}

// ✅ Developers see (in logs only):
logger.error({ err }, "Stack trace and details");
```

### Stack Trace Hiding (Production)

```typescript
// src/app.ts - Global error handler
app.use((err: Error, req: Request, res: Response) => {
  // Log full error
  logger.error({ err }, "Unhandled error");
  
  // Send safe response
  const message = process.env.NODE_ENV === 'production'
    ? "Internal server error"
    : err.message;
  
  res.status(500).json({
    error: "INTERNAL_SERVER_ERROR",
    message
  });
});
```

### HTTP Header Security

**Current: no header hardening is implemented in `src/app.ts`.** There is no `helmet`
dependency (confirmed absent from `package.json`), and grepping `src/` finds no
`X-Content-Type-Options`, `X-Frame-Options`, `X-XSS-Protection`, `Content-Security-Policy`,
or `X-Powered-By` handling anywhere. Express's default `X-Powered-By: Express` header is
still sent as-is.

What `src/app.ts` actually does today, top to bottom:
- `pinoHttp` structured request/response logging
- `cors()` with default (permissive) settings
- `express.json()` and `express.urlencoded({ extended: true })` body parsing
- the global in-memory rate limiter (`REQUEST_COUNTS`, 1000 req / 15 min), which sets
  `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset` response headers
- mounts the API router at `app.use("/api", router)`
- a `GET /` landing page route that renders an inline HTML status page
- a global Express error handler that logs the error and returns
  `{ error: "INTERNAL_SERVER_ERROR", message }` with status 500

**Proposed — not yet implemented.** The following is a reasonable hardening pattern to
add (either by hand or via the `helmet` package), but it does not exist in the codebase
today:

```typescript
// PROPOSED — not present in src/app.ts
app.use((req, res, next) => {
  // Remove version info
  res.removeHeader('X-Powered-By');
  
  // Security headers
  res.setHeader('X-Content-Type-Options', 'nosniff');
  res.setHeader('X-Frame-Options', 'DENY');
  res.setHeader('X-XSS-Protection', '1; mode=block');
  res.setHeader('Content-Security-Policy', "default-src 'self'");
  
  next();
});
```

---

## 7. Network Security

### Firewall Rules

```bash
# Allow only from load balancer / reverse proxy
sudo ufw default deny incoming
sudo ufw allow from 10.0.1.0/24 to any port 5000

# Allow SSH for admin
sudo ufw allow 22/tcp

# PostgreSQL (only from API server)
sudo ufw allow from 10.0.0.10 to any port 5432
```

### VPC Security (AWS)

```hcl
# terraform/security_group.tf
resource "aws_security_group" "terrium_api" {
  name = "terrium-api"
  
  # Inbound: Only from ALB
  ingress {
    from_port   = 5000
    to_port     = 5000
    protocol    = "tcp"
    security_groups = [aws_security_group.alb.id]
  }
  
  # Outbound: Allow all (or restrict to specific services)
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
```

### TLS Certificate Validation

```bash
# Verify certificate
openssl s_client -connect api.example.com:443

# Check expiration
echo | openssl s_client -servername api.example.com -connect api.example.com:443 2>/dev/null | openssl x509 -noout -dates
```

---

## 8. Logging & Audit Trail

### Structured Logging

**Current Implementation:** Pino (structured logging)

```typescript
logger.info({ jobId, domain, parameters }, "Simulation started");
// Produces:
// {
//   "level": 30,
//   "time": "2026-08-09T12:34:56Z",
//   "jobId": "abc-123",
//   "domain": "sir",
//   "parameters": {...},
//   "msg": "Simulation started"
// }
```

**Audit Events to Log:**
- ✅ Simulation requests (who, what, when)
- ✅ Parameter changes
- ✅ Errors and exceptions
- ✅ Rate limit violations
- ✅ Database operations

**Don't Log:**
- ❌ Full query text (too large)
- ❌ Sensitive parameters
- ❌ API keys or tokens
- ❌ User email addresses

### Log Retention

```bash
# 14-day retention
logrotate /etc/logrotate.d/terrium

# Archive to S3 after rotation
s3cmd sync /var/log/terrium/ s3://terrium-logs-archive/
```

### Log Integrity (Optional)

```bash
# Log signatures (prevent tampering)
echo "message" | openssl dgst -sha256 -sign key.pem

# Verify
openssl dgst -sha256 -verify pub.pem -signature sig message
```

---

## 9. Security Testing

**Current: none of the code below exists.** There is no `src/__tests__/security.fuzz.test.ts`,
no `fast-check` dependency (confirmed absent from `package.json`), and no `validateQuery` or
`resolveParameters` functions in `src/`. This whole section is **proposed test coverage**, not
a description of tests that run today. The closest real equivalents are the Zod validation in
`src/lib/schemas.ts` (`ResolveBody`) and the parameter-override extraction/validation in
`src/lib/queryResolver.ts` (`extractParameterOverrides`, `ArrayOverrideValidationError`), which
are exercised by `src/__tests__/schemas.test.ts`, `src/__tests__/queryOverrides.test.ts`, and
`src/__tests__/arrayOverride.test.ts` — but none of those tests use fuzzing (`fast-check`) or
target SQL/command-injection payloads by name the way the examples below suggest.

### Input Fuzzing (proposed)

```typescript
// PROPOSED — src/__tests__/security.fuzz.test.ts does not exist
import { fc } from 'fast-check';

it("rejects arbitrary input safely", () => {
  fc.assert(
    fc.property(fc.string(), (input) => {
      expect(() => validateQuery(input)).not.toThrow();
      // Should handle gracefully, not crash
    })
  );
});
```

### SQL Injection Testing (proposed)

```typescript
it("prevents SQL injection", async () => {
  const payloads = [
    "'; DROP TABLE simulations; --",
    "1 OR 1=1",
    "UNION SELECT * FROM users",
  ];
  
  for (const payload of payloads) {
    expect(() => validateQuery(payload)).toThrow();
  }
});
```

### Command Injection Testing (proposed)

```typescript
it("prevents command injection", () => {
  const payloads = [
    "; rm -rf /",
    "| cat /etc/passwd",
    "` whoami `",
  ];
  
  for (const payload of payloads) {
    expect(() => validateQuery(payload)).toThrow();
  }
});
```

### Parameter Pollution (proposed)

```typescript
it("handles duplicate parameters safely", () => {
  // ?beta=0.5&beta=0.3
  // Should use one value, not both
  const result = resolveParameters({ beta: ["0.5", "0.3"] });
  expect(result.beta).toBeDefined();
  expect(typeof result.beta).toBe("number");
});
```

---

## 10. Compliance & Regulations

### GDPR (If Storing User Data)

**Current:** No user data stored, stateless simulations

**If Needed:**
- Implement data deletion (right to be forgotten)
- Track data processing activities
- Obtain explicit consent
- Implement data minimization

### HIPAA (If Processing Medical Data)

**Status:** Not applicable (scientific research, not medical data)

**If Needed:**
- Encryption at rest/transit (AES-256, TLS 1.2+)
- Access controls and audit logs
- Data integrity checks
- Business Associate Agreements (BAAs)

### SOC 2 (If Required by Customers)

**Audit Checklist:**
- ✅ Security: Risk assessments, vulnerability management
- ✅ Availability: Uptime >99.5%, incident response
- ✅ Processing Integrity: Data validation, error handling
- ✅ Confidentiality: Encryption, access controls
- ✅ Privacy: Data handling policies, consent

---

## 11. Incident Response (Security)

### Security Incident Detection

**Monitor for:**
- Unusual error rates
- Rate limit violations
- Failed authentication attempts
- Database query errors
- Resource exhaustion

### Incident Response Plan

1. **Detect** - Alert fires
2. **Contain** - Stop the damage (kill connection, rollback, etc.)
3. **Investigate** - Review logs, identify root cause
4. **Remediate** - Fix the vulnerability
5. **Communicate** - Notify affected users/stakeholders
6. **Document** - Post-mortem and improvements

### Breach Notification

```bash
# If sensitive data exposed:
# 1. Immediately isolate affected systems
# 2. Gather evidence
# 3. Notify users within 72 hours
# 4. Document the incident
# 5. Implement fixes
```

---

## 12. Security Checklist

### Development

- [ ] Input validation on all user inputs
- [ ] No hardcoded secrets
- [ ] No direct SQL queries
- [ ] Error messages don't leak info
- [ ] Logging doesn't log secrets
- [ ] Dependency audit passes
- [ ] Unit tests include security tests

### Deployment

- [ ] HTTPS/TLS configured
- [ ] Secrets loaded from secrets manager
- [ ] Firewall rules configured
- [ ] Rate limiting enabled
- [ ] Logging sent to centralized system
- [ ] Monitoring and alerting set up
- [ ] Backups encrypted and tested

### Operations

- [ ] Security patches applied within 30 days
- [ ] Access logs reviewed weekly
- [ ] Vulnerability scans run monthly
- [ ] Disaster recovery tested quarterly
- [ ] Security training for team
- [ ] Incident response plan documented

---

## 13. Security Tools & Configuration

### Automated Scanning

```bash
# OWASP Dependency Check
npm install -g dependency-check
dependency-check --scan .

# Container scanning (if using Docker)
docker scan terrium-api:latest

# SAST (Static Application Security Testing)
npm install -g semgrep
semgrep --config=p/security-audit src/
```

### Manual Testing

```bash
# Penetration testing (local)
npm install -g artillery
artillery quick --count 100 http://localhost:5000/api/simulate

# OWASP ZAP (Web Application Firewall testing)
docker run -t owasp/zap2docker-stable \
  zap-baseline.py -t http://localhost:5000
```

---

## 14. Security Best Practices Summary

| Practice | Implementation | Benefit |
|----------|-----------------|---------|
| **Input Validation** | Zod schemas on all inputs | Prevents injection attacks |
| **Rate Limiting** | 1000 req/15min global | Prevents DDoS and abuse |
| **Encryption** | TLS in transit, at-rest optional | Protects data confidentiality |
| **Secrets Management** | Plain `process.env` vars today; AWS Secrets Manager is a proposal, not yet implemented | Prevents credential exposure |
| **Dependency Scanning** | Manual `pnpm audit`; not yet wired into CI/CD | Catches known vulnerabilities |
| **Error Handling** | User-safe errors, detailed logs | Prevents information disclosure |
| **Network Isolation** | Firewall and VPC rules | Limits attack surface |
| **Audit Logging** | Structured logs, 14-day retention | Enables investigation |
| **Access Control** | API keys, rate limiting per-user | Prevents unauthorized use |
| **Incident Response** | Playbook documented | Minimizes damage |

---

## References

- OWASP Top 10: https://owasp.org/www-project-top-ten/
- OWASP Dependency Check: https://owasp.org/www-community/attacks/Attack_on_the_Supply_Chain
- CWE Top 25: https://cwe.mitre.org/top25/
- Node.js Security Best Practices: https://nodejs.org/en/docs/guides/security/

---

**Security Review Date:** August 9, 2026  
**Next Review:** November 9, 2026 (quarterly)  
**Owner:** Security team
