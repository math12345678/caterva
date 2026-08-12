#!/usr/bin/env node
/**
 * End-to-End Integration Test
 * Tests web server → PubMed → Terium → Results
 */

const http = require('http');

function request(method, path, body = null) {
  return new Promise((resolve, reject) => {
    const options = {
      hostname: 'localhost',
      port: 3000,
      path,
      method,
      headers: { 'Content-Type': 'application/json', timeout: 30000 }
    };

    const req = http.request(options, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try {
          const json = JSON.parse(data);
          resolve({ status: res.statusCode, data: json });
        } catch (e) {
          resolve({ status: res.statusCode, data: data });
        }
      });
    });

    req.on('error', reject);
    req.setTimeout(30000, () => req.abort());
    if (body) req.write(JSON.stringify(body));
    req.end();
  });
}

async function testSimulation(enzyme, substrate, model, km, vmax, s0) {
  console.log(`\n🧬 Testing: ${enzyme} + ${substrate} (${model})`);

  try {
    // Submit
    console.log('  → Submitting...');
    const submit = await request('POST', '/api/simulate', {
      query: model,
      parameters: { km, vmax, s0 },
      enzyme,
      substrate
    });

    if (submit.status !== 200) {
      console.log(`  ✗ Failed: ${submit.status}`);
      return false;
    }

    const jobId = submit.data.jobId;
    console.log(`  ✓ Job queued: ${jobId}`);

    // Poll for completion
    console.log('  → Waiting for results (max 30s)...');
    let job = null;
    for (let i = 0; i < 30; i++) {
      const status = await request('GET', `/api/jobs/${jobId}`);
      job = status.data;

      if (job.status === 'complete') {
        console.log(`  ✓ Completed in ${job.duration}ms`);
        break;
      } else if (job.status === 'error') {
        console.log(`  ✗ Error: ${job.error}`);
        return false;
      } else {
        console.log(`  ⏳ Progress: ${job.progress}%`);
        await new Promise(r => setTimeout(r, 1000));
      }
    }

    if (!job || job.status !== 'complete') {
      console.log('  ✗ Timeout');
      return false;
    }

    // Validate results
    const result = job.result;
    console.log(`  ✓ Validated: ${result.validated}`);
    console.log(`  ✓ Confidence: ${(result.validationConfidence * 100).toFixed(1)}%`);
    if (result.results?.finalValue) {
      console.log(`  ✓ Final substrate: ${result.results.finalValue.toFixed(3)} mM`);
    }

    return true;
  } catch (error) {
    console.log(`  ✗ Exception: ${error.message}`);
    return false;
  }
}

async function runTests() {
  console.log('\n' + '='.repeat(60));
  console.log('TERRIUM END-TO-END INTEGRATION TESTS');
  console.log('='.repeat(60));

  const testCases = [
    {
      name: 'Michaelis-Menten',
      enzyme: 'lactate dehydrogenase',
      substrate: 'lactate',
      model: 'michaelis-menten',
      km: 5.2,
      vmax: 12.8,
      s0: 10
    },
    {
      name: 'Competitive Inhibition',
      enzyme: 'catalase',
      substrate: 'hydrogen peroxide',
      model: 'competitive-inhibition',
      km: 3.0,
      vmax: 15.0,
      s0: 8
    },
    {
      name: 'Non-Competitive Inhibition',
      enzyme: 'amylase',
      substrate: 'starch',
      model: 'non-competitive-inhibition',
      km: 4.5,
      vmax: 10.0,
      s0: 12
    }
  ];

  let passed = 0;
  let failed = 0;

  for (const test of testCases) {
    const success = await testSimulation(
      test.enzyme,
      test.substrate,
      test.model,
      test.km,
      test.vmax,
      test.s0
    );
    if (success) passed++;
    else failed++;
  }

  console.log('\n' + '='.repeat(60));
  console.log(`RESULTS: ${passed} passed, ${failed} failed`);
  console.log('='.repeat(60) + '\n');

  process.exit(failed > 0 ? 1 : 0);
}

// Wait for server to be ready
setTimeout(runTests, 2000);
