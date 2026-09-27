# Caterva — Science Agent Pipeline

Scientific computing for teaching labs. Students ask a question in plain language; Caterva resolves parameters from the literature (BRENDA/KEGG/PubMed), runs the Caterva ODE engine, and returns a verified trajectory with citations.

## Run & Operate

### Frontend (landing page)
```bash
cd Science-Agent-Pipeline
PORT=18612 BASE_PATH=/ pnpm --filter @workspace/caterva-landing dev
```

### API server (required for the pipeline)
```bash
cd Science-Agent-Pipeline/artifacts/api-server
PORT=5000 pnpm run start
```

Or rebuild first:
```bash
cd Science-Agent-Pipeline/artifacts/api-server
PORT=5000 pnpm run dev
```

### Full stack (two terminals)
```bash
# Terminal 1 — API server
cd Science-Agent-Pipeline
PORT=5000 pnpm --filter @workspace/api-server run dev

# Terminal 2 — Frontend
cd Science-Agent-Pipeline
PORT=18612 BASE_PATH=/ pnpm --filter @workspace/caterva-landing dev
```

### CLI
```bash
cd Science-Agent-Pipeline/scripts
pnpm run cli simulate "lactate dehydrogenase km" --poll --base http://localhost:5000/api
pnpm run cli health --base http://localhost:5000/api
pnpm run cli status <jobId> --base http://localhost:5000/api
pnpm run cli stream <jobId> --base http://localhost:5000/api
pnpm run demo
```

### Build & typecheck
```bash
cd Science-Agent-Pipeline
pnpm run typecheck
pnpm run build
```

### Regenerate API client from spec
```bash
pnpm --filter @workspace/api-spec run codegen
```

## Required env
- **PORT** — api-server (5000), caterva-landing (18612)
- **BASE_PATH** — caterva-landing, mockup-sandbox (usually `/`)
- **OPENAI_API_KEY** or **LLM_API_KEY** — optional, enables LLM query resolution
- **DATABASE_URL** — optional PostgreSQL connection (graceful fallback)
- **API_SERVER_URL** — optional, defaults to `http://localhost:5000`

## Stack
- pnpm workspaces, Node.js 24, TypeScript 5.9
- Frontend: React 19, Vite 7, Tailwind CSS v4, shadcn/ui, Framer Motion, Recharts
- API: Express 5, Zod, Pino
- DB: PostgreSQL + Drizzle ORM (optional)
- Python bridge: Caterva engine (antimony + libroadrunner + libSBML)
- Literature: BRENDA / KEGG / UniProt / PubMed live APIs

## Pipeline flow
User query → LLM or keyword resolver → Python science agent (BRENDA/KEGG/PubMed) → Python Caterva engine (ODE simulation) → PostgreSQL persistence → SSE stream

## Architecture
```
Science-Agent-Pipeline/
├── artifacts/
│   ├── api-server/          Express 5 REST API + Python bridge
│   ├── caterva-landing/     Main React frontend
│   └── mockup-sandbox/      UI component preview server
├── lib/
│   ├── api-spec/            OpenAPI 3.1 spec + Orval codegen
│   ├── api-client-react/    Generated React-Query hooks
│   ├── api-zod/             Generated Zod schemas
│   └── db/                  Drizzle ORM schema + client
├── scripts/                 CLI tool (sci-pipe)
└── attached_assets/         Design specs

Caterva/
├── caterva/               Python ODE engine (MM, SIR, SEIR)
├── Tests/                   BRENDA/KEGG/PubMed literature layer
└── scripts/                 Environment verification
```
