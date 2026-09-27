# Data Quality & Reproducibility Framework

**Purpose:** Ensure all simulations are reproducible, verifiable, and scientifically sound  
**Status:** Implementation Framework  
**Last Updated:** 2026-08-09  
**Owner:** Quality Assurance & Reproducibility Team  

---

## Core Principle

**EVERY RESULT MUST BE INDEPENDENTLY REPRODUCIBLE**

All inputs, parameters, conditions, random seeds, and algorithms must be documented such that:
1. Any researcher can reproduce results identically
2. Code and data are version-controlled
3. Intermediate outputs are preserved
4. All assumptions are explicit

---

## Reproducibility Checklist

### Pre-Simulation Verification

```
Input Validation:
  [ ] All parameters have literature sources
  [ ] All parameters within documented ranges
  [ ] All parameters have uncertainty quantified
  [ ] Experimental conditions fully specified (T, pH, buffer, etc.)
  [ ] Enzyme concentration documented
  [ ] Substrate concentration documented
  [ ] Measurement duration justified
  [ ] Sampling frequency appropriate

Model Assumptions:
  [ ] Steady-state assumption verified
  [ ] No substrate depletion (< 10%)
  [ ] No product inhibition
  [ ] Enzyme not deactivating
  [ ] Single enzyme form assumed
  [ ] All assumptions documented with citations

Numerical Parameters:
  [ ] Solver algorithm specified (e.g., RK45)
  [ ] Tolerance settings documented (atol, rtol)
  [ ] Step size appropriate
  [ ] Random seed (if applicable) recorded
  [ ] Numerical stability verified

Configuration:
  [ ] Software version recorded (Node.js, Python, etc.)
  [ ] Dependency versions frozen (package-lock.json)
  [ ] Compiler settings documented
  [ ] Platform documented (OS, architecture)
  [ ] Git commit hash recorded
```

### Simulation Execution Documentation

```typescript
interface SimulationExecutionRecord {
  // Execution metadata
  execution: {
    jobId: string;
    startTime: ISO8601;
    endTime: ISO8601;
    durationSeconds: number;
    systemUsed: string;        // e.g., "nodejs:18.16.0_ubuntu22.04"
    executionEnvironment: {
      osType: 'linux' | 'macos' | 'windows';
      osVersion: string;
      architecture: 'x64' | 'arm64';
      cpuCount: number;
      memoryAvailableMB: number;
    };
    gitCommitHash: string;
    gitBranch: string;
  };
  
  // Input parameters (complete snapshot)
  inputs: {
    query: string;
    resolvedParameters: {
      [key: string]: {
        value: number;
        unit: string;
        source: 'user' | 'literature' | 'default';
        literatureRef?: string;  // DOI
        confidence: number;      // 0-1
      };
    };
    conditions: {
      temperature: { value: number; unit: 'C' };
      pH: number;
      buffer: string;
      ionicStrength?: number;
    };
    modelSpecification: {
      equation: 'michaelis-menten' | 'ode-system';
      differentialEquations: string[];  // LaTeX format
      initialConditions: { [key: string]: number };
    };
  };
  
  // Numerical solver configuration
  numericalConfiguration: {
    solver: 'RK45' | 'RK23' | 'DOP853' | 'implicit';
    absoluteTolerance: number;
    relativeTolerance: number;
    eventHandling: string[];
    maxSteps: number;
    randomSeed?: number;      // For stochastic simulations
  };
  
  // Execution trace
  execution_trace: {
    phase1_domainDetection: {
      duration_ms: number;
      detected_domain: string;
      confidence: number;
    };
    phase2_parameterResolution: {
      duration_ms: number;
      parameters_resolved: number;
      sources_queried: string[];  // DOIs
    };
    phase3_validation: {
      duration_ms: number;
      checks_performed: number;
      issues_found: string[];
    };
    phase4_simulation: {
      duration_ms: number;
      steps_computed: number;
      solver_warnings: string[];
    };
    phase5_resultValidation: {
      duration_ms: number;
      data_quality_score: number;  // 0-1
      biological_plausibility: string;
    };
  };
  
  // Exact output (to many decimal places)
  output: {
    trajectory: Array<{
      time: number;
      substrate: number;
      product: number;
      velocity: number;
      // Include many decimal places for reproducibility
    }>;
    finalState: {
      [key: string]: number;
    };
    computedMetrics: {
      [key: string]: number;
    };
  };
  
  // Reproducibility hash
  reproducibility: {
    inputHash: string;           // SHA-256 of all inputs
    outputHash: string;          // SHA-256 of output
    reproductionKey: string;     // For exact reproduction
  };
}
```

### Post-Simulation Verification

```
Output Validation:
  [ ] All output values are finite (no NaN, Infinity)
  [ ] Output is biologically plausible
  [ ] Output matches expected ranges
  [ ] No unexpected discontinuities
  [ ] Trajectory is smooth and reasonable
  [ ] Statistical properties reasonable (no wild swings)

Comparison to Literature:
  [ ] Results within reported ranges in literature
  [ ] Relative error < 10% from literature values
  [ ] Outliers identified and explained
  [ ] Comparison to at least 3 independent sources

Documentation Completeness:
  [ ] All parameters documented
  [ ] All assumptions documented
  [ ] All sources cited
  [ ] Conditions fully specified
  [ ] Limitations stated
  [ ] Uncertainty quantified
```

---

## Version Control & Reproducibility

### Data & Code Version Control

```
Repository Structure:
├── src/
│   ├── models/
│   │   ├── michaelis-menten.ts
│   │   └── sir.ts
│   ├── validators/
│   ├── resolvers/
│   └── simulators/
│
├── literature/
│   ├── enzyme-kinetics/
│   │   ├── km-values.json      # Curated parameter library
│   │   ├── vmax-values.json
│   │   └── references/
│   │       ├── smith2020.json  # Full metadata
│   │       ├── johnson2018.json
│   │       └── ...
│   └── validation-data/
│
├── simulations/
│   ├── 2026-08-09/
│   │   ├── sim_001/
│   │   │   ├── input.json      # Complete input snapshot
│   │   │   ├── output.json     # Raw output
│   │   │   ├── metadata.json   # Execution metadata
│   │   │   ├── log.txt         # Execution log
│   │   │   └── reproducibility_key.txt
│   │   └── ...
│   └── checksums.json          # Verify data integrity
│
├── validation/
│   ├── test-cases/
│   │   ├── known-enzyme_mm_1.json
│   │   ├── expected-output_mm_1.json
│   │   └── ...
│   └── validation-results/
│
└── docs/
    ├── PARAMETERS.md           # Parameter values and sources
    ├── MODELS.md              # Mathematical formulations
    ├── ASSUMPTIONS.md         # All model assumptions
    └── VALIDATION.md          # Validation procedures
```

### Git Commit Standards

Every commit must include:

```
commit 1a2b3c4d5e6f7g8h9i0j1k2l3m4n5o6p

Author: Name <email>
Date:   Wed Aug 09 12:34:56 2026 +0000

    Add literature-backed Km parameter for LDH

    - Source: Smith et al. (2020), DOI: 10.xxxx/xxxxxx
    - Value: 5.2 mM (range: 4.9-5.5 mM)
    - Conditions: 37°C, pH 7.4
    - Confidence: 0.96
    - Cross-verified against: Johnson et al. (2018), Williams et al. (2022)
    - Validated by: reviewer_name (timestamp)

    Related: issue #234
    Test: validation/test-cases/ldh-km.json
```

---

## Reproducibility Testing

### Automated Reproduction Verification

```typescript
async function verifyReproducibility(
  originalJobId: string
): Promise<ReproducibilityTest> {
  
  // Step 1: Retrieve original execution record
  const original = await getExecutionRecord(originalJobId);
  
  // Step 2: Extract reproduction key
  const reproductionKey = original.reproducibility.reproductionKey;
  
  // Step 3: Re-run with identical inputs
  const reproduced = await runSimulation({
    inputs: original.inputs,
    configuration: original.numericalConfiguration,
    seed: original.numericalConfiguration.randomSeed,
    forceExactReproduction: true
  });
  
  // Step 4: Compare outputs
  const comparison = compareOutputs(original.output, reproduced.output);
  
  // Step 5: Verify hashes
  const inputHashMatch = 
    original.reproducibility.inputHash === reproduced.reproducibility.inputHash;
  
  const outputHashMatch = 
    Math.abs(
      hashDifference(
        original.reproducibility.outputHash,
        reproduced.reproducibility.outputHash
      )
    ) < 1e-10; // Allow for floating point precision
  
  // Step 6: Report results
  return {
    originalJobId,
    reproductionAttempt: reproduced.execution.jobId,
    
    // Verification results
    verification: {
      inputHashMatches: inputHashMatch,
      outputHashMatches: outputHashMatch,
      outputsIdentical: comparison.allPointsIdentical,
      maxRelativeError: comparison.maxRelativeError,
      meanRelativeError: comparison.meanRelativeError,
      
      reproducibilityStatus: 
        inputHashMatch && outputHashMatch 
          ? 'FULLY_REPRODUCIBLE'
          : 'NUMERICALLY_EQUIVALENT',
      
      passed: inputHashMatch && comparison.maxRelativeError < 1e-6
    };
    
    // Differences (if any)
    differences: comparison.maxRelativeError > 0 ? {
      possibleCauses: [
        'Different floating-point implementations',
        'Compiler optimization differences',
        'Numerical solver variations'
      ],
      conclusion: 'Results numerically equivalent within expected precision'
    } : undefined;
    
    // Report
    summary: `
    Original job: ${originalJobId}
    Reproduction: ${reproduced.execution.jobId}
    
    Status: ${comparison.allPointsIdentical ? 'FULLY REPRODUCIBLE' : 'NUMERICALLY EQUIVALENT'}
    
    Max difference: ${comparison.maxRelativeError.toExponential(2)} relative error
    Mean difference: ${comparison.meanRelativeError.toExponential(2)} relative error
    
    Conclusion: ${
      inputHashMatch && outputHashMatch
        ? 'Results fully reproducible - can be independently verified'
        : 'Results numerically equivalent - variations within expected floating-point precision'
    }
    `
  };
}
```

### Continuous Reproducibility Verification

```typescript
// Runs nightly: verify reproducibility of all recent simulations
async function nightly_reproducibility_check() {
  const recentSimulations = await getSimulationsFromPastDay();
  const results = [];
  
  for (const sim of recentSimulations) {
    try {
      const result = await verifyReproducibility(sim.jobId);
      
      if (!result.verification.passed) {
        alertScientificTeam({
          severity: 'warning',
          message: `Reproducibility check failed for ${sim.jobId}`,
          details: result,
          action: 'Review execution environment'
        });
      }
      
      results.push(result);
    } catch (error) {
      alertScientificTeam({
        severity: 'critical',
        message: `Could not reproduce simulation ${sim.jobId}`,
        error: error.message,
        action: 'Immediate investigation required'
      });
    }
  }
  
  // Summary report
  const passed = results.filter(r => r.verification.passed).length;
  const total = results.length;
  
  console.log(`
  Nightly Reproducibility Check
  ==============================
  Passed: ${passed}/${total}
  Success rate: ${((passed/total)*100).toFixed(1)}%
  
  ${passed === total ? '✓ ALL SIMULATIONS REPRODUCIBLE' : '⚠ ISSUES FOUND'}
  `);
  
  return results;
}
```

---

## Data Integrity & Verification

### Checksum Verification

```typescript
async function verifyDataIntegrity(jobId: string): Promise<IntegrityCheck> {
  const record = await getExecutionRecord(jobId);
  
  // Recompute checksums
  const inputChecksum = SHA256(JSON.stringify(record.inputs));
  const outputChecksum = SHA256(JSON.stringify(record.output));
  
  return {
    jobId,
    integrity: {
      inputsIntact: inputChecksum === record.reproducibility.inputHash,
      outputsIntact: outputChecksum === record.reproducibility.outputHash,
      recordComplete: record.execution_trace !== undefined
    },
    
    allIntact: 
      inputChecksum === record.reproducibility.inputHash &&
      outputChecksum === record.reproducibility.outputHash &&
      record.execution_trace !== undefined
  };
}

// Verify all stored simulations weekly
async function weeklyIntegrityAudit() {
  const allSimulations = await getAllStoredSimulations();
  const failures = [];
  
  for (const sim of allSimulations) {
    const check = await verifyDataIntegrity(sim.jobId);
    if (!check.allIntact) {
      failures.push({
        jobId: sim.jobId,
        issues: check.integrity
      });
    }
  }
  
  if (failures.length > 0) {
    alertSecurityTeam({
      severity: 'critical',
      message: 'Data integrity violations detected',
      count: failures.length,
      details: failures
    });
  }
  
  return {
    total: allSimulations.length,
    intact: allSimulations.length - failures.length,
    integrityScore: (allSimulations.length - failures.length) / allSimulations.length
  };
}
```

---

## Open Science & FAIR Principles

### FAIR Data Compliance

**Findable:**
- [ ] DOI assigned to simulation dataset
- [ ] Metadata indexed in scientific registries
- [ ] Simulation available via API with full metadata

**Accessible:**
- [ ] Data available without restrictions
- [ ] Non-proprietary formats (JSON, CSV)
- [ ] Downloadable and reproducible locally

**Interoperable:**
- [ ] Data uses standard formats
- [ ] Metadata uses standard vocabularies
- [ ] Export capability to standard formats

**Reusable:**
- [ ] Clear license (CC0 or CC-BY)
- [ ] Complete documentation
- [ ] Provenance clearly stated
- [ ] Usage rights clear

### Dataset Registration

```typescript
interface DatasetRegistration {
  // Open Science Framework registration
  osf_project: {
    title: string;
    description: string;
    tags: string[];
    contributors: string[];
    license: 'CC0' | 'CC-BY' | 'CC-BY-SA';
    openData: true;
    openCode: true;
  };
  
  // Zenodo registration (for preservation)
  zenodo: {
    deposition_id: string;
    doi: string;
    url: string;
  };
  
  // GitHub repository
  github: {
    repository: string;
    branch: string;
    commit: string;
    reproducibility_instructions: string;
  };
}

async function registerDataset(simulation: SimulationResult) {
  // Register on Open Science Framework
  const osf = await registerOSF({
    title: `Simulation: ${simulation.query}`,
    description: buildDescription(simulation),
    files: [
      simulation.input,
      simulation.output,
      simulation.metadata
    ]
  });
  
  // Register on Zenodo (for long-term preservation)
  const zenodo = await registerZenodo({
    title: osf.title,
    description: osf.description,
    doi_to_cite: simulation.literatureReferences.map(r => r.doi),
    files: await packDataset(simulation)
  });
  
  // Document in GitHub
  await updateREADME({
    dataset_osf: osf.url,
    dataset_zenodo: zenodo.url,
    doi: zenodo.doi,
    reproduction_instructions: buildReproductionGuide(simulation)
  });
  
  return {
    osf: osf.url,
    zenodo: zenodo.url,
    doi: zenodo.doi,
    github: `https://github.com/caterva/...`
  };
}
```

---

## Error Handling & Rollback

### If Reproducibility Fails

```
ERROR: Cannot reproduce simulation XYZ123

Investigation Checklist:
1. [ ] Environment differences?
   - [ ] Check Node.js/Python version
   - [ ] Check OS/architecture
   - [ ] Check dependency versions
   
2. [ ] Numerical precision?
   - [ ] Check floating-point settings
   - [ ] Check solver tolerance
   - [ ] Check random seed
   
3. [ ] Code changes?
   - [ ] Verify git commit hash matches
   - [ ] Check for uncommitted changes
   - [ ] Review recent commits
   
4. [ ] Data corruption?
   - [ ] Run integrity check
   - [ ] Compare checksums
   - [ ] Restore from backup
   
5. [ ] Documentation?
   - [ ] Review execution record
   - [ ] Check parameter sources
   - [ ] Verify all assumptions

RESOLUTION:
- If environmental: Document and accept small numerical differences
- If data corruption: Restore from backup and re-run
- If code changes: Identify breaking change and document
- If parameter error: Correct parameter and re-run (with new jobId)

DO NOT MODIFY ORIGINAL RESULTS. Create new simulation with corrected inputs.
```

---

## Quality Metrics Dashboard

**This is a mockup, not a live report.** An earlier version of this section
presented the numbers below as if "Updated Daily" from a running system.
Nothing in `ReproducibilityService` supports that: it holds `private records:
Map<string, ExecutionRecord>` (`src/reproducibility/reproducibilityEngine.ts:641`)
-- one process's in-memory job history, wiped on every restart -- with no
24-hour rollup, no scheduled aggregation, and no persistence between runs.
847 simulations, a 99.5% reproduction rate, 156 sourced parameters: none of
these were ever measured. They illustrate the SHAPE a dashboard could report
if this service were backed by persistent storage and a rollup job, which it
currently is not.

```
Illustrative example only -- not measured, not live:

Overall System Reproducibility:
  ├─ Simulations run past 24h: 847
  ├─ Successfully reproduced: 843 (99.5%)
  ├─ Failed reproducibility: 2 (0.2%)
  ├─ Data integrity verified: 847 (100%)
  └─ Trend: ✓ Improving

Literature Coverage:
  ├─ Parameters with sources: 156/156 (100%)
  ├─ Cross-verified (2+ sources): 142/156 (91%)
  ├─ Average literature sources: 3.2
  └─ Trend: ✓ Increasing

Data Quality:
  ├─ Average data quality score: 0.97/1.0
  ├─ Simulations with warnings: 18 (2.1%)
  ├─ Failed validations: 0 (0%)
  └─ Trend: ✓ Stable

Documentation Completeness:
  ├─ Fully documented: 835/847 (98.6%)
  ├─ Missing metadata: 12 (1.4%)
  ├─ Average documentation score: 0.96/1.0
  └─ Trend: ✓ Excellent

Confidence Scores (Aggregate):
  ├─ Very high (0.9-1.0): 612 (72%)
  ├─ High (0.8-0.9): 185 (22%)
  ├─ Medium (0.7-0.8): 43 (5%)
  ├─ Low (<0.7): 7 (1%)
  └─ Trend: ✓ Excellent
```

What's real today: `ReproducibilityService.checkIntegrity(jobId)` and
`verifyReproducibility(jobId, reproducer)` report on ONE job at a time, on
demand, against whatever is still in that process's memory (see
`reproducibilityEngine.ts:640` onward). Building the dashboard above for
real would mean persisting `ExecutionRecord`s past process restart and
adding a rollup job -- neither exists yet.

---

## Document Control

**Version:** 1.0  
**Status:** Active  
**Last Updated:** 2026-08-09  
**Next Review:** 2026-11-09  
**Owner:** Quality Assurance & Reproducibility Team  

**Core Principles:**
1. EVERY RESULT MUST BE INDEPENDENTLY REPRODUCIBLE
2. ALL DATA MUST BE VERIFIABLE
3. PROVENANCE MUST BE COMPLETE
4. ERRORS MUST STOP EXECUTION (fail-fast principle)
