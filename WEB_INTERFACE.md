> **Corrected 2026-08-11.** This doc documented `/api/literature/search`
> with a full example response. That route exists on neither server; the
> section now shows how literature search actually works — inside
> `POST /api/simulate`, via the `enzyme` and `substrate` fields.
>
> Its "178/178 tests passing" figure is unverified; run `npm test`. Real
> routes it omits are listed in [`docs/API.md`](docs/API.md), which is
> checked against the servers on every build.

# Terrium Web Interface

## Quick Start

Build and run the web server:

```bash
chmod +x start-server.sh
./start-server.sh
```

Then open **http://localhost:3000** in your browser.

## What You Get

✅ **Interactive Dashboard** — Submit simulations via web form
✅ **Real-time Results** — Job polling with progress tracking
✅ **Live Charts** — Trajectory visualization with Chart.js
✅ **Results Table** — Recent simulation history
✅ **REST API** — Programmatic access to everything

## API Endpoints

### Submit a Simulation

```bash
curl -X POST http://localhost:3000/api/simulate \
  -H "Content-Type: application/json" \
  -d '{
    "query": "michaelis-menten",
    "parameters": { "km": 5.2, "vmax": 12.8, "s0": 10 },
    "enzyme": "lactate dehydrogenase",
    "substrate": "lactate"
  }'

# Returns: { "jobId": "job_1234...", "status": "queued" }
```

### Check Job Status

```bash
curl http://localhost:3000/api/jobs/job_1234...

# Returns: { "status": "running|complete|error", "progress": 50, "result": {...}, ... }
```

### Health Check

```bash
curl http://localhost:3000/api/health

# Returns: { "status": "ok", "uptime": 123.45, "jobs": {...} }
```

### Search PubMed Literature

There is no literature-search route. This section documented one, with a
working-looking `curl`, and it has never existed on either server.

PubMed search happens **inside** `POST /api/simulate`: supply `enzyme` and
`substrate` and the server looks up real kinetics before running, then
returns the papers it used attached to the job result.

```bash
curl -X POST http://localhost:3000/api/simulate \
  -H 'Content-Type: application/json' \
  -d '{
        "query": "michaelis-menten",
        "parameters": { "km": 5.2, "vmax": 12.8, "s0": 10.0 },
        "enzyme": "lactate dehydrogenase",
        "substrate": "pyruvate"
      }'

# Then poll: curl http://localhost:3000/api/jobs/<jobId>
```

## How It Works

1. **Submit** → User enters enzyme/substrate + kinetic model parameters in dashboard
2. **Queue** → Request goes to POST /api/simulate, gets a jobId
3. **Process** → Background job:
   - Searches PubMed for real literature (5-10s)
   - Runs Tellurium kinetics simulation (2-3s)
   - Stores results in-memory
4. **Poll** → Dashboard calls GET /api/jobs/:jobId every 1 second (max 60s timeout)
5. **Display** → Results rendered in table + trajectory chart

## Real Data Integration

When you submit a simulation with enzyme/substrate:

1. **PubMed Search** — Finds peer-reviewed papers with kinetics data
2. **Multi-Strategy Fallback** — Tries broad, then narrow, then enzyme-only queries
3. **CrossRef Resolution** — Validates DOIs from papers
4. **SBML Model Generation** — Creates valid Systems Biology Markup Language
5. **Tellurium Execution** — Runs kinetic equations, returns time-series data

If literature is found: ✅ Results marked as "validated"
If no literature: ⚠️ Results marked as "unverified" + clear warning

## Architecture

```
Browser (Dashboard)
    ↓ POST /api/simulate
Node.js HTTP Server (dist/src/web/server.js)
    ├→ Background Job Processor
    │   ├→ searchPubMedForEnzymeKinetics()
    │   ├→ resolveDOIFromCrossRef()
    │   ├→ ScientificPipeline.execute()
    │   └→ Tellurium simulation
    │
    └→ GET /api/jobs/:jobId (polling)
        └→ Returns: status, progress, results, duration
```

## Development

### File Structure

```
src/web/
├── server.ts           # Node.js HTTP server (no Express dependency)
├── dashboard.html      # Interactive web interface
└── README.md

dist/src/web/
├── server.js           # Compiled server
└── dashboard.html      # Copied from src/web
```

### Running in Development

With ts-node (auto-compile TypeScript):

```bash
npm install -D ts-node
npx ts-node src/web/server.ts
```

With built files (faster startup):

```bash
npm run build
node dist/src/web/server.js
```

### Adding New Endpoints

Edit `src/web/server.ts`, add routing logic in the `createServer()` callback:

```typescript
// GET /api/custom
if (pathname === '/api/custom' && req.method === 'GET') {
  res.writeHead(200, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify({ data: 'your data' }));
  return;
}
```

Then rebuild: `npm run build`

## Troubleshooting

**Port 3000 already in use?**
```bash
PORT=3001 node dist/src/web/server.js
```

**Dashboard not loading?**
- Make sure `dashboard.html` is in `dist/src/web/`
- Check browser console (F12) for errors
- Verify server is running: `curl http://localhost:3000/api/health`

**Simulations timing out?**
- PubMed searches can take 5-10 seconds
- Tellurium simulation adds 2-3 seconds
- Dashboard max timeout is 60 seconds
- Check logs for "Simulation error" or "PubMed failed"

**No results table?**
- Click "Run Simulation" to submit a job
- Dashboard polls automatically for 60 seconds
- If job doesn't complete, check browser console for fetch errors

## Next Steps

- [ ] WebSocket support for real-time progress (vs polling)
- [ ] Database persistence (vs in-memory jobs)
- [ ] Authentication & rate limiting
- [ ] Multi-user job queue
- [ ] Advanced parameter sweep UI
- [ ] Export results as CSV/JSON
- [ ] Literature citation export (BibTeX)
