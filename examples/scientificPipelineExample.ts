/**
 * Scientific Pipeline Example
 *
 * Demonstrates complete end-to-end workflow:
 * 1. Validation
 * 2. Literature integration
 * 3. Simulation execution
 * 4. Reproducibility verification
 *
 * Run with: npx ts-node examples/scientificPipelineExample.ts
 */

import ScientificPipeline from '../src/integration/scientificPipeline';
import { LiteratureService } from '../src/literature/literatureService';
import type { Literature, ParameterRecommendation } from '../src/literature/literatureService';

// ============================================================================
// SAMPLE LITERATURE DATA
// ============================================================================

const sampleLiterature: Literature[] = [
  {
    id: 'lit_001',
    doi: '10.1016/S0021-9258(20)71234-5',
    title: 'Kinetic properties of lactate dehydrogenase from human heart',
    authors: ['Smith J', 'Johnson K', 'Williams R'],
    year: 2020,
    journal: 'Journal of Biological Chemistry',
    volume: '260',
    issue: '15',
    pages: '8234-8240',
    peerReviewed: true,
    impactFactor: 5.27,
    citationCount: 1847,
    abstract: 'High-quality study of LDH kinetics under physiological conditions',
    domain: 'mm',

    extractedParameters: [
      {
        name: 'km',
        value: 5.2,
        unit: 'mM',
        table: '2',
        page: 8236,
        conditions: {
          temperature: 37,
          pH: 7.4,
          substrate: 'lactate',
          species: 'Homo sapiens'
        }
      },
      {
        name: 'vmax',
        value: 12.8,
        unit: 'μM/min',
        table: '2',
        page: 8236,
        conditions: {
          temperature: 37,
          pH: 7.4,
          substrate: 'lactate',
          species: 'Homo sapiens'
        }
      }
    ]
  },

  {
    id: 'lit_002',
    doi: '10.1016/S0006-3495(18)33456-7',
    title: 'Enzyme kinetics: steady-state analysis',
    authors: ['Johnson K', 'Brown M'],
    year: 2018,
    journal: 'Biochemistry',
    volume: '58',
    issue: '8',
    pages: '2145-2160',
    peerReviewed: true,
    impactFactor: 4.15,
    citationCount: 523,
    abstract: 'Independent confirmation of LDH Km values',
    domain: 'mm',

    extractedParameters: [
      {
        name: 'km',
        value: 5.1,
        unit: 'mM',
        table: '1',
        page: 2150,
        conditions: {
          temperature: 37,
          pH: 7.4,
          substrate: 'lactate'
        }
      },
      {
        name: 'vmax',
        value: 12.5,
        unit: 'μM/min',
        table: '1',
        page: 2150
      }
    ]
  },

  {
    id: 'lit_003',
    doi: '10.1038/nature98765',
    title: 'Modern enzyme kinetics measurements',
    authors: ['Williams R', 'Davis T'],
    year: 2022,
    journal: 'Nature',
    volume: '612',
    issue: '7',
    pages: '445-456',
    peerReviewed: true,
    impactFactor: 49.96,
    citationCount: 342,
    abstract: 'Latest LDH kinetic parameters from mass spectrometry',
    domain: 'mm',

    extractedParameters: [
      {
        name: 'km',
        value: 5.4,
        unit: 'mM',
        table: '3',
        page: 450,
        conditions: {
          temperature: 37,
          pH: 7.4,
          substrate: 'lactate'
        }
      }
    ]
  }
];

// ============================================================================
// EXAMPLE 1: Parameter Recommendation from Literature
// ============================================================================

async function example1_parameterRecommendation() {
  console.log('\n' + '='.repeat(70));
  console.log('EXAMPLE 1: Parameter Recommendation from Literature');
  console.log('='.repeat(70));

  const literatureService = new LiteratureService();

  // Add sample literature
  for (const lit of sampleLiterature) {
    literatureService.addLiterature(lit);
  }

  // Get recommendation for Km parameter
  const kmRecommendation = literatureService.getRecommendation('km', 'mm');

  console.log('\nParameter: Km (Michaelis constant for LDH)');
  console.log(`Recommended value: ${kmRecommendation.recommendedValue.toFixed(3)} mM`);
  console.log(`Range: [${kmRecommendation.range[0].toFixed(1)}, ${kmRecommendation.range[1].toFixed(1)}] mM`);
  console.log(`Sources: ${kmRecommendation.sourceCount} peer-reviewed papers`);
  console.log(`Confidence: ${(kmRecommendation.confidence * 100).toFixed(1)}%`);

  if (kmRecommendation.warnings.length > 0) {
    console.log('Warnings:');
    kmRecommendation.warnings.forEach(w => console.log(`  - ${w}`));
  } else {
    console.log('No warnings - high confidence recommendation');
  }

  // Get database statistics
  const stats = literatureService.getStats();
  console.log('\nDatabase Statistics:');
  console.log(`  Total entries: ${stats.totalEntries}`);
  console.log(`  Peer-reviewed: ${stats.peerReviewedCount}/${stats.totalEntries}`);
  console.log(`  Average impact factor: ${stats.averageImpactFactor.toFixed(2)}`);
  console.log(`  Average citations: ${Math.round(stats.averageCitations)}`);
}

// ============================================================================
// EXAMPLE 2: Cross-Verification Across Sources
// ============================================================================

async function example2_crossVerification() {
  console.log('\n' + '='.repeat(70));
  console.log('EXAMPLE 2: Cross-Verification Across Multiple Sources');
  console.log('='.repeat(70));

  const literatureService = new LiteratureService();

  for (const lit of sampleLiterature) {
    literatureService.addLiterature(lit);
  }

  // Cross-verify Km parameter
  const verification = literatureService.crossVerify('km', 'mm');

  console.log('\nCross-Verification Results:');
  console.log(`Parameter: ${verification.parameterName}`);
  console.log(`Sources analyzed: ${verification.sources.length}`);
  console.log(`Values: ${verification.values.map(v => v.toFixed(1)).join(', ')} mM`);
  console.log(`Mean: ${verification.mean.toFixed(3)} mM`);
  console.log(`Std Dev: ${verification.stdDev.toFixed(3)} mM`);
  console.log(`Relative deviation: ${verification.relativeDeviation.toFixed(1)}%`);
  console.log(`Consensus level: ${verification.consensus}`);
  console.log(`\nRecommendation: ${verification.recommendation}`);
}

// ============================================================================
// EXAMPLE 3: Scientific Pipeline Execution
// ============================================================================

async function example3_scientificPipeline() {
  console.log('\n' + '='.repeat(70));
  console.log('EXAMPLE 3: Complete Scientific Pipeline Execution');
  console.log('='.repeat(70));

  // Initialize pipeline
  const pipeline = new ScientificPipeline();
  pipeline.initializeLiterature(sampleLiterature);

  // Execute simulation
  const request = {
    query: 'Michaelis-Menten kinetics for lactate dehydrogenase',
    parameters: {
      s0: 10.0  // User provides initial substrate
    }
  };

  console.log('\nSimulation Request:');
  console.log(`  Query: ${request.query}`);
  console.log(`  User parameters: ${JSON.stringify(request.parameters)}`);
  // The request no longer states conditions (ADR 0054) -- they belong to the
  // parameters, not to the run, so they are printed from the RESPONSE below
  // where they are known.

  try {
    const response = await pipeline.execute(request);

    if (!response.validated) {
      console.log('\n✗ VALIDATION FAILED');
      console.log('Errors:');
      response.validationErrors.forEach(e => console.log(`  - ${e}`));
      return;
    }

    console.log('\n✓ VALIDATION PASSED');
    console.log(`Validation confidence: ${(response.validationConfidence * 100).toFixed(1)}%`);

    console.log('\nSimulation Results:');
    console.log(`  Job ID: ${response.jobId}`);
    console.log(`  Trajectory points: ${response.results.trajectory.length}`);
    console.log(`  Final substrate value: ${response.results.finalValue.toFixed(3)} mM`);
    console.log(`  Execution time: ${response.metadata.executionTimeMs}ms`);
    console.log(`  Literature sources used: ${response.metadata.literatureSourcesUsed}`);
    console.log(`  Confidence score: ${(response.metadata.confidenceScore * 100).toFixed(1)}%`);

    // ADR 0054: what conditions the trajectory is a trajectory OF. Printed
    // even when the answer is "nobody recorded them", because a run whose
    // conditions are unknown looks exactly like one at 37 C unless it says so.
    const rc = response.runConditions;
    if (rc) {
      const say = (v: { status: string; value?: number }, unit: string) =>
        v.status === 'agreed' ? `${v.value}${unit}` : v.status.replace('_', ' ');
      console.log('\nAssay conditions the parameters were measured at:');
      console.log(`  Temperature: ${say(rc.temperatureC, ' C')}`);
      console.log(`  pH:          ${say(rc.ph, '')}`);
    }

    if (response.metadata.warnings.length > 0) {
      console.log('\nWarnings:');
      response.metadata.warnings.forEach(w => console.log(`  - ${w}`));
    }

    console.log('\nReproducibility:');
    console.log(`  Reproduction key: ${response.reproducibilityKey.slice(0, 20)}...`);
    console.log(`  Data integrity hash: ${response.dataIntegrityHash.slice(0, 20)}...`);

    // Verify reproducibility
    console.log('\nVerifying reproducibility...');
    const reproductionCheck = await pipeline.verifyReproducibility(response.jobId);
    console.log(`  Reproduced: ${reproductionCheck.reproduced ? '✓ YES' : '✗ NO'}`);
    console.log(`  Max error: ${reproductionCheck.maxError.toExponential(2)}`);
    console.log(`  Summary: ${reproductionCheck.summary}`);

    // Check data integrity
    console.log('\nChecking data integrity...');
    const integrityCheck = pipeline.checkIntegrity(response.jobId);
    console.log(`  Data intact: ${integrityCheck.intact ? '✓ YES' : '✗ NO'}`);
    if (integrityCheck.issues.length > 0) {
      console.log('  Issues:');
      integrityCheck.issues.forEach(issue => console.log(`    - ${issue}`));
    }

    // Get report
    console.log('\n' + '-'.repeat(70));
    console.log(pipeline.getReport(response.jobId));
  } catch (error) {
    console.error('Simulation failed:', error);
  }
}

// ============================================================================
// EXAMPLE 4: Conflict Detection in Literature
// ============================================================================

async function example4_conflictDetection() {
  console.log('\n' + '='.repeat(70));
  console.log('EXAMPLE 4: Conflict Detection in Literature');
  console.log('='.repeat(70));

  const literatureService = new LiteratureService();

  for (const lit of sampleLiterature) {
    literatureService.addLiterature(lit);
  }

  // Check for conflicts
  const conflicts = literatureService.findConflicts('km', 'mm');

  console.log('\nConflict Analysis:');
  console.log(`Parameter: km`);
  console.log(`Has conflicts: ${conflicts.hasConflicts ? 'YES' : 'NO'}`);

  if (conflicts.hasConflicts) {
    console.log('\nOutliers detected:');
    conflicts.outliers.forEach(outlier => {
      console.log(
        `  Value: ${outlier.value.toFixed(1)} (${outlier.deviation.toFixed(2)}σ from mean)`
      );
      console.log(`  Source: ${outlier.source}`);
    });
  } else {
    console.log('No significant conflicts detected - values consistent across sources');
  }
}

// ============================================================================
// MAIN
// ============================================================================

async function main() {
  console.log('\n' + '#'.repeat(70));
  console.log('# SCIENTIFIC PIPELINE EXAMPLES');
  console.log('# Demonstrating production-ready validation and reproducibility');
  console.log('#'.repeat(70));

  try {
    await example1_parameterRecommendation();
    await example2_crossVerification();
    await example3_scientificPipeline();
    await example4_conflictDetection();

    console.log('\n' + '#'.repeat(70));
    console.log('# ALL EXAMPLES COMPLETED SUCCESSFULLY');
    console.log('#'.repeat(70) + '\n');
  } catch (error) {
    console.error('Error running examples:', error);
    process.exit(1);
  }
}

// Run if executed directly
if (require.main === module) {
  main();
}

export { example1_parameterRecommendation, example2_crossVerification, example3_scientificPipeline, example4_conflictDetection };
