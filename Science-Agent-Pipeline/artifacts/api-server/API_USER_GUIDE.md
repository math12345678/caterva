# Caterva API User Guide

**For:** Researchers, students, scientists using the API  
**Status:** August 2026  
**Last Updated:** August 9, 2026

---

## Getting Started

### What is Caterva?

Caterva is a science agent that runs simulations based on your natural language descriptions. Tell it what you want to simulate, and it figures out the domain, parameters, and runs the computation.

**Example:**
```
Input Query: "michaelis menten kinetics for lactate dehydrogenase vmax=5 s0=10 end=10 points=51"
Processing: Recognizes Michaelis-Menten (enzyme kinetics), resolves Km from BRENDA, reads your other values
Output: Simulation output with time series data
```

> **Archived domains (note, 2026-11-01).** Epidemiology (SIR, SEIR), population genetics (Wright-Fisher, two-locus Wright-Fisher), PCR, Monte Carlo, the ODE oscillators (Lotka-Volterra, repressilator, cell-cycle oscillator) and Lennard-Jones molecular dynamics were archived on 2026-09-27, after v0.4.0. This build refuses a question about them, naming the archive date and v0.4.0, the last release that runs them. Earlier versions of this guide used SIR as the running example.

### Quick Start (5 Minutes)

#### 1. Submit a Simulation

```bash
curl -X POST http://localhost:5000/api/simulate \
  -H "Content-Type: application/json" \
  -d '{
    "query": "simulate michaelis menten km=0.5 vmax=2 s0=10 end=10 points=51"
  }'
```

**Response** (`202 Accepted`):
```json
{
  "jobId": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "query": "simulate michaelis menten km=0.5 vmax=2 s0=10 end=10 points=51",
  "status": "pending",
  "progress": 0,
  "createdAt": "2026-08-09T12:34:56Z",
  "updatedAt": "2026-08-09T12:34:56Z"
}
```

#### 2. Check Status

```bash
curl http://localhost:5000/api/simulate/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

**Possible statuses:**
- `pending` - Waiting to run
- `resolving` - Figuring out domain and parameters
- `validating` - Checking parameters are valid
- `running` - Simulation in progress
- `completed` - Done! Result ready
- `failed` - Error occurred
- `cancelled` - User cancelled it

#### 3. Get Results

When status is `completed`:

```bash
curl http://localhost:5000/api/simulate/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

**Full response includes** (abbreviated; the trajectory has `points` rows):
```json
{
  "jobId": "...",
  "status": "completed",
  "result": {
    "runId": "...",
    "domain": "mm",
    "parameters": {
      "km": 0.5,
      "vmax": 2,
      "s0": 10,
      "end": 10,
      "points": 51
    },
    "trajectory": [
      { "time": 0, "[S]": 10, "[P]": 0 },
      { "time": 0.2, "[S]": 9.6194, "[P]": 0.3806 },
      ...
      { "time": 10, "[S]": 2.06e-8, "[P]": 10 }
    ],
    "parameterProvenance": { ... },
    "provenance": { ... },
    "completedAt": "..."
  }
}
```

---

## Understanding Results

### The Trajectory

The `trajectory` field contains your simulation output: a time-series of state variables.

**For Michaelis-Menten** (concentrations in mM, time in seconds):
```json
{
  "time": 0,
  "[S]": 10,       // Substrate
  "[P]": 0         // Product
}
```

**For Gillespie SSA decay** (molecule counts):
```json
{
  "time": 0,
  "a": 200,        // Reactant A
  "b": 0           // Product B
}
```

### Parameters

The `parameters` field shows the exact values used for the simulation.

**User-supplied** (you specified):
- Clearly marked in your query

**Auto-resolved** (system figured out):
- From literature if not specified
- From keywords if LLM unavailable

**Default** (system chose standard):
- Used when parameter was truly optional

### Parameter Provenance

**Critical for reproducibility:** Understanding where each parameter came from.

```json
"parameterProvenance": {
  "km": {
    "origin": "resolved",
    "source": "brenda_exact",
    "citation": "BRENDA (ref 740253) — https://www.brenda-enzymes.org/enzyme.php?ecno=1.1.1.27",
    "organism": "Homo sapiens",
    "citationStatus": "flagged",
    "citationLocators": [
      { "kind": "brenda_ec", "value": "1.1.1.27", "deepLink": "https://www.brenda-enzymes.org/enzyme.php?ecno=1.1.1.27" },
      { "kind": "brenda_ref", "value": "740253" }
    ],
    "strendaStatus": "incomplete",
    "note": "Assay pH and temperature not reported by the source; STRENDA requires them for kinetic data, so this value is flagged rather than verified."
  },
  "vmax": { "origin": "user" },
  "s0": { "origin": "user" }
}
```

**Origin meanings:**

| Origin | Meaning | Trust Level |
|--------|---------|------------|
| `user` | You specified it | ✅ High (your responsibility) |
| `resolved` | From published literature | ✅ High (peer-reviewed) |
| `default` | System standard value | ✅ Medium (documented) |
| `llm` | Language model guessed | ⚠️ Low (verify independently) |

### Model Provenance

```json
"provenance": {
  "reasoning": "Keywords related to enzyme kinetics were found; defaulting to a Michaelis-Menten simulation.",
  "modelCitations": [
    "Michaelis L., Menten M.L. (1913) Die Kinetik der Invertinwirkung. Biochemische Zeitschrift 49, 333-369. ...",
    "Lehninger, A. L., Nelson, D. L., & Cox, M. M. (2008). Lehninger Principles of Biochemistry (5th ed.)"
  ],
  "flags": [
    "assumed: organism = Homo sapiens. The query names no organism, so the KM lookup used Homo sapiens, chosen for you; ...",
    "Resolved KM=10.73 mM from brenda_exact.",
    "Applied parameter overrides found in the query string."
  ]
}
```

**Read the flags carefully!** They indicate assumptions or limitations in the results.

---

## Query Syntax

### Basic Format

```
<Domain keywords> [with] [parameter=value] [parameter=value] ...
```

### Examples by Domain

> SIR, SEIR, Lotka-Volterra, Wright-Fisher and the other archived domains were removed from this section on 2026-11-01; they were archived on 2026-09-27, after v0.4.0 (the last release that runs them), and a query for one is refused.

#### Michaelis-Menten (Enzyme Kinetics)

```
"lactate dehydrogenase with Km=5"
"enzyme kinetics for aldolase Km=1.5 Vmax=100"
"LDH assay S0=10 end=60"
```

**Parameters:**
- `km` - Michaelis constant (required)
- `vmax` - Maximum velocity (or provide `kcat` and `enzyme_conc`)
- `s0` - Initial substrate (required)
- `end` - Time range
- `points` - Number of time points

#### Competitive Inhibition

```
"competitive inhibition of hexokinase km=2 ki=1 vmax=5 s0=10 i0=1 end=10 points=51"
```

**Parameters:** as Michaelis-Menten, plus
- `ki` - Inhibition constant
- `i0` - Inhibitor concentration

#### Gillespie Stochastic Simulation

```
"gillespie SSA with a0=100 k=0.1 end=50"
"stochastic simulation starting 100 molecules, rate 0.1"
```

**Parameters:**
- `a0` - Initial molecule count (required)
- `k` - Reaction rate (required)
- `end` - Simulation end time (required)
- `seed` - Random seed (optional; for reproducibility)

### Parameter Syntax Rules

**Allowed delimiters:** `=` or `:`
```
km=0.5        ✅
km: 0.5       ✅
km 0.5        ✅
vmax: 2       ✅
```

**Numbers:**
```
0.5           ✅ Decimal
100           ✅ Integer
1e-3          ✅ Scientific notation
0.0           ✅ Zero
```

**One number per parameter.** No live parameter takes a list, so `km=1,2` is refused rather than read as `km=1`. (The array syntax this guide used to show, `starting_frequencies=[...]`, belonged to two-locus Wright-Fisher, archived on 2026-09-27, after v0.4.0, the last release that runs it.)

**Recognised names:** `km`, `ki`, `vmax`, `kcat`, `enzyme_conc`, `s0`, `i0`, `end`, `points`, `a0`, `b0`, `k`, `n_replicates`, `seed`. Any other `name=value` (for example `beta=0.5`) is not an override and is ignored.

**Case-insensitive:**
```
"Michaelis Menten"   ✅
"michaelis menten"   ✅
KM=0.5               ✅ (parameter name)
```

---

## Common Workflows

### Workflow 1: Quick Progress Curve

**Goal:** See how fast an enzyme consumes its substrate

```bash
curl -X POST http://localhost:5000/api/simulate \
  -d '{"query":"michaelis menten kinetics for lactate dehydrogenase vmax=5 s0=10 end=10 points=51"}'

# System resolves Km from the literature and cites it
# Returns substrate and product over time
```

**Then:** Extract `trajectory` and plot `[S]` and `[P]` over time

### Workflow 2: Parameter Sensitivity Analysis

**Goal:** How does result change with different parameters?

```bash
# Run 1: Tight binding
curl -X POST http://localhost:5000/api/simulate \
  -d '{"query":"michaelis menten km=0.1 vmax=2 s0=10 end=10 points=51"}'

# Run 2: Weak binding
curl -X POST http://localhost:5000/api/simulate \
  -d '{"query":"michaelis menten km=10 vmax=2 s0=10 end=10 points=51"}'

# Compare trajectories
```

**Analysis:** With `s0` well above Km the rate is near Vmax; with `s0` below Km it is roughly proportional to `[S]`

### Workflow 3: Reproduce Published Results

**Goal:** Verify a paper's simulation matches published figures

```bash
# Find paper's exact parameters (Km, Vmax, [S]0, assay length)

# Query with exact values
curl -X POST http://localhost:5000/api/simulate \
  -d '{"query":"michaelis menten km=0.5 vmax=2 s0=10 end=10 points=1001"}'

# Compare result trajectory to paper's figures
# Should match if parameters and solver are same
```

### Workflow 4: Literature Parameter Lookup

**Goal:** Find published parameter values for your organism/enzyme

**How Caterva helps:**

```bash
curl -X POST http://localhost:5000/api/simulate \
  -d '{"query":"lactate dehydrogenase kinetics"}'

# System looks up LDH parameters from literature
# Returns parameter provenance with citations
```

**Then:** Use those values in your own research

### Workflow 5: Batch Simulations

**Goal:** Run many parameter combinations

```bash
# Script to run multiple queries
for km in 0.1 0.3 0.5 0.7 0.9; do
  curl -X POST http://localhost:5000/api/simulate \
    -d "{\"query\":\"michaelis menten km=$km vmax=2 s0=10 end=10 points=51\"}"
done

# Collect jobIds, then poll for results
```

---

## Interpreting Common Results

### Michaelis-Menten Progress Curve

**What you see:**
```
[S] (substrate):    Decreasing curve
[P] (product):      Increasing curve ([S] + [P] = [S]0)
```

**What it means:**
- The initial slope is close to Vmax when `s0` is well above Km
- The curve flattens as substrate runs out
- A larger Km means a slower approach at the same Vmax

**How to use it:**
- Estimate how long an assay takes to consume its substrate
- Compare against a measured progress curve

### Gillespie Stochastic Decay

**What you see:**
```
a (reactant):   Step-wise decrease
b (product):    Step-wise increase
```

**What it means:**
- Stochastic process; different seeds give different trajectories
- Fewer molecules → larger relative fluctuations

**How to use it:**
- See when copy numbers are small enough that noise matters
- Fix `seed` to reproduce a run exactly

---

## Troubleshooting & FAQ

### "My query didn't work"

**Check:**
1. Did you get a jobId? (If not, syntax error)
2. Check status: `curl http://localhost:5000/api/simulate/{jobId}`

**Common issues:**

| Error | Cause | Fix |
|-------|-------|-----|
| `MISSING_REQUIRED_INPUT` | Missing required parameter | Add parameter: `vmax=5` |
| `TOO_MANY_REQUESTS` | More than 10 `POST /api/simulate` requests in 60 seconds | Wait up to 60 seconds and retry |
| `PIPELINE_ERROR` | Unexpected failure | Contact support with jobId |

### "What if I don't specify a parameter?"

**System does this:**
1. Tries LLM to guess (if available)
2. Falls back to keyword matching
3. Uses published literature value
4. Uses project default

**Each step tracked in `parameterProvenance`**

### "How do I ensure reproducibility?"

**Three ways:**

1. **Specify all parameters explicitly:**
   ```
   "michaelis menten km=0.5 vmax=2 s0=10 end=10 points=1001"
   ```

2. **Use the stochastic seed:**
   ```
   "Gillespie SSA a0=100 k=0.1 seed=12345"
   ```

3. **Save jobId and parameters:**
   ```json
   {
     "jobId": "...",
     "parameters": { ... },
     "parameterProvenance": { ... }
   }
   ```

### "Why is my result different from a paper?"

**Possible causes:**

1. **Different parameters** - Check `parameterProvenance`, might differ from paper
2. **Different solver** - Caterva uses specific ODE solvers
3. **Different precision** - Numerical resolution (`points` parameter)
4. **Stochastic variation** - For Gillespie SSA, different seed = different result

**How to debug:**
```bash
# Get exact parameters used
curl http://localhost:5000/api/simulate/{jobId} | jq '.result.parameters'

# Compare to paper's parameters
# Adjust and re-run if different
```

### "How long do simulations take?"

**Typical times:**
- Deterministic ODE: 50–200ms
- Stochastic (Gillespie): 100ms–2s (depends on steps)
- LLM classification: 500ms–2s
- **Total:** 1–7 seconds typical

### "Can I get results as CSV?"

**Export endpoint:**
```bash
curl http://localhost:5000/api/simulate/{jobId}/export
# Returns CSV format
```

**Columns:** time, state_variable_1, state_variable_2, ...

### "Is parameter value verified?"

**Check `parameterProvenance.citationStatus`:**
```json
{
  "citationStatus": "verified"      // Exact organism match
  "citationStatus": "flagged"       // Cross-species, use with caution
}
```

**Flagged parameters are still usable, but:**
- May not match your specific organism
- Should verify independently before publication

---

## Best Practices

### 1. Always Check Provenance

**Before using results for publication:**
```bash
# Review parameter provenance
jq '.result.parameterProvenance' result.json

# Look for flags
jq '.result.provenance.flags' result.json
```

**Disclose assumptions in your paper:**
> "Km for lactate dehydrogenase was taken from BRENDA (ref 740253); the source did not report assay pH or temperature, so Caterva flagged it rather than verified it."

### 2. Validate Against Known Results

**First time with new domain:**
```bash
# Find published baseline (textbook or paper)
# Run Caterva with same parameters
# Compare results visually
```

**This verifies:**
- You're using the system correctly
- Parameters are reasonable

### 3. Perform Sensitivity Analysis

**For any important parameter:**
```bash
# Vary ±50% and observe impact
# E.g., if km=0.5:
#   Run with km=0.25 and km=0.75
# Is result robust to parameter uncertainty?
```

### 4. Document Seed for Reproducibility

**For stochastic simulations:**
```json
{
  "query": "Gillespie SSA a0=100 k=0.1 seed=42",
  "note": "Seed=42 ensures reproducibility"
}
```

**Always include in supplementary materials**

### 5. Save Complete Job Metadata

**For future reference or reproduction:**
```bash
curl http://localhost:5000/api/simulate/{jobId} > simulation_result.json

# Includes:
# - Original query
# - Resolved parameters
# - Parameter provenance
# - Full trajectory
# - Execution timestamp
```

---

## Advanced Usage

### Custom Integration Endpoints

**Streaming results (real-time updates):**
```bash
curl http://localhost:5000/api/simulate/{jobId}/stream
# Server-Sent Events: get updates as simulation progresses
```

**Cancel a running job:**
```bash
curl -X POST http://localhost:5000/api/simulate/{jobId}/cancel
```

**List recent jobs:**
```bash
curl http://localhost:5000/api/simulate
# Returns all in-memory jobs (no limit), sorted most-recently-updated first
```

---

## Example Queries by Discipline

### Biochemistry

```
"Enzyme kinetics for catalase"
"Michaelis-Menten for hexokinase"
"Lactate dehydrogenase kinetics"
```

### Stochastic Kinetics

```
"Gillespie SSA a0=100 k=0.1 end=50 seed=42"
"bimolecular association a0=100 b0=100 k=0.005 end=10"
```

> Epidemiology, ecology, population-genetics and physics examples were removed on 2026-11-01: those domains were archived on 2026-09-27, after v0.4.0 (the last release that runs them).

---

## Contact & Support

**Questions?**
- Check this guide (most common questions covered)
- Review provenance for parameter sources
- Check error messages for specific issues

**Report a Bug:**
- Note the jobId
- Include your query
- Describe unexpected behavior

---

**Version:** 1.0  
**Last Updated:** August 9, 2026  
**Live domains (as of 2026-11-01):** `mm`, `mm_competitive_inhibition`, `gillespie_ssa`, `gillespie_ssa_bimolecular`, `gillespie_ssa_replicates`, and the `sbml` escape hatch. The "16 domains" this line used to state predates the 2026-09-27 archive (made after v0.4.0, the last release that runs the archived domains).
