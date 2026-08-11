/**
 * Terrium Web Server
 *
 * REST API for scientific simulations
 * Serves interactive dashboard
 * Uses Node.js built-in HTTP module (no external dependencies)
 */

import * as http from 'http';
import * as fs from 'fs';
import * as path from 'path';
import { URL } from 'url';
import { logger } from '../logger';
import ScientificPipeline from '../integration/scientificPipeline';
import { searchPubMedForEnzymeKinetics } from '../integrations/crossref-pubmed-real';
import { resolveDOIFromCrossRef } from '../integrations/crossref-pubmed-real';

const PORT = parseInt(process.env.PORT || '3000', 10);

// In-memory job storage
const jobs = new Map<string, any>();

// ============================================================================
// HTTP SERVER
// ============================================================================

const server = http.createServer(async (req, res) => {
  // Enable CORS
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') {
    res.writeHead(200);
    res.end();
    return;
  }

  const url = new URL(req.url || '', `http://${req.headers.host}`);
  const pathname = url.pathname;

  try {
    // POST /api/simulate
    if (pathname === '/api/simulate' && req.method === 'POST') {
      let body = '';
      req.on('data', chunk => (body += chunk));
      req.on('end', async () => {
        try {
          const { query, parameters, enzyme, substrate } = JSON.parse(body);

          if (!query || !parameters) {
            res.writeHead(400, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ error: 'Missing query or parameters' }));
            return;
          }

          const jobId = `job_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
          logger.info({ jobId, query }, 'API: Simulation requested');

          res.writeHead(200, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ jobId, status: 'queued' }));

          // Background job processing
          (async () => {
            try {
              jobs.set(jobId, { status: 'running', startTime: Date.now(), progress: 0 });

              let literature: any[] = [];
              if (enzyme && substrate) {
                try {
                  jobs.set(jobId, { ...jobs.get(jobId), progress: 10 });
                  const papers = await searchPubMedForEnzymeKinetics(enzyme, substrate, 5);

                  for (const paper of papers) {
                    if (!paper.doi) continue;
                    try {
                      const resolved = await resolveDOIFromCrossRef(paper.doi);
                      if (resolved) {
                        literature.push({
                          id: `lit_${paper.pmid}`,
                          doi: paper.doi,
                          pubmedId: paper.pmid.toString(),
                          title: paper.title,
                          authors: paper.authors || [],
                          year: paper.year,
                          journal: paper.journal || 'Unknown',
                          peerReviewed: false,
                          abstract: paper.abstract || '',
                          domain: 'mm',
                          extractedParameters: []
                        });
                      }
                    } catch (e) {
                      // Skip unresolvable papers
                    }
                  }
                  jobs.set(jobId, { ...jobs.get(jobId), progress: 30 });
                } catch (e) {
                  logger.warn({ jobId, error: e }, 'Literature fetch failed');
                }
              }

              jobs.set(jobId, { ...jobs.get(jobId), progress: 50 });

              const pipeline = new ScientificPipeline();
              pipeline.initializeLiterature(literature);

              const response = await pipeline.execute({
                query,
                parameters,
                conditions: { temperature: 37, pH: 7.4 }
              });

              jobs.set(jobId, {
                status: 'complete',
                progress: 100,
                result: response,
                endTime: Date.now(),
                duration: Date.now() - (jobs.get(jobId)?.startTime || 0)
              });

              logger.info({ jobId, validated: response.validated }, 'Simulation complete');
            } catch (error) {
              jobs.set(jobId, {
                status: 'error',
                error: error instanceof Error ? error.message : String(error),
                endTime: Date.now(),
                duration: Date.now() - (jobs.get(jobId)?.startTime || 0)
              });
              logger.error({ jobId, error }, 'Simulation error');
            }
          })();
        } catch (e) {
          res.writeHead(400, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ error: 'Invalid JSON' }));
        }
      });
      return;
    }

    // GET /api/jobs/:jobId
    if (pathname.match(/^\/api\/jobs\//) && req.method === 'GET') {
      const jobId = pathname.split('/').pop();
      const job = jobs.get(jobId || '');

      if (!job) {
        res.writeHead(404, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: 'Job not found' }));
        return;
      }

      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify(job));
      return;
    }

    // GET /api/health
    if (pathname === '/api/health' && req.method === 'GET') {
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({
        status: 'ok',
        timestamp: new Date().toISOString(),
        uptime: process.uptime(),
        jobs: {
          total: jobs.size,
          running: Array.from(jobs.values()).filter(j => j.status === 'running').length,
          completed: Array.from(jobs.values()).filter(j => j.status === 'complete').length,
          failed: Array.from(jobs.values()).filter(j => j.status === 'error').length
        }
      }));
      return;
    }

    // GET / (dashboard)
    if (pathname === '/' && req.method === 'GET') {
      const dashboardPath = path.join(__dirname, 'dashboard.html');
      const content = fs.readFileSync(dashboardPath, 'utf-8');
      res.writeHead(200, { 'Content-Type': 'text/html' });
      res.end(content);
      return;
    }

    // 404
    res.writeHead(404, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ error: 'Not found' }));
  } catch (error) {
    res.writeHead(500, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ error: 'Server error' }));
    logger.error({ error }, 'Server error');
  }
});

server.listen(PORT, () => {
  console.log(`\n🧪 Terrium Dashboard: http://localhost:${PORT}\n`);
  logger.info({ port: PORT }, `✓ Server running`);
});
