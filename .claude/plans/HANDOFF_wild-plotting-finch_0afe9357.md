# HANDOFF — implement the `/run-debate` overhaul plan

- **PATH_TO_PLAN**: `/Users/kleshcv/.claude/plans/wild-plotting-finch.md`
- **PATH_TO_CONVERSATION**: `/Users/kleshcv/.claude/projects/-Users-kleshcv-Desktop-my-packages-science-debate/0afe9357-11ca-4334-90ba-3456127ea895.jsonl`
- **Related per-session handoff** (different scope — defines `full_debate.html` structure that §4 must encode): `/Users/kleshcv/Desktop/my_packages/science_debate/.claude/plans/HANDOFF_wild-plotting-finch_35ab7dec.md`

## Goal

Implement the seven-chapter plan in `wild-plotting-finch.md` — `/run-debate` skill overhaul touching 19 issues across faithfulness self-assessment, team-spawn plumbing, live debate flow, end-of-debate HTML + audio exports, cast affiliation sourcing, model-variant differentiation, token accounting, and an in-flight running-session handoff.

The plan was assembled from 7 parallel Opus chapter-writers and conforms to the format-plan required 5-section structure (Problem · Solution steps · What to implement · Module wiring · Advisory). Every chapter is implementation-ready; the work is editing files and writing new scripts per each chapter's §3.

## Current Progress

- ✅ **Plan complete** at `/Users/kleshcv/.claude/plans/wild-plotting-finch.md` (~1000 lines, 7 chapters + Open Issues + Appendix). Verified ALL_COVERED against 32 user inputs by an Opus verification subagent.
- ✅ **Format-plan run** via per-section parallel strategy (7 Opus subagents, one per chapter). All 7 chapters returned and were assembled into the master plan.
- ✅ **Folder check** of `debate_events/ariasA_davidsonB_2026-05-26_c7893c/` informed concrete file-naming conventions (per-draft files + canonical: `intro_<X>_draft<N>.md` and `intro_<X>.md`).
- ✅ **Per-session handoff doc** for the in-flight debate (`HANDOFF_wild-plotting-finch_35ab7dec.md`) was read and its `full_debate.html` structural requirements folded into §4.
- ✅ **User decisions captured** in the plan's Appendix (verbatim from `AskUserQuestion` exchanges).
- ⬜ **No code or skill edits yet** — implementation is the next agent's job.
- ⬜ **Running session** (`ariasA_davidsonB_2026-05-26_c7893c`) is still mid-Phase C (last seen ~entry 630 of session `35ab7dec-…`) and won't auto-pick up changes — §7 handles this.

## What Worked

- **Per-section parallel chapter-writers.** 7 Opus subagents in parallel, each writing one chapter (covering 1–5 issues each). Wall-time was ~3 minutes; each chapter independently followed the 5-section structure. The 2 subagents that initially blocked on `/tmp` writes resumed cleanly once told to write to their harness-assigned `~/.claude/plans/wild-plotting-finch-agent-<id>.md` path.
- **Folder-check before plan-finalisation.** Reading the actual `debate_events/ariasA_davidsonB_2026-05-26_c7893c/` directory caught two design issues (no `team.json` exists; per-draft file convention is already in use) that the original plan had wrong. Re-aligning the plan to reality avoided spec drift.
- **Verifier subagent against extracted user inputs.** `/verify-plan-against-inputs` confirmed ALL_COVERED for 32 user input items before exiting plan mode. The verifier flagged minor numbering quirks (resolved) and no coverage gaps.
- **Issue-grouped chapters** (not 1-issue-per-chapter): faithfulness+contamination → §1 (3 issues), team plumbing → §2 (5 issues), live debate → §3 (2 issues), HTML+audio → §4 (4 issues), etc. Grouping by shared root cause kept each chapter coherent.
- **Inline handoff body in §7.** Embedding the verbatim handoff markdown body in §7 §3 (rather than describing it abstractly) means the implementer can `Write` the file mechanically without re-deriving the structure.

## What Didn't Work

- **First instinct was `/tmp/` for chapter outputs.** Plan mode blocks writes outside the assigned plan file. Two subagents (§6, §7) initially halted asking for `/tmp` write permission. Fix that worked: tell them to write to their harness-assigned `~/.claude/plans/wild-plotting-finch-agent-<agentId>.md` path instead.
- **First Edit pass introduced issue-numbering drift.** Adding issues 16/17/18/19 with `replace_all=false` inserted them before issue 15 instead of after, breaking the 1–19 monotonic order. Resolved by a manual swap edit; the assembled plan now reads 1–19 in order in the chapter-grouped form.
- **ExitPlanMode rejected three times** while plan was still expanding. Each rejection added new issues (12 → 13 → 14/15 → 16–19). Lesson: when the user is actively iterating, ask "any other issues?" before requesting approval; don't assume completeness from your own checklist.
- **Backup-plan path** (`/tmp/.format-plan-backup-*.md`) was permission-denied for several chapter subagents — they composed from the task brief alone. Acceptable because each brief was self-contained, but in future, pass the backup content as part of the brief text rather than as a path to Read.

## Next Steps — implementation roadmap

Implement chapters in the order below. Some have hard dependencies; respect them.

### Phase 1: Foundation (no dependencies)
1. **§1 — Faithfulness self-assessment & contamination.** Edit `debate/agents/scientist.md` (frontmatter + new subsection) and `.claude/skills/assess-transcript-faithfulness/SKILL.md` (description + body). Rewrite B5a/B5b in `.claude/skills/run-debate/SKILL.md`. **No new scripts.** Smallest blast radius — start here.
2. **§2 — Team spawn plumbing.** Insert B5_pre in `run-debate/SKILL.md`, rewrite C0 (spawn only journalist), add task-wording banner. Defines `team.json` schema that §3 / §4 / §6 depend on. **No new scripts.**
3. **§5 — Cast affiliations + structured audience.log.** Two edits to `run-debate/SKILL.md` (B0.5 WebSearch step + Phase C1 JSONL-emission pattern). Defines `inputs.json` schema additions that §4 depends on, and `audience.log` format that §4 reads. **No new scripts** (the optional `render_audience_log.py` is deferred).
4. **§6 — Model picker + token accounting.** Rewrite Phase A Batch 4 prose, insert post-B4 briefing-size sanity check, add `/usage` baseline/delta steps. Coordinates with §2 (`team.json` `model` field). **No new scripts.**

### Phase 2: Live debate flow (depends on §1 and §2)
5. **§3 — Live debate flow.** Add Moderator-role banner at top of `run-debate/SKILL.md`. Rewrite Phase C1 stage-loop body (minimal prompts, scientists self-append, Moderator read+print). Relies on §1's scientist.md `Write`/`Skill` tools and §2's `team.json` for ID → real-name resolution.

### Phase 3: End-of-debate artifacts (depends on §1, §2, §5)
6. **§4 — HTML + audio exports.** Five new files:
   - `debate/scripts/compose_transcript.py` (~150 LoC)
   - `debate/scripts/compose_full_event.py` (~350 LoC)
   - `debate/scripts/render_audio.py` (~400 LoC)
   - `debate/scripts/_methodology_template.md` (asset)
   - Edits to `debate/scripts/package_outputs.py` (`HIGHLIGHTS_PATTERNS`) and SKILL.md Phase C4 sequence.

   Order matters: `compose_full_event.py` → `render_html.py` (existing) → `render_audio.py` → `package_outputs.py`. Test against the reference event `ariasA_davidsonB_2026-05-26_c7893c/` whose hand-crafted `full_debate.md` is the golden fixture.

   **Dependencies to install before running §4:** `bash scripts/helper_scripts/run_conda_bash.sh -- pip install kokoro soundfile pydub` + `brew install ffmpeg`. First Kokoro run downloads a ~330 MB model.

### Phase 4: In-flight session handoff (depends on §1–§6 being committed)
7. **§7 — Running-session handoff.** **As your absolute last action** before reporting to the user:
   - `Write` `debate_events/ariasA_davidsonB_2026-05-26_c7893c/handoff_for_running_moderator.md` — verbatim content from §7 §3.
   - In your final user-facing message, include the paste-in instruction so the user can copy it into the still-running VSCode conversation (slug `ariasA_davidsonB_2026-05-26_c7893c`).

## Open issues to resolve at implementation time

Listed in detail in the plan's **Open Issues** section. The load-bearing ones to surface to the user as you implement:

- **OI-1.3** — what does "iteration-3-failure" return? (Decide before §1's B5a/B5b implementation.)
- **OI-2.1** — does the Agent Teams runtime expose a stable `agent_id` separate from `name`? Verify on first spawn; if not, drop the field from `team.json`.
- **OI-4.B** — gender field provenance for default voice map. Cross-chapter §5↔§4 decision. Recommend asking the user at briefing time (one extra `AskUserQuestion` per scientist in §5's B0.5 alongside the affiliation confirm).
- **OI-4.D** — spoken disclaimer wording. Default draft in §4 §3.3; review with user before locking `render_audio.py`.
- **OI-4.E** — are audience interjections voiced in the recording? Yes/no decision; if yes, `compose_full_event.py` must inject them at break-points.
- **OI-4.F** — `compose_transcript.py` resume behaviour: clobber or skip-if-exists? Recommend skip-if-exists + `--force` flag.
- **OI-6.3** — verify task-notification `usage` block shape against an actual payload before implementing §6.6. If the harness only emits a `total`, escalate.

## Reference paths

- Parent plan: `/Users/kleshcv/.claude/plans/wild-plotting-finch.md`
- Backup of pre-format-plan plan: `/tmp/.format-plan-backup-wild-plotting-finch-20260526-090147.md`
- Per-chapter draft files (intermediate outputs from the format-plan subagents, kept for audit):
  - `/Users/kleshcv/.claude/plans/wild-plotting-finch-agent-ad121d8874b19463b.md` (§1)
  - `/Users/kleshcv/.claude/plans/wild-plotting-finch-agent-a411411148db2403c.md` (§2)
  - `/Users/kleshcv/.claude/plans/wild-plotting-finch-agent-a5469c9e41fce1305.md` (§3)
  - `/Users/kleshcv/.claude/plans/wild-plotting-finch-agent-a5b1304c876a8376d.md` (§4)
  - `/Users/kleshcv/.claude/plans/wild-plotting-finch-agent-a641a5b3bfc5d1bc4.md` (§5)
  - `/Users/kleshcv/.claude/plans/wild-plotting-finch-agent-a78b142ad2f29d9b3.md` (§6)
  - `/Users/kleshcv/.claude/plans/wild-plotting-finch-agent-a7c4c77baf5cc36af.md` (§7)
- Running session (in-flight debate): `/Users/kleshcv/.claude/projects/-Users-kleshcv-Desktop-my-packages-science-debate/35ab7dec-f16e-440b-bbc0-9b016b38d875.jsonl`
- Running event folder: `/Users/kleshcv/Desktop/my_packages/science_debate/debate_events/ariasA_davidsonB_2026-05-26_c7893c/`
- Reference `full_debate.md` / `full_debate.html` (hand-crafted, used as golden fixture for §4): same folder as above
