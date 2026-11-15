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
