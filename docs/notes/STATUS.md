# Project status (handoff note)

Last updated: 15 November 2026, evening. Branch `feat/phase02-core`, pushed to GitHub as `main`.
Submission deadline: 15 November 2026, 23:50.

## Done (all committed, tests green: 81 pytest, 12 Playwright)
- Personas (3 × 16 projects), dev set (~200 jobs/persona) and held-out set: `scripts/data/build_personas.py`.
- MCP servers: portfolio (installable, own README), marketplace (GigSim adapter, idempotency, dry_run,
  bearer auth, audit log), workspace (mock). Upwork live adapter, GitHub MCP ingestion. Schema snapshot test.
- RAG: V0–V5, V8, claim verification; V4 ships by measurement.
- Bid graph and conversation graph: parallel analysis, critic loop, compliance, approval interrupts,
  exactly-once submit, budgets, dead letter, style and outcome memory with promotion rules.
- FastAPI + React UI (all screens), SSE run viewer, degraded mode, worker, Docker/compose, CI with eval gate.
- Evaluations in `evals/results/`: retrieval, decisions, R&D A (tool granularity), R&D C (single vs
  supervisor vs graph), X2 A/B in GigSim, local LLM speed, V8 calibration, smoke gate.
- Docs: README (generated results tables), ARCHITECTURE, TOOLS, RUNBOOK, DEPLOY, EXTENSION, DATA_CARD,
  AI_USAGE, ADRs, report draft `docs/REPORT.md`.

## Only the student can do these (before 23:50)
1. **Judge calibration**: fill the `human` column (good or weak) in `evals/datasets/judge_labels.csv`
   for all 30 rows yourself, then `python -m evals.runners.judge_calibration kappa`.
2. **Deploy**: follow `docs/DEPLOY.md` (Hugging Face Space, free), put the URL in README.md.
3. **GitHub**: set `main` as the default branch.
4. **Report PDF**: read and edit `docs/REPORT.md` in your own words, export it to PDF.
5. **Demo video (3 min)** and **README GIF**: one job inbox → approval, a scam skipped, an injection
   ignored, a client reply handled.
6. **Traces**: set LANGSMITH_TRACING=true and LANGSMITH_API_KEY (free) or run Langfuse via compose,
   run three jobs, and put the three public trace links in README.md.
7. **MCP Inspector screenshots**: `npx @modelcontextprotocol/inspector`, connect to
   `python -m mcp_servers.marketplace.server`, save screenshots to `docs/images/`.
8. **Technical write-up** (1,200–1,800 words) and the two-line résumé bullet from results files.
9. Submit on Classroom: URL, reviewer login (private comment), repo link, PDF, video, write-up link.

## Machine facts
- Windows 11, 16 GB RAM, CPU only. `.venv` on D:, HF and pip caches on D:. Groq key in `.env` (git ignored).
- Ollama models on D: are served by a second server on port 11500; the desktop app still uses C:
  until "Model location" is changed in its settings.
