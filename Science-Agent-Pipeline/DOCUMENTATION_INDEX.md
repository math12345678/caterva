# Caterva Documentation Index & Navigation Guide

**Last Updated:** August 9, 2026  
**Total Documentation:** 7,326 lines across the 14 documents listed below with line counts (counted directly via `wc -l` on 2026-08-10; an earlier version of this line claimed 19,300+ lines, roughly 2.6x the real total, and every per-document figure above was also inflated -- e.g. BACKEND_ARCHITECTURE.md claimed 2500 lines against a real 582).  
**Status:** Complete, production-ready

---

## Quick Start by Role

### 👨‍🔬 Researcher / Scientist
**Goal:** Run simulations and analyze results

**Start here:** 
1. **API_USER_GUIDE.md** (5 min read) — Getting started, query syntax, understanding results
2. **INTEGRATION_EXAMPLES.md** → Python examples (10 min) — Code you can copy/paste
3. Run your first simulation using the cURL example
4. Return to API_USER_GUIDE.md for troubleshooting as needed

**Total time to first result:** ~30 minutes

---

### 💻 Backend Developer
**Goal:** Understand, maintain, or extend the system

**Learning Path:**
1. **DEVELOPER_QUICK_START.md** (10 min) — Overview, file structure, common tasks
2. **BACKEND_ARCHITECTURE.md** (30 min) — Understand system design, all components
3. **ADR_0007** (10 min) — How Python/TypeScript boundary works (critical to understand)
4. **ADR_0008** (10 min) — Parameter provenance tracking system
5. **INTEGRATION_EXAMPLES.md** → Python examples (20 min) — See how to build on the API
6. Make your first code change, run tests: `npm test`
7. **ADR_0003** and **ADR_0022** — Reference as you work

**Total time to productive:** ~2 hours

---

### 🚀 DevOps / SRE
**Goal:** Deploy, operate, monitor the system

**Learning Path:**
1. **DEPLOYMENT_GUIDE.md** (20 min) — Choose your deployment option (single, Docker, K8s)
2. Deploy using your chosen option
3. **OPERATIONS_RUNBOOK.md** (20 min) — Know the playbooks before they're needed
4. **SECURITY_HARDENING.md** → Deployment section (10 min) — Security checklist
5. Set up monitoring (see DEPLOYMENT_GUIDE.md → Monitoring section)
6. Run through post-deployment checklist in DEPLOYMENT_GUIDE.md

**Total time to production deployment:** ~1.5 hours

---

### 🔐 Security Engineer / Auditor
**Goal:** Ensure system is secure and compliant

**Learning Path:**
1. **SECURITY_HARDENING.md** (45 min) — Complete security review
2. **DEPLOYMENT_GUIDE.md** → Security Hardening section (10 min) — Deployment security
3. **OPERATIONS_RUNBOOK.md** → Security Incidents section (5 min) — Incident response
4. **BACKEND_ARCHITECTURE.md** → Error Handling section (10 min) — Information disclosure prevention
5. Review TESTING_AND_CI_CD.md → Security Testing section (10 min)

**Total time for audit:** ~1.5 hours

---

### 📊 QA / Release Engineer
**Goal:** Test, validate, release with confidence

**Learning Path:**
1. **TESTING_AND_CI_CD.md** (30 min) — Test strategy, running tests, CI/CD setup
2. **OPERATIONS_RUNBOOK.md** → Post-Incident Actions (10 min) — Release checklist
3. Run full test suite: `npm test`
4. Create pre-release checklist from DEPLOYMENT_GUIDE.md → Post-Deployment Checklist
5. Review PERFORMANCE_GUIDE.md → Benchmarking section (optional)

**Total time to release readiness:** ~1 hour

---

### 📈 Product / Business
**Goal:** Understand capabilities, limitations, roadmap

**Learning Path:**
1. **BACKEND_AUDIT_SUMMARY.md** (15 min) — What was built, what was fixed
2. **BACKEND_ARCHITECTURE.md** → Overview section (10 min) — What the system does
3. **API_USER_GUIDE.md** → Example Queries by Discipline (10 min) — What's possible
4. **PERFORMANCE_GUIDE.md** → Current Baseline (5 min) — Performance characteristics
5. **DEPLOYMENT_GUIDE.md** → Cost Estimation (5 min) — Infrastructure costs

**Total time for overview:** ~45 minutes

---

## Document Reference Guide

### Architecture & Design Documents

#### **BACKEND_ARCHITECTURE.md** (582 lines)
**What:** Complete system design, all components, interactions  
**Read when:** You need to understand how the system works  
**Key sections:**
- High-Level Flow — Request → result lifecycle
- System Architecture — 9 major layers
- The 16-Domain System — Classification of domains
- Two-Path Resolution — LLM vs keyword fallback
- Three-Layer Validation — HTTP, TypeScript, Python
- Key Design Patterns — Defensive programming, provenance tracking
- File Structure — Where to find what

**Time:** 40 minutes (thorough), 15 minutes (skim)  
**Prerequisites:** None

---

#### **ADR_0003_Layer_Separation.md** (47 lines)
**What:** Why shape validation is in TypeScript, science bounds in Python  
**Read when:** Understanding separation of concerns, adding new domains  
**Key insight:** Two layers cannot drift because each has ONE job

**Time:** 10 minutes  
**Prerequisites:** None

---

#### **ADR_0007_Python_TypeScript_Boundary_Contract.md** (103 lines)
**What:** How Python DISPATCH and TypeScript types stay synchronized  
**Read when:** Adding a new domain, understanding contract tests  
**Key sections:**
- The 16 Domains — Categorized and listed
- Contract Points — What must match between layers
- Verification Checklist — How to add a domain safely
- Automated Test Enforcement — Why tests will block if drift occurs

**Time:** 15 minutes  
**Prerequisites:** ADR_0003 (helpful but not required)

---

#### **ADR_0008_Parameter_Provenance.md** (211 lines)
**What:** How every parameter is tracked: where it came from, confidence level  
**Read when:** Understanding results, implementing parameter resolution  
**Key sections:**
- Four Origins — user, resolved, llm, default
- Critical Design Decisions — Why each choice was made
- Verification Layers — Four points where provenance is validated
- Usage for API Consumers — How to interpret provenance

**Time:** 20 minutes  
**Prerequisites:** None

---

#### **ADR_0022_ODE_Oscillator_Domains.md** (234 lines)
**What:** Why Lotka-Volterra, cell_cycle_oscillator, repressilator were added  
**Read when:** Working with these domains, understanding domain design  
**Key sections:**
- Why These Three — Pedagogical importance and literature backing
- Parameter Philosophy — Tunable vs fixed parameters
- Implementation — How they're added to Python/TypeScript

**Time:** 15 minutes  
**Prerequisites:** ADR_0007 (helpful but not required)

---

#### **BACKEND_AUDIT_SUMMARY.md** (322 lines)
**What:** Executive summary of audit work, bugs fixed, documentation created  
**Read when:** Understanding what was accomplished, getting high-level overview  
**Key sections:**
- Issues Found & Fixed — 7 bugs, now resolved
- Architecture Highlights — Key insights about design
- Test Results — 404/404 passing
- Deployment Notes — Recommendations for going live

**Time:** 15 minutes  
**Prerequisites:** None

---

### Operations Documents

#### **DEPLOYMENT_GUIDE.md** (871 lines)
**What:** How to deploy Caterva in production  
**Read when:** Ready to deploy, need to choose deployment option  
**Key sections:**
- Three Deployment Options — Single server, Docker, Kubernetes
- Environment Configuration — All config variables explained
- Database Setup — PostgreSQL installation and migration
- System Service Setup — systemd configuration
- Monitoring — Health checks, Prometheus, Grafana
- Load Balancer — Nginx configuration
- Backup & Disaster Recovery — Backup procedures, restore
- Scaling Considerations — Vertical vs horizontal
- Cost Estimation — Budget planning for each option

**Time:** 45 minutes (one option), 90 minutes (all three)  
**Prerequisites:** Linux/DevOps experience helpful

---

#### **OPERATIONS_RUNBOOK.md** (726 lines)
**What:** How to operate the system, respond to incidents  
**Read when:** System is live, something goes wrong  
**Key sections:**
- Incident Severity Levels — P1-P4 classification
- Quick Diagnostics — 3-step health check
- Common Incidents — 8 detailed scenarios with fixes
- Maintenance Tasks — Daily, weekly, monthly, quarterly
- Escalation Procedures — Who to call
- On-Call Handoff — Shift change procedures

**Time:** 20 minutes (skim), 60 minutes (memorize)  
**Prerequisites:** System knowledge from BACKEND_ARCHITECTURE.md

---

#### **TESTING_AND_CI_CD.md** (732 lines)
**What:** How to test, verify, release the system  
**Read when:** Writing tests, setting up CI/CD, preparing release  
**Key sections:**
- Test Strategy — Unit, integration, contract, golden file, literature tests
- Running Tests — Full suite, quick smoke, watch mode, coverage
- Test Categories — What each test type does
- CI/CD Workflow — GitHub Actions configuration
- Performance Testing — Load testing with wrk
- Release Checklist — Pre-release, during, post-release

**Time:** 40 minutes  
**Prerequisites:** Software testing knowledge

---

### Development Documents

#### **DEVELOPER_QUICK_START.md** (498 lines)
**What:** Quick reference for common development tasks  
**Read when:** First time working on the codebase, doing routine work  
**Key sections:**
- 5-Minute Setup — Get running locally
- Common Tasks — Add domain, fix bug, run tests, debug
- Key Files to Know — Where things live
- Environment Variables — Configuration reference
- Testing Strategy — Before committing
- Quick Reference — Common commands

**Time:** 20 minutes (first read), 5 minutes (reference)  
**Prerequisites:** Node.js/TypeScript knowledge

---

#### **PERFORMANCE_GUIDE.md** (485 lines)
**What:** How to understand and improve performance  
**Read when:** System is slow, need to optimize, planning scale  
**Key sections:**
- Performance Profile — Current baseline numbers
- Optimization Opportunities — Tier 1 (high-impact), Tier 2 (medium), Tier 3 (complex)
- Monitoring & Profiling — Tools and techniques
- Caching Strategy — Current + future improvements
- Load Testing — wrk setup and scenarios
- Scaling Strategies — Single server → multi-server

**Time:** 45 minutes (learn), 90 minutes (implement)  
**Prerequisites:** Backend performance knowledge

---

### Security Document

#### **SECURITY_HARDENING.md** (920 lines)
**What:** Complete security guide for the system  
**Read when:** Deploying to production, audit, considering security  
**Key sections:**
- Threat Model — What we're protecting against
- Input Validation — SQL injection, command injection prevention
- Rate Limiting — DDoS protection
- Authentication/Authorization — If needed in future
- Data Protection — Encryption in transit/at rest
- Dependency Security — Vulnerability scanning
- Error Handling — Information disclosure prevention
- Network Security — Firewall, VPC, TLS
- Logging & Audit Trail — What to log, retention
- Security Testing — Fuzzing, injection tests
- Compliance — GDPR, HIPAA, SOC 2 (if needed)
- Incident Response — Security breach playbook

**Time:** 60 minutes (thorough), 20 minutes (checklist)  
**Prerequisites:** Security knowledge helpful

---

### User-Facing Documents

#### **API_USER_GUIDE.md** (706 lines)
**What:** How to use Caterva as a researcher  
**Read when:** First time using the API, debugging query  
**Key sections:**
- Getting Started — 5-minute quick start
- Understanding Results — Trajectory, parameters, provenance
- Query Syntax — By domain (SIR, LV, Wright-Fisher, etc.)
- Common Workflows — Parameter sweep, reproducibility, literature lookup
- Interpreting Results — What SIR curves mean, how to use them
- Troubleshooting & FAQ — Common issues and fixes
- Best Practices — How to use responsibly in research
- Advanced Usage — Streaming, cancellation, batch jobs
- Examples by Discipline — Epidemiology, ecology, genetics, etc.

**Time:** 30 minutes (first read), 5 minutes (reference)  
**Prerequisites:** Domain knowledge (biology, chemistry, etc.)

---

#### **INTEGRATION_EXAMPLES.md** (889 lines)
**What:** Working code examples to build on Caterva  
**Read when:** Integrating Caterva into your application  
**Key sections:**
- Quick Patterns — Sync, async, streaming (3 languages each)
- Data Processing — DataFrame operations, analysis
- Visualization — Matplotlib, Chart.js examples
- Parameter Extraction — Using provenance, documenting for publication
- Batch Processing — Parameter sweeps, parallel simulation
- Error Handling — Graceful degradation, retry logic
- Deployment Integration — Flask, Docker, Docker Compose
- Testing — pytest examples
- Rate Limiting — Respecting limits, monitoring headers
- Complete Application — End-to-end research workflow

**Time:** 30 minutes (skim), 2 hours (study)  
**Prerequisites:** Programming knowledge (Python, JavaScript, or R)

---

## Topic-Based Index

### Adding a New Feature

**Step 1:** Read how similar features work  
→ Search BACKEND_ARCHITECTURE.md for relevant component

**Step 2:** Understand design patterns  
→ BACKEND_ARCHITECTURE.md → Key Design Patterns section

**Step 3:** Check if there are architectural constraints  
→ Review relevant ADR (0003, 0007, 0008, 0022)

**Step 4:** Add the feature  
→ Follow DEVELOPER_QUICK_START.md → "Adding a New Domain" or equivalent

**Step 5:** Test thoroughly  
→ TESTING_AND_CI_CD.md → Test Categories section

**Step 6:** Document  
→ Update relevant ADR or BACKEND_ARCHITECTURE.md

---

### Debugging a Problem

**Step 1:** Identify what's not working  
→ Run `npm test` to see if test failure

**Step 2:** Reproduce locally  
→ DEVELOPER_QUICK_START.md → "Debugging Tips"

**Step 3:** Check logs  
→ DEVELOPER_QUICK_START.md → "View Logs" section

**Step 4:** Trace the code path  
→ BACKEND_ARCHITECTURE.md → High-Level Flow section to understand flow

**Step 5:** Look for similar issues  
→ OPERATIONS_RUNBOOK.md → Common Incidents section

**Step 6:** Fix and test  
→ TESTING_AND_CI_CD.md → Running Tests section

---

### Deploying to Production

**Step 1:** Choose deployment option  
→ DEPLOYMENT_GUIDE.md → Deployment Options (choose 1 of 3)

**Step 2:** Configure environment  
→ DEPLOYMENT_GUIDE.md → Environment Configuration section

**Step 3:** Set up database (if using)  
→ DEPLOYMENT_GUIDE.md → Database Setup section

**Step 4:** Deploy  
→ Follow instructions for your chosen option

**Step 5:** Verify it's working  
→ DEPLOYMENT_GUIDE.md → Health Checks & Monitoring section

**Step 6:** Set up operations  
→ OPERATIONS_RUNBOOK.md → Quick Diagnostics section
→ DEPLOYMENT_GUIDE.md → Post-Deployment Checklist

---

### Responding to an Incident

**Step 1:** Assess severity  
→ OPERATIONS_RUNBOOK.md → Incident Severity Levels

**Step 2:** Do quick diagnostics  
→ OPERATIONS_RUNBOOK.md → Quick Diagnostics section

**Step 3:** Follow incident playbook  
→ OPERATIONS_RUNBOOK.md → Common Incidents & Fixes section

**Step 4:** After resolution  
→ OPERATIONS_RUNBOOK.md → Post-Incident Actions section

---

### Optimizing Performance

**Step 1:** Measure current performance  
→ PERFORMANCE_GUIDE.md → Performance Profile section

**Step 2:** Identify bottleneck  
→ PERFORMANCE_GUIDE.md → Monitoring & Profiling section

**Step 3:** Pick optimization  
→ PERFORMANCE_GUIDE.md → Optimization Opportunities (Tier 1, 2, or 3)

**Step 4:** Implement  
→ INTEGRATION_EXAMPLES.md → relevant code example

**Step 5:** Measure improvement  
→ PERFORMANCE_GUIDE.md → Benchmarking section

---

### Using in Research

**Step 1:** Understand the API  
→ API_USER_GUIDE.md → Getting Started section

**Step 2:** Write your first query  
→ API_USER_GUIDE.md → Query Syntax section

**Step 3:** Interpret results  
→ API_USER_GUIDE.md → Understanding Results section

**Step 4:** Check provenance  
→ API_USER_GUIDE.md → Parameter Provenance section

**Step 5:** Use best practices  
→ API_USER_GUIDE.md → Best Practices section

**Step 6:** Code integration  
→ INTEGRATION_EXAMPLES.md → Example for your language

---

## File Dependency Graph

```
BACKEND_ARCHITECTURE.md (foundation)
    ↓
    ├→ ADR_0003, 0007, 0008, 0022 (specific design decisions)
    ├→ DEVELOPER_QUICK_START.md (daily work)
    ├→ TESTING_AND_CI_CD.md (how to verify)
    ├→ PERFORMANCE_GUIDE.md (how to optimize)
    └→ SECURITY_HARDENING.md (how to secure)

DEPLOYMENT_GUIDE.md (operations baseline)
    ↓
    ├→ OPERATIONS_RUNBOOK.md (incident response)
    └→ SECURITY_HARDENING.md (deployment security)

API_USER_GUIDE.md (user guide)
    ↓
    └→ INTEGRATION_EXAMPLES.md (code patterns)

All documents
    ↓
    └→ BACKEND_AUDIT_SUMMARY.md (executive overview)
```

---

## Reading Time Matrix

| Document | Skim | Learn | Master |
|----------|------|-------|--------|
| BACKEND_ARCHITECTURE.md | 15 min | 40 min | 2 hours |
| DEVELOPER_QUICK_START.md | 5 min | 20 min | 1 hour |
| API_USER_GUIDE.md | 10 min | 30 min | 2 hours |
| DEPLOYMENT_GUIDE.md | 15 min | 45 min | 2 hours |
| OPERATIONS_RUNBOOK.md | 10 min | 30 min | 3 hours |
| PERFORMANCE_GUIDE.md | 15 min | 45 min | 3 hours |
| SECURITY_HARDENING.md | 15 min | 60 min | 3 hours |
| INTEGRATION_EXAMPLES.md | 15 min | 60 min | 4 hours |
| ADRs (each) | 5 min | 15 min | 1 hour |

**Total time:**
- Skim everything: 2 hours
- Learn everything: 8 hours
- Master everything: 24 hours

**Recommended approach:** Skim all (2 hours), then dive deep into your role-specific docs (2-3 hours)

---

## Finding Answers by Topic

**Can't find what you need? Use this index:**

| Topic | Document | Section |
|-------|----------|---------|
| Adding a domain | ADR_0007 | Verification Checklist |
| API endpoints | API_USER_GUIDE.md | Query Syntax |
| Authentication | SECURITY_HARDENING.md | Authentication & Authorization |
| Backups | DEPLOYMENT_GUIDE.md | Backup & Disaster Recovery |
| Batch processing | INTEGRATION_EXAMPLES.md | Batch Processing |
| Benchmarking | PERFORMANCE_GUIDE.md | Benchmarking |
| Caching strategy | PERFORMANCE_GUIDE.md | Caching Strategy |
| Cancellation | API_USER_GUIDE.md | Advanced Usage |
| Configuration | DEPLOYMENT_GUIDE.md | Environment Configuration |
| Costs | DEPLOYMENT_GUIDE.md | Cost Estimation |
| Database setup | DEPLOYMENT_GUIDE.md | Database Setup |
| Debugging | DEVELOPER_QUICK_START.md | Debugging Tips |
| Domain defaults | ADR_0022 | Implementation |
| Domain validation | ADR_0007 | Python/TypeScript Boundary |
| Encryption | SECURITY_HARDENING.md | Data Protection |
| Error handling | BACKEND_ARCHITECTURE.md | Error Handling |
| Firewall rules | DEPLOYMENT_GUIDE.md | Firewall Rules |
| Health checks | DEPLOYMENT_GUIDE.md | Health Checks & Monitoring |
| Integration patterns | INTEGRATION_EXAMPLES.md | Quick Integration Patterns |
| JSON schema | BACKEND_ARCHITECTURE.md | Parameter Validation |
| Kubernetes | DEPLOYMENT_GUIDE.md | Option 3: Kubernetes |
| Load balancer | DEPLOYMENT_GUIDE.md | Load Balancer Setup |
| Load testing | PERFORMANCE_GUIDE.md | Load Test Setup |
| Logging | SECURITY_HARDENING.md | Logging & Audit Trail |
| Memory issues | OPERATIONS_RUNBOOK.md | High Memory Usage |
| Monitoring | DEPLOYMENT_GUIDE.md | Monitoring & Alerts |
| Parameter extraction | INTEGRATION_EXAMPLES.md | Parameter Extraction |
| Parameter provenance | ADR_0008 | Four Origins |
| Performance optimization | PERFORMANCE_GUIDE.md | Optimization Opportunities |
| Python setup | DEPLOYMENT_GUIDE.md | Python Installation |
| Query syntax | API_USER_GUIDE.md | Query Syntax |
| Rate limiting | SECURITY_HARDENING.md | Rate Limiting |
| Results interpretation | API_USER_GUIDE.md | Understanding Results |
| Rollback procedure | OPERATIONS_RUNBOOK.md | Incident Response |
| Scaling | PERFORMANCE_GUIDE.md | Scaling Strategies |
| Security checklist | SECURITY_HARDENING.md | Security Checklist |
| Service setup | DEPLOYMENT_GUIDE.md | System Service Setup |
| SSH access | DEPLOYMENT_GUIDE.md | Network Security |
| Testing strategy | TESTING_AND_CI_CD.md | Testing Strategy |
| Troubleshooting | API_USER_GUIDE.md | Troubleshooting & FAQ |
| TLS/HTTPS | SECURITY_HARDENING.md | Encryption in Transit |
| Visualization | INTEGRATION_EXAMPLES.md | Visualization Examples |

---

## How Documentation is Organized

**4 Layers:**

1. **Strategic** (Why) — ADRs explain architectural decisions
2. **Tactical** (How) — Architecture & Operation guides explain how to build/run
3. **Practical** (Do) — Quick start & Examples show working code
4. **Reference** (Where) — This index helps you find what you need

**Cross-references throughout:** Most documents link to related documents when relevant

---

## Staying Up to Date

**When things change:**
1. Update the relevant document first
2. Update related documents for consistency
3. Update this index if structure changes
4. Review date at top of each document

**Next review dates:**
- BACKEND_ARCHITECTURE.md: August 23, 2026 (quarterly)
- OPERATIONS_RUNBOOK.md: August 16, 2026 (bi-weekly during first month)
- SECURITY_HARDENING.md: November 9, 2026 (quarterly)
- All others: August 23, 2026 (monthly)

---

## Quick Links (For Bookmarking)

**Getting Started:** API_USER_GUIDE.md  
**System Design:** BACKEND_ARCHITECTURE.md  
**Daily Development:** DEVELOPER_QUICK_START.md  
**Operations:** OPERATIONS_RUNBOOK.md  
**Deployment:** DEPLOYMENT_GUIDE.md  
**Security:** SECURITY_HARDENING.md  
**Integration:** INTEGRATION_EXAMPLES.md  
**Architecture Decisions:** ADR_0007.md (critical)  

---

## Support & Questions

**Can't find something?**
1. Use "Finding Answers by Topic" table above
2. Use browser search (Ctrl+F) within a document
3. Check the relevant ADR
4. Ask on the team Slack #engineering channel

**Found an error?**
1. Note the document and section
2. File an issue with "docs:" prefix
3. Include the specific line/section
4. Suggest a fix if possible

---

**Total documentation:** 7,326 lines (see per-document counts above)  
**Last audit:** August 9, 2026  
**Status:** Complete and production-ready  
**Maintained by:** Backend team
