HASEOS_SESSION_HANDOFF.md
# HASEOS / QueenBee Session Hand-off
**Date:** 2026-08-21  
**Partners:** Noah Nemo (Light-Keeping Architect / HITL) + Grok (Team Leading Supervisor / QC)  
**Mode:** CDD split-screen coding saddle (Cursor + SuperGrok)

## Current Project Path
`/home/noah/haseos-spiral-swarm/`

## Core Runtime Status
- QueenBee is live on **1-bit Bonsai 27B** (`Bonsai-27B-Q1_0.gguf`)
- Served by `llama-server` at **http://127.0.0.1:8080** (loopback only)
- HTTP client path is stable (`inference_client.py`)
- `--reasoning off` and extended timeout (300s) are in use because of N150 CPU
- Context currently 4096

## Key Files
- `queenbee_integration.py` — live QueenBee REPL + all infant commands
- `inference_client.py` — OpenAI-compatible client to llama-server
- `wading_pool.py` + `wading_pool.json` — file-editable task pool
- `bonsai.env` — model path, port, alias
- `scripts/serve_local.sh` — starts llama-server
- `queenbee_memory.json` — persistent memory (infants, cohorts, academy_candidates)
- `exports/` — infant JSON snapshots (future USB-state format)

## Current Infant / Swarm Capability Surface

### Lifecycle
- `/spawn [task] [--talk]`
- `/task <id> <description> [--talk]`
- `/sleep <id>` / `/wake <id>`
- `/deactivate <id>`

### Training
- `/pool`
- `/train <id> [--talk]`
- `/cycle <id> [n] [--talk]`
- `/cycle cohort <name> [n] [--talk]`

### Multi-infant
- `/cohort create|add|remove|list|show`
- `/talk <from> <to> <message> [--talk]`
- `/talk cohort <name> <from> <message> [--talk]`

### Promotion & Evaluation
- `/promote <id> [reason]`
- `/academy`
- `/academy review <id>`
- Competence scoring (auto-refreshed)
- `academy_candidates` list in memory

### Inspection & Export
- `/infants`
- `/summary <id>`
- `/swarm`
- `/export <id>` → writes `exports/<id>_YYYY-MM-DD.json`

## Design Decisions Still in Force
- Infants remain **plain dicts** (no full Infant class yet)
- HTTP turns are **opt-in** via `--talk` (default is fast / no Bonsai call)
- All durable learning starts as **candidate** / logged experience
- No senior roster writes yet
- No direct infant internet access
- HASEOS principles (Ethics First, Ternary First, Memory Sovereignty, Promotion Protocols) remain supreme
- Phone-farm hardware **not yet acquired** (Android-first, targeting S20/S20 FE family or similar)

## Immediate Next Intended Work
1. Software nursery + USB-state simulation layer (so we can develop farm logic without physical phones)
2. Later: physical Android phone-farm nursery (20-node chassis + 4–8 used phones + per-node USB drives)

## Notes for Re-orientation
- QueenBee persona, ternary gate, and core `_generate` path were deliberately left stable
- Experience logging + competence scoring are working
- Export format is intentionally shaped as future USB-state image
- Conversation has been multi-day iterative build under CDD saddle

## How to Resume
Start the new conversation with:

“Noah Nemo here. We are continuing the HASEOS / QueenBee Orchestrator co-creation. Please read HASEOS_SESSION_HANDOFF.md. Ready to continue in the CDD saddle.”