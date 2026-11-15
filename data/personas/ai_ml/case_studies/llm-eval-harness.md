---
id: case:ai_ml:llm-eval-harness
persona: ai_ml
type: case_study
project: llm-eval-harness
title: LLM evaluation harness
skills:
- LLM Evaluation
- Python
- OpenAI API
- Pytest
- LangSmith
date: '2025-04-01'
client_industry: software
provenance: synthetic
---

# LLM evaluation harness

## The problem
The client, a software company, had a problem: a startup shipped prompt changes without knowing if quality dropped.

## What I built
I built an evaluation harness with 600 graded cases and an LLM judge calibrated against human labels. The stack was LLM Evaluation, Python, OpenAI API, Pytest and LangSmith.

## Result
The work caught two regressions before release; judge agreement reached Cohen's kappa 0.78.
