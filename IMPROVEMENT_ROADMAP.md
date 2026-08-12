> **⚠️ CORRECTION (2026-08-11):** the Phase-1 checklist below marks "✅ Advanced Export (CSV/JSON/BibTeX/PDF)" as done. It isn't — `src/storage/job-database.ts` exposes only `saveJob/getJob/getAllJobs/getRecentJobs/getJobsByStatus/getJobsByQuery/getStatistics`; no export/CSV/BibTeX method exists anywhere in that file or elsewhere in `src/storage/`. Treat that checkbox as aspirational, not complete, until an actual export function is added.

# Terrium Improvement Roadmap

**Goal:** Transform from MVP to production-grade scientific platform  
**Timeline:** Prioritized by impact and complexity

---

## 🔥 Phase 1: High-Impact Immediate Wins (Next 2-4 hours)

### 1.1 Parameter Sweep Engine ⭐⭐⭐
**Impact:** Enables exploration of parameter space  
**Complexity:** Medium

```bash
# CLI: Sweep Km from 1-10 mM
npm run cli -- sweep "michaelis-menten" --km 1:10:0.5 --vmax 12.8 --s0 10

# Web: Add "📊 Parameter Sweep" button
# Shows grid of results: Km vs final substrate value
```

**Implementation:**
- Add `sweep()` function to ScientificPipeline
- New CLI command: `npm run cli -- sweep`
- New API endpoint: `POST /api/sweep`
- Web dashboard visualization (heatmap)

### 1.2 Batch Job Processing ⭐⭐⭐
**Impact:** Run multiple simulations in parallel  
**Complexity:** Medium

```bash
# CLI: Run 5 simulations in batch
npm run cli -- batch "michaelis-menten" \
  --km 5.2,5.5,5.8,6.1,6.4 \
  --vmax 12.8 --s0 10

# API: POST /api/batch with array of parameters
```

**Implementation:**
- Add `batch()` function to pipeline
- Job queue management (process 3 at a time)
- Progress tracking (2/5 jobs complete)
- CSV export of results

### 1.3 Database Persistence ⭐⭐
**Impact:** Preserve job history across restarts  
**Complexity:** Low-Medium

**Use SQLite for simplicity:**
```typescript
// Store: jobId, query, parameters, result, timestamp
// Query: GET /api/jobs/history (list all jobs)
//        GET /api/jobs/:jobId (retrieve specific)
```

**Implementation:**
- Add `npm install sqlite3` (or better-sqlite3)
- Migrations script to create tables
- Update server.ts to persist to DB instead of Map
- Add `/api/jobs/history` endpoint

### 1.4 Advanced Results Export ⭐⭐
**Impact:** Make results actionable (research, reporting)  
**Complexity:** Low

**Formats to support:**
- CSV (trajectory data)
- JSON (full job data + metadata)
- BibTeX (literature citations)
- PDF report (summary + charts)

**Implementation:**
- Add `/api/jobs/:jobId/export?format=csv|json|bibtex|pdf`
- Use existing libraries (papaparse, pdfkit)

---

## 📈 Phase 2: Scientific Enhancement (4-8 hours)

### 2.1 Multi-Model Comparison ⭐⭐⭐
**Impact:** Compare which kinetic model fits best  
**Complexity:** Medium

```bash
# Run same parameters across all 4 models
npm run cli -- compare "michaelis-menten,competitive,non-competitive,product" \
  --km 5.2 --vmax 12.8 --s0 10
```

**Output:** Side-by-side trajectories + fit quality scores

### 2.2 Sensitivity Analysis ⭐⭐⭐
**Impact:** Understand which parameters matter most  
**Complexity:** Medium

```bash
# How sensitive is final value to ±10% change in each parameter?
npm run cli -- sensitivity "michaelis-menten" \
  --km 5.2 --vmax 12.8 --s0 10 \
  --variation 10
```

**Output:** Parameter importance ranking

### 2.3 Literature Search Enhancement ⭐⭐
**Impact:** Better integration with scientific databases  
**Complexity:** Medium

**Add:**
- BRENDA enzyme database (kinetic constants)
- PubChem for substrate info
- More sophisticated query building
- Citation network analysis

### 2.4 Model Validation Against Literature ⭐⭐
**Impact:** Verify results are scientifically sound  
**Complexity:** Medium

**Add:**
- Extract kinetic parameters from papers (OCR/NLP)
- Compare user parameters to literature ranges
- Flag outliers with explanations
- Suggest better parameter values

---

## 🎨 Phase 3: User Experience Enhancement (3-6 hours)

### 3.1 Enhanced Dashboard ⭐⭐⭐
**Impact:** Make system more discoverable and intuitive  
**Complexity:** Low-Medium

**Add:**
- Example scenarios (pre-filled forms)
- Quick-start wizard
- Results history sidebar
- Parameter recommendations
- Export buttons on results table

### 3.2 Real-Time WebSocket Updates ⭐⭐
**Impact:** Live progress without polling  
**Complexity:** Medium

**Current:** Poll every 1 second  
**Better:** Server pushes updates via WebSocket

### 3.3 Dark Mode + Themes ⭐
**Impact:** Better UX, accessibility  
**Complexity:** Low

**Add:**
- Dark/light toggle
- High contrast mode
- Colorblind-friendly palettes

### 3.4 Mobile-First Responsive Design ⭐
**Impact:** Use on phone/tablet  
**Complexity:** Low

**Current:** Desktop-focused  
**Better:** Touch-friendly, mobile optimized

---

## 🔧 Phase 4: DevOps & Deployment (2-4 hours)

### 4.1 Docker & Compose ⭐⭐⭐
**Impact:** One-command deployment  
**Complexity:** Low

```bash
docker-compose up
# http://localhost:3000
```

**Files:**
- Dockerfile (Node + TypeScript)
- docker-compose.yml (web + sqlite)

### 4.2 GitHub Actions CI/CD ⭐⭐
**Impact:** Automated testing on push  
**Complexity:** Low

**Add:**
- Test on every commit
- Type-check, lint, test
- Build Docker image
- Push to registry

### 4.3 Kubernetes Deployment ⭐
**Impact:** Production-grade scaling  
**Complexity:** Medium-High

### 4.4 Monitoring & Observability ⭐⭐
**Impact:** Production visibility  
**Complexity:** Medium

**Add:**
- Prometheus metrics
- Health check endpoint
- Error tracking (Sentry)
- Performance profiling

---

## 🏆 Phase 5: Advanced Features (6-12 hours)

### 5.1 Machine Learning Model Fitting ⭐⭐⭐
**Impact:** Auto-fit kinetic models to experimental data  
**Complexity:** High

**Use Python backend + Node wrapper:**
```python
# scipy.optimize for curve fitting
# Input: experimental data (time, concentration)
# Output: fitted Km, Vmax, Ki, Kp values
```

### 5.2 Differential Equation Solver Options ⭐⭐
**Impact:** More sophisticated simulations  
**Complexity:** High

**Current:** Tellurium (good for kinetics)  
**Add:** SciPy ODE solver for complex systems

### 5.3 Multi-Substrate Simulations ⭐⭐
**Impact:** Handle competitive substrates  
**Complexity:** High

### 5.4 Enzyme Inhibition Library ⭐⭐
**Impact:** Pre-built common inhibitors  
**Complexity:** Low-Medium

```javascript
const inhibitors = {
  'competitive': { type: 'competitive', Ki: 2.5 },
  'non-competitive': { type: 'non-competitive', Ki: 5.0 },
  'product': { type: 'product', Kp: 3.2 }
};
```

---

## 📊 Implementation Priority Matrix

```
IMPACT (↑) vs EFFORT (→)

HIGH IMPACT,    │
LOW EFFORT      │  ✓ 1.1 Sweep
                │  ✓ 1.2 Batch  
                │  ✓ 1.3 Database
                │  ✓ 1.4 Export
                │  ✓ 2.1 Compare
                │  ✓ 4.1 Docker
                │
MEDIUM IMPACT,  │  2.2 Sensitivity
MEDIUM EFFORT   │  2.3 Literature
                │  3.1 Dashboard
                │  4.2 CI/CD
                │  5.1 ML Fitting
                │
LOW IMPACT      │  3.3 Dark Mode
HIGH EFFORT     │  3.2 WebSocket
                │  5.2 ODE Solver
────────────────┴──────────────────
```

**Recommend doing in this order:**
1. **Phase 1** (2-4 hrs) — Sweep + Batch + Database + Export = 4 high-impact features
2. **Phase 3** (3 hrs) — Dashboard enhancement + Mobile responsive
3. **Phase 2** (4 hrs) — Model comparison + Sensitivity analysis
4. **Phase 4** (2 hrs) — Docker + CI/CD for deployment

---

## 🎯 Success Metrics

**After Phase 1 complete:**
- [ ] Can run parameter sweeps (10 simulations)
- [ ] Can process batch jobs (5 simultaneous)
- [ ] Jobs persist across server restarts
- [ ] Can export results as CSV/JSON/BibTeX
- [ ] Test coverage stays at 84%+
- [ ] Zero regressions in existing tests

**After Phase 2 complete:**
- [ ] Can compare 4 kinetic models side-by-side
- [ ] Sensitivity analysis shows parameter importance
- [ ] Literature integration improved
- [ ] Results validated against literature ranges

**After Phase 3 complete:**
- [ ] Mobile-responsive design
- [ ] Real-time WebSocket updates
- [ ] Dark mode available
- [ ] 95%+ user satisfaction (hypothetical)

**After Phase 4 complete:**
- [ ] Docker deployment one-command
- [ ] GitHub Actions CI/CD green
- [ ] Prometheus metrics exposed
- [ ] Production-ready monitoring

---

## 💡 Quick Wins (Can Do Today)

1. **Parameter Sweep** (1 hour)
   - Add `/api/sweep` endpoint
   - Add `--sweep` CLI flag
   - Simple grid visualization

2. **Batch Processing** (1 hour)
   - Handle array of parameters
   - Process 3 at a time (simple queue)
   - Return results array

3. **Database Persistence** (1.5 hours)
   - SQLite storage
   - Migrate jobs from Map to DB
   - Add job history endpoint

4. **Export to CSV/JSON** (1 hour)
   - Trajectory data as CSV
   - Full result as JSON
   - Download buttons on dashboard

**Total: 4.5 hours → 4 major features**

---

## 🚀 Let's Start With Phase 1

All quick wins that have massive impact on usability:

1. ✅ Parameter sweeps
2. ✅ Batch jobs
3. ✅ Persistent storage
4. ✅ Advanced export

These make Terrium from "interesting research tool" to "genuinely useful platform."
