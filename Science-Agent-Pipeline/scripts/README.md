# Science Agent Pipeline CLI

Command-line interface for the Science Agent Pipeline simulation API.

## Installation

```bash
cd scripts
npm install
npm run build
```

## Usage

```bash
# Submit a simulation query (polling for completion)
sci-pipe simulate "simulate lactate dehydrogenase with pyruvate" --poll

# Check job status
sci-pipe status <jobId>

# Stream real-time updates via SSE
sci-pipe stream <jobId>

# Check server health
sci-pipe health
```

## Commands

### `simulate <query>`

Submit a natural-language simulation query to the pipeline.

**Options:**
- `-b, --base <url>` — API base URL (default: `http://localhost:3000/api`)
- `--poll` — Wait for completion and show result
- `--interval <ms>` — Polling interval in ms (default: 1000)

**Examples:**
```bash
# Michaelis-Menten enzyme kinetics
sci-pipe simulate "simulate lactate dehydrogenase with pyruvate" --poll

# With parameter overrides
sci-pipe simulate "simulate enzyme kinetics km=5 vmax=10" --poll

# SIR epidemiology
sci-pipe simulate "simulate SIR epidemic with beta=0.5 gamma=0.2" --poll

# SEIR with incubation period
sci-pipe simulate "simulate SEIR with exposed compartment" --poll
```

### `status <jobId>`

Check the current status of a simulation job.

### `stream <jobId>`

Stream real-time job updates via Server-Sent Events (SSE).

### `health`

Check the API server health endpoint.

## Query Format

The pipeline accepts natural-language queries and resolves them to one of three simulation domains:

- **mm** — Michaelis-Menten enzyme kinetics (parameters: `km`, `vmax`, `s0`, `end`, `points`)
- **sir** — SIR epidemiology (parameters: `beta`, `gamma`, `s0`, `i0`, `r0_recovered`, `end`, `points`)
- **seir** — SEIR epidemiology (parameters: `beta`, `sigma`, `gamma`, `s0`, `e0`, `i0`, `r0_recovered`, `end`, `points`)

Parameter overrides can be specified inline: `km=2.5 vmax=10 s0=20`

## Development

```bash
npm run dev    # Watch mode with tsx
npm run cli    # Run with tsx directly
npm run build  # Compile to dist/
```