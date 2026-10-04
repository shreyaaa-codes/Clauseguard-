# ClauseGuard — Full Project Plan & Task Assignment

**One assumption stated up front:** the repo and your planning doc only define Review 1
explicitly. I don't have your course's exact Review 2 / Final rubric, so I've built the
rest of the roadmap from what your own planning doc already marked as "deferred, not
cut" (Part D of the Review 1 doc) plus what a project with two stated RQs needs before
final submission: a real evaluation, tuned weights, and the UI layers built on top of
already-working data. If your actual review structure has different milestones or
deadlines, tell me and I'll re-cut the phases — the person-by-person task lists below
will mostly carry over regardless.

Three phases, matching the natural shape of the work:
- **Phase 1 — Review 1** (covered in the previous doc — recapped briefly below)
- **Phase 2 — Review 2**: full evaluation, weight tuning, wiring the UI to real data
- **Phase 3 — Final submission**: polish, extension, final report, stretch goals

---

## Whole-project status snapshot

| Component | Status |
|---|---|
| C1 Extraction | Partial — real data for Google/Spotify/WhatsApp; Instagram raw text present, unextracted; no TF-IDF/LogReg pre-filter; two competing extraction scripts |
| C2 Canonicalization | ✅ Done, verified |
| C3 Portfolio storage | ✅ Done, verified |
| C4 Scoring engine | ✅ Done, verified — but only using severity + specificity, not the full schema |
| C5 Marginal risk | ✅ Done, verified |
| C6 Demo | Partial — pieces exist, no single run script yet |
| Dashboard (`clauseguard_dashboard.html`, `export_dashboard_data.py`) | **Ahead of plan** — already has Portfolio overview, Entity exposure breakdown, Risk category breadth, and a Marginal risk demo section. Currently runs off a static exported JSON, not live queries. |
| Weight tuning (w1/w2) | Not started — deliberately deferred, per plan |
| Full evaluation (precision/recall, ablation) | Not started — only preliminary numbers exist |
| Overlap graph visualization | Not started as a real graph (dashboard has a table-style breakdown, not a network viz) |
| Marginal-risk comparator UI (2 services side by side) | Not started — current dashboard shows one add-on, not a comparator |
| Chrome extension | **Does not exist in this repo at all** — no manifest, no extension code found. If it exists in the original ClauseGuard repo, it needs to be pulled in; otherwise it's a from-scratch Phase 3 item |
| DPDP-specific compliance checks | Not started — explicitly optional, only if time allows |
| Policy-change re-scoring | **Permanently out of scope** — your own plan already ruled this out as scope creep that doesn't answer either RQ. Don't revive it unless your RQs change. |

---

## Phase 1 — Review 1 (recap — see previous doc for full detail)

- Person 1: extraction pre-filter, canonical extraction path, extract Instagram
- Person 2: extend schema fields, wire into scoring
- Person 3: end-to-end demo runner
- Person 4: written deliverables + integration coordination

If Phase 1 isn't merged yet, finish it before starting Phase 2 tasks below — Phase 2
directly builds on Phase 1's schema and data.

---

## Phase 2 — Review 2

### Person 1 — Full evaluation + ablation study

**Owns:** annotation set, an evaluation script (new: `evaluate.py`)

1. Expand your annotated clause set beyond whatever partial subset exists — this is what turns "preliminary, N=X clauses" into real precision/recall numbers.
2. Write `evaluate.py`: compute precision/recall/F1 of the extraction pipeline against your annotated ground truth.
3. Run the **ablation comparison** properly: naive baseline vs. composite score, across all 4 services, with the actual delta reported as a number in your results — not just printed to terminal like in Review 1.
4. Document extraction error patterns you find (e.g. cases the LLM mis-classifies) — this becomes a "limitations" discussion point, which reviewers reward.

**Deliverable:** an evaluation report (numbers + a short write-up of what the ablation shows) and `evaluate.py` in the repo.

---

### Person 2 — Weight tuning + formula refinement

**Owns:** `scoring.py` (weight logic), a small weight-tuning script

1. Build a small set of **expert-ranked test portfolios** (a handful of realistic service combinations, ranked by a human for "which portfolio feels riskier") — this is your ground truth for tuning.
2. Try a few w1/w2 splits against that ranking (grid search is fine — you don't need anything fancy) and pick the one that best matches expert ranking order.
3. Resolve the **mean vs. sum** decision from Phase 1 for real, now that you have ranked data to justify it either way — don't leave it as a documented-but-arbitrary choice anymore.
4. Update the scoring formula slide/section with your tuned weights and the reasoning, replacing the "uniform starting assumption" language from Review 1.

**Deliverable:** tuned w1/w2 with a documented justification, and updated `scoring.py` defaults.

---

### Person 3 — Wire the dashboard to live data + build the overlap graph

**Owns:** `clauseguard_dashboard.html`, `export_dashboard_data.py`

1. Right now the dashboard reads a **static exported JSON**. Replace the static-file flow with the dashboard pulling from the current `portfolio.db` state (either a small local API, or regenerate `dashboard_data.json` automatically as part of the demo runner) so it's not stale the moment someone re-runs the pipeline.
2. Build the **overlap graph visualization** — a real node/edge graph (services as one node type, canonical entities as another, edges = mentions) instead of the current table-style entity exposure breakdown. This was explicitly deferred in Review 1, it's due now.
3. Build the **marginal-risk comparator UI** — side-by-side view of two candidate new services and their marginal impact, instead of the current single-add view.
4. Keep the whole thing in the existing HTML/JS structure — don't introduce a new framework this late unless the team agrees it's worth the risk.

**Deliverable:** dashboard reading live pipeline output, a working overlap graph, and a two-service comparator view.

---

### Person 4 — Integration, regression testing, and Review 2 written material

**Owns:** coordination, updated slides, regression checks

1. Update the problem statement / RQ slides if Person 2's tuned weights or Person 1's evaluation numbers change how you describe the contribution.
2. Write the **evaluation results section**: pull Person 1's precision/recall numbers and ablation comparison into a clear slide/table.
3. Update the **"done / in progress / planned" status slide** for Review 2 using the status table at the top of this doc as the base.
4. **Regression-check that nothing from Phase 1 broke:** after Persons 1–3 merge, re-run the full Phase 1 demo script (`run_demo.py` or equivalent) and confirm it still produces sane output — tuning weights or changing the dashboard shouldn't silently break the core pipeline.

**Deliverable:** Review 2 slide content, and a signed-off regression check that Phase 1 + Phase 2 work together.

---

## Phase 3 — Final submission

### Person 1 — Chrome extension (build or integrate)

1. Check whether the original ClauseGuard project (that this one is adapted from) already has extension code — if so, pull it in and adapt it to call your extraction pipeline instead of rebuilding from scratch.
2. If nothing exists, build a minimal extension: auto-detect a privacy policy page, extract the text, send it through your existing extraction pipeline.
3. Polish the popup UI (auto-detection UX, popup design) — this was explicitly deferred, it's due now, but keep it functional over fancy.

**Deliverable:** a working Chrome extension that feeds real pages into your existing pipeline.

---

### Person 2 — Robustness + optional DPDP checks

1. Stress-test the pipeline against messier real-world policies (longer documents, unusual formatting) — final submission is where "it worked on my 4 clean test files" stops being good enough.
2. Fix whatever breaks — this is maintenance work, not new features.
3. **Only if time allows:** add basic DPDP-specific compliance flags as a clearly-labeled stretch feature — your own plan marks this as out of scope for the core RQs, so don't let it eat time that robustness work needs.

**Deliverable:** a pipeline that survives real-world messy input, plus DPDP flags only if time genuinely allows.

---

### Person 3 — Final dashboard polish + full demo rehearsal

1. Final visual/UX pass on the dashboard — this is the one phase where "polish" is actually the point, since the underlying computation has already been proven in Phase 2.
2. Merge the overlap graph and comparator UI improvements from Phase 2 with any new extension-driven data flow from Person 1.
3. Rehearse the **final live demo** end to end: extension → extraction → dashboard, timed and scripted.

**Deliverable:** final polished dashboard and a rehearsed, timed final demo.

---

### Person 4 — Final report + submission package

1. Write the full final report, incorporating Phase 1's methodology, Phase 2's evaluation numbers and tuned weights, and Phase 3's final feature set.
2. Update the competitive positioning and literature review sections with anything that changed since Review 1.
3. Assemble the final submission package (report + slides + repo link + demo video if required).
4. Run one last full regression check across everything before submission.

**Deliverable:** the complete final submission package.

---

## Git workflow for the full project (not just Phase 1)

**Same branch-per-task pattern for every phase, off `main`:**

```bash
git checkout main
git pull origin main
git checkout -b feature/<name>-<short-description>
# Phase 2 examples:
#   feature/person1-evaluation-ablation
#   feature/person2-weight-tuning
#   feature/person3-dashboard-live-data
#   feature/person4-review2-docs
# Phase 3 examples:
#   feature/person1-chrome-extension
#   feature/person2-robustness-dpdp
#   feature/person3-final-dashboard-polish
#   feature/person4-final-report
```

**Commit and push regularly, verify locally before opening a PR** — same pipeline check
as Phase 1, extended with whatever new script your phase added (e.g. `evaluate.py` in
Phase 2):

```bash
rm -f data/db/portfolio.db
python3 db.py
python3 canonicalize.py
python3 scoring.py
python3 marginal.py data/extracted/<file>.json "<Name>" <category>
python3 evaluate.py            # once it exists, Phase 2 onward
```

**Merge order per phase — same dependency logic as Phase 1, repeated each phase:**
1. Person 1 first (their work is what the others' data/scoring/UI depend on)
2. Person 2 second (rebase on Person 1's merge)
3. Person 3 third (rebase on 1+2 — dashboard/extension needs the latest pipeline)
4. Person 4 last (docs + final regression check, after everyone else is in)

**Tag a milestone commit at the end of each phase**, so you always have a clean
fallback if something breaks later:

```bash
git checkout main
git pull origin main
git tag -a review1-final -m "Review 1 submission state"
git push origin review1-final
# later:
git tag -a review2-final -m "Review 2 submission state"
git push origin review2-final
```

If Phase 3 work breaks something, you can always diff against `review2-final` to see
exactly what changed, instead of guessing.

**Final integration check before any submission (Person 4 runs this every phase):**

```bash
git checkout main
git pull origin main
rm -f data/db/portfolio.db
python3 run_demo.py
```

Clean run, sane numbers → `main` is submission-ready for that phase.
