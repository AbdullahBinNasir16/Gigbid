# AI Usage Disclosure

- Tool: Copilot SDK in VS Code.
- Assisted with the starter-kit packaging, CI and Docker scaffolding, repository-rule checker, and focused tests.
- Incorrect suggestion corrected: the first rule-checker version only inspected Python imports and prompt strings. It now also checks JavaScript and TypeScript files, and tests cover those cases.
- I reviewed the changes and remain responsible for the code.

## Claude Code (Opus 5.5)
- Phase 1 foundation: agent/config.yaml, agent/config.py, agent/llm.py, agent/handoffs.py, agent/state.py, agent/marketplace_port.py, mcp_servers/marketplace/adapters/fake.py and their unit tests.
- Incorrect first design, caught and changed: the first state.py gave `status` a "most severe wins" reducer. That meant a thread could never go from awaiting_approval back to running after an approval. `status` is now a plain field that only sequential nodes write, so LangGraph raises an error if two parallel branches ever write it in the same step.
- Small catch: a code comment containing the word "Ollama" matched the model-name grep (it contains "llama"). The comment was reworded, so the grep stays a reliable check.
- Phase 0B data pipeline and GigSim: scripts/data/*, data/real/taxonomy.yaml, gigsim/*, scripts/gigsim_sanity.py and their tests.
- Caught: the first skill matcher used one regex alternation of 1,300 skills. Python tests it at every character, so the run was far too slow. Replaced with a word n-gram dictionary lookup (same results, linear time).
- Caught: in pandas 3, `astype(str)` keeps missing values as NaN instead of "nan", which crashed the cleaner after a 7 minute run. Fixed with `fillna("")` first.
- Caught by a unit test: the first GigSim weights could be gamed by padding. A short generic letter got a bigger "too short" penalty than a padded one got for "too long", so padding raised the reply chance. The long penalty is now larger and grows with length.
- Caught by the sanity check: the first calibration gave specific letters a reply rate near the cap, which would leave nothing for the writer to improve. reply_scale and weights were lowered.
- Caught: the first scam lexicon was dominated by one company's boilerplate repeated across many fraud rows. Texts are now de-duplicated before counting, which also revealed that the dataset's fraud rows are machine-generated filler (recorded in DATA_CARD).

## Claude Code (Opus 5.5), 15 November 2026: Phase 2 (core system)
- Files: `scripts/data/persona_specs.py`, `scripts/data/build_personas.py`, `rag/**`,
  `mcp_servers/**` (servers, GigSim and Upwork adapters, common), `agent/nodes/**`,
  `agent/graphs/**`, `agent/memory/**`, `agent/prompts/**`, `agent/mcp_client.py`,
  `apps/api/**`, `apps/web/**`, `worker/main.py`, `evals/runners/**`, `infra/docker/**`,
  `.github/workflows/**`, docs. I reviewed the code and ran every test and evaluation myself.
- Caught: the first API ran CPU-heavy work (embeddings, cross-encoder, sync graph nodes) on the
  event loop, so the server stopped answering while 12 jobs were analysed. Fixed by moving
  blocking work to threads and capping concurrent runs.
- Caught: shell-escaping turned regex `\b` into a literal backspace character in two files,
  which silently broke the template writer's pattern; found by ruff (PLE2510).
- Caught: after switching to outcome-aware retrieval, the writer cited past proposals as proof
  of experience ("I built a script that pulled STR data"). A past proposal only shows how work
  was pitched. Claim verification now accepts only CV, case study, repo, code and review
  evidence (evals/results/demo_proposal.json shows the before/after behaviour).
- Caught: the first gold labels allowed planted near-duplicates to be "bid".
- Caught: on the Groq free tier (8,000 tokens/min for gpt-oss-120b) the writer hit 429s and
  silently fell back to the template writer, which would have contaminated the A/B arm. The
  client now backs off on 429s, every row records which writer produced it, and arm A counts
  only real LLM drafts.
- Measured, not assumed: qwen2.5:7b does not fit in RAM next to the stack, and the cross-encoder
  grade does not separate relevant evidence on this corpus (evals/results/llm_speed.json,
  v8_calibration.json).
