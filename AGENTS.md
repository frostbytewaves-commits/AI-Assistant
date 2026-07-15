# AI-Assistant (JARVIS track)

## Source of truth

- Architecture & roadmap: [docs/JARVIS_ARCHITECTURE.md](docs/JARVIS_ARCHITECTURE.md)
- Dev laws (see `.cursor/rules/model-first-reasoning.mdc`):
  1. **Model thinks** — no keyword NLP sprawl
  2. **Thin Orchestrator** — Core interfaces + plugins, not a god object

## Core direction

`Sense → Context → Reason → Planner → Act → Memory`  
Chat assistant ≠ game agents (`game_agents/` separately). Actions via `plugins/`.

## Current stack

- Local Ollama text/vision models
- Overlay UI, hotkeys, game knowledge (Minecraft / ONI)
- Target desktop: RTX 5070 Ti 16GB + 64GB RAM
