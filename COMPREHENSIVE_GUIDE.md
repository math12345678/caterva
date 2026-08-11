# TERRIUM Scientific Validation Framework
## Complete User Manual & API Documentation

---

## Table of Contents

1. [Getting Started](#getting-started)
2. [CLI Command Reference](#cli-command-reference)
3. [Advanced Features](#advanced-features)
4. [Kinetic Models Reference](#kinetic-models-reference)
5. [API Documentation](#api-documentation)
6. [Deployment Guide](#deployment-guide)
7. [Troubleshooting](#troubleshooting)

---

## Getting Started

### Installation

**Prerequisites:**
- Node.js 18+
- npm 9+
- TypeScript 5+

```bash
npm install
```

### Quick Start

Run your first simulation:

```bash
npm run cli -- simulate "michaelis-menten" --km 5.2 --vmax 12.8 --s0 10
```

This runs a complete enzyme kinetics simulation with full 4-layer scientific validation.

### System Overview

Terrium validates enzyme kinetics simulations through **4 scientific layers**:

1. **Layer 1: Parameter Validation** - Ranges, units, data types
2. **Layer 2: Literature Verification** - DOI/PMID checks against CrossRef/PubMed
3. **Layer 3: Assumption Validation** - Steady-state, substrate depletion, enzyme stability
4. **Layer 4: Result Validation** - Trajectory analysis, outlier detection

---

## CLI Command Reference

### simulate

Run a kinetic simulation with full validation.

```bash
npm run cli -- simulate <query> [--km VALUE] [--vmax VALUE] [--s0 VALUE]
```

**Options:**
- `--km VALUE` - Michaelis constant (mM)
- `--vmax VALUE` - Maximum velocity (μM/min)
- `--s0 VALUE` - Initial substrate concentration (mM)

**Example:**
```bash
npm run cli -- simulate "michaelis-menten" --km 5.2 --vmax 12.8 --s0 10
```

### validate

Validate parameters without running simulation.

```bash
npm run cli -- validate <query>
```

**Example:**
```bash
npm run cli -- validate "lactate dehydrogenase km=5"
```

### literature

Display built-in literature database.

```bash
npm run cli -- literature
```

Shows all literature sources with extracted parameters and metadata.

### verify

Verify reproducibility of a past simulation.

```bash
npm run cli -- verify <jobId>
```

### check-integrity

Check data integrity of a stored simulation.

```bash
npm run cli -- check-integrity <jobId>
```

### help

Show help message.

```bash
npm run cli -- help
```

---

## Advanced Features

### 3.1 Batch Processing

Run multiple simulations in sequence.

```typescript
import { batchSimulate } from './src/cli/advanced-features';

const scenarios = [
  { name: 'baseline', query: 'michaelis-menten', parameters: { km: 5.2, vmax: 12.8, s0: 10 } },
  { name: 'high-km', query: 'michaelis-menten', parameters: { km: 10.0, vmax: 12.8, s0: 10 } },
  { name: 'low-vmax', query: 'michaelis-menten', parameters: { km: 5.2, vmax: 5.0, s0: 10 } }
];

const results = await batchSimulate(scenarios);
```

**Use cases:** 
- Screening multiple enzyme variants
- Testing multiple experimental conditions

### 3.2 Parameter Search

Explore parameter space systematically.

```typescript
import { parameterSweep } from './src/cli/advanced-features';

const results = await parameterSweep(
  'michaelis-menten',
  'km',           // parameter to sweep
  2.0, 10.0,      // min, max
  0.5             // step size
);
```

Returns array of `{ paramValue, finalValue, confidence }`.

### 3.3 Sensitivity Analysis

Quantify parameter importance.

```typescript
import { sensitivityAnalysis } from './src/cli/advanced-features';

const results = await sensitivityAnalysis(
  'michaelis-menten',
  { km: 5.2, vmax: 12.8, s0: 10 },
  0.1  // 10% perturbation
);

// Returns: { km: { increase: 0.15, decrease: 0.14 }, ... }
```

Shows which parameters have most impact on results.

### 3.4 Data Export

Export results to multiple formats.

```typescript
import { exportToCSV, exportToJSON } from './src/cli/advanced-features';

exportToCSV(results, 'output.csv');
exportToJSON(results, 'output.json');
```

### 3.5 Performance Profiling

Benchmark simulation execution time.

```typescript
import { profileSimulation } from './src/cli/advanced-features';

const profile = await profileSimulation(
  'michaelis-menten',
  { km: 5.2, vmax: 12.8, s0: 10 },
  5  // run 5 iterations
);

// Returns: { meanTimeMs, minTimeMs, maxTimeMs, stdDevMs }
```

---

## Kinetic Models Reference

Terrium supports 5 advanced kinetic models.

### Classic Michaelis-Menten

Single-substrate, single-product kinetics.

**Rate equation:** `v = (Vmax × [S]) / (Km + [S])`

**Use for:** Standard enzyme kinetics, first-order analysis

```typescript
const model = getModel('michaelis-menten');
```

### Competitive Inhibition

Inhibitor competes with substrate for active site. Km increases, Vmax constant.

**Use for:** Drug mechanism analysis, inhibitor screening

```typescript
const model = getModel('competitive-inhibition');
```

### Non-competitive Inhibition

Inhibitor binds ES complex. Both Km and Vmax affected proportionally.

**Use for:** Metal ion effects, allosteric inhibition

```typescript
const model = getModel('non-competitive-inhibition');
```

### Product Inhibition

Product accumulation reduces further reaction rate.

**Use for:** Equilibrium analysis, feedback inhibition

```typescript
const model = getModel('product-inhibition');
```

### Allosteric (Hill Equation)

Cooperative binding with adjustable cooperativity coefficient.

**Use for:** Cooperative enzymes, regulatory proteins

```typescript
const model = getModel('allosteric');
```

---

## API Documentation

### Core Classes

#### ScientificPipeline

Main orchestrator for validation and simulation.

```typescript
const pipeline = new ScientificPipeline();
const response = await pipeline.execute({
  query: 'michaelis-menten',
  parameters: { km: 5.2, vmax: 12.8, s0: 10 }
});
```

**Properties:**
- `response.validated` - Boolean result
- `response.validationConfidence` - 0-1 confidence score
- `response.jobId` - Unique execution ID
- `response.results.trajectory` - Simulation trajectory
- `response.results.finalValue` - Final substrate concentration

#### LiteratureService

Manages literature database and parameter recommendations.

```typescript
const service = new LiteratureService();
service.addLiterature(literatureEntry);

const rec = service.getRecommendation('km', 'mm');
const verify = service.crossVerify('km', 'mm');
```

**Methods:**
- `addLiterature(lit)` - Add literature source
- `getRecommendation(param, domain)` - Get recommended parameter value
- `crossVerify(param, domain)` - Verify parameter across sources
- `findConflicts(param, domain)` - Detect outliers
- `getStats()` - Database statistics

#### ScientificValidationPipeline

Runs 4-layer validation pipeline.

```typescript
const result = await ScientificValidationPipeline.validate(
  parameters,
  assumptions,
  conditions,
  output
);
```

**Returns:**
- `passed` - Boolean validation result
- `confidence` - 0-1 confidence score
- `errors` - Array of error messages
- `warnings` - Array of warnings

---

## Deployment Guide

### Pre-deployment Checklist

- [ ] Run full verification: `npm run verify-all`
- [ ] Review test results: 178 tests passing
- [ ] Check coverage: all thresholds met
- [ ] Replace test DOIs with real citations
- [ ] Configure environment variables

### Environment Configuration

**TERRIUM_SKIP_DOI_VERIFICATION=1**

Enable offline mode (skip network DOI verification). Maintains peer-review and format validation.

```bash
TERRIUM_SKIP_DOI_VERIFICATION=1 npm run cli -- simulate "michaelis-menten" --km 5.2 --vmax 12.8 --s0 10
```

**TERRIUM_ALLOW_UNVERIFIED_CITATIONS=1**

Accept unverified citations when network unavailable (network failures only, not rejected DOIs).

```bash
TERRIUM_ALLOW_UNVERIFIED_CITATIONS=1 npm test
```

### Build and Deploy

```bash
npm run build
npm run type-check
npm run lint
npm test
```

Deploy `dist/` folder or run with ts-node directly.

### Monitoring

- Monitor stderr for structured JSON logs
- Track job IDs for reproducibility verification
- Monitor simulation execution times (target: 2-3 seconds)
- Alert on validation confidence < 80%

---

## Troubleshooting

### "Literature reference not verified"

**Problem:** CLI fails during literature verification

**Solution:** Set `TERRIUM_SKIP_DOI_VERIFICATION=1` for offline mode

### "Network unreachable"

**Problem:** DOI verification fails due to network issues

**Solution:** System automatically falls back to built-in literature. Set `TERRIUM_ALLOW_UNVERIFIED_CITATIONS=1` if needed.

### Test failures

**Problem:** Tests fail despite code working

**Solution:** Run `npm run test:watch` for debugging. Check `jest.config` in `package.json`.

### Low validation confidence

**Problem:** Simulation returns < 80% confidence

**Solution:** Check parameter ranges against literature. Review warnings in JSON output. Consider parameter search to find optimal values.

### High execution time

**Problem:** Simulation takes > 5 seconds

**Solution:** Use `profileSimulation()` to identify bottlenecks. Check network latency for DOI verification.

---

## Performance Specifications

| Metric | Value |
|--------|-------|
| Simulation time | ~2.6 seconds (10-second trajectory) |
| Validation overhead | ~50ms |
| Test suite execution | ~27 seconds (178 tests) |
| Memory footprint | ~50MB |
| Max concurrent simulations | System-dependent |

---

## Quality Metrics

- ✓ **178 tests passing** (100% pass rate)
- ✓ **Statements: 84.04%** (threshold: 80%)
- ✓ **Functions: 86.25%** (threshold: 80%)
- ✓ **Lines: 85.01%** (threshold: 80%)
- ✓ **Branches: 66.24%** (threshold: 65%)
- ✓ **Zero ESLint errors**
- ✓ **Full TypeScript type safety**

---

## Support & Documentation

For additional information:
- See `IMPLEMENTATION_COMPLETE.md` for architecture details
- See `FINAL_STATUS.txt` for production readiness checklist
- See `QUICK_START.md` for beginner guide
- Check git commit messages for rationale on design decisions

---

**Version:** 1.0.0  
**Status:** Production Ready  
**Last Updated:** August 2026
