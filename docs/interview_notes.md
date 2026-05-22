# Interview Talking Points — Visa RAG

> **How to use this:** This is a study aid, not a script. Interviewers probe —
> if you can't explain a point in your own words, either learn it properly
> (cross-check `CONCEPTS.md`) or drop it. Every claim here is something the
> project actually does; make sure you can defend each one.

---

## The 2-minute pitch (English, ready to deliver)

> Visa RAG is a retrieval-augmented assistant for international students dealing
> with F-1 status, OPT, and the STEM OPT extension. I built it because
> immigration rules are high-stakes — getting a deadline wrong can cost you your
> status — and general chatbots will confidently hallucinate immigration rules.
>
> So the whole system is designed around trust. Every answer is grounded in
> official sources — the USCIS Policy Manual, 8 CFR, SEVP guidance — with
> passage-level citations, and it refuses to answer when the retrieved sources
> don't actually cover the question. Anything involving dates — like "when can I
> file for OPT" — is routed to a deterministic rules engine instead of the LLM,
> because LLMs miscompute dates and each date needs to cite the specific
> regulation it comes from.
>
> It also tracks the user's personal case — their program date, their stage in
> the OPT process — and gives a personalized "what to do next" view with
> deadline countdowns.
>
> Technically it's a hybrid-retrieval RAG pipeline — pgvector plus lexical
> search, Cohere reranking, an answerability gate, and a post-generation
> self-check — with a FastAPI backend, Postgres, containerized with Docker. I
> also built an evaluation harness that measures routing accuracy, citation
> coverage, and out-of-scope refusal rate.

---

## Deep-dive points (when they say "tell me more")

- **Two-path routing.** An intent classifier sends date/deadline questions to a
  deterministic rules engine and everything else to the RAG pipeline. The LLM is
  used for *understanding*, never for date math.
- **Hybrid retrieval.** Dense vector search (pgvector) + lexical search, fused
  with Reciprocal Rank Fusion, then a Cohere reranker for precision.
- **Two hallucination guards.** An *answerability gate* before generation (do
  the retrieved passages actually contain the answer?) and a *self-check* after
  (is every claim in the draft grounded?). Either failing → refusal.
- **Rules engine.** OPT/STEM filing windows computed in deterministic Python;
  every date cites the CFR section it implements.
- **Conversation-aware profile.** When a message reveals a case change, the app
  *suggests* a profile update — detect, suggest, confirm — never a silent change.
- **Evaluation harness.** A golden set scored on routing accuracy, key-fact
  coverage, and out-of-scope refusal rate.

---

## Likely questions and how to answer

**"Why RAG instead of fine-tuning or just a big prompt?"**
RAG keeps answers grounded in the current official text, citations are
verifiable, and when regulations change you update the corpus — not the model.

**"How do you prevent hallucination?"**
Three layers: a relevance threshold and answerability gate before generation, a
citation-required generation prompt, and a self-check that re-verifies the draft
against the passages. If any layer is unsatisfied, the system refuses.

**"Why not let the LLM compute the dates?"**
LLMs miscompute date arithmetic, and an immigration deadline error is
high-stakes. Dates go through deterministic Python that also cites its CFR
source, so the math is correct and auditable.

**"How do you know it works?"**
An evaluation harness over a golden set — routing accuracy, key-fact coverage,
out-of-scope refusal. It also caught a real bug (see below).

**"Why HNSW over IVFFlat for the vector index?"**
IVFFlat partitions vectors into lists and probes only a few per query; on a
small corpus most lists are empty, so recall is unstable. HNSW works reliably at
any corpus size.

**"What would you improve / what are the limitations?"**
Honest answer: the eval set is a 16-question seed and should grow toward ~100
with adversarial cases; it's single-user with no auth; grading is substring-based
and could use an LLM-as-judge; and it isn't deployed publicly yet.

---

## The challenge story (have this ready)

> "I built an evaluation harness for the system. The first run showed routing
> and citation accuracy at 100%, but out-of-scope refusal was only 50% — the
> system was answering questions about H-1B and green cards instead of refusing.
>
> I diagnosed it: the refusal logic relied on an embedding relevance score.
> That score filters out clearly-unrelated questions, but immigration-adjacent
> questions retrieved tangentially-related passages that cleared the threshold.
> The relevance score is just a similarity proxy — it doesn't actually check
> whether the passages answer the question.
>
> So I added an answerability gate: before generating, an LLM reads the retrieved
> passages and judges whether they contain the answer. That raised out-of-scope
> refusal from 50% to 100%, with no regressions on in-scope questions — which I
> confirmed by re-running the eval."

This story works because it shows the full loop: **measure → find a real
problem → diagnose the root cause → fix → re-measure.** That loop is what
separates a senior engineer from a junior one.

(You also debugged a chain of environment/dependency issues — a stalled Docker
build, a missing system library, a library version conflict — and a vector-index
misconfiguration. Good "lots of small real-world problems" material.)

---

## Honest framing

Don't oversell. "100% on a 16-question set I designed myself" means *no obvious
failures in a small seed set* — not *the system is perfect*. Saying that
yourself, before the interviewer points it out, signals good judgment. The
project's strength is the **engineering discipline** — grounding, refusal,
the LLM/rules separation, the eval loop — not a perfect score.
