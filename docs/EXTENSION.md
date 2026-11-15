# Signature extension: X2 Proposal experiments

**Question.** Does the shipped proposal strategy (a grounded LLM writer whose claims are
verified against the portfolio) get more client replies than a deterministic, evidence-only
template, when everything else is held fixed?

## Design

* **Job set.** GigSim jobs from each persona's main category that GigBid itself decides to bid
  on (the real analysis nodes decide; no cherry-picking), up to 10 per persona.
* **Arms.** For the *same* job and the *same* price quote:
  * **A, grounded LLM writer**: writer (gpt-oss-120b on the hosted open profile) →
    claim verification → compliance. This is the shipped path.
  * **B, evidence-only template**: deterministic letter that mirrors the client's need and quotes
    up to two "I built …" sentences verbatim from case studies → verification → compliance.
* **Isolation.** Each arm submits from its own GigSim user, so the two proposals for a job never
  compete for Connects or affect each other's outcome. GigSim seeds every outcome by
  (user, job, client), so results are repeatable.
* **Outcome.** After submitting, simulated time is advanced one week and each proposal's state is
  read back. Primary metric: replied or better (replied, interview, hired).
* **Test.** Fisher's exact test, two-sided, on the 2×2 table of arm × replied-or-better (small
  samples; no normal approximation).
* **Validity guards.** Arm A only counts proposals the LLM actually wrote: if a hosted call fails
  and the writer falls back to the template, that row is excluded and marked (`writer` field in
  each row). The run lowers GigSim's Connects cost to 1 through the admin policy endpoint so both
  arms can afford the sample, then restores the previous policy; both are recorded in the results.

## Run

```bash
MODEL_PROFILE=open_hosted python -m evals.runners.gigsim_outcomes --per-persona 10
python -m evals.runners.results_table      # refresh the README table
```
Results: `evals/results/gigsim_outcomes.json` (per-proposal rows, summary, Fisher test) and the
"Signature extension X2" table in the README.

## How to read it

GigSim's client rule rewards naming the client's hidden must-have skills, citing concrete past
work, a non-generic opening that mirrors the problem, and a price under the hidden ceiling, and
it penalises padding. Both arms cite real work, so the experiment isolates what the LLM adds:
mirroring the problem and covering more of the client's skills in natural prose. With about 30
pairs, only a large difference will reach significance; a non-significant result is reported as
such, with the observed effect size.
