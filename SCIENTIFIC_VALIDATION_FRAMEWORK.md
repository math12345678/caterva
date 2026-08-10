# Scientific Validation Framework

**Purpose:** Ensure all simulations, parameters, and results are scientifically valid and literature-backed  
**Status:** Framework Definition & Implementation Guide  
**Last Updated:** 2026-08-09  
**Owner:** Scientific Review Team  

---

## Core Principle

**NO CODE SHIPS WITHOUT SCIENTIFIC VALIDATION**

Every parameter, every default value, every model assumption must:
1. Have scientific literature justification
2. Include proper citations (DOI preferred)
3. Be verified by peer review
4. Include confidence intervals
5. Document limitations and assumptions

---

## Validation Layers

### Layer 1: Parameter Validation

#### Michaelis-Menten Kinetics (MM Domain)

**Required Parameters:**
```typescript
interface MMParameters {
  // Core kinetic parameters (from literature)
  km: {
    value: number;           // Michaelis constant (mM)
    min: number;              // Literature range minimum
    max: number;              // Literature range maximum
    literature?: LiteratureRef[];  // Supporting citations
    confidence: number;       // Confidence (0-1)
  };
  
  vmax: {
    value: number;           // Maximum velocity (μM/min)
    min: number;
    max: number;
    literature?: LiteratureRef[];
    confidence: number;
  };
  
  // Reaction conditions (must match literature)
  temperature: {
    value: number;           // Celsius
    uncertainty: number;     // ±X degrees
    literature?: LiteratureRef[];
  };
  
  pH: {
    value: number;
    uncertainty: number;
    literature?: LiteratureRef[];
  };
  
  // Substrate concentration
  s0: {
    value: number;
    unit: string;
    justification: string;   // Why this concentration?
    literature?: LiteratureRef[];
  };
}
```

**Validation Rules:**

```typescript
function validateMMParameters(params: MMParameters): ValidationResult {
  const errors: ValidationError[] = [];
  const warnings: ValidationWarning[] = [];
  
  // Rule 1: Km must be within known range for enzyme
  if (params.km.value < params.km.min || params.km.value > params.km.max) {
    errors.push({
      field: 'km',
      message: `Km ${params.km.value} outside literature range [${params.km.min}, ${params.km.max}]`,
      severity: 'error',
      fix: 'Provide literature justification or revise value'
    });
  }
  
  // Rule 2: Vmax must be measurable
  if (params.vmax.value <= 0) {
    errors.push({
      field: 'vmax',
      message: 'Vmax must be positive',
      severity: 'error'
    });
  }
  
  // Rule 3: Temperature must match literature conditions
  if (!params.temperature.literature || params.temperature.literature.length === 0) {
    warnings.push({
      field: 'temperature',
      message: 'No literature justification for temperature',
      severity: 'warning'
    });
  }
  
  // Rule 4: pH must be physiologically relevant or justified
  const validPhRange = [6.0, 8.5]; // Normal physiology
  if (params.pH.value < validPhRange[0] || params.pH.value > validPhRange[1]) {
    warnings.push({
      field: 'pH',
      message: `pH ${params.pH.value} outside physiological range`,
      severity: 'warning',
      fix: 'Provide justification for non-physiological pH'
    });
  }
  
  // Rule 5: S0 must be justified
  if (!params.s0.justification) {
    errors.push({
      field: 's0',
      message: 'Substrate concentration requires justification',
      severity: 'error'
    });
  }
  
  return {
    valid: errors.length === 0,
    errors,
    warnings,
    confidence: calculateConfidence(params)
  };
}
```

### Layer 2: Literature Integration

#### Citation Format

**All citations must include:**

```typescript
interface LiteratureReference {
  // Unique identifiers
  doi?: string;              // Preferred: 10.xxxx/xxxxx
  pubmedId?: string;         // PubMed Central ID
  arxivId?: string;          // For preprints
  
  // Bibliographic info
  title: string;
  authors: string[];         // First author at minimum
  year: number;
  journal: string;
  volume?: string;
  issue?: string;
  pages?: string;
  
  // Access
  url?: string;
  accessDate?: Date;
  
  // Relevance
  relevantSections: string[]; // Which sections/tables support this
  extractedValue?: any;       // What value was extracted
  confidence: number;         // 0-1 confidence in accuracy
  
  // Quality
  peerReviewed: boolean;
  impactFactor?: number;
  citations?: number;        // How many times cited
  
  // Notes
  notes?: string;            // Why this source is relevant
}

// Example usage in code
const lactateDH_km: LiteratureReference = {
  doi: '10.1016/S0021-9258(20)71234-5',
  title: 'Kinetic properties of lactate dehydrogenase from human heart',
  authors: ['Smith J', 'Johnson K', 'Williams R'],
  year: 1985,
  journal: 'Journal of Biological Chemistry',
  volume: '260',
  issue: '15',
  pages: '8234-8240',
  
  url: 'https://www.jbc.org/article/S0021-9258(20)71234-5',
  accessDate: new Date('2026-08-09'),
  
  relevantSections: ['Table 2', 'Figure 3'],
  extractedValue: { km: 5.2, unit: 'mM', substrate: 'lactate' },
  confidence: 0.95,
  
  peerReviewed: true,
  impactFactor: 5.27,
  citations: 1847,
  
  notes: 'Direct measurement of Km under physiological conditions (37°C, pH 7.4)'
};
```

#### Literature Verification Process

```typescript
async function verifyLiteratureReference(ref: LiteratureReference): Promise<VerificationResult> {
  const checks: VerificationCheck[] = [];
  
  // Check 1: DOI resolution
  if (ref.doi) {
    const doiValid = await resolveDOI(ref.doi);
    checks.push({
      name: 'DOI Resolution',
      passed: doiValid.success,
      error: doiValid.error,
      severity: 'critical'
    });
  }
  
  // Check 2: Peer review status
  if (!ref.peerReviewed) {
    checks.push({
      name: 'Peer Review',
      passed: false,
      error: 'Non-peer-reviewed sources require editorial approval',
      severity: 'high'
    });
  }
  
  // Check 3: Citation count (popularity/acceptance)
  if (ref.citations && ref.citations < 10) {
    checks.push({
      name: 'Citation Count',
      passed: false,
      error: `Low citation count (${ref.citations}) - verify relevance`,
      severity: 'medium'
    });
  }
  
  // Check 4: Impact factor (journal quality)
  if (ref.impactFactor && ref.impactFactor < 1.5) {
    checks.push({
      name: 'Journal Quality',
      passed: false,
      error: `Low impact factor (${ref.impactFactor}) - consider alternatives`,
      severity: 'medium'
    });
  }
  
  // Check 5: Recency (not too old for rapidly advancing fields)
  const ageYears = new Date().getFullYear() - ref.year;
  if (ageYears > 20) {
    checks.push({
      name: 'Recency',
      passed: ageYears <= 30,  // Warning but acceptable
      error: `Paper is ${ageYears} years old - verify still current`,
      severity: 'low'
    });
  }
  
  return {
    reference: ref,
    checks,
    verified: checks.filter(c => !c.passed && c.severity === 'critical').length === 0,
    requiresReview: checks.filter(c => !c.passed).length > 0,
    confidence: calculateLiteratureConfidence(checks)
  };
}
```

### Layer 3: Model Validation

#### Kinetic Model Assumptions

```typescript
interface ModelAssumptions {
  // Enzyme kinetics assumptions
  steadyState: {
    assumed: boolean;
    validWhen: string;       // Time frames, conditions
    literature?: LiteratureReference[];
  };
  
  noProductInhibition: {
    assumed: boolean;
    validWhen: string;
    literature?: LiteratureReference[];
  };
  
  noSubstrateDepletion: {
    assumed: boolean;
    validWhen: string;
    measuredSubstrateLoss?: number; // % of starting concentration
    literature?: LiteratureReference[];
  };
  
  enzymeNotDeactivated: {
    assumed: boolean;
    validWhen: string;
    literature?: LiteratureReference[];
  };
  
  singleEnzymeForm: {
    assumed: boolean;
    validWhen: string;
    literature?: LiteratureReference[];
  };
  
  // Additional assumptions
  custom: Array<{
    name: string;
    description: string;
    justification: string;
    literature?: LiteratureReference[];
  }>;
}

// Validation
function validateModelAssumptions(
  assumptions: ModelAssumptions,
  experimentalConditions: ExperimentalConditions
): AssumptionValidation {
  const violations: AssumptionViolation[] = [];
  
  // Check steady state assumption
  if (assumptions.steadyState.assumed) {
    // Steady state typically requires 5-10x initial velocity
    const timeToSteadyState = estimateSteadyStateTime(
      experimentalConditions.km,
      experimentalConditions.vmax
    );
    
    if (experimentalConditions.measurementTime < timeToSteadyState) {
      violations.push({
        assumption: 'steadyState',
        violated: true,
        reason: `Measurement time (${experimentalConditions.measurementTime}s) < steady state time (${timeToSteadyState}s)`,
        severity: 'high',
        remediation: 'Increase measurement time or use pre-steady-state kinetics model'
      });
    }
  }
  
  // Check substrate depletion
  if (assumptions.noSubstateDepletion.assumed) {
    const substrateDepletion = calculateSubstrateDepletion(
      experimentalConditions.s0,
      experimentalConditions.vmax,
      experimentalConditions.duration
    );
    
    if (substrateDepletion > 5) { // >5% is significant
      violations.push({
        assumption: 'noSubstrateDepletion',
        violated: true,
        reason: `Substrate depletion (${substrateDepletion}%) exceeds acceptable limit (5%)`,
        severity: 'medium',
        remediation: 'Use lower substrate concentration or shorter measurement time'
      });
    }
  }
  
  return {
    allAssumptionsValid: violations.length === 0,
    violations,
    modelReliability: calculateModelReliability(violations)
  };
}
```

### Layer 4: Simulation Validation

#### Output Validation

```typescript
interface SimulationValidation {
  // Data quality
  dataQuality: {
    noNaNValues: boolean;
    noInfinityValues: boolean;
    reasonableRange: boolean;   // Within expected biological range
    monotonicity: boolean;       // Trajectory makes biological sense
    noise: number;               // Estimated measurement noise
  };
  
  // Biological plausibility
  biologicalPlausibility: {
    substrateDepleted: boolean;  // Should deplete if K >> S0
    productFormed: boolean;       // Should form product
    enzymeNotSaturated: boolean; // If S0 << Km
    reactionContinues: boolean;   // Shouldn't plateau too early
  };
  
  // Literature comparison
  literatureComparison: {
    withinExpectedRange: boolean;
    similarToReferences: number;  // % similarity to literature values
    outlierDetection: string[];   // Any unusual results
  };
  
  // Statistical quality
  statistics: {
    rSquared: number;             // Goodness of fit
    residualStd: number;          // Standard deviation of residuals
    confidenceInterval: [number, number]; // 95% CI
  };
}

async function validateSimulationResults(
  simulation: SimulationResult,
  parameters: MMParameters,
  literatureReferences: LiteratureReference[]
): Promise<SimulationValidation> {
  
  // Check 1: Data quality
  const dataQuality = {
    noNaNValues: !simulation.trajectory.some(p => isNaN(p.value)),
    noInfinityValues: !simulation.trajectory.some(p => !isFinite(p.value)),
    reasonableRange: simulation.trajectory.every(p => p.value >= 0 && p.value <= 1000),
    monotonicity: checkMonotonicity(simulation.trajectory),
    noise: estimateNoise(simulation.trajectory)
  };
  
  // Check 2: Biological plausibility
  const lastPoint = simulation.trajectory[simulation.trajectory.length - 1];
  const substrateDepleted = (lastPoint.value < parameters.s0.value * 0.05);
  
  const biologicalPlausibility = {
    substrateDepleted: substrateDepleted,
    productFormed: simulation.product && simulation.product.length > 0,
    enzymeNotSaturated: parameters.s0.value < parameters.km.value,
    reactionContinues: !isPrematurePlateau(simulation.trajectory)
  };
  
  // Check 3: Literature comparison
  const literatureComparison = {
    withinExpectedRange: isWithinLiteratureRange(
      simulation.result,
      literatureReferences
    ),
    similarToReferences: calculateSimilarityToLiterature(
      simulation.result,
      literatureReferences
    ),
    outlierDetection: detectOutliers(simulation.trajectory, literatureReferences)
  };
  
  // Check 4: Statistical quality
  const statistics = {
    rSquared: calculateRSquared(simulation.trajectory),
    residualStd: calculateResidualStd(simulation.trajectory),
    confidenceInterval: calculateConfidenceInterval(simulation.trajectory, 0.95)
  };
  
  return {
    dataQuality,
    biologicalPlausibility,
    literatureComparison,
    statistics
  };
}
```

---

## Validation Workflow

```
┌─────────────────────────────────────────────────────────┐
│ INPUT: User Query & Parameters                          │
└────────────────────┬────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────┐
│ LAYER 1: Parameter Validation                           │
│ • Check ranges (min, max)                               │
│ • Verify literature backing                             │
│ • Calculate confidence                                  │
│ • Flag any out-of-range values                          │
└────────────────────┬────────────────────────────────────┘
                     ↓
        ┌────────────────────┐
        │ PASS?              │
        └────────┬───────────┘
                 │ NO
                 ↓
        ┌──────────────────────┐
        │ REQUEST EDITOR       │
        │ APPROVAL / REVISION  │
        └──────────────────────┘
                 │ YES (revised)
                 ↓
        ┌──────────────────────┐
        │ RE-VALIDATE          │
        └────────┬─────────────┘
                 │
                 └──────────→ PASS ─→ Continue
                 │
                 NO → Reject
                 ↓
        ┌──────────────────────┐
        │ CANNOT PROCEED       │
        │ Invalid Parameters   │
        └──────────────────────┘
                 ↓
┌─────────────────────────────────────────────────────────┐
│ LAYER 2: Literature Integration                         │
│ • Verify all citations (DOI, PubMed, etc)              │
│ • Check peer review status                              │
│ • Validate citation relevance                           │
│ • Extract values accurately                             │
└────────────────────┬────────────────────────────────────┘
                     ↓
        ┌────────────────────┐
        │ ALL CITATIONS      │
        │ VERIFIED?          │
        └────────┬───────────┘
                 │ NO
                 ↓
        ┌──────────────────────┐
        │ FLAG & REQUEST       │
        │ SCIENTIFIC REVIEW    │
        └──────────────────────┘
                 │ APPROVED
                 ↓
        ┌──────────────────────┐
        │ CONTINUE WITH        │
        │ REDUCED CONFIDENCE   │
        └────────┬─────────────┘
                 │ YES (all verified)
                 ↓
┌─────────────────────────────────────────────────────────┐
│ LAYER 3: Model Validation                               │
│ • Verify assumptions hold                               │
│ • Check condition compatibility                         │
│ • Validate mathematical model                           │
└────────────────────┬────────────────────────────────────┘
                     ↓
        ┌────────────────────┐
        │ ASSUMPTIONS        │
        │ VALID?             │
        └────────┬───────────┘
                 │ NO
                 ↓
        ┌──────────────────────┐
        │ FLAG VIOLATIONS      │
        │ (may proceed with    │
        │  reduced confidence) │
        └────────┬─────────────┘
                 │ YES
                 ↓
┌─────────────────────────────────────────────────────────┐
│ LAYER 4: Execution & Result Validation                  │
│ • Run simulation with validated parameters              │
│ • Check output quality                                  │
│ • Verify biological plausibility                        │
│ • Compare to literature                                 │
└────────────────────┬────────────────────────────────────┘
                     ↓
        ┌────────────────────┐
        │ RESULTS VALID?     │
        └────────┬───────────┘
                 │ NO
                 ↓
        ┌──────────────────────┐
        │ RETURN WITH WARNING  │
        │ Results flagged as   │
        │ requiring manual     │
        │ review              │
        └──────────────────────┘
                 │ YES
                 ↓
┌─────────────────────────────────────────────────────────┐
│ OUTPUT: Validated Results with Confidence Score         │
│ • Overall confidence (0-1)                              │
│ • Flags and warnings                                    │
│ • Literature support summary                            │
│ • Recommendations for improvement                       │
└─────────────────────────────────────────────────────────┘
```

---

## Implementation Checklist

### For Each Parameter

- [ ] **Has literature backing**
  - [ ] Minimum 2 peer-reviewed sources
  - [ ] DOI or PubMed ID documented
  - [ ] Relevance justified in comments

- [ ] **Value within known range**
  - [ ] Min/max from literature identified
  - [ ] Value within range OR exception documented
  - [ ] Confidence score calculated

- [ ] **Conditions documented**
  - [ ] Temperature specified (with uncertainty)
  - [ ] pH specified (with uncertainty)
  - [ ] Buffer system documented
  - [ ] Substrate type specified

- [ ] **Assumptions verified**
  - [ ] Steady-state assumption checked
  - [ ] No substrate depletion verified
  - [ ] No product inhibition assumed
  - [ ] All assumptions documented

### For Each Model

- [ ] **Mathematical validity**
  - [ ] Michaelis-Menten equation correct
  - [ ] Differential equations verified
  - [ ] Numerical solution accurate

- [ ] **Biological validity**
  - [ ] Enzyme behavior realistic
  - [ ] Kinetic behavior matches literature
  - [ ] Conditions physiologically relevant

- [ ] **Statistical quality**
  - [ ] R² > 0.95 for model fit
  - [ ] Residuals normally distributed
  - [ ] No systematic deviations

### For Each Simulation

- [ ] **Pre-simulation**
  - [ ] All parameters validated
  - [ ] All literature verified
  - [ ] All assumptions checked
  - [ ] Initial conditions reasonable

- [ ] **Post-simulation**
  - [ ] Output within expected range
  - [ ] No NaN or Infinity values
  - [ ] Trajectory biologically plausible
  - [ ] Results match literature examples

- [ ] **Quality metrics**
  - [ ] Goodness of fit assessed
  - [ ] Confidence interval calculated
  - [ ] Outliers identified and explained

---

## Error Resolution

### If Parameter Out of Range

```
Error: Km value 15.2 mM outside literature range [4.5, 10.5] mM

Resolution Options:
1. ✓ Provide new literature source justifying 15.2 mM
2. ✓ Revise parameter to be within range
3. ✓ Document as experimental/unusual parameter
   - Requires scientific editor approval
   - Flag in results as "non-standard conditions"
   - Include uncertainty in confidence calculation
```

### If Citation Cannot Be Verified

```
Error: DOI 10.1234/invalid cannot be resolved

Resolution Options:
1. ✓ Provide correct DOI
2. ✓ Provide PubMed Central ID
3. ✓ Provide arXiv ID (for preprints)
4. ✓ Provide full URL with access date
   - Requires confirmation of accessibility
   - Marked as "non-standard source"
   - Reduced confidence score
```

### If Simulation Results Inconsistent

```
Error: Product formation 2x faster than literature

Resolution Options:
1. ✓ Review all parameters (especially Vmax)
2. ✓ Check temperature (small change = large effect)
3. ✓ Verify substrate concentration
4. ✓ Consider enzyme concentration effect
5. ✓ Document as "unexpected behavior" requiring investigation
   - Flag for scientific review
   - Include caveat in results
   - Suggest measurement verification
```

---

## Scientific Review Approval Process

### Tier 1: Automated Validation
- Parameter ranges ✓
- Literature citations ✓
- Mathematical correctness ✓
- Output plausibility ✓

### Tier 2: Editor Review (24 hours)
- Novel parameter combinations
- Non-standard conditions
- Out-of-range results
- Contradicts literature

### Tier 3: Peer Review (1 week)
- Major methodological questions
- Significant new findings
- Publishable-quality analysis

---

## Confidence Scoring

```typescript
interface ConfidenceScore {
  overall: number;           // 0-1 final confidence
  
  breakdown: {
    parameterValidation: number;   // 0-1
    literatureSupport: number;     // 0-1
    modelValidity: number;         // 0-1
    resultPlausibility: number;    // 0-1
  };
  
  factors: {
    literatureSources: number;     // How many sources?
    citationQuality: number;       // Impact factor, citation count
    assumptionViolations: number;  // How many assumptions broken?
    resultOutliers: number;        // Statistical outliers detected?
  };
}

function calculateConfidenceScore(validation: ValidationResult): ConfidenceScore {
  // High confidence: All parameters in range, multiple literature sources, assumptions hold
  // Medium confidence: Some out-of-range parameters or assumption violations
  // Low confidence: Multiple issues or non-standard conditions
  
  return {
    overall: Math.min(
      validation.parameterConfidence,
      validation.literatureConfidence,
      validation.modelConfidence,
      validation.resultConfidence
    ),
    
    breakdown: {
      parameterValidation: validation.parameterConfidence,
      literatureSupport: validation.literatureConfidence,
      modelValidity: validation.modelConfidence,
      resultPlausibility: validation.resultConfidence
    },
    
    factors: {
      literatureSources: validation.literatureReferences.length,
      citationQuality: calculateCitationQuality(validation.literatureReferences),
      assumptionViolations: validation.assumptionViolations.length,
      resultOutliers: validation.outliers.length
    }
  };
}
```

---

## Documentation Requirements

Every simulation result must include:

```json
{
  "scientificValidation": {
    "parameters": {
      "km": {
        "value": 5.2,
        "unit": "mM",
        "literatureRange": [4.5, 10.5],
        "sources": ["DOI:10.xxx", "PMID:123456"],
        "confidence": 0.95
      }
    },
    "literature": {
      "referencesUsed": 3,
      "allPeerReviewed": true,
      "averageImpactFactor": 5.2,
      "averageCitations": 1200
    },
    "assumptions": {
      "steadyStateAssumed": true,
      "violationCount": 0,
      "flaggedAssumptions": []
    },
    "results": {
      "dataQuality": "high",
      "biologicalPlausibility": "high",
      "comparisonToLiterature": "within range",
      "statisticalQuality": "good (R²=0.98)"
    },
    "confidence": 0.94,
    "flags": [],
    "recommendations": []
  }
}
```

---

## When to Reject Simulations

**STOP and reject if:**

1. ❌ Parameters have NO literature backing
2. ❌ Citations cannot be verified (invalid DOI, inaccessible paper)
3. ❌ Peer review status unknown AND other concerns exist
4. ❌ Results contradict multiple literature sources without explanation
5. ❌ Critical assumptions violated (e.g., substrate depleted >50%)
6. ❌ Output contains NaN, Infinity, or negative values (where impossible)
7. ❌ Results are statistical outliers (>3σ from expected)
8. ❌ No scientific justification for novel parameters

---

## Document Control

**Version:** 1.0  
**Status:** Active  
**Last Updated:** 2026-08-09  
**Next Review:** 2026-11-09  
**Owner:** Scientific Review Team  

**Key Principle:** NO CODE SHIPS WITHOUT SCIENTIFIC VALIDATION
