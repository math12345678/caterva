# Terrium API User Guide

**For:** Researchers, students, scientists using the API  
**Status:** August 2026  
**Last Updated:** August 9, 2026

---

## Getting Started

### What is Terrium?

Terrium is a science agent that runs simulations based on your natural language descriptions. Tell it what you want to simulate, and it figures out the domain, parameters, and runs the computation.

**Example:**
```
Query: "SIR model with beta=0.5 and gamma=0.1, starting with S0=900"
↓
System: Recognizes SIR (epidemiology), extracts parameters
↓
Result: Simulation output with time series data
```

### Quick Start (5 Minutes)

#### 1. Submit a Simulation

```bash
curl -X POST http://localhost:5000/api/simulate \
  -H "Content-Type: application/json" \
  -d '{
    "query": "SIR epidemic model beta=0.5 gamma=0.1 S0=900"
  }'
```

**Response:**
```json
{
  "jobId": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
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

**Full response includes:**
```json
{
  "jobId": "...",
  "status": "completed",
  "result": {
    "domain": "sir",
    "parameters": {
      "beta": 0.5,
      "gamma": 0.1,
      "s0": 900,
      "i0": 1,
      "r0_recovered": 0,
      "end": 100,
      "points": 1001
    },
    "trajectory": [
      { "time": 0, "S": 900, "I": 1, "R": 0 },
      { "time": 0.1, "S": 898.5, "I": 2.3, "R": 0.2 },
      ...
    ],
    "parameterProvenance": { ... },
    "provenance": { ... }
  }
}
```

---

## Understanding Results

### The Trajectory

The `trajectory` field contains your simulation output: a time-series of state variables.

**For SIR model:**
```json
{
  "time": 0,
  "S": 900,        // Susceptible
  "I": 1,          // Infected
  "R": 0           // Recovered
}
```

**For Lotka-Volterra:**
```json
{
  "time": 0,
  "P": 100,        // Prey population
  "V": 10          // Predator population
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
  "beta": {
    "origin": "resolved",
    "source": "BRENDA enzyme database",
    "citation": "Kermack & McKendrick (1927) Royal Society 115:700-721",
    "organism": "Homo sapiens",
    "citationStatus": "verified",
    "note": "Exact organism match"
  },
  "gamma": {
    "origin": "user",
    "note": "Supplied in query: gamma=0.1"
  },
  "s0": {
    "origin": "default",
    "source": "Terrium standard parameters",
    "note": "SIR default: 900 susceptible population"
  }
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
  "reasoning": "Query mentions 'SIR' and epidemic, resolved to SIR model",
  "modelCitations": [
    "Kermack, McKendrick (1927) Royal Society 115:700-721"
  ],
  "flags": [
    "gamma cross-species fallback: resolved from Ebola, applied to general SIR"
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

#### SIR (Epidemiology)

```
"SIR model with beta=0.5 gamma=0.1"
"simulate an epidemic with R0=2.5"
"measles transmission beta=0.9 gamma=0.3"
```

**Parameters:**
- `beta` - Transmission rate
- `gamma` - Recovery rate
- `s0` - Initial susceptible
- `i0` - Initial infected (default 1)
- `r0_recovered` - Initial recovered (default 0)
- `end` - Simulation end time (default 100)
- `points` - Number of time points (default 1001)

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

#### Lotka-Volterra (Predator-Prey)

```
"predator-prey dynamics with p0=100 v0=10"
"lotka-volterra alpha=0.5 beta=0.02 gamma=0.02 delta=0.5"
"population dynamics for rabbits and wolves"
```

**Parameters:**
- `alpha` - Prey growth rate (default 0.5)
- `beta` - Predation rate (default 0.02)
- `gamma` - Predation efficiency (default 0.02)
- `delta` - Predator death rate (default 0.5)
- `p0` - Initial prey (default 100)
- `v0` - Initial predator (default 10)
- `end` - Simulation end time (default 20)

#### Population Genetics (Wright-Fisher)

```
"Wright-Fisher selection model population_size=1000 starting_frequency=0.5"
"genetic drift with 500 individuals and 0.1 mutation rate"
```

**Parameters:**
- `population_size` - Effective population (required)
- `starting_frequency` - Allele frequency [0,1] (required)
- `generations` - Number of generations (required)
- `replicate_runs` - Number of replicates (required)
- `mutation_rate` - Mutation rate (optional)
- `selection_coefficient` - Selection strength (optional)
- `dominance` - Dominance parameter (optional)

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
beta=0.5      ✅
beta: 0.5     ✅
beta 0.5      ✅
gamma: 0.1    ✅
```

**Numbers:**
```
0.5           ✅ Decimal
100           ✅ Integer
1e-3          ✅ Scientific notation
0.0           ✅ Zero
```

**Arrays** (for multi-locus genetics):
```
"starting_frequencies=[0.5,0,0,0.5]"
```

**Case-insensitive:**
```
"SIR"         ✅
"sir"         ✅
"Sir"         ✅
BETA=0.5      ✅ (parameter name)
```

---

## Common Workflows

### Workflow 1: Quick Epidemic Projection

**Goal:** Estimate how an epidemic spreads with current parameters

```bash
curl -X POST http://localhost:5000/api/simulate \
  -d '{"query":"SIR epidemic R0=2.5"}'

# System estimates beta and gamma from R0
# Returns projection to disease elimination
```

**Then:** Extract `trajectory` and plot S, I, R over time

### Workflow 2: Parameter Sensitivity Analysis

**Goal:** How does result change with different parameters?

```bash
# Run 1: Low transmission
curl -X POST http://localhost:5000/api/simulate \
  -d '{"query":"SIR beta=0.1 gamma=0.1"}'

# Run 2: High transmission  
curl -X POST http://localhost:5000/api/simulate \
  -d '{"query":"SIR beta=0.9 gamma=0.1"}'

# Compare trajectories
```

**Analysis:** Peak infection timing/magnitude changes with beta

### Workflow 3: Reproduce Published Results

**Goal:** Verify a paper's simulation matches published figures

```bash
# Find paper's exact parameters
# e.g., "Kermack & McKendrick 1927"

# Query with exact values
curl -X POST http://localhost:5000/api/simulate \
  -d '{"query":"SIR beta=0.5 gamma=0.33 S0=1000 I0=1"}'

# Compare result trajectory to paper's figures
# Should match if parameters and solver are same
```

### Workflow 4: Literature Parameter Lookup

**Goal:** Find published parameter values for your organism/enzyme

**How Terrium helps:**

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
for beta in 0.1 0.3 0.5 0.7 0.9; do
  curl -X POST http://localhost:5000/api/simulate \
    -d "{\"query\":\"SIR beta=$beta gamma=0.1\"}"
done

# Collect jobIds, then poll for results
```

---

## Interpreting Common Results

### SIR Epidemic Curve

**What you see:**
```
S (susceptible):    Decreasing curve
I (infected):       Peak then decline
R (recovered):      Increasing curve (S + I + R = constant)
```

**What it means:**
- Peak I indicates epidemic maximum (healthcare load)
- R0 affects curve steepness
- Lower gamma = slower recovery = broader peak

**How to use it:**
- Estimate when peak hits (healthcare planning)
- Calculate total infected (R at end)
- Predict disease elimination time

### Lotka-Volterra Predator-Prey

**What you see:**
```
Prey (P):       Oscillates with lag
Predator (V):   Oscillates with lag
```

**What it means:**
- Predator population lags prey population
- Classic cycle: prey ↑ → predators ↑ → prey ↓ → predators ↓
- Amplitude indicates population stability

**How to use it:**
- Understand predator-prey cycles in ecosystems
- Estimate population doubling time
- Detect if population crashes (extinction risk)

### Wright-Fisher Genetic Drift

**What you see:**
```
Allele frequency:   Random walk toward 0 or 1
```

**What it means:**
- Stochastic process; different runs give different outcomes
- Eventually fixes to one allele (frequency = 0 or 1)
- Smaller population → faster fixation

**How to use it:**
- Calculate fixation probability
- Estimate time to fixation
- Understand neutral evolution

---

## Troubleshooting & FAQ

### "My query didn't work"

**Check:**
1. Did you get a jobId? (If not, syntax error)
2. Check status: `curl http://localhost:5000/api/simulate/{jobId}`

**Common issues:**

| Error | Cause | Fix |
|-------|-------|-----|
| `MISSING_REQUIRED_INPUT` | Missing required parameter | Add parameter: `beta=0.5` |
| `RATE_LIMITED` | Too many requests | Wait 15 minutes |
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
   "SIR beta=0.5 gamma=0.1 S0=900 I0=1 end=100 points=1001"
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
2. **Different solver** - Terrium uses specific ODE solvers
3. **Different precision** - Numerical resolution (`points` parameter)
4. **Stochastic variation** - For Gillespie/Wright-Fisher, different seed = different result

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
- Population genetics: 500ms–5s (depends on generations)
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
> "We used Kermack-McKendrick SIR parameters from [cite]. For gamma, we used a cross-species estimate from measles."

### 2. Validate Against Known Results

**First time with new domain:**
```bash
# Find published baseline (textbook or paper)
# Run Terrium with same parameters
# Compare results visually
```

**This verifies:**
- You're using the system correctly
- Parameters are reasonable

### 3. Perform Sensitivity Analysis

**For any important parameter:**
```bash
# Vary ±50% and observe impact
# E.g., if beta=0.5:
#   Run with beta=0.25 and beta=0.75
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
# Returns last 50 jobs with status
```

---

## Example Queries by Discipline

### Epidemiology

```
"Model COVID-19 transmission with R0=3"
"SIR for measles vaccination scenario"
"SEIR epidemic with 10% immunity"
"flu dynamics with seasonal forcing"
```

### Ecology

```
"Predator-prey dynamics for wolf-elk system"
"Population growth with carrying capacity"
"Lotka-Volterra with p0=100 v0=5"
```

### Biochemistry

```
"Enzyme kinetics for catalase"
"Michaelis-Menten for hexokinase"
"Lactate dehydrogenase kinetics"
```

### Population Genetics

```
"Wright-Fisher drift in 100-person population"
"Fixation time for beneficial allele"
"Neutral evolution 1000 generations"
```

### Physics/Chemistry

```
"Molecular dynamics 100 particles"
"PCR amplification 40 cycles"
"Monte Carlo simulation 10000 samples"
```

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
**All domains:** 16 (14 primary + 2 engine internal + 1 escape hatch)
