# Literature Integration & Citation Tracking Guide

**Purpose:** Comprehensive system for integrating, verifying, and tracking all scientific literature  
**Status:** Implementation Framework  
**Last Updated:** 2026-08-09  
**Owner:** Literature & Research Team  

---

## Core Principle

**EVERY PARAMETER IS TRACEABLE TO PRIMARY LITERATURE**

No magic numbers. No assumptions without sources. Every value can be traced back to peer-reviewed publications with full citations.

---

## Literature Database Schema

```typescript
interface LiteratureDatabaseEntry {
  // Unique identifiers
  id: string;                    // Internal ID (lit_12345)
  doi?: string;                  // Primary identifier
  pubmedId?: string;
  pubmedCentralId?: string;
  arxivId?: string;
  
  // Bibliographic metadata
  bibliographic: {
    title: string;
    authors: {
      firstName: string;
      lastName: string;
      affiliation?: string;
    }[];
    year: number;
    month?: number;
    journal: string;
    volume: string;
    issue?: string;
    pages?: string;
    doi?: string;
  };
  
  // Journal quality metrics
  journalMetrics: {
    impactFactor: number;        // JCR impact factor
    citationScore: number;       // Scopus citation score
    quartile: 'Q1' | 'Q2' | 'Q3' | 'Q4';
    peerReviewed: boolean;
  };
  
  // Content classification
  classification: {
    primaryDomain: string;       // mm, sir, etc.
    subdomains: string[];
    methodologicalType: 'experimental' | 'theoretical' | 'review' | 'meta-analysis';
    relevanceScore: number;      // 0-1 relevance to project
  };
  
  // Key findings extracted
  keyFindings: {
    parameters: Array<{
      name: string;             // km, vmax, etc.
      value: number;
      unit: string;
      conditions?: string;      // Temperature, pH, etc.
      confidence: number;       // 0-1
      tableNumber?: string;
      figureNumber?: string;
    }>;
    
    methods: string[];          // Key experimental methods
    species: string[];          // Organisms studied
    substrates: string[];       // Substrates tested
    enzymes: string[];          // Enzymes studied
  };
  
  // Full text and excerpts
  content: {
    abstract: string;
    keyExcerpts: Array<{
      text: string;
      pageNumber: number;
      relevance: string;
    }>;
    fullTextUrl?: string;
    pdfPath?: string;           // Local copy path
    accessDate: Date;
  };
  
  // Access and licensing
  access: {
    openAccess: boolean;
    accessibleTo: 'all' | 'subscribers' | 'restricted';
    license?: string;
    preprint: boolean;
  };
  
  // Usage tracking
  usage: {
    citations: number;          // Times cited globally
    citedBy: string[];          // DOIs citing this paper
    usedInProject: {
      projectName: string;
      usedFor: string[];        // What parameters/models?
      usageDate: Date;
      confidence: number;
    }[];
  };
  
  // Quality assessment
  quality: {
    methodologyScore: number;   // 0-1 quality of methods
    reproductibilityScore: number; // 0-1 detail of methodology
    dataQualityScore: number;   // 0-1 quality of results
    overallScore: number;       // 0-1 overall quality
    issues?: string[];          // Known issues/criticisms
  };
  
  // Verification status
  verification: {
    fullyVerified: boolean;
    verificationType: 'manual' | 'automated' | 'peer-reviewed';
    verifiedBy?: string;        // Person/system that verified
    verifiedDate?: Date;
    verificationNotes?: string;
  };
}
```

---

## Parameter Extraction & Verification

### Structured Extraction Process

```typescript
interface ParameterExtraction {
  // Source location
  source: {
    doi: string;
    tableNumber?: string;
    figureNumber?: string;
    pageNumber: number;
    excerpt: string;          // Exact text from paper
  };
  
  // Extracted value
  value: {
    number: number;
    unit: string;
    uncertainty?: {
      type: 'range' | 'std-error' | 'confidence-interval';
      min: number;
      max: number;
    };
    condition: {
      temperature?: { value: number; unit: 'C' | 'K' };
      pH?: number;
      substrate?: string;
      enzyme?: string;
      species?: string;
    };
  };
  
  // Verification
  extraction: {
    extractedBy: string;       // Person/AI who extracted
    confidence: number;        // 0-1 confidence in accuracy
    notes: string;
  };
}

// Example: Extracting Km for Lactate Dehydrogenase
const kmExtraction: ParameterExtraction = {
  source: {
    doi: '10.1016/S0021-9258(20)71234-5',
    tableNumber: '2',
    pageNumber: 8236,
    excerpt: 'The Km for lactate at 37°C and pH 7.4 was 5.2 ± 0.3 mM'
  },
  
  value: {
    number: 5.2,
    unit: 'mM',
    uncertainty: {
      type: 'std-error',
      min: 4.9,
      max: 5.5
    },
    condition: {
      temperature: { value: 37, unit: 'C' },
      pH: 7.4,
      substrate: 'lactate',
      enzyme: 'lactate dehydrogenase',
      species: 'Homo sapiens'
    }
  },
  
  extraction: {
    extractedBy: 'researcher_id_123',
    confidence: 0.98,
    notes: 'Direct from Table 2, clear methodology in methods section'
  }
};
```

### Cross-Verification Against Multiple Sources

```typescript
async function crossVerifyParameter(
  parameterName: string,
  extractedValues: ParameterExtraction[]
): Promise<CrossVerificationResult> {
  
  // Step 1: Collect all values
  const values = extractedValues.map(e => e.value.number);
  const sources = extractedValues.map(e => e.source.doi);
  
  // Step 2: Statistical analysis
  const stats = {
    mean: calculateMean(values),
    stdDev: calculateStdDev(values),
    min: Math.min(...values),
    max: Math.max(...values),
    range: Math.max(...values) - Math.min(...values),
    relativeDeviation: (calculateStdDev(values) / calculateMean(values)) * 100
  };
  
  // Step 3: Outlier detection
  const outliers = detectOutliers(values, stats.mean, stats.stdDev);
  
  // Step 4: Source quality weighting
  const weightedMean = values.reduce((sum, val, i) => {
    const sourceQuality = await assessSourceQuality(sources[i]);
    return sum + (val * sourceQuality);
  }, 0) / values.length;
  
  // Step 5: Consensus decision
  let recommendation: 'accept' | 'caution' | 'reject' = 'accept';
  if (stats.relativeDeviation > 20) {
    recommendation = 'caution'; // High variability
  }
  if (outliers.length === values.length) {
    recommendation = 'reject'; // All inconsistent
  }
  
  return {
    parameterName,
    extractedValues,
    statistics: stats,
    outliers,
    weightedMean,
    recommendation,
    confidence: calculateCrossVerificationConfidence(stats, outliers, sources),
    interpretation: `Based on ${sources.length} sources, ${recommendation} value of ${weightedMean.toFixed(2)}`
  };
}
```

---

## Literature Database Integration

### API-Level Integration

```typescript
// All literature references available to API endpoints
class LiteratureService {
  private db: LiteratureDatabaseEntry[] = [];
  
  /**
   * Find all literature supporting a parameter
   */
  async findParameterLiterature(
    parameterName: string,
    domain: string
  ): Promise<LiteratureDatabaseEntry[]> {
    return this.db.filter(entry => 
      entry.keyFindings.parameters.some(p => p.name === parameterName) &&
      entry.classification.primaryDomain === domain
    );
  }
  
  /**
   * Get recommended value for parameter based on literature
   */
  async getRecommendedValue(
    parameterName: string,
    domain: string,
    conditions: ExperimentalConditions
  ): Promise<ParameterRecommendation> {
    const literature = await this.findParameterLiterature(parameterName, domain);
    
    // Filter to matching conditions
    const matching = literature.filter(entry =>
      this.conditionsMatch(entry, conditions)
    );
    
    if (matching.length === 0) {
      // No exact match, find closest
      return await this.findClosestMatch(parameterName, domain, conditions);
    }
    
    // Calculate consensus value
    return this.calculateConsensus(matching, parameterName);
  }
  
  /**
   * Verify parameter is within literature bounds
   */
  async verifyParameterBounds(
    parameterName: string,
    value: number,
    domain: string
  ): Promise<BoundsVerification> {
    const literature = await this.findParameterLiterature(parameterName, domain);
    const values = literature.flatMap(e =>
      e.keyFindings.parameters
        .filter(p => p.name === parameterName)
        .map(p => p.value)
    );
    
    if (values.length === 0) {
      return {
        verified: false,
        reason: 'No literature found for parameter',
        suggestedReferences: literature.slice(0, 5)
      };
    }
    
    const [min, max] = [Math.min(...values), Math.max(...values)];
    const buffer = (max - min) * 0.1; // 10% buffer for uncertainty
    
    return {
      verified: value >= (min - buffer) && value <= (max + buffer),
      min: min - buffer,
      max: max + buffer,
      literatureReferences: literature.length,
      suggestion: value < min ? `Consider using ${min.toFixed(2)}` : 
                 value > max ? `Consider using ${max.toFixed(2)}` :
                 'Value within literature bounds'
    };
  }
  
  private conditionsMatch(
    entry: LiteratureDatabaseEntry,
    conditions: ExperimentalConditions
  ): boolean {
    // Match temperature, pH, substrate, species
    const findings = entry.keyFindings.parameters[0];
    if (!findings.conditions) return false;
    
    // Parse conditions from string and compare
    return this.parseConditions(findings.conditions).match(conditions);
  }
  
  private async findClosestMatch(
    parameterName: string,
    domain: string,
    conditions: ExperimentalConditions
  ): Promise<ParameterRecommendation> {
    const literature = await this.findParameterLiterature(parameterName, domain);
    
    // Score each by how close conditions are
    const scored = literature.map(entry => ({
      entry,
      score: this.scoreConditionMatch(entry, conditions)
    }));
    
    scored.sort((a, b) => b.score - a.score);
    
    return {
      value: scored[0].entry.keyFindings.parameters[0].value,
      source: scored[0].entry.bibliographic.doi || 'unknown',
      confidenceScore: scored[0].score,
      warning: 'Not exact match - conditions differ slightly'
    };
  }
  
  private calculateConsensus(
    literature: LiteratureDatabaseEntry[],
    parameterName: string
  ): ParameterRecommendation {
    const values = literature.flatMap(e =>
      e.keyFindings.parameters
        .filter(p => p.name === parameterName)
        .map(p => ({
          value: p.value,
          quality: e.quality.overallScore,
          citations: e.usage.citations
        }))
    );
    
    // Weighted mean by journal quality
    const weightedMean = values.reduce((sum, v) => 
      sum + (v.value * v.quality), 0) / values.length;
    
    return {
      value: weightedMean,
      range: [Math.min(...values.map(v => v.value)), 
               Math.max(...values.map(v => v.value))],
      sourceCount: literature.length,
      averageJournalQuality: literature.reduce((s, e) => 
        s + e.journalMetrics.impactFactor, 0) / literature.length,
      recommendation: 'Use weighted consensus value',
      sources: literature.map(e => e.bibliographic.doi || 'unknown')
    };
  }
}
```

---

## Citation Tracking & Lineage

### Citation Lineage Graph

```typescript
interface CitationLineage {
  parameter: string;
  value: number;
  unit: string;
  
  // Direct sources
  directSources: {
    primaryLiterature: LiteratureDatabaseEntry[];
    extractionDate: Date;
  };
  
  // Traceback path
  lineage: {
    source1: {
      doi: string;
      extractedValue: number;
      conditions: string;
      confidence: number;
    };
    source2: {
      doi: string;
      citesSource1: boolean;
      extractedValue: number;
      confidence: number;
    };
    source3?: {
      // ... and so on
    };
  };
  
  // Chain of custody
  chainOfCustody: Array<{
    step: number;
    action: 'extracted' | 'verified' | 'cited' | 'recalculated';
    from: string;        // Paper or person
    date: Date;
    confidence: number;
    notes: string;
  }>;
}

/**
 * For every parameter value used, we can trace back:
 * - Which paper was it extracted from? (with page number)
 * - Who did the extraction? (with confidence score)
 * - Has it been cross-verified? (which other papers confirm it?)
 * - What are the measurement conditions? (T, pH, substrate, etc.)
 * - How certain are we? (0-1 confidence with justification)
 */
```

### Interactive Citation Explorer

```typescript
class CitationExplorer {
  /**
   * Show complete path from parameter value to original papers
   */
  async explainParameterOrigin(
    parameterName: string,
    value: number
  ): Promise<string> {
    // Example output:
    return `
Parameter: km = ${value} mM
Source: Smith et al. (2020), Nature Enzymology, DOI: 10.xxxx/xxxxxx
  - Extracted from: Table 2, page 156
  - Experimental conditions: 37°C, pH 7.4, substrate lactate
  - Measurement uncertainty: ±5% (0.05 mM)
  - Authors' conclusion: "Km for human LDH is 5.2 ± 0.3 mM"

Cross-validation:
  - Johnson et al. (2018) reported 5.1 mM (independent confirmation)
  - Williams et al. (2022) reported 5.4 mM (recent measurement)
  - Consensus range: [4.9, 5.5] mM
  - Confidence score: 0.96/1.0 (high confidence)

Traceback complete: Value confirmed in 3 independent peer-reviewed sources
    `;
  }
  
  /**
   * Identify potential conflicts in literature
   */
  async findConflictingSources(
    parameterName: string
  ): Promise<ConflictAnalysis> {
    const sources = await literatureDB.findParameterLiterature(
      parameterName,
      'mm'
    );
    
    const values = sources.map(s => ({
      value: s.keyFindings.parameters[0].value,
      source: s.bibliographic.doi,
      conditions: s.keyFindings.parameters[0].conditions
    }));
    
    // Find outliers
    const outliers = this.identifyOutliers(values);
    
    if (outliers.length > 0) {
      return {
        hasConflicts: true,
        conflictingValues: outliers,
        possibleCauses: [
          'Different experimental conditions (temperature, pH)',
          'Different substrates',
          'Different species/organisms',
          'Measurement errors in original papers',
          'Evolution of protocols over time'
        ],
        recommendation: 'Use values from most recent high-quality study',
        resolveBy: 'Conduct new experiments to verify'
      };
    }
    
    return { hasConflicts: false };
  }
}
```

---

## Automated Literature Integration

### Periodic Literature Review

```typescript
async function performPeriiodicLiteratureReview() {
  // Runs monthly to find new publications
  
  const domains = ['mm', 'sir'];  // Domains to monitor
  const keywords = ['enzyme kinetics', 'michaelis-menten', 'SIR model'];
  
  for (const domain of domains) {
    for (const keyword of keywords) {
      // Search PubMed
      const pubmedResults = await searchPubMed(keyword, {
        dateFrom: '1_month_ago',
        sort: 'date'
      });
      
      // Search arXiv (for preprints)
      const arxivResults = await searchArXiv(keyword, {
        dateFrom: '1_month_ago',
        sort: 'date'
      });
      
      for (const result of [...pubmedResults, ...arxivResults]) {
        // Automatically extract if new
        if (!await literatureDB.exists(result.doi)) {
          const entry = await extractLiteratureEntry(result);
          
          // Extract parameters automatically (if possible)
          const extraction = await autoExtractParameters(entry);
          
          if (extraction.confidence > 0.8) {
            // High confidence - auto-add
            await literatureDB.add(entry);
            console.log(`✓ Added: ${entry.bibliographic.title}`);
          } else {
            // Flag for manual review
            await flagForManualReview(entry, extraction);
            console.log(`⚠ Flagged for review: ${entry.bibliographic.title}`);
          }
        }
      }
    }
  }
}
```

---

## Quality Assurance

### Citation Quality Scorecard

```
Scorecard: Lactate Dehydrogenase, Km Parameter

Source 1: Smith et al. (2020) ✓✓✓✓✓
├─ DOI: Verified ✓
├─ Peer reviewed: Yes ✓
├─ Impact factor: 5.27 (Q1) ✓
├─ Citations: 1847 ✓
├─ Method clarity: High ✓
├─ Value: 5.2 mM
├─ Uncertainty: ±0.3 mM ✓
└─ Score: 0.98/1.0

Source 2: Johnson et al. (2018) ✓✓✓✓
├─ DOI: Verified ✓
├─ Peer reviewed: Yes ✓
├─ Impact factor: 4.15 (Q1) ✓
├─ Citations: 523 ✓
├─ Method clarity: Medium (~)
├─ Value: 5.1 mM
├─ Uncertainty: ±0.5 mM
└─ Score: 0.92/1.0

Source 3: ArXiv Preprint (2023) ⚠
├─ DOI: N/A ⚠
├─ Peer reviewed: No ⚠
├─ Value: 5.4 mM
├─ Uncertainty: Not reported ⚠
└─ Score: 0.60/1.0 (use with caution)

CONSENSUS:
├─ Mean: 5.23 mM
├─ Range: [4.9, 5.5] mM
├─ Confidence: 0.95/1.0
└─ Recommendation: ACCEPT (high confidence value)
```

---

## Document Control

**Version:** 1.0  
**Status:** Active  
**Last Updated:** 2026-08-09  
**Next Review:** 2026-11-09  
**Owner:** Literature & Research Team  

**Key Principle:** EVERY PARAMETER IS TRACEABLE TO PRIMARY LITERATURE
