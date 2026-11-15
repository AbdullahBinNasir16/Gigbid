# My retrieval got twice as good, and my AI started lying

*What I learned building GigBid, a multi-agent copilot that writes freelance proposals*

For a university R&D project I built GigBid: a system of LangGraph agents that scans freelance
job posts, decides whether a job is worth bidding on, and drafts a proposal in which every claim
must be backed by the freelancer's real portfolio. A human approves everything before it is sent.

I expected the hard part to be the agents. It wasn't. The most surprising thing my experiments
showed was this: **the single best improvement I made to retrieval quietly taught my writer to
make things up, and once I fixed that, better evidence still did not get more replies.**

Here is how that happened, with the numbers.

## The setup

GigBid's writer is only as honest as the evidence it is given. For each job, a Fit Matcher agent
retrieves items from the freelancer's portfolio: CV lines, case studies, repo READMEs and code,
client reviews, and about 150 past proposals per persona, each labelled won, replied or ignored.
The writer must tag every experience claim with the evidence item it came from. A claim
verifier then checks each sentence against that evidence and deletes anything unsupported
before a critic agent ever sees the draft.

The portfolios were built to be hard for naive retrieval: each project is described three
different ways (a case study, a terse CV line, a technical README), some skills appear only in
code, and past proposals mix good and bad writing.

I compared retrieval designs on a dev set of about 200 jobs per persona, scoring whether the
right projects came back (Recall@5, nDCG@10).

## What I expected to win, and what did

Before running anything I wrote down a hypothesis: splitting a job into separate requirements and
searching for each one, combined with hybrid keyword-plus-embedding search, would beat the naive
baseline by at least ten points.

It did not. Requirement decomposition on its own *lowered* Recall@5, from 0.3032 to 0.2756.
Decomposition plus hybrid search gained only about one point (0.3129). The requirements my
extractor produced were short skill tokens, so a dozen separate searches mostly returned the same
few projects.

Hybrid search alone helped (0.347), and a cross-encoder reranker helped a bit more (0.3766), at
roughly seven seconds per query on my laptop's CPU.

The clear winner was something I had added almost as an afterthought: **outcome-aware ranking**,
which boosts evidence from projects and past proposals that won or got replies. It took Recall@5
from 0.3032 to 0.5666 and nDCG@10 from 0.2973 to 0.536. It nearly doubled retrieval quality, ran
in about a second, and adding anything else on top of it made it worse. So it shipped.

## Then the writer started lying

Shortly after switching, I ran a live proposal and read the claims. One said, confidently:
"I recently built a Python script that pulled occupancy data from the STR website."

The freelancer had never done that. The claim was tagged with evidence, but the evidence was a
*past proposal*, and the past proposal had simply restated an earlier client's job post.

Outcome-aware ranking does exactly what it says: it pushes winning past proposals up the list. On
many jobs, all six evidence slots the writer received were past proposals. A past proposal is
evidence of how something was *pitched*, not that it was *done*. The writer, told to back every
claim with an evidence item, did precisely that, using the wrong kind of evidence.

My claim verifier initially accepted it, because the sentence really did match the evidence text.
The bug was not in any one component. It was in the interaction: better ranking changed *which
kind* of evidence dominated, and the rules downstream had silently assumed all evidence was proof.

## Fixing it made the first fix look worse, briefly

The fix was a policy, not a model: past proposals can inform phrasing, but only CV lines, case
studies, repos, code and reviews count as proof. I changed the verifier to accept only those types
and labelled past proposals in the writer's prompt as "phrasing reference only, never cite it".

The next run was humbling. The verifier stripped all four claims from a draft, because every one
of them had been pinned to a past proposal, and some were actually true (the freelancer really had
built a churn model with an AUC of 0.86, but the writer had cited the wrong source for it).
Letters collapsed into one-line stubs.

The real fix was in retrieval again: the matcher now fetches proof items separately, so the writer
always sees real case studies alongside the high-ranking proposals. After that, true claims
survived and invented ones still died. In my A/B run, unsupported claims per LLM-written proposal
went from 0.2069 before verification to 0.0 after.

## And yet: no more replies

Here is the second surprise. I measured the end-to-end outcome in a marketplace simulator whose
clients reply based on things real clients care about: whether you name the skills they need,
cite concrete past work, avoid a generic opening, and price sensibly.

I ran the same jobs at the same price with two writers, each from its own simulated account: the
grounded LLM writer, and a dumb template that just quotes "I built..." sentences from case studies.
Over a simulated week, the LLM writer got 1 reply out of 29 proposals and the template got 2 out
of 30. A second run with an improved prompt gave 1 of 30 versus 0 of 30. Fisher's exact test
p-value: 1.0 both times. No difference.

Both rates sit far below the simulator's own calibration for specific letters (a 0.325 reply rate).
I checked the obvious suspects: only 5 of 30 quotes were above the client's maximum, and letters
were long enough not to be penalised. Neither explains it. My best remaining explanation is that
the simulated clients reward naming their hidden must-have skills, and a *grounded* letter can
only name skills the portfolio actually proves. Honesty caps how well you can pattern-match a
client.

So retrieval quality nearly doubled, unsupported claims went to zero, and reply rate did not move.
**Retrieval was not the bottleneck for replies. It was the bottleneck for trust.**

## What I would tell another engineer

**1. Measure the interaction, not just the component.** Outcome-aware ranking was a clean win on
every retrieval metric I had. Nothing in Recall@5 or nDCG said "your writer will now cite
proposals as proof". I only found it by reading generated output. I now treat "read twenty
outputs after every retrieval change" as part of the evaluation, not an optional extra.

**2. Make grounding a node, not an instruction.** I also compared three architectures on the same
jobs with the same model: one ReAct agent with all tools, a prebuilt supervisor, and my hand-built
graph. The single agent and the supervisor both produced unsupported claims (1.667 and 2.667 per
proposal) despite being told not to. The graph produced none, because verification is a step the
draft cannot skip. It was also the cheapest, at 1,472 tokens per job against 2,643 for the single
agent and 6,618 for the supervisor.

**3. Calibrate your judge, then distrust it a little.** When I labelled 30 proposals myself and
compared with my LLM judge, we agreed 70% of the time (Cohen's kappa 0.4255, moderate). Most
disagreements were proposals with a specific-sounding opening attached to an irrelevant project. I
gave them credit for the opening; the judge marked them down for the mismatch. Looking back, the
judge was usually right. That changed how I read every judge score after it.

**4. Negative results are results.** Two of my most useful findings were things that did not work:
requirement decomposition, and a corrective retrieval loop whose relevance grader turned out to
give relevant evidence *lower* scores (median 0.002) than irrelevant evidence (0.0132), so it
refused almost every job. Writing those down saved me from shipping them.

## The takeaway

I went in thinking a better retriever would produce better proposals and better outcomes. What I
actually learned is that every improvement to *what the model sees* changes *what the model
believes it is allowed to say*, and that honesty and persuasion pull in different directions when
the evidence is thin.

GigBid now does what I most wanted it to do: it never claims experience the freelancer does not
have, and it never sends anything without a human saying yes. Whether that wins more clients is
still an open question. But it is the version I would trust with my own profile.

*All numbers come from the project's committed evaluation files. Code:
github.com/AbdullahBinNasir16/Gigbid. I used an AI coding assistant during the project; the
experiments, judgments and conclusions are my own.*
