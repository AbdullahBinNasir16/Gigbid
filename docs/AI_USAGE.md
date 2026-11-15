# AI Usage Disclosure

- Tool: Copilot SDK in VS Code.
- Assisted with the starter-kit packaging, CI and Docker scaffolding, repository-rule checker, and focused tests.
- Incorrect suggestion corrected: the first rule-checker version only inspected Python imports and prompt strings. It now also checks JavaScript and TypeScript files, and tests cover those cases.
- I reviewed the changes and remain responsible for the code.

## Claude Code (Opus 5.5)
- Phase 1 foundation: agent/config.yaml, agent/config.py, agent/llm.py, agent/handoffs.py, agent/state.py, agent/marketplace_port.py, mcp_servers/marketplace/adapters/fake.py and their unit tests.
- Incorrect first design, caught and changed: the first state.py gave `status` a "most severe wins" reducer. That meant a thread could never go from awaiting_approval back to running after an approval. `status` is now a plain field that only sequential nodes write, so LangGraph raises an error if two parallel branches ever write it in the same step.
- Small catch: a code comment containing the word "Ollama" matched the model-name grep (it contains "llama"). The comment was reworded, so the grep stays a reliable check.
