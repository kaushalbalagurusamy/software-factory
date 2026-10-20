#!/usr/bin/env python3
"""Generates docs/explorer/software-factory.model.json (the source of the explorer).
  python3 docs/explorer/build_model.py <commit> docs/explorer/software-factory.model.json   (run from the repo root)
Then check and build with skills/mermaid-nesting-dolls/scripts/nesting_dolls.py (see docs/explorer/README.md)."""

import json, sys

nodes = {}
SF = "~/.claude/skills/sf/SKILL.md"


def F(path, lines=None, contains=None, note=None, ext=False):
    d = {"path": path}
    if lines: d["lines"] = lines
    if contains: d["contains"] = contains
    if note: d["note"] = note
    if ext: d["external"] = True
    return d


def X(path, lines=None, contains=None, note=None):  # external (outside repo) file
    return F(path, lines, contains, note, ext=True)


def D(choice, why, alternatives=None):
    d = {"choice": choice, "why": why}
    if alternatives: d["alternatives"] = alternatives
    return d


def C(status, note, gaps=None):
    d = {"status": status, "note": note}
    if gaps: d["gaps"] = gaps
    return d


def N(id, title, summary, kind=None, detail=None, design=None, files=None, cov=None, diagram=None, children=None):
    n = {"title": title, "summary": summary}
    if kind: n["kind"] = kind
    if detail: n["detail"] = detail
    if design: n["design"] = design
    if files: n["files"] = files
    if cov: n["coverage"] = cov
    if diagram: n["diagram"] = diagram
    if children: n["children"] = children
    nodes[id] = n


# =================================================================================================== ROOT
N("factory", "Claude Software Factory",
  "A set of skills, rules, deterministic gates and designed agent roles that turn an AI coding assistant from a 'vibe-coder' into a disciplined engineer: requirements are verified before use, tests come before code, the implementer is blind to the tests, and verification is deterministic and independent.",
  kind="system",
  detail=["The factory is three things layered together. The method (the /sf build loop and its skills) is the part that runs today. A deterministic engine (the sf CLI) enforces test integrity and one-way-door detection. An agent layer (seven roles with hooks) is specified and tested-in-advance but not implemented.",
          "Click any stacked box to open the diagram inside it. The Coverage tab lists what is built, partial, only designed, outside the repo, or a gap, with reasons."],
  design=[D("Guard one-way doors; leave two-way doors fast", "Local, reversible work (UI, helpers, cache TTLs) runs autonomously; schemas, auth, public API and vector dimensions need a Socratic debate and an ADR.", "One uniform, rigid process for every change"),
          D("Verification is deterministic; models advise, they do not vote", "Hash baselines, AST scans and hooks cannot be talked around, which is the answer to reward hacking.", "LLM committees grading each other's work")],
  files=[F("README.md", "12-41", "ONE-WAY DOORS", "The manifesto and the two-door model"),
         F("RESEARCH_MANIFESTO.md", "1-10", "Panopticon", "The research argument behind the design"),
         F("docs/factory/METHODOLOGY.md", "5-12", "Requirements first", "Rules every agent must follow")],
  cov=C("partial", "The method runs and the CLI engine exists; the agent layer that would enforce the method mechanically is specified, not built.",
        ["Agent-layer hooks and roles are not implemented, so most of the method is still advice enforced by discipline",
         "This repository has no build-loop profile, so /sf is not applied to the factory's own development"]),
  diagram=[
      "flowchart LR",
      "  intake[\"Requirements intake<br/>sweep the brief\"] -->|\"verified requirements<br/>become a ledger\"| build-loop[\"Build loop<br/>/sf, 12 stages\"]",
      "  skills-library[\"Skills library<br/>procedures per stage\"] -->|\"each stage invokes<br/>a skill\"| build-loop",
      "  governance-docs[\"Decisions and rules<br/>ADRs, contracts, plans\"] -->|\"binding rules\"| build-loop",
      "  governance-docs -->|\"contracts the<br/>roles implement\"| agent-layer[\"Agent layer<br/>8 roles + hooks\"]",
      "  build-loop -->|\"split work across<br/>roles (designed)\"| agent-layer",
      "  build-loop -->|\"run the deterministic<br/>gates\"| verification-engine[\"Verification engine<br/>factory/ and sf CLI\"]",
      "  agent-layer -->|\"graded blind by\"| evals-gate[\"Evals and golden gate\"]",
      "  verification-engine -->|\"routing decisions,<br/>shadow only\"| routing[\"Jev routing\"]",
      "  build-loop -->|\"state, hygiene,<br/>owner briefings\"| ops-runtime[\"Session ops<br/>and dashboards\"]",
  ],
  children=["intake", "build-loop", "skills-library", "governance-docs", "agent-layer", "verification-engine", "evals-gate", "routing", "ops-runtime"])

# =================================================================================================== INTAKE
N("intake", "Requirements intake and sweep",
  "Before any line of a brief becomes a requirement, it is transcribed verbatim, swept for traps (licences, provider terms, impossible guarantees, inverted rubrics), settled by research and experiments, and only then written into a PRD and a requirements ledger.",
  kind="process",
  detail=["Every line of prose in a source brief is a requirement, including 'optional' items and out-of-scope lists. The ledger is the one summary table allowed to exist because stage 9 of the loop rebuilds its touched rows from the source every time."],
  design=[D("Sweep the brief before trusting it", "Briefs and rubrics can carry traps: a licence you cannot meet, a guarantee theory rules out, a rubric that rewards the wrong thing. Finding them after building is far more expensive.", "Trusting the PRD as written"),
          D("The sweep is a loop, not a one-shot gate", "Suspects are settled with grounded research and experiments until the loop converges; the PRD is written only after.", "A single checklist pass")],
  files=[X(SF, "99-124", "Sweep the brief before trusting it", "Stage 1 describes the minesweeper discovery loop"),
         F("docs/plans/2026-10-14-minesweeper-skill-proposal.md", "180-182", "The discovery loop")],
  cov=C("partial", "The skills exist outside this repo and the process is written into /sf; this repository only holds the design proposal.",
        ["The only in-repo document about the sweep still says 'Nothing is built yet', while an engine, 26 lens packs and tests exist under ~/.claude/skills/minesweeper"]),
  diagram=[
      "flowchart LR",
      "  brief[\"Source brief<br/>untrusted\"] -->|\"every line becomes a row\"| spec-recomposition[\"spec-recomposition<br/>verbatim register\"]",
      "  spec-recomposition -->|\"claims to sweep\"| minesweeper[\"minesweeper<br/>trap sweep\"]",
      "  minesweeper -->|\"suspects\"| research-loop[\"Research and experiments<br/>grounded, deep, experiment-designer\"]",
      "  research-loop -->|\"settled findings\"| minesweeper",
      "  minesweeper -->|\"problem definition +<br/>trap register\"| prd-writer[\"prd-writer<br/>the real PRD\"]",
      "  prd-writer -->|\"one row per line,<br/>trust status per row\"| req-ledger[\"Requirements ledger<br/>satisfied / partial / blocked / unserved\"]",
  ],
  children=["brief", "spec-recomposition", "minesweeper", "research-loop", "prd-writer", "req-ledger"])
N("brief", "Source brief", "The partner brief, assignment, RFP or rubric that arrives, treated as untrusted input.", kind="input",
  cov=C("external", "Supplied per project; none lives in this repository."))
N("spec-recomposition", "Spec recomposition", "Transcribes an external spec verbatim, extracts every line as a categorised, linked requirement row, and verifies by script that no line was missed.", kind="skill",
  files=[X("~/.claude/skills/spec-recomposition/SKILL.md", None, "verbatim", "Installed skill; not versioned in this repo")],
  cov=C("external", "Global skill under ~/.claude/skills, not catalogued in README.md or PROMOTIONS.md."))
N("research-loop", "Research and experiments", "grounded-research verifies single claims, deep-research surveys a topic, and experiment-designer pre-registers a fair comparison when two or more approaches remain.", kind="skills",
  design=[D("Enumerate candidates from a dated source, never from recall", "A list written from memory stops at the training cutoff; a committed enumeration lets a reader tell 'rejected' from 'never considered'.")],
  files=[X(SF, "125-154", "Build the candidate list from a dated enumeration", "Stage 2 rules")],
  cov=C("external", "Skills live in ~/.claude/skills."))
N("prd-writer", "PRD writer", "Writes the real PRD (work units with file scope, accepted ADRs, experiment verdicts) from the checked problem definition and the trap register.", kind="skill",
  files=[X("~/.claude/skills/prd-writer/SKILL.md", None, "PRD", "Installed skill")],
  cov=C("external", "Global skill; not catalogued in this repo's skills tables."))
N("req-ledger", "Requirements ledger", "One row per requirement line with a status and the artifact that satisfies it or the dependency it waits on. It is what makes 'the run ends when requirements are met' measurable.", kind="artifact",
  design=[D("Pick the next slice from the ledger, not from a queue", "A queue is a guess at what the requirements need and runs out first; unserved rows with no producer are the highest-value work.")],
  files=[X(SF, "36-63", "requirements ledger", "The termination rule"),
         F("docs/factory/requirements.md", "1-12", "Requirements register", "The agent layer's own register (R-01 to R-24), a worked example of the form")],
  cov=C("partial", "The agent-layer register exists in the repo; the ledger rows for the factory as a whole do not.",
        ["No ledger exists for the factory itself; only for the agent-layer build"]))
N("minesweeper", "Minesweeper", "Sweeps a brief for traps with swappable lens packs, assigns deterministic severity, and hands a checked problem definition to the PRD writer.", kind="skill",
  detail=["Lenses cover licence, provider terms, privacy, regulation, hallucinated dependencies, impossible guarantees, inverted rubrics and omitted trust or threat models. An open Critical finding blocks scheduling of the rows it conditions until the owner signs off."],
  design=[D("Modular lens packs", "New domains and releases add a lens directory instead of rewriting the engine.", "One monolithic checklist")],
  files=[F("docs/plans/2026-10-14-minesweeper-skill-proposal.md", "68-80", "lens.md", "Architecture: lens packs"),
         X("~/.claude/skills/minesweeper/SKILL.md", None, "minesweeper")],
  cov=C("partial", "Installed with an engine, lens packs and tests; not catalogued here and its proposal document is stale. Its tests were not run in this exploration.",
        ["Proposal still says 'Nothing is built yet'", "Not listed in README.md or PROMOTIONS.md"]))

# =================================================================================================== BUILD LOOP
stages = [
    ("stage-1-research", "1 Research", "Establish what is true now, from primary sources, seeded from the course corpus before any web search.", "99-124"),
    ("stage-2-experiment", "2 Experiment", "Produce multi-metric numbers for any choice that matters; candidate lists come from a dated enumeration.", "125-154"),
    ("stage-3-decide", "3 Decide", "Record the decision as an ADR; one-way doors go through the one-way-door skill.", "155-158"),
    ("stage-4-spec", "4 MECE spec", "One thin tracer-bullet slice, decomposed so parts neither overlap nor leave gaps; names what the dashboard must show.", "159-168"),
    ("stage-5-tests-first", "5 Tests first", "Author tests and evals before any implementation; a case may exist before its producer and then resolves to blocked.", "169-174"),
    ("stage-6-implement-blind", "6 Implement blind", "The implementer never reads the test or eval files; it fixes against the contract.", "175-179"),
    ("stage-7-separate-runner", "7 Separate runner", "A different agent runs the tests, the cheapest guard against a green result that was arranged.", "180-182"),
    ("stage-8-review", "8 Adversarial review", "An independent skeptical reviewer hunts the 'third state': a pass earned for the wrong reason.", "183-190"),
    ("stage-9-drift", "9 Drift check", "Reread the verbatim source line by line, then update the ledger rows the slice touched.", "191-203"),
    ("stage-10-doc-sync", "10 Doc sync", "Propagate the decision into every document and dashboard that derives from it.", "204-220"),
    ("stage-11-commit", "11 Atomic commit", "One commit per logical change, as each lands.", "221-222"),
    ("stage-12-inbound", "12 Check inbound", "Look at what arrived while working, rank it into the ledger or backlog, say 'nothing new' explicitly, then brief the owner.", "223-252"),
]
stage_design = {
    "stage-5-tests-first": [D("Tests and evals precede implementation", "Scheduling tests after the feature is a defect in the plan; a case written first cannot be shaped to fit the code.", "Tests written once the feature works")],
    "stage-6-implement-blind": [D("Blindness by hook, not by instruction", "ADR-0003 says hooks enforce and prompts advise; the guard is specified in TB-06.", "A PRD sentence saying 'do not read evals/'")],
    "stage-7-separate-runner": [D("Author and runner are different agents", "The party that wrote the code cannot arrange its own green.")],
    "stage-8-review": [D("Different model family reviews where available", "Correlated blind spots between implementer and reviewer are the risk; METHODOLOGY asks for a different vendor.", "Self-review by the implementer")],
    "stage-9-drift": [D("Re-derive from the source, never from a summary table", "The summary table is exactly where drift hides.")],
}
for sid, title, summ, ln in stages:
    cov = None
    if sid == "stage-6-implement-blind":
        cov = C("gap", "Blindness is currently only by instruction: this repo has no profile and no hooks, so nothing mechanical stops an implementer reading evals/.",
                ["MECE audit finding P0-5: this build's implementers are blind to evals/ only by instruction"])
    elif sid in ("stage-5-tests-first", "stage-7-separate-runner", "stage-8-review"):
        cov = C("external", "Defined in the installed /sf skill; mechanical enforcement waits on the agent layer.")
    nodes_ = N(sid, title, summ, kind="stage", design=stage_design.get(sid),
               files=[X(SF, ln, None, "Stage text in the installed /sf skill (not versioned in this repo)")], cov=cov)

L = lambda i: f'{stages[i][0]}["{stages[i][1]}"]'
N("build-loop", "Build loop (/sf)",
  "The fixed twelve-stage loop every implementation slice follows, bound into a checklist with one todo per stage so a skipped stage is visible instead of forgotten.",
  kind="process",
  detail=["The loop is not a variable: schedule pressure may reorder or slice work smaller but never drop a stage. The run ends when every requirement line is satisfied or recorded as blocked with what it waits on, not when a queue empties."],
  design=[D("Make the back half of the loop a checklist", "Research and experiments are interesting and get done; tests-first, blind implementation, separate runner, adversarial review and drift check cost time without visible progress, so they quietly vanish. A todo per stage makes a skip visible.", "A process document consulted from memory")],
  files=[X(SF, "17-35", "A defined development loop decays", "Why the loop exists"),
         X(SF, "95-98", "Create one todo per stage", "The stages section")],
  cov=C("partial", "Fully written and in daily use on other projects; absent for this repository itself.",
        ["The installed skill is the only copy: the repository's own history does not version it"]),
  diagram=[
      "flowchart LR",
      "  subgraph truth[\"Establish what is true\"]",
      "    direction LR",
      "    " + " --> ".join(L(i) for i in (0, 1, 2)),
      "  end",
      "  subgraph prove[\"Specify and prove\"]",
      "    direction LR",
      "    " + " --> ".join(L(i) for i in (3, 4, 5, 6, 7)),
      "  end",
      "  subgraph close[\"Close the loop\"]",
      "    direction LR",
      "    " + " --> ".join(L(i) for i in (8, 9, 10, 11)),
      "  end",
      "  truth -->|\"decision recorded\"| prove",
      "  prove -->|\"earned pass\"| close",
      "  close -->|\"ledger updated\"| next-slice([\"Next slice is chosen<br/>from the ledger, not a queue\"])",
      "  build-profile[\"Project profile<br/>.claude/build-loop.md\"] -->|\"paths, commands, reviewer\"| truth",
      "  build-hygiene[\"Hygiene<br/>disk and memory\"] -.->|\"beside every stage\"| prove",
  ],
  children=[s[0] for s in stages] + ["build-profile", "build-hygiene"])
N("build-profile", "Project profile", "A per-project file that names where verbatim requirements, ADRs, specs, tests live, the test command and the reviewer. The skill is project-independent; everything specific lives here.", kind="config",
  files=[X(SF, "85-94", "Load the project profile first")],
  cov=C("gap", "This repository deliberately has none: the owner decision on 2026-10-09 was to stand by until asked for factory changes, so the factory is not built with its own loop.",
        ["No .claude/build-loop.md exists in this checkout"]))
N("build-hygiene", "Hygiene", "A deterministic script scans disk and memory before fan-out and after merges so a long run does not die of ENOSPC mid-write.", kind="harness",
  files=[X(SF, "253-294", "Hygiene: disk and memory"), X("~/.claude/skills/sf/hygiene/hygiene.sh")],
  cov=C("external", "Scripts live in the installed skill directory, not in this repo."))

# =================================================================================================== SKILLS LIBRARY
N("skills-library", "Skills library",
  "The reusable procedures each stage and role loads. Masters live in ~/.claude/skills (a separate local git repository), not here; this repo keeps the catalog, the retired originals and a CI check on frontmatter.",
  kind="library",
  design=[D("Skills are procedures; roles sit above them", "ADR-0003 keeps skills as what a role loads and replaces none of them, so consolidating skills does not lose step ownership."),
          D("Masters live outside the repository", "One shared, versioned home for personal skills across every project and for Codex via a link.", "Copies of each skill in every repo")],
  files=[F("README.md", "48-60", "versioned in this repository", "Skills catalog and where the masters live"),
         F("PROMOTIONS.md", "7-31", "Current state", "The promotion ledger")],
  cov=C("partial", "The catalog and archive are in the repo; most of the working skill set is not.",
        ["README.md lists 5 skills and PROMOTIONS.md about 21; minesweeper, spec-recomposition, biz-decomposer, prd-writer, doc-sync, progress-briefing, ops-dashboard-design, experiment-designer, good-night and good-morning appear in neither"]),
  diagram=[
      "flowchart LR",
      "  skills-spec[\"Spec chain<br/>recompose, sweep, PRD, axioms\"] -->|\"feeds\"| skills-decide[\"Decide and review<br/>one-way-door, review\"]",
      "  skills-decide -->|\"gates\"| skills-test[\"Tests and evals<br/>eval-designer, experiment-designer\"]",
      "  skills-test -->|\"shipped by\"| skills-ship[\"Ship and observe<br/>deploy-verify, dashboards, doc-sync\"]",
      "  skills-session[\"Session control<br/>sf, away-mode, good-night\"] -->|\"drives\"| skills-spec",
      "  promotions-ledger[\"Promotion ledger<br/>PROMOTIONS.md\"] -.->|\"tracks (partially)\"| skills-decide",
      "  skills-archive[\"Retired originals<br/>skills/_archive\"] -.->|\"history only\"| skills-decide",
      "  skills-ci[\"CI frontmatter check\"] -->|\"validates skills/**/SKILL.md\"| skills-archive",
  ],
  children=["skills-spec", "skills-decide", "skills-test", "skills-ship", "skills-session", "promotions-ledger", "skills-archive", "skills-ci"])
N("skills-spec", "Spec chain", "spec-recomposition, minesweeper, biz-decomposer, prd-writer, axiomatic-spec and brownfield-explorer turn a brief into verified, scoped, contract-level requirements.", kind="skills",
  files=[X("~/.claude/skills/axiomatic-spec/SKILL.md"), X("~/.claude/skills/brownfield-explorer/SKILL.md"), X("~/.claude/skills/biz-decomposer/SKILL.md")],
  cov=C("external", "Installed skills; only axiomatic-spec and brownfield-explorer are in the promotion ledger."))
N("skills-decide", "Decide and review", "one-way-door (door check then ADR debate), implementation-review (independent review, drift, earned passes), orchestration (division of labour, safe parallel dispatch) and plan-adherence.", kind="skills",
  files=[F("PROMOTIONS.md", "7-31", "one-way-door"), X("~/.claude/skills/one-way-door/SKILL.md"), X("~/.claude/skills/implementation-review/SKILL.md")],
  cov=C("external", "Merged from the retired sf-* skills on 2026-09-24; the trigger smoke checks exist for most.", ["The merged one-way-door skill 'not yet run through the trigger-eval loop' per the promotion ledger"]))
N("skills-test", "Tests and evals", "eval-designer designs deterministic eval harnesses; experiment-designer pre-registers a fair comparison between candidate approaches.", kind="skills",
  files=[F("templates/deterministic-eval-template.py", None, "unittest", "The reusable eval template CI runs"), X("~/.claude/skills/eval-designer/SKILL.md")],
  cov=C("external", "Installed skills; the template is in this repo and exercised by CI."))
N("skills-ship", "Ship and observe", "deploy-verify (gate, deploy, verify loop, Deploy Log), ops-dashboard-design, doc-sync and progress-briefing.", kind="skills",
  files=[X("~/.claude/skills/deploy-verify/SKILL.md"), X("~/.claude/skills/doc-sync/SKILL.md"), X("~/.claude/skills/ops-dashboard-design/SKILL.md")],
  cov=C("external", "Installed skills."))
N("skills-session", "Session control", "sf, away-mode, good-night and good-morning, session-handoff keep a long unattended run resumable and the owner informed.", kind="skills",
  files=[X("~/.claude/skills/away-mode/SKILL.md"), X("~/.claude/skills/good-night/SKILL.md"), X("~/.claude/skills/session-handoff/SKILL.md")],
  cov=C("external", "Installed skills."))
N("promotions-ledger", "Promotion ledger", "A table that tracks each capability's rung (skill, harness) and location, and what is pending.", kind="doc",
  files=[F("PROMOTIONS.md", "7-31", "Current state"), F("PROMOTIONS.md", "33-37", "Pending promotions")],
  cov=C("gap", "Stale: it omits roughly ten installed skills and its own header dates from 2026-09-15 to 2026-09-24.", ["Row set no longer matches ~/.claude/skills"]))
N("skills-archive", "Retired originals", "The five original sf-* skills (door-guard, adr-debate, interface-auditor, io-analyzer, spec-testing), kept as history after consolidation.", kind="archive",
  files=[F("skills/_archive/sf-door-guard/SKILL.md", None, "name:"), F("docs/plans/2026-09-24-skills-consolidation-proposal.md", None, "sf-door-guard", "Why they were merged")],
  cov=C("built", "Present and read-only history; not installed."))
N("skills-ci", "CI frontmatter check", "The only CI job validates that each skills/**/SKILL.md has frontmatter with a name and description, then runs the deterministic eval template.", kind="ci",
  files=[F(".github/workflows/ci.yml", "11-51", "Validate Skill Frontmatters")],
  cov=C("gap", "CI never runs tests/ or evals/agents/, so the factory's own code and golden gate are not gated.", ["No pytest step in .github/workflows/ci.yml"]))

# =================================================================================================== GOVERNANCE DOCS
N("governance-docs", "Decisions and rules",
  "The written authority the rest of the factory obeys: three accepted ADRs, the methodology every agent must follow, the requirements register, binding contracts and the plans.",
  kind="docs",
  design=[D("Rules live in the repo, not only in skills or memory", "Planners and reviewers from other vendors cannot load Claude skills; if a plan conflicts with METHODOLOGY the plan is wrong.")],
  files=[F("docs/factory/METHODOLOGY.md", "1-4", "written here, not only in skills"), F("docs/adr/ADR-0003-agent-roles-above-skills.md", "26-28", "Decision Outcome")],
  cov=C("partial", "Decisions are well documented; the summary documents have drifted.", ["ROADMAP.md has no mention of the agent layer or ADR-0003", "README says 25/25 tests pass; a bare run here gave 31 passed and 9 failed"]),
  diagram=[
      "flowchart LR",
      "  adrs[\"ADRs 0001 to 0003<br/>docs/adr\"] -->|\"decisions\"| methodology[\"Methodology<br/>rules for every agent\"]",
      "  methodology -->|\"IDs and sources\"| requirements[\"Requirements register<br/>R-01 to R-24\"]",
      "  requirements -->|\"published as\"| contracts[\"Contracts<br/>docs/contracts\"]",
      "  plans[\"Plans and research<br/>Austin plan, capability map\"] -->|\"inform\"| adrs",
      "  roadmap[\"Roadmap<br/>two-repo phases\"] -.->|\"older frame\"| plans",
  ],
  children=["adrs", "methodology", "requirements", "contracts", "plans", "roadmap"])
N("adrs", "Architecture decision records", "ADR-0001 chooses the Unity-IR dual-plane substrate, ADR-0002 the zero-trust verification substrate, ADR-0003 seven agent roles above skills.", kind="docs",
  design=[D("Unity-IR (ADR-0001)", "A deterministic three-layer schema decouples reasoning from lexical syntax; reviewers audit semantic delta rather than lines.", "Raw polyglot source in the model context"),
          D("Zero-trust verification (ADR-0002)", "Hashed baselines, design-by-contract and symbolic exploration remove reward hacking structurally.", "Trusting model-written tests"),
          D("Roles above skills (ADR-0003)", "Split by context boundary, not pipeline phase; one writer per tree; hooks enforce, prompts advise.", "A fixed seven-stage relay")],
  files=[F("docs/adr/ADR-0001-unity-invariant-substrate.md", "26-28", "Option 3"), F("docs/adr/ADR-0002-epistemic-zero-trust-verification.md", "26-34", "Cryptographic Baseline Locking"), F("docs/adr/ADR-0003-agent-roles-above-skills.md", "26-40", "Option 3")],
  cov=C("partial", "All three accepted. ADR-0002's decision lists four implementation requirements; the code implements only the first.",
        ["deal contracts, CrossHair and hypothesis are in requirements.txt but never imported by factory/", "ADR-0003 itself says roles and hooks are not built yet"]))
N("methodology", "Methodology", "Six rules: requirements first, contracts next, evals before features, independent MECE audit, implement blind, deterministic verification then independent review; plus roles, parallel work, gates and 'done means'.", kind="docs",
  files=[F("docs/factory/METHODOLOGY.md", "5-12", "Evals before features"), F("docs/factory/METHODOLOGY.md", "26-35", "Pause and ask a person")],
  cov=C("built", "A complete, internally consistent rule set; enforcement is the agent layer's job."))
N("requirements", "Requirements register", "R-01 to R-24 for the agent layer, each with a source and the tracer bullets that deliver it.", kind="docs",
  files=[F("docs/factory/requirements.md", None, "R-24")], cov=C("built", "Complete for the agent layer and traced to PRDs and golden cases by the MECE audit."))
N("contracts", "Published contracts", "Hook input/output, project profile, role specs and generated agent files, stage graph and ticket ledger, plus the binding clarifications that win over PRDs when they differ.", kind="docs",
  files=[F("docs/contracts/hook-io.md", "16-18", "Python API"), F("docs/contracts/clarifications.md", "1-5", "Binding clarifications")],
  cov=C("built", "Published; evals and implementers both depend on them and on nothing else."))
N("plans", "Plans and research", "The Austin-ready plan, the seven-agents design, the capability map, the skills consolidation, the minesweeper proposal and a token-saving research note.", kind="docs",
  files=[F("docs/plans/2026-09-23-austin-ready-software-factory-plan.md", "36-67", "flowchart TD", "Ticket-in, PR-out graph"), F("docs/plans/2026-09-24-agent-capability-map.md", "28-30", "The seven agents"), F("research/claude-code-token-saving.md", "6-10", "Headline")],
  cov=C("partial", "Rich design material; several documents record 'DESIGN, nothing built' and need a status refresh as work lands."))
N("roadmap", "Roadmap", "The original two-repository (unity and software-factory) phased roadmap with milestone status.", kind="docs",
  files=[F("ROADMAP.md", "70-81", "software-factory"), F("ROADMAP.md", "94-96", "Phased Implementation Roadmap")],
  cov=C("gap", "Written before the agent layer: it does not mention roles, hooks, contracts or the build loop.", ["Needs an update or a pointer to the Austin plan"]))

# =================================================================================================== AGENT LAYER
N("agent-layer", "Agent layer",
  "Seven agent definitions (orchestrator, research, design, audit, implement, test, review) with their own models, tool allowlists and hooks, generated from a project profile so nothing names a specific project. Specified through 14 tracer-bullet PRDs; none implemented.",
  kind="subsystem",
  detail=["Hooks enforce what prompts only advise: path ownership, implement blindness to evals, secrets, git hygiene, a stop gate against weakened tests, and a tamper-evident ticket ledger. All hooks are pure decision functions with no network or model call."],
  design=[D("Split by context boundary, not pipeline phase", "Phase-based splits add coordination overhead and lost accuracy on sequential tasks.", "A seven-stage relay"),
          D("Everything project-specific comes from a profile", "Roles, skills and hooks stay generic; the profile supplies paths, one-way-door patterns, deploy route.", "Per-project forks of the role files")],
  files=[F("docs/adr/ADR-0003-agent-roles-above-skills.md", "26-40", "Option 3"), F("docs/prds/INDEX.md", "1-30", "TB-01"), F("docs/plans/2026-09-24-agent-layer-status.md", "5-20", "Not done")],
  cov=C("partial", "The specification layer is built: requirements, 5 contracts, 14 PRDs and 1,302 pre-written eval cases. The runtime layer is not: factory/agents and factory/hooks do not exist.",
        ["Zero of the 14 tracer bullets implemented", "Paused on 2026-09-24; five P0 audit findings still unaddressed"]),
  diagram=[
      "flowchart LR",
      "  profile-loader[\"Project profile<br/>TB-01\"] -->|\"roles, paths, patterns\"| role-specs[\"Seven role specs<br/>TB-02\"]",
      "  profile-loader -->|\"stages and gates as data\"| stage-graph[\"Stage graph<br/>TB-12\"]",
      "  role-specs -->|\"rendered to files\"| agent-generator[\"Agent file generator<br/>TB-03\"]",
      "  profile-loader -->|\"paths and patterns\"| hooks[\"Hooks<br/>TB-04 to TB-10\"]",
      "  hooks -->|\"audit trail\"| ticket-ledger[\"Ticket ledger<br/>TB-11\"]",
      "  agent-generator -->|\"agents\"| settings-emitter[\"Settings emitter<br/>TB-13\"]",
      "  hooks -->|\"hook wiring\"| settings-emitter",
      "  settings-emitter -->|\"project settings\"| walking-skeleton[\"Walking skeleton<br/>TB-14\"]",
      "  build-waves[\"Build waves<br/>dependency order\"] -.->|\"sequences\"| walking-skeleton",
  ],
  children=["profile-loader", "role-specs", "stage-graph", "agent-generator", "hooks", "ticket-ledger", "settings-emitter", "walking-skeleton", "build-waves"])
for pid, title, tb, summ, fp in [
    ("profile-loader", "Project profile loader", "TB-01", "Parses and validates the per-project profile: graph, per-role overrides, eval and held-out paths, one-way-door patterns, deploy route, git rules.", "docs/contracts/profile.md"),
    ("stage-graph", "Stage graph", "TB-12", "Loads the stage graph from the profile as data: stages, gates and roles are validated, loops must be declared, small tickets may select a subset of roles.", "docs/contracts/graph-and-ledger.md"),
    ("agent-generator", "Agent file generator", "TB-03", "Renders each role spec plus the profile into a Claude Code agent file using only supported frontmatter fields, at most 20 tools, and no platform names.", "docs/contracts/roles-and-generation.md"),
    ("ticket-ledger", "Ticket ledger", "TB-11", "An append-only per-ticket Markdown ledger with fixed sections; each agent may write only its own section; a session-start loader and an audit-trail entry per sub-agent run; tampering with earlier entries is detected.", "docs/contracts/graph-and-ledger.md"),
    ("settings-emitter", "Settings emitter", "TB-13", "Turns the profile into project-level hook and permission settings as a reviewable diff; idempotent, never touches user-level settings, never writes secrets.", "docs/prds/TB-13-settings-emitter.md"),
    ("walking-skeleton", "Walking skeleton", "TB-14", "End to end: a fixture project's profile produces agent files and settings, and a simulated event stream with no model calls is allowed or blocked exactly as the requirements say; Jev routing is logged in shadow.", "docs/prds/TB-14-walking-skeleton.md"),
]:
    N(pid, title, summ, kind=tb, files=[F(fp, None, tb if "prds" in fp else {"docs/contracts/profile.md":"profile","docs/contracts/graph-and-ledger.md":"Ledger","docs/contracts/roles-and-generation.md":"RoleSpec"}[fp])],
      cov=C("designed", f"{tb} is a published PRD with contracts and pre-written eval cases; no implementation exists."))
nodes["walking-skeleton"]["coverage"]["gaps"] = ["Whether a sub-agent's frontmatter Stop hook runs as SubagentStop is unverified (clarification C-34)"]
N("build-waves", "Build waves", "Five waves from the dependency graph: TB-01 and TB-02; then TB-03, TB-04, TB-12; then seven parallel hooks in two batches; then TB-13; then TB-14. Slices in a wave are file-disjoint and run in separate worktrees.", kind="plan",
  design=[D("Dependency graph from real inputs, not list order", "Items that need only committed inputs run in parallel; the orchestrator alone edits shared seams between agents.")],
  files=[F("docs/prds/INDEX.md", "31-35", "Wave 5"), F("docs/factory/METHODOLOGY.md", "20-24", "dependency graph")],
  cov=C("designed", "Plan only; no wave has started."))

# ---- role specs group
N("role-specs", "Seven role specs", "Orchestrator, Research, Design, Audit, Implement, Test and Review, each with a model, tools, skills, MCP servers and hooks.", kind="TB-02",
  design=[D("Narrow tools, smallest adequate model", "Every subagent inherits the plugin and skill listing, so each role lists at most 20 tools and only read tools of an MCP server unless it needs more.")],
  files=[F("docs/plans/2026-09-24-seven-core-agents.md", "24-34", "**Implement**"), F("docs/contracts/roles-and-generation.md", "5-7", "RoleSpec")],
  cov=C("designed", "Model choices are proposals to be measured before fixing."),
  diagram=[
      "flowchart LR",
      "  role-orchestrator[\"Orchestrator<br/>sequences, no app code\"] -->|\"fan-out, read-only\"| role-research[\"Research\"]",
      "  role-orchestrator -->|\"brief to PRD, ADR\"| role-design[\"Design\"]",
      "  role-orchestrator -->|\"legacy read pass\"| role-audit[\"Audit\"]",
      "  role-orchestrator -->|\"one per worktree\"| role-implement[\"Implement<br/>only writer of app code\"]",
      "  role-design -->|\"spec\"| role-test[\"Test<br/>evals first, then frozen\"]",
      "  role-test -.->|\"hidden from\"| role-implement",
      "  role-implement -->|\"diff and traces\"| role-review[\"Review<br/>different vendor\"]",
      "  role-test -->|\"verdicts\"| role-review",
  ],
  children=["role-orchestrator", "role-research", "role-design", "role-audit", "role-implement", "role-test", "role-review"])
roles = [
    ("role-orchestrator", "Orchestrator", "Holds state, sequences stages, dispatches, calls humans at gates and runs deploy. Writes no application code; its routing is code, not model judgement.", "Opus (main session)", "One-way-door hook asks a human before deploys and destructive actions."),
    ("role-research", "Research", "Verifies facts and surveys topics; orients in a repo. Read-only fan-out; each returns a 1,000 to 2,000 token summary.", "Sonnet lead, Haiku workers", "Writes only research/*.md and its ledger section."),
    ("role-design", "Design", "Brief to PRD, axioms and contracts, one-way-door check, ADR. Runs behind gates G0, G1 and G2.", "Opus", "Writes only docs/prd, docs/spec, docs/adr."),
    ("role-audit", "Audit", "Complete read pass over legacy code before a rewrite; produces a bug catalog. Fan-out one unit per dispatch.", "Sonnet per unit, Haiku for inventory", "Writes only docs/audit."),
    ("role-implement", "Implement", "Builds one slice against the spec; the only role that edits application code, one per worktree, in a fresh-context loop with a cap.", "Sonnet; Opus after repeated failure", "Blind to eval and held-out paths by hook; cannot edit frozen tests."),
    ("role-test", "Test", "Writes evals first from the spec and freezes them, runs them, triages failures and runs post-deploy checks.", "Opus to author, Haiku to run", "Writes eval files only before implementation exists."),
    ("role-review", "Review", "Independent read of the diff, traces and passes; drift against requirements. Read-only; verdict only.", "A different vendor from Implement where available", "Verdict must be APPROVE or REJECT with citations."),
]
for rid, title, summ, model, rule in roles:
    N(rid, title, summ, kind="role", detail=[f"Proposed model: {model}.", rule],
      files=[F("docs/plans/2026-09-24-seven-core-agents.md", "24-34", f"**{title}**", "Role table row")],
      cov=C("designed", "A role definition in a design table; no generated agent file exists. Model choice is a proposal."))
nodes["role-review"]["coverage"]["gaps"] = ["Cross-vendor review depends on a second billing surface; Codex roles are out of scope by owner decision"]

# ---- hooks group
N("hooks", "Hooks", "Seven deterministic hook specs share one core: a payload parser and decision type, then guards for paths, blindness, secrets, Bash, stop and sub-agent stop. Guards fail closed on malformed input.", kind="TB-04..10",
  design=[D("Hooks enforce; prompts advise", "Each 'must never' is a hook or a missing tool, so an agent cannot talk its way past it.", "Instructions in the role prompt"),
          D("Hooks are pure decision functions with a thin protocol adapter", "No network, no model call, easy to test with recorded payloads.", "Hooks that call a model to judge")],
  files=[F("docs/contracts/hook-io.md", "1-30", "PreToolUse"), F("docs/plans/2026-09-24-agent-capability-map.md", "104-108", "Secrets")],
  cov=C("designed", "Contract published, eval cases written, no hook code exists."),
  diagram=[
      "flowchart LR",
      "  hook-core[\"Hook core<br/>payload + decision (TB-04)\"] -->|\"PreToolUse: where may this role write?\"| path-guard[\"Path guard<br/>TB-05\"]",
      "  hook-core -->|\"PreToolUse: implement only\"| blindness-guard[\"Blindness guard<br/>TB-06\"]",
      "  hook-core -->|\"PreToolUse: key-shaped value?\"| secrets-guard[\"Secrets guard<br/>TB-07\"]",
      "  hook-core -->|\"PreToolUse: Bash\"| bash-guard[\"Bash guard<br/>TB-08\"]",
      "  hook-core -->|\"Stop: implement says done\"| stop-gate[\"Stop gate<br/>TB-09\"]",
      "  hook-core -->|\"SubagentStop\"| subagent-validators[\"Sub-agent validators<br/>TB-10\"]",
  ],
  children=["hook-core", "path-guard", "blindness-guard", "secrets-guard", "bash-guard", "stop-gate", "subagent-validators"])
for hid, title, tb, summ, contains in [
    ("hook-core", "Hook core", "TB-04", "A frozen Payload dataclass, a Decision type (allow, deny, ask) and a thin adapter that turns stdin JSON into a decision and exit code; the command-line shape every hook shares.", "Payload"),
    ("path-guard", "Path guard", "TB-05", "Each role may write only its own folders (Research under research/, Design under docs/prd, spec and adr, Audit under docs/audit, Review nowhere). Only Implement writes application code.", "Path guard"),
    ("secrets-guard", "Secrets guard", "TB-07", "For every agent, blocks Write, Edit and Bash content containing a key-shaped value (sk-ant-, ghp_, private-key headers); allows references by variable name.", "Secrets guard"),
    ("bash-guard", "Bash guard", "TB-08", "Blocks git add -A and add ., --no-verify, force push, amend and rebase without approval; asks a human before destructive SQL, resource deletion, any deploy and every profile one-way-door pattern.", "Bash guard"),
    ("stop-gate", "Stop gate", "TB-09", "Refuses 'done' from Implement if a test was skipped, xfailed, deleted or given a trivial assertion, a frozen test's hash changed, or there is no evidence of a full-suite run.", "stop gate"),
    ("subagent-validators", "Sub-agent validators", "TB-10", "At SubagentStop: Research must have a sources section and mark unverified claims; Audit rows need file, line and severity; Review verdict must be APPROVE or REJECT with citations.", "validators"),
]:
    prd = {"TB-04": "docs/prds/TB-04-hook-core.md", "TB-05": "docs/prds/TB-05-path-guard.md", "TB-07": "docs/prds/TB-07-secrets-guard.md", "TB-08": "docs/prds/TB-08-bash-guard.md", "TB-09": "docs/prds/TB-09-stop-gate.md", "TB-10": "docs/prds/TB-10-subagent-stop-validators.md"}[tb]
    N(hid, title, summ, kind=tb, files=[F(prd, None, tb)], cov=C("designed", f"{tb} PRD and eval cases exist; no hook code."))
nodes["path-guard"]["coverage"]["gaps"] = ["MECE audit P0-4: Bash writes by full-mode roles bypass the path guard, and .factory/ and .claude/ are not protected"]
nodes["bash-guard"]["coverage"]["gaps"] = ["Golden set has no case with a project-specific one-way-door pattern (audit P0-1)"]
nodes["stop-gate"]["coverage"]["gaps"] = ["'No evidence of a full-suite run' has no golden case (audit P0-3)"]

N("blindness-guard", "Blindness guard", "For the implement agent only, denies Read, Grep, Glob and Bash commands that reference eval or held-out paths, including indirect forms. Every other role is never affected.", kind="TB-06",
  design=[D("Block by hook on agent_type, not by prompt instruction", "A PreToolUse payload carries agent_type, so one shared hook can block a path for one agent only.", "Read(evals/**) permission deny alone, which does not stop shell reads")],
  files=[F("docs/prds/TB-06-blindness-guard.md", "14-19", "Required behaviour"), F("docs/plans/2026-09-24-agent-capability-map.md", "15", "Blindness limits")],
  cov=C("designed", "PRD and eval cases exist, no hook code; known holes are listed below.",
        ["Golden set had no allowed-Bash case, so deny-all-Bash would pass (audit P0-2)", "A shell script that reads eval files without naming them is not stopped; the OS sandbox is the only backstop"]),
  diagram=[
      "flowchart LR",
      "  call[\"Tool call from a sub-agent\"] -->|\"payload.agent_type\"| role-check{\"implement?\"}",
      "  role-check -->|\"no: always allow\"| allow[\"Allow\"]",
      "  role-check -->|\"yes\"| bi-paths[\"Protected paths<br/>paths.eval, paths.held_out\"]",
      "  bi-paths -->|\"file_path, path, glob\"| bi-direct[\"Read, Grep, Glob\"]",
      "  bi-paths -->|\"command text\"| bi-bash[\"Bash commands\"]",
      "  bi-direct -->|\"normalise then match\"| bi-indirect[\"Indirect forms<br/>../ globs ~ symlinks\"]",
      "  bi-bash -->|\"normalise then match\"| bi-indirect",
      "  bi-indirect -.->|\"cannot see\"| bi-limits[\"Known limits<br/>scripts that read without naming\"]",
  ],
  children=["bi-paths", "bi-direct", "bi-bash", "bi-indirect", "bi-limits"])
N("bi-paths", "Protected paths", "paths.eval and paths.held_out from the profile, never hard-coded; a path is protected after normalising against cwd, collapsing . and .., and resolving symlinks.", kind="rule",
  files=[F("docs/prds/TB-06-blindness-guard.md", "16", "Protected paths")], cov=C("designed", "Specified; generality is not yet gated at golden level (audit P0-1)."))
N("bi-direct", "Read, Grep, Glob", "Deny a protected file_path, and deny a Grep or Glob whose path is missing, '.', or a strict ancestor of a protected path, telling the agent to search a specific subfolder instead.", kind="rule",
  files=[F("docs/prds/TB-06-blindness-guard.md", "17", "Read: deny")], cov=C("designed", "Specified."))
N("bi-bash", "Bash commands", "Deny commands that name a protected path in any argument form, run recursive searches that would reach it, or use interpreter one-liners; allow ordinary builds, tests of the agent's own directories, git diff and ls src.", kind="rule",
  files=[F("docs/prds/TB-06-blindness-guard.md", "18", "Bash: deny")], cov=C("designed", "Specified; a deny-all implementation would still pass the golden set until P0-2 is fixed."))
N("bi-indirect", "Indirect forms", "Relative, absolute, parent (../), quoted, glob (ev*/, **/evals), tilde and $VAR forms that could expand to a protected path.", kind="rule",
  files=[F("docs/prds/TB-06-blindness-guard.md", "18", "glob")], cov=C("designed", "Specified in the PRD with many diagnostic cases."))
N("bi-limits", "Known limits", "A permissions.deny rule applies to sub-agents and best-effort to Grep and Glob, but does not stop a shell command or script that reads the files without naming them. The sandbox is the OS-level backstop.", kind="limit",
  files=[F("docs/plans/2026-09-24-agent-capability-map.md", "15", "does **not** stop a shell command")],
  cov=C("gap", "An acknowledged residual hole, recorded in the design but with no mitigation built.", ["This build's own implementers are blind only by instruction until hooks exist (audit P0-5)"]))

# =================================================================================================== VERIFICATION ENGINE
N("verification-engine", "Verification engine (sf CLI)",
  "A small deterministic Python package behind the sf command: it classifies architectural doors, locks test baselines against reward hacking, runs a gated synthesis loop around the Claude CLI, and transpiles with a proved equivalence. About 2,000 lines.",
  kind="subsystem",
  design=[D("Bare-metal CLI over a framework", "A lightweight Python runner that shells out to the local claude CLI; sub-70 ms invariant checks.", "A heavier orchestration service")],
  files=[F("factory/cli.py", "237-293", "add_subparsers", "Four subcommands"), F("pyproject.toml", "29-31", "[project.scripts]"), F("README.md", "62-80", "sf audit")],
  cov=C("partial", "Code and tests exist and run here, but only 31 of 40 tests pass in a clean environment.",
        ["9 tests fail without the sibling unity repo: tests hard-code /Users/kaushal/... paths", "pyproject.toml pins unity-ir to file:///Users/kaushal/Projects/unity, so a clean install cannot resolve it", "CI does not run these tests"]),
  diagram=[
      "flowchart LR",
      "  sf-cli[\"sf CLI<br/>factory/cli.py\"] -->|\"sf audit\"| governance[\"Governance engine<br/>door classification\"]",
      "  sf-cli -->|\"sf verify\"| zero-trust[\"Zero-trust substrate<br/>test integrity\"]",
      "  sf-cli -->|\"sf run\"| synthesis[\"Synthesis engine<br/>gated patch loop\"]",
      "  sf-cli -->|\"sf transpile\"| transpiler[\"Transpiler<br/>Python to Go\"]",
      "  synthesis -->|\"gate 1\"| governance",
      "  synthesis -->|\"gate 2\"| zero-trust",
      "  synthesis -->|\"claude -p --restricted\"| claude-cli[\"Claude Code CLI<br/>external\"]",
      "  governance -->|\"semantic delta\"| unity-ir[\"unity-ir compiler<br/>external, optional\"]",
      "  transpiler -->|\"equivalence proof\"| unity-ir",
  ],
  children=["sf-cli", "governance", "zero-trust", "synthesis", "transpiler", "claude-cli", "unity-ir"])
N("sf-cli", "sf CLI", "Argparse entry point with four subcommands: audit, verify, run and transpile; installed as sf and as a backward-compatible factory alias.", kind="module",
  files=[F("factory/cli.py", "237-273", "add_subparsers"), F("pyproject.toml", "29-31", "sf = ")],
  cov=C("built", "Implemented with tests in tests/test_cli.py; two of its tests need the unity repo's example files."))
N("governance", "Governance engine", "Classifies a change as a one-way or two-way door from the semantic delta and source patterns (lock removal, purity loss, contract violation, public API, schema, auth boundary, symbol removal) and drafts an ADR.", kind="module",
  design=[D("Two door types with eight risk categories", "ONE_WAY means irreversible with high blast radius and requires debate and an ADR; TWO_WAY runs autonomously.", "A single severity score")],
  files=[F("factory/governance.py", "28-43", "ONE_WAY"), F("factory/governance.py", "214-222", "audit_source_pair")],
  cov=C("partial", "Works through Unity when it is installed and falls back to pattern checks when it is not.", ["Door tests that need the Unity compiler fail on a clean checkout"]))
N("zero-trust", "Zero-trust substrate", "Locks pre-existing tests by SHA-256 baseline manifest and parses the AST to catch reward hacking: dropped assertion counts, injected skip or xfail, and trivial assertions such as assert True.", kind="module",
  design=[D("Hash the tests, scan the AST, do not ask a model", "Reward hacking by an agent that writes both code and tests is caught structurally.", "LLM judging whether tests were weakened")],
  files=[F("factory/zero_trust.py", "73-120", "class BaselineHashGuard"), F("factory/zero_trust.py", "208-244", "class ZeroTrustGate")],
  cov=C("partial", "The hash and AST guard is implemented and its tests pass. The formal-proof half promised by ADR-0002 is not.",
        ["ZeroTrustGate accepts contract_violations but synthesis never supplies them", "z3, deal, crosshair and hypothesis are never imported by factory/"]))
N("transpiler", "Polyglot transpiler", "Synthesizes a cross-lingual anchor (for example Python to Go) and claims a certified zero semantic delta between source and target.", kind="module",
  files=[F("factory/transpiler.py", "65-80", "class PolyglotTranspiler")],
  cov=C("partial", "Implemented; all five of its tests fail in a clean environment because they need the Unity compiler and sibling example files."))
N("claude-cli", "Claude Code CLI", "The synthesis step shells out to claude -p with --restricted, which removes the built-in tools that run commands or code, so the call produces text only.", kind="external",
  files=[F("factory/synthesis.py", "151-166", "--restricted")],
  cov=C("external", "Verified against this machine's claude --help: --restricted exists."))
N("unity-ir", "Unity-IR compiler", "A sibling repository that lowers code to a canonical three-layer IR and computes semantic delta with Z3. Optional at runtime: the governance engine falls back to patterns when it is missing.", kind="external",
  files=[F("factory/governance.py", "20-26", "UNITY_AVAILABLE"), F("ROADMAP.md", "56-68", "unity")],
  cov=C("external", "Separate repository, pinned in pyproject.toml to a developer's absolute path."))

N("synthesis", "Synthesis engine", "Gathers context, asks the Claude CLI for a candidate patch, stages it atomically, and accepts it only if three deterministic gates pass; otherwise it rolls back and retries with the failure as feedback, up to three times.", kind="module",
  design=[D("Atomic staging with backups and rollback", "A rejected candidate leaves the tree exactly as it found it.", "Applying patches in place and fixing forward"),
          D("Deterministic gates, then self-repair", "Failure text from a gate, not model self-assessment, drives the next attempt.", "Asking the model if its patch is good")],
  files=[F("factory/synthesis.py", "136-150", "class SynthesisEngine"), F("factory/synthesis.py", "304-306", "max_retries")],
  cov=C("partial", "The loop is implemented with tests; one governance-rejection test needs Unity. The Claude call has a 600 s timeout and no cost accounting."),
  diagram=[
      "flowchart TD",
      "  syn-context[\"Gather context<br/>sources, Unity-IR, tests\"] --> syn-candidate[\"Candidate patch<br/>claude -p --restricted\"]",
      "  syn-candidate --> syn-stage[\"Stage atomically<br/>keep backups\"]",
      "  syn-stage --> syn-gate1{\"Gate 1<br/>one-way door?\"}",
      "  syn-gate1 -->|\"clear\"| syn-gate2{\"Gate 2<br/>tests weakened?\"}",
      "  syn-gate2 -->|\"clear\"| syn-gate3{\"Gate 3<br/>suite passes?\"}",
      "  syn-gate3 -->|\"pass\"| syn-receipt[\"Receipt<br/>files, iterations\"]",
      "  syn-gate1 -->|\"fail\"| syn-repair[\"Rollback and retry<br/>feedback from gate\"]",
      "  syn-gate2 -->|\"fail\"| syn-repair",
      "  syn-gate3 -->|\"fail\"| syn-repair",
      "  syn-repair -->|\"up to 3 attempts\"| syn-candidate",
  ],
  children=["syn-context", "syn-candidate", "syn-stage", "syn-gate1", "syn-gate2", "syn-gate3", "syn-repair", "syn-receipt"])
for sid, title, summ, fp, contains, lines, status, note in [
    ("syn-context", "Gather context", "Reads target source files, lowers them to Unity-IR where possible, and collects baseline test files and their hashes.", "factory/synthesis.py", "extract_repo_context", "168-176", "built", "Implemented."),
    ("syn-candidate", "Candidate patch", "Builds the prompt (spec, context, previous failure feedback) and calls the local claude CLI in restricted mode, so it returns text and takes no actions.", "factory/synthesis.py", "_call_claude_cli", "151-166", "built", "Implemented; a dry-run mode skips the call."),
    ("syn-stage", "Stage atomically", "Parses the response into file patches, records original contents as backups, then writes the new files.", "factory/synthesis.py", "backups[target_path]", "355-358", "built", "Implemented."),
    ("syn-gate1", "Gate 1: governance", "Compares each changed non-test source file with its original; any ONE_WAY risk rejects the candidate and rolls back with the risk descriptions as feedback.", "factory/synthesis.py", "Gate 1: Governance Matrix", "359-386", "partial", "Works; its test needs the Unity compiler to detect lock removal."),
    ("syn-gate2", "Gate 2: zero-trust", "Verifies the baseline manifest and original test contents: deleted, weakened or skipped assertions reject the candidate.", "factory/synthesis.py", "Gate 2: Epistemic Zero-Trust Gate", "388-403", "built", "Implemented; contract violations are never fed in."),
    ("syn-gate3", "Gate 3: run the tests", "Runs the project's test suite on the staged tree; failure feeds the last 1,500 characters of output back as feedback.", "factory/synthesis.py", "Gate 3: Test Suite Execution", "405-413", "built", "Implemented."),
    ("syn-repair", "Rollback and retry", "Atomically restores backups and loops with the gate's failure text; after max_retries (default 3) returns a failure result with the last feedback.", "factory/synthesis.py", "def _rollback", "447-455", "built", "Implemented."),
    ("syn-receipt", "Receipt", "On success returns modified files, iteration count and a generated receipt of what was done.", "factory/synthesis.py", "_generate_receipt", "477-495", "built", "Implemented."),
]:
    N(sid, title, summ, kind="step", files=[F(fp, lines, contains)], cov=C(status, note))

# =================================================================================================== EVALS GATE
N("evals-gate", "Evals and golden gate",
  "Evals are authored from published contracts before any implementer exists, then locked. 1,302 cases (129 golden must-pass, 1,173 diagnostic) all resolve to 'blocked' until something implements them; an independent audit found the golden gate not collectively exhaustive.",
  kind="subsystem",
  design=[D("A case written early resolves to blocked, never pass", "lib.need() imports the producer; if it is missing the case is blocked, so a skeleton cannot earn a green.", "Skipping cases until the feature exists"),
          D("Golden membership is locked in GOLDEN.json", "run.py requires the golden-tagged set to equal the list exactly; changing it is a reviewed baseline update.")],
  files=[F("evals/agents/README.md", "15-17", "Golden membership"), F("evals/agents/run.py", "30-50", "GOLDEN VERDICT")],
  cov=C("partial", "The suite is built and runs; its gate is not yet trustworthy.", ["Golden verdict is NOT GREEN by design until implementation, and MECE fails", "Eval results are gitignored (evals/agents/results/)"]),
  diagram=[
      "flowchart LR",
      "  contracts-in[\"Published contracts<br/>docs/contracts\"] -->|\"expectations quoted from\"| eval-cases[\"Eval cases<br/>129 golden, 1,173 diagnostic\"]",
      "  eval-cases -->|\"pytest + run.py\"| eval-runner[\"Runner and verdict<br/>blocked, pass, fail\"]",
      "  eval-cases -->|\"graded as MECE by\"| mece-audit[\"Independent MECE audit<br/>verdict: FAIL\"]",
      "  mece-audit -->|\"five blocking findings\"| golden-fix[\"Golden gate fixes<br/>not yet applied\"]",
      "  trigger-smoke[\"Skill trigger smoke checks<br/>docs/evals/triggers\"] -.->|\"separate, skill-level\"| eval-cases",
  ],
  children=["contracts-in", "eval-cases", "eval-runner", "mece-audit", "golden-fix", "trigger-smoke"])
N("contracts-in", "Published contracts", "Evals and implementers both depend on the contracts in docs/contracts and nothing else; expectations are quoted or paraphrased from them with the clause checked.", kind="input",
  files=[F("evals/agents/README.md", "13", "Expectations come only from the published contracts")], cov=C("built", "Published and used as the single source for expectations."))
N("eval-cases", "Eval cases", "pytest tests tagged with an id (TB05-G-001 golden or TB05-D-114 diagnostic), a tier, the tracer bullet and the requirement ids; fixture profiles base.yaml and alt.yaml vary project settings.", kind="artifact",
  files=[F("evals/agents/README.md", "5-9", "Case model"), F("evals/agents/GOLDEN.json", None, "TB01-G-001"), F("evals/agents/lib.py", "19-22", "def need")],
  cov=C("built", "1,302 cases exist across TB-01 to TB-14, with per-TB coverage notes.", ["All blocked: nothing under test is implemented"]))
N("eval-runner", "Runner and verdict", "run.py runs pytest, writes results/latest.json and prints counts per tier, per tracer bullet and per requirement; the golden verdict is green only if every golden case passes and the membership matches.", kind="tool",
  files=[F("evals/agents/run.py", "30-50", "GOLDEN VERDICT"), F("evals/agents/README.md", "19", "python evals/agents/run.py")],
  cov=C("built", "Runs; plain pytest does not collect evals/ (testpaths = tests)."))
N("trigger-smoke", "Trigger smoke checks", "A small checker that tests whether five skills' descriptions trigger on realistic prompts.", kind="tool",
  files=[F("docs/evals/triggers/trigger_check.py", None, "def run_one"), F("docs/evals/triggers/README.md", None, "trigger")],
  cov=C("partial", "Smoke-level only for five of the skills; not part of CI."))
N("golden-fix", "Golden gate fixes", "The remedial set from the audit: swap in cases that vary project settings, add an allowed-Bash case, add the full-suite-evidence case, protect .factory/ and .claude/, and make implementer blindness mechanical.", kind="todo",
  files=[F("docs/plans/2026-09-24-agent-layer-status.md", "9-15", "P0")],
  cov=C("gap", "Not applied: the last change to evals/ is the audit itself (2026-09-24) and the status note says to fix these before any implementer starts."))
N("mece-audit", "Independent MECE audit", "A read-only agent that did not author the cases graded the golden gate for mutual exclusivity and exhaustiveness. Verdict: FAIL. Mostly non-redundant (4 overlaps) but a shortcut implementation passes the whole golden set.", kind="audit",
  design=[D("The author of a gate does not grade it", "A separate agent checks the golden set against the requirements and the repository before implementers start.", "The eval author self-certifying coverage")],
  files=[F("evals/agents/audit/MECE-AUDIT.md", "9-16", "MECE: FAIL")],
  cov=C("built", "The audit is complete and its findings are specific."),
  diagram=[
      "flowchart LR",
      "  audit-verdict[\"Verdict: MECE FAIL\"] --> p0-generality[\"P0-1 Generality<br/>not gated at golden\"]",
      "  audit-verdict --> p0-bash[\"P0-2 No allowed-Bash case\"]",
      "  audit-verdict --> p0-evidence[\"P0-3 No full-suite evidence case\"]",
      "  audit-verdict --> p0-tamper[\"P0-4 Implement can edit<br/>its own gates\"]",
      "  audit-verdict --> p0-blind[\"P0-5 Blind by instruction only\"]",
  ],
  children=["audit-verdict", "p0-generality", "p0-bash", "p0-evidence", "p0-tamper", "p0-blind"])
N("audit-verdict", "Audit verdict", "MECE: FAIL. Run result at audit time: 1,302 cases, 129 golden blocked, 1,173 diagnostic blocked, 0 failed, no membership problem, golden verdict NOT GREEN.", kind="result",
  files=[F("evals/agents/audit/MECE-AUDIT.md", "5-16", "MECE: FAIL")], cov=C("built", "Recorded with the exact run output."))
for pid, title, summ, ln, contains in [
    ("p0-generality", "P0-1 Generality not gated", "Every golden case for TB-05, 06, 08 and the TB-14 stream uses the base fixture only, so hard-coded paths and a hard-coded deploy command pass. This violates the owner's generality requirement.", "121-125", "P0-1"),
    ("p0-bash", "P0-2 No allowed-Bash case", "Because no golden case allows an implement Bash command, 'deny all implement Bash' passes the gate while making the agent unable to build or test.", "126", "P0-2"),
    ("p0-evidence", "P0-3 No full-suite evidence case", "R-15's clause 'no evidence of a full-suite run' has no golden case; every golden stop-gate case removes the checks.", "127", "P0-3"),
    ("p0-tamper", "P0-4 Implement can edit its own gates", "Through Bash the implement agent can rewrite .factory/profile.yaml, .factory/baseline.json or the stop-gate counter, and Write/Edit .claude/settings.json, defeating blindness and the stop gate.", "128-138", "P0-4"),
    ("p0-blind", "P0-5 Blind by instruction only", "This build's own implementers are barred from evals/ only by PRD text, with no profile and no hook, which contradicts 'hooks enforce, prompts advise'.", "139", "P0-5"),
]:
    N(pid, title, summ, kind="finding", files=[F("evals/agents/audit/MECE-AUDIT.md", ln, contains)],
      cov=C("gap", "Open: listed as 'fix before any implementer starts'; no later commit addresses it."))

# =================================================================================================== ROUTING
N("routing", "Jev routing (shadow)",
  "A typed-decision client that asks the Jev model to choose among options (for example a model tier), applies probability bands (act, flag, human) and logs the result next to the actual choice. It never changes routing.",
  kind="subsystem",
  design=[D("Shadow mode only", "Thresholds are placeholders until our own labelled past tasks set them; decisions are logged beside the real choice to build that data.", "Letting the classifier route from day one"),
          D("Deterministic rules first, a typed classifier second", "Rules that are cheap and exact run before any model call; a Jev fault is recorded, never raised.", "Model-only routing")],
  files=[F("factory/routing/jev_client.py", "152-165", "def route"), F("factory/routing/jev-policy.yaml", "1-12", "shadow mode only")],
  cov=C("partial", "Client, policy and recorded-response tests exist.", ["Not wired into anything (promotion ledger)", "Endpoint is an alpha API; thresholds are placeholders", "Requires an OpenRouter key at run time"]),
  diagram=[
      "flowchart LR",
      "  jev-policy[\"Policy file<br/>jev-policy.yaml\"] -->|\"decisions, bands, pinned model\"| jev-request[\"Build request<br/>build_request\"]",
      "  jev-request -->|\"rules first, else call\"| jev-transport[\"Transport<br/>OpenRouter alpha endpoint\"]",
      "  jev-transport -->|\"probabilities\"| jev-parse[\"Parse answer<br/>parse_answer\"]",
      "  jev-parse -->|\"top, margin\"| jev-band[\"Band<br/>act, flag, human\"]",
      "  jev-band --> jev-log[\"Log record<br/>shadow only\"]",
  ],
  children=["jev-policy", "jev-request", "jev-transport", "jev-parse", "jev-band", "jev-log"])
for jid, title, summ, fp, lines, contains, status, note in [
    ("jev-policy", "Policy file", "Versioned YAML: pinned model typesafe/jev-1.13 (never a floating alias), endpoint, 800 ms timeout, no retries, probability bands and per-decision rules. Wording is behaviour, so it changes through review.", "factory/routing/jev-policy.yaml", "1-30", "policy_version", "partial", "Thresholds are placeholders."),
    ("jev-request", "Build request", "Builds the decision request from the policy and the task state fields, trying deterministic rules before any network call.", "factory/routing/jev_client.py", "73-105", "def build_request", "built", "Covered by recorded-response tests."),
    ("jev-transport", "Transport", "A default HTTP transport with an injectable replacement so tests run without the network; a fault is recorded in the result, not raised.", "factory/routing/jev_client.py", "107-128", "_default_transport", "partial", "Live endpoint use is unverified here; the transport is an alpha API."),
    ("jev-parse", "Parse answer", "Turns the response into option probabilities and checks them against the allowed options.", "factory/routing/jev_client.py", "130-143", "def parse_answer", "built", "Covered by tests."),
    ("jev-band", "Band", "Maps top probability and margin to act (0.90 and 0.50), flag (0.70 and 0.20) or human; below flag asks a person or uses the deterministic rule.", "factory/routing/jev_client.py", "144-151", "def _band", "partial", "Band numbers are placeholders."),
    ("jev-log", "Log record", "Builds the record logged next to the actual choice, with a state digest, so routing quality can be measured later.", "factory/routing/jev_client.py", "196-211", "def log_record", "partial", "Nothing consumes the log yet."),
]:
    N(jid, title, summ, kind="step", files=[F(fp, lines, contains)], cov=C(status, note))

# =================================================================================================== OPS
N("ops-runtime", "Session ops and dashboards",
  "The harness around a long unattended run: keep-awake, overnight mode, disk and memory hygiene, owner briefings and per-project ops dashboards. It lives in the global skills directory and local state files, not in this repository.",
  kind="harness",
  design=[D("Never stop on a blocker", "Record what it waits on and move to the next independent requirement; stop only for an operator ceiling such as budget or an irreversible action.", "Halting the run and waiting for a human")],
  files=[X(SF, "64-84", "Start away mode with the run")],
  cov=C("external", "Operational, in daily use, and outside this repository.", ["Not reproducible from the repo alone: the scripts and state files are unversioned here"]),
  diagram=[
      "flowchart LR",
      "  away-mode[\"Away mode<br/>keep-awake, remote control\"] -->|\"session stays reachable\"| overnight[\"Overnight mode<br/>good-night, good-morning\"]",
      "  overnight -->|\"journal each event\"| session-state[\"Session state<br/>.claude/state.md, ledgers\"]",
      "  ops-hygiene[\"Hygiene scan<br/>disk, memory\"] -->|\"before fan-out\"| overnight",
      "  session-state -->|\"summarised for\"| owner-briefing[\"Owner briefing<br/>progress-briefing\"]",
      "  ops-dashboards[\"Ops dashboards<br/>per project\"] -.->|\"fed at stage 10\"| owner-briefing",
  ],
  children=["away-mode", "overnight", "session-state", "ops-hygiene", "owner-briefing", "ops-dashboards"])
N("away-mode", "Away mode", "Scripts that keep a session running and reachable from a phone through Remote Control; /sf starts it indefinitely.", kind="harness",
  files=[X("~/.claude/skills/away-mode/scripts/start.sh"), X(SF, "64-77", "Start away mode with the run")], cov=C("external", "Global skill scripts."))
N("overnight", "Overnight mode", "good-night opens a run that never stalls (blockers are broken with research and experiments, one-way doors queued only if owner-gated); good-morning closes it and walks the owner through queued decisions.", kind="harness",
  files=[X("~/.claude/skills/good-night/scripts/overnight.sh"), X(SF, "78-84", "Overnight mode")], cov=C("external", "Global skill scripts."))
N("session-state", "Session state", "Working notes, a snapshot, a sub-agent ledger and a run registry kept under .claude/ (the run registry is a local process list and is not cited here) so a resumed or compacted session can recover.", kind="state",
  files=[F(".gitignore", None, "runtime state of the bounded test runner", "Only .sf/ is ignored here; .claude/ is not tracked at all, so it is described but not cited")],
  cov=C("gap", "Valuable and untracked: if the checkout is lost the history of owner decisions is lost with it.", [".claude/ is not in git in this repo"]))
N("ops-hygiene", "Hygiene scan", "hygiene.sh scans disk and memory before parallel fan-out and after merges; it never deletes branches, dirty worktrees, keys or evidence.", kind="harness",
  files=[X("~/.claude/skills/sf/hygiene/hygiene.sh"), X(SF, "253-263", "Hygiene")], cov=C("external", "Installed with the sf skill."))
N("owner-briefing", "Owner briefing", "progress-briefing keeps one private three-tab page per project: status with analogies, the research and experiment story, and an open-question survey.", kind="skill",
  files=[X(SF, "238-252", "progress-briefing")], cov=C("external", "Global skill; pages are private artifacts."))
N("ops-dashboards", "Ops dashboards", "Each project grows a dashboard of evals, error traces, LLM traces, logs and gate status as its slices land (ops-dashboard-design).", kind="skill",
  files=[X(SF, "204-220", "ops dashboard")], cov=C("external", "Defined by a global skill and built inside each product project."))


# =================================================================================================== REFRESH 2026-10-19 (after the sf toolchain build)
def setcov(i, status, note, gaps=None):
    nodes[i]["coverage"] = C(status, note, gaps)

def addfiles(i, *fs):
    nodes[i].setdefault("files", [])
    nodes[i]["files"] = list(fs) + nodes[i]["files"]

EV = "Acceptance cases for this slice all pass (evals/agents); the blind implementer never saw them."
setcov("factory", "partial", "The method, the sf CLI and tool groups, the agent layer (roles, generator, settings emitter, seven hooks, ledger, stage graph, walking skeleton), slices, intake, structure, contracts/solver, QA loop and dashboard are implemented and tested: 4,017 unit tests and 1,497 eval cases pass, golden gate 141 of 141. Live behaviour inside a real Claude Code session and cross-vendor review are not verified.",
       ["Hooks are mechanical only in projects where sf has generated the project settings; exercised through the command line and simulated event streams, not a live session (clarification C-34 is still open)",
        "The Bash and blindness guards are command-text guards and cannot be complete; the OS sandbox is the backstop (see the residual-risk sections of docs/hooks/bash_guard.md and blindness_guard.md)",
        "One acceptance case is open by design pending a decision: TB06-D-035 (docs/adr/ADR-0004)",
        "The repository has a build-loop profile now (docs/development-workflow.md) but the factory is not yet run through its own loop for every change"])
nodes["factory"]["detail"] = ["The factory is three things layered together. The method (the /sf build loop, its skills and the new sf toolchain) runs today. A deterministic engine (the sf CLI) enforces test integrity, one-way-door detection and, through factory/verify, honest solver verdicts on a small pure subset. An agent layer (seven roles, eight hooks, generator, settings emitter, ledger, walking skeleton) is implemented and acceptance-tested but not yet exercised in a live Claude Code session.",
                              "Click any stacked box to open the diagram inside it. The Coverage tab lists what is built, partial, only designed, outside the repo, or a gap, with reasons."]
nodes["factory"]["diagram"] += ['  build-loop -->|"stage commands, gates, records"| sf-toolchain["sf toolchain<br/>slices, intake, verify, QA, dashboard"]']
nodes["factory"]["children"] += ["sf-toolchain"]

# ---- agent layer: built
setcov("agent-layer", "partial", "All 14 tracer bullets are implemented by blind implementers and pass their acceptance cases after QA iterations; one diagnostic case is open pending ADR-0004.",
       ["TB06-D-035 open (ADR-0004); everything else green, golden 141 of 141", "Not exercised in a real Claude Code session (C-34); command-text guards have documented residual risk"])
nodes["agent-layer"]["detail"] = ["Seven roles, eight hook ids, a profile loader, a stage graph, an agent file generator, a settings emitter, a tamper-evident ticket ledger and an end-to-end simulation with a shadow routing log exist as code, with 1,000+ acceptance cases behind them. Implementers were mechanically blind to the evals (sparse worktrees without evals/), and an independent runner graded each slice; QA feedback and the clarifications C-36 to C-39 record what the iterations found."]
code = {
 "profile-loader": ("factory/agents/profile.py", "def load_profile"), "stage-graph": ("factory/agents/graph.py", "class GraphError"),
 "agent-generator": ("factory/agents/generate.py", "HOOK_REGISTRATION"), "ticket-ledger": ("factory/ledger.py", "def verify"),
 "settings-emitter": ("factory/agents/settings.py", "def emit_settings"), "walking-skeleton": ("factory/agents/simulate.py", "def run_events"),
 "hook-core": ("factory/hooks/core.py", "class Payload"), "path-guard": ("factory/hooks/path_guard.py", "def decide"),
 "secrets-guard": ("factory/hooks/secrets_guard.py", "def decide"), "bash-guard": ("factory/hooks/bash_guard.py", "def decide"),
 "stop-gate": ("factory/hooks/stop_gate.py", "def decide"), "subagent-validators": ("factory/hooks/subagent_stop.py", "def decide"),
 "blindness-guard": ("factory/hooks/blindness_guard.py", "def decide"), "role-specs": ("factory/agents/roles.py", "def load_roles"),
}
for i, (pth, cont) in code.items():
    addfiles(i, F(pth, None, cont, "Implementation"))
for i in ["profile-loader", "stage-graph", "agent-generator", "ticket-ledger", "settings-emitter", "walking-skeleton", "hook-core", "path-guard", "secrets-guard", "bash-guard", "stop-gate", "subagent-validators", "role-specs"]:
    setcov(i, "built", "Implemented from the published contract by a blind implementer. " + EV)
nodes["walking-skeleton"]["coverage"]["gaps"] = ["Whether a sub-agent's frontmatter Stop hook runs as SubagentStop is unverified (C-34); the manual live rehearsal in docs/hooks/e2e.md is not yet done"]
setcov("path-guard", "built", "Implemented; hardened after automated security review (clarification C-38: awk, sed, git abbreviations, MultiEdit and NotebookEdit). " + EV, ["Command-text parsing cannot be complete: the OS sandbox is the backstop (docs/hooks/path_guard.md)"])
setcov("secrets-guard", "built", "Implemented; hardened after security review (C-39: whole-value placeholders, bounded scanning, de-quoted Bash scan). " + EV, ["A key split by shell quoting is caught only when the value has a known key shape"])
setcov("bash-guard", "built", "Implemented; wrapper options are parsed from tables and anything unclassifiable fails closed; su, runuser, doas, ssh and similar wrappers are never unwrapped (always ask or deny). " + EV, ["Not a complete defence: shell-style git aliases, xargs and find -exec chains, variables set outside the command; the OS sandbox is the backstop"])
setcov("blindness-guard", "partial", "Implemented and tightened over several QA and security iterations; all but one acceptance case pass.", ["TB06-D-035 open: Glob through a symlink (docs/adr/ADR-0004)", "Run-time-built file names, interpreter internals and other checkouts remain documented residual gaps"])
for i in ["bi-paths", "bi-direct", "bi-bash", "bi-indirect"]:
    setcov(i, "built", "Implemented in factory/hooks/blindness_guard.py; unit tests and acceptance cases pass.")
setcov("bi-limits", "gap", "An acknowledged residual hole with no mitigation in the guard: the sandbox is the backstop.", ["File names built at run time, awk/editor internals, git diff of revisions, other checkouts are documented as accepted residual risk"])
setcov("hooks", "built", "Eight hook ids are implemented behind one registry; every guard has acceptance cases; security-review hardening recorded as clarifications C-36 to C-39.")
for r in ["role-orchestrator","role-research","role-design","role-audit","role-implement","role-test","role-review"]:
    setcov(r, "partial", "Role data is loaded and validated and a generated agent file can be emitted from it; model choices remain proposals to measure.")
setcov("build-waves", "built", "All five waves executed: 14 slices implemented, reviewed by an independent runner, with QA iterations recorded in the merge history.")
setcov("role-specs", "built", "Seven role files load and validate; generated agents follow them.")

# ---- verification engine
setcov("verification-engine", "built", "The sf engine is implemented and tested with Unity installed (4,017 tests pass in the bounded full run); governance now fails closed and the CLI exposes the new tool groups.",
       ["The semantic verifier is Unity, which an earlier audit found ledger-specific; this was not re-run here. The new honest solver gate for a pure subset is factory/verify (sf contracts)", "tests marked requires_unity need the sibling Unity repo; CI runs the rest", "One intermittent failure of the transpiler parity test was seen once and not explained"])
setcov("governance", "built", "A missing or crashing verifier now returns GATE FAILED (exit 3), never a harmless classification; pattern-only analysis is labelled UNVERIFIED.", ["Semantic classification still depends on Unity being installed"])
setcov("zero-trust", "partial", "The hash and AST guard is implemented; the formal-proof half promised by ADR-0002 now lives in factory/verify (z3) rather than here.", ["ZeroTrustGate still accepts contract_violations that synthesis never supplies", "deal and CrossHair are not used by production code"])
setcov("sf-cli", "built", "audit, verify, run, transpile plus the tool groups slice, structure, contracts, intake, ops and qa.")
setcov("transpiler", "partial", "Implemented; tests pass with Unity installed; one intermittent failure seen once.", ["Needs the Unity compiler"])

# ---- evals
setcov("evals-gate", "built", "1,498 cases (golden 141): 1,496 pass, 1 open diagnostic (TB06-D-035), 1 library self-check blocked by design. The golden gate is GREEN. The five audit P0 findings are closed; C-38 and C-39 added cases.",
       ["TB06-D-035 is open pending ADR-0004", "Results are gitignored (evals/agents/results/)"])
for p in ["p0-generality","p0-bash","p0-evidence","p0-tamper","p0-blind"]:
    setcov(p, "built", "Closed: cases swapped or added and, for P0-4 and P0-5, clarification C-36 and scripts/implementer-worktree.sh; the mechanical blindness is in use.")
setcov("golden-fix", "built", "Applied (golden 129 to 139, then 141 with C-38/C-39) with the baseline note in evals/agents/README.md.")
setcov("mece-audit", "built", "The audit's blocking findings are closed; a fresh MECE audit of the new golden set has not been run.", ["Re-audit the 141-case golden set independently"])

# ---- skills, docs
setcov("skills-library", "partial", "13 skills are versioned in skills/ with scripts/skills_sync.py; live copies in ~/.claude/skills are identical or being adopted; minesweeper and a few others are still live-only.", ["Install into ~/.claude/skills is opt-in (--adopt) and not yet run for the changed skills", "minesweeper (14 MB) is not versioned here"])
setcov("promotions-ledger", "partial", "Updated with the missing skills by slice B; still a manual ledger.")
setcov("skills-ci", "partial", "CI validates skill frontmatter, runs the eval template and the unit tests that do not need Unity.", ["evals/agents is not run in CI", "Unity-dependent tests are not run in CI"])
setcov("governance-docs", "partial", "Decisions are well documented and extended (ADR-0004 proposed; binding clarifications C-36 to C-39); the roadmap is stale.", ["ROADMAP.md still has no mention of the agent layer or the sf toolchain"])
setcov("adrs", "partial", "ADR-0001 to 0003 accepted; ADR-0004 (blindness guard and symlinks) is proposed and needs a decision.", ["deal and CrossHair from ADR-0002 are still unused by production code; the z3 solver gate in factory/verify covers a small pure subset"])
setcov("ops-dashboards", "partial", "A factory dashboard exists: historical snapshots per commit from git plus separate runtime telemetry (factory/ops, ops/shell). It has not been deployed.", ["Per-product dashboards reuse the same bundle; not yet applied to a product", "Not hosted"])

# ---- new level-1 group: the sf toolchain
N("sf-toolchain", "sf toolchain",
  "The commands that make the owner's flow checkable: intake gate, slice format, structural scan, contract verification, the QA loop, the dashboard, resource limits and the blind-worktree script. Each is a module under factory/ exposed as `sf <group>`.",
  kind="subsystem",
  design=[D("Deterministic gates over model judgement where a check can be mechanical", "Hash chains, ledger coverage, solver verdicts and role-checked ticks cannot be argued with; the judgement stays in review.", "More prose in the skills")],
  files=[F("factory/cli.py", None, "TOOL_GROUPS = {", "Tool groups wired into sf"), F("docs/sf-flow.md", None, "flowchart", "The flow with current versus planned behaviour")],
  cov=C("built", "Implemented and tested; used by this very build (QA loop concepts, slices, bounded tests, dashboard bundle).", ["Adversarial acceptance of verify and structure is in progress", "Not yet run on a product project"]),
  diagram=[
    "flowchart LR",
    "  intake-gate[\"Intake gate<br/>ledger, sweep record\"] -->|\"verified rows\"| slice-format[\"Slice format<br/>UX stories first\"]",
    "  slice-format -->|\"affected area\"| structure-scan[\"Structure scan<br/>ast, labelled edges\"]",
    "  structure-scan -->|\"symbols, callers\"| contract-verify[\"Contracts and solver<br/>honest verdicts\"]",
    "  contract-verify -->|\"frozen criteria\"| blind-worktree[\"Blind worktree<br/>evals/ absent\"]",
    "  blind-worktree --> qa-loop[\"QA loop<br/>bounded retries\"]",
    "  qa-loop -->|\"verified tasks\"| ops-dashboard[\"Dashboard<br/>snapshots + telemetry\"]",
    "  resource-limits[\"Resource limits<br/>bounded tests\"] -.->|\"wraps every test run\"| qa-loop",
  ],
  children=["intake-gate", "slice-format", "structure-scan", "contract-verify", "blind-worktree", "qa-loop", "ops-dashboard", "resource-limits"])
N("intake-gate", "Intake gate", "Ledger with one row per source line and a trust column, a recorded minesweeper sweep per source hash, a gate that fails when the sweep did not run, an open Critical has no sign-off or a High has no disposition, plus checks for research seeds and experiment records.", kind="module",
  files=[F("factory/intake/ledger.py", None, "def check"), F("factory/intake/sweep.py", None, "def build_record"), F("docs/intake-format.md", None, "ledger")],
  cov=C("partial", "Implemented and tested (61 tests). The sweep and the value-extraction pass are model procedure; only recording and gating are deterministic.", ["Minesweeper's locator format could not be confirmed; every integer in a locator is read as a source line", "The register schema is copied from the live skill and can drift"]))
N("slice-format", "Slice format", "docs/slices/<id>/ with UX stories first, public acceptance criteria with IDs, a two-state task list (implemented by the implementer, verified only by QA), a criteria lock and an additive-only amendment log; checker, triage and a completion gate.", kind="module",
  files=[F("factory/slices/cli.py", None, "def cmd_done"), F("docs/slice-format.md", None, "OpenSpec")],
  cov=C("built", "Implemented and tested (28 tests). OpenSpec's own validator accepted the fixture layout (its tool was run in a throwaway directory with telemetry off); compatibility beyond that is not claimed.", ["The chain cannot catch deleting the newest entries together with the head; git is the backstop", "A hand-edited [x] in tasks.md is not blocked, though `done` still needs a QA chain entry"]))
N("structure-scan", "Structure scan", "stdlib ast extraction of symbols, imports and calls with stable ids and spans; edges labelled resolved, syntactic or unresolved with a reason; bounded scope; symbol diff by normalised AST hash; output becomes a dolls model that the checker verifies.", kind="module",
  files=[F("factory/structure/extract.py", None, "def make_source"), F("factory/structure/diff.py", None, "def diff_extractions")],
  cov=C("built", "Implemented and tested (34 tests); run on this repo's own factory/ package.", ["Python only; never a complete call graph", "Independent adversarial acceptance is in progress"]))
N("contract-verify", "Contracts and solver", "Independent contracts for pure int/bool functions with IDs, frame conditions and assumptions; contract review before code; z3 verification of the real implementation with PROVED, COUNTEREXAMPLE (replayed on the real function), UNSUPPORTED (routed), UNKNOWN and TIMEOUT; fails closed; counterexamples become regression tests.", kind="module",
  design=[D("Replay every counterexample on the real function", "If z3 and Python disagree the translator is wrong; that is MODEL_MISMATCH and fails the gate.", "Trusting the solver model")],
  files=[F("factory/verify/solve.py", None, "class Verdict"), F("factory/verify/gate.py", None, "def run_gate"), F("docs/verification-ir.md", None, "floor")],
  cov=C("built", "Implemented and tested (152 tests plus a differential test of the z3 model against real Python); demonstrated end to end on a labelled minimal fixture (examples/dogfood-limits).", ["Supported subset only: no loops, calls, floats or containers; everything else must route to tests", "int64 is modelled as checked overflow, not wraparound", "Generated regression tests replay an absolute source path", "Independent adversarial acceptance is in progress"]))
N("blind-worktree", "Blind worktree", "scripts/implementer-worktree.sh creates a worktree with protected paths absent (sparse checkout), a local Read deny rule, and cleans up if any step fails.", kind="script",
  files=[F("scripts/implementer-worktree.sh", None, "sparse-checkout")],
  cov=C("built", "Tested (7 tests); used for every blind implementer in this build.", ["The object database still holds the protected files: a shell command could read them from git; the hooks and sandbox are the backstop"]))
N("qa-loop", "QA loop", "State per slice, a failure signature, a bounded retry policy with measured escalation, behavioural feedback guarded by a leak check against protected material, regression proposals, and a reviewer hand-off; QA alone marks tasks verified.", kind="module",
  files=[F("factory/qa/decide.py", None, "def decide("), F("factory/qa/leak.py", None, "def leak_check"), F("docs/qa-loop.md", None, "signature")],
  cov=C("built", "Implemented and tested (79 tests including a scripted fake-implementer simulation); policy defaults are configurable and tuned from recorded attempts.", ["Not yet run against real agent sessions", "Tamper detection misses someone who rewrites the logs and the state together"]))
N("ops-dashboard", "Dashboard", "factory.ops bundles historical development artifacts per commit from the git object database into content-addressed blobs, collects runtime telemetry separately with measured / not-measured labels, and a static shell offers a commit selector and tabs.", kind="module",
  files=[F("factory/ops/bundle.py", None, "def put_blob"), F("factory/ops/runtime.py", None, "def collect_runtime"), F("ops/shell/index.html", None, "snapshot")],
  cov=C("partial", "Built and tested (27 + 8 tests); verified in a real browser against this repository's history.", ["Not deployed", "Runtime telemetry covers only what its config declares; most figures are 'not measured' without configuration", "Langfuse and CI figures are reported only when configured"]))
N("resource-limits", "Resource limits", "Repo-root conftest.py caps address space and per-test time; scripts/bounded-pytest.sh adds a wall-clock kill, a lock and a limits log. Added after a 19 GB runaway test killed a session.", kind="harness",
  files=[F("conftest.py", None, "RLIMIT_AS"), F("scripts/bounded-pytest.sh", None, "prlimit")],
  cov=C("built", "Tested (4 tests); every test run since the incident used it.", ["A tripped limit is a failure, not a pass; a limit that is too tight would need tuning"]))


nodes["sf-toolchain"]["children"] += ["native-install", "human-stop"]
nodes["sf-toolchain"]["diagram"] += ['  resource-limits -.-> native-install["Native install<br/>agents, hooks, Sonnet pin"]', '  native-install -->|"doctor executes the hooks"| human-stop["Human stop<br/>sf hitl"]']
N("native-install", "Native install", "sf install writes the generated agents, settings-level hooks with absolute verified commands, the Sonnet-only pin and a manifest into a project; doctor executes every hook command (a hook that cannot run fails open); uninstall restores from backups.", kind="module",
  files=[F("factory/install/core.py", None, "ENV_PIN"), F("factory/install/doctor.py", None, "def check_roles"), F("docs/native-install.md", None, "fail")],
  cov=C("built", "Implemented and unit-tested (35 tests); verified in real headless Claude Code sessions: skills, agents and hooks resolve, hooks block in subagents, the pin overrides an inherited default (docs/native-verification/2026-10-19/REPORT.md).", ["Interactive (non -p) use not exercised", "The user-level default model (Opus) is deliberately unchanged; sessions elsewhere without --model sonnet or a project pin still inherit it", "A hook parser guard is not OS isolation"]))
N("human-stop", "Human stop", "sf hitl request/status/release: a hash-chained stop ledger under .factory/stops that sf slice done and sf qa next obey; release needs a person at a terminal and the release command is a one-way door.", kind="module",
  files=[F("factory/hitl/store.py", None, "def release")],
  cov=C("built", "Implemented and unit-tested (23+ tests); obeyed in a real session: slice done refused (exit 5), release refused, stop still open.", ["Friction, not proof: a role with full Bash could allocate a terminal; no out-of-band secret"]))
import os, re as _re


# =================================================================================================== REFRESH 2026-10-20 (lsf, eli12-docs, editor links, ops events, eight roles, flow)
def setsum(i, text):
    nodes[i]["summary"] = text

def addchildren(i, *ids, diagram=()):
    nodes[i]["children"] = list(nodes[i]["children"]) + list(ids)
    nodes[i]["diagram"] = list(nodes[i]["diagram"]) + list(diagram)

EV_DOC = "Test and eval counts are recorded in docs/sf-flow.md ('Evidence base') and docs/adr/ADR-0005-sonnet-only-roles-and-qa-role.md section 3; this explorer cites them instead of restating them."
ADR5 = "docs/adr/ADR-0005-sonnet-only-roles-and-qa-role.md"
NV19 = "docs/native-verification/2026-10-19/REPORT.md"
NV20 = "docs/native-verification/2026-10-20/REPORT.md"

# ---- stale prose in existing nodes (item 7)
setcov("factory", "partial", "The method, the sf CLI and tool groups, the eight-role agent layer (generator, settings emitter, eight hook ids, ledger, stage graph, walking skeleton), slices, intake, structure, contracts/solver, the QA loop, the ops dashboard and the lite factory (lsf) are implemented and tested. " + EV_DOC + " Real headless sessions verified the hooks, the qa role and the self-updating dashboard (" + NV19 + ", " + NV20 + "); the intake gate, a full QA loop with real agents, reviewer amendments and interactive use have not run in a real session.",
       ["Hooks are mechanical only in projects where sf has generated the project settings; verified through headless sessions and simulated event streams, not an interactive session (clarification C-34 is still open)",
        "The Bash and blindness guards are command-text guards and cannot be complete; the OS sandbox is the backstop (see the residual-risk sections of docs/hooks/bash_guard.md and blindness_guard.md)",
        "One acceptance case is open by design pending a decision: TB06-D-035 (docs/adr/ADR-0004)",
        "Not yet run in a real session: intake gate, the full QA loop, reviewer amendments, the lsf skill driven by Claude Code (" + NV20 + " 'Not covered')"])
nodes["factory"]["detail"] = ["The factory is layered. The method (the /sf build loop, its skills and the sf toolchain) runs today. A deterministic engine (the sf CLI) enforces test integrity, one-way-door detection and, through factory/verify, honest solver verdicts on a small pure subset. An agent layer (eight roles, eight hook ids, generator, settings emitter, ledger, walking skeleton) is implemented and acceptance-tested. A lite factory (lsf) runs the same flow in one hour on a laptop with a phase clock, human checkpoints and an offline dashboard.",
                              "Click any stacked box to open the diagram inside it. The Coverage tab lists what is built, partial, only designed, outside the repo, or a gap, with reasons."]
setsum("factory", "A set of skills, rules, deterministic gates and eight Sonnet-pinned agent roles that turn an AI coding assistant from a 'vibe-coder' into a disciplined engineer: requirements are verified before use, tests come before code, the implementer is blind to the tests, QA supervises and verification is deterministic and independent.")
nodes["factory"]["files"] += [F("docs/sf-flow.md", None, "The /sf flow as implemented", "The flow, its evidence base and what is unverified"),
                              F(ADR5, None, "## 2. Decision", "The latest accepted decision")]
addchildren("factory", "lsf", diagram=['  build-loop -->|"same flow, one hour, laptop"| lsf["Lite factory (lsf)<br/>phase clock, checkpoints, dashboard"]'])

setcov("build-profile", "built", "This repository now has a profile at docs/development-workflow.md (source requirements, ADRs, tests, the blind eval path, test commands). The skill's own default location, .claude/build-loop.md, is untracked and is not cited here.",
       ["The installed sf skill is the only copy of the loop text; this repo's history does not version it"])
nodes["build-profile"]["files"] = [X(SF, "85-94", "Load the project profile first"), F("docs/development-workflow.md", None, "Build-loop profile: software-factory", "The profile for this repository")]
setcov("stage-6-implement-blind", "partial", "Blindness is mechanical where sf install generated the settings: blindness_guard plus scripts/implementer-worktree.sh (sparse checkout without evals/). Verified in headless real sessions; the interactive case and ADR-0004's open symlink case are not.",
       ["TB06-D-035 open (ADR-0004); command-text guards have documented residual risk", "Interactive (non -p) sessions not exercised"])
setcov("stage-7-separate-runner", "partial", "Defined in the installed /sf skill and now carried by the qa role and sf qa; the qa role's path limits were verified in a real headless session, a full QA loop with a real implementer and QA agent has not run.",
       ["Full QA loop with real agents not yet run (" + NV20 + " 'Not covered')"])
setcov("stage-8-review", "partial", "Defined in the installed /sf skill; the review role now carries implementation-review, code-review, mermaid-nesting-dolls, minesweeper and doc-sync, and sf slice amend --role reviewer exists. Reviewer amendments have not run in a real session.",
       ["Reviewer amendments not yet exercised by a real reviewer agent"])
setcov("intake", "partial", "The skills exist outside this repo and the deterministic half (ledger, sweep record, gate) is implemented as sf intake; the sweep itself is a model procedure and the gate has not run in a real session.",
       ["The only in-repo document about the sweep (docs/plans/2026-10-14-minesweeper-skill-proposal.md) still says 'Nothing is built yet'", "Intake gate not yet run in a real session"])

setcov("skills-library", "partial", "15 skills are versioned under skills/ (axiomatic-spec, contract-verify, doc-sync, eli12-docs, eval-designer, implementation-review, intake-gate, lsf, mermaid-nesting-dolls, ops-dashboard-design, orchestration, prd-writer, qa-supervisor, sf, structure-scan) with scripts/skills_sync.py; the external ones are pinned in docs/external-skills.json and checked by sf install doctor.",
       ["minesweeper (14 MB) and a few others are still live-only in ~/.claude/skills", "Install into ~/.claude/skills is opt-in and is not done by this explorer"])
setcov("governance-docs", "partial", "Five ADRs (0001 to 0005), the methodology, the requirements register, contracts with binding clarifications, plans and reviews. Some summary documents lag the code.",
       ["ROADMAP.md still has no mention of the agent layer or the sf toolchain", "ADR-0003 still reads 'Seven agent definitions' and 'not built yet'; ADR-0005 supersedes it in count and records the edits"])
setsum("governance-docs", "The written authority the rest of the factory obeys: five ADRs, the methodology every agent must follow, the requirements register, binding contracts and clarifications, the plans and the review reports.")
nodes["governance-docs"]["diagram"] = [l.replace("ADRs 0001 to 0003", "ADRs 0001 to 0005") for l in nodes["governance-docs"]["diagram"]]
setsum("plans", "The Austin-ready plan, the original seven-agents design (now eight roles, see ADR-0005), the capability map, the skills consolidation, the minesweeper proposal and a token-saving research note.")
setsum("adrs", "ADR-0001 chooses the Unity-IR dual-plane substrate, ADR-0002 the zero-trust verification substrate, ADR-0003 agent roles above skills, ADR-0004 (proposed) the blindness guard and symlinks, ADR-0005 Sonnet for every role plus a qa role and the test and eval edits that followed.")
nodes["adrs"]["design"] += [D("Sonnet for every role, plus a qa role (ADR-0005)", "The owner's flow asks for one model across roles and QA agents that supervise and re-initiate; the loader, installer and doctor reject any other model unless explicitly allowed.", "Per-role model tiers (Opus to author, Haiku to run) proposed in the 2026-09-24 design")]
nodes["adrs"]["files"] += [F(ADR5, None, "## 2. Decision", "Accepted 2026-10-20; section 4 lists every test and eval edit"),
                           F("docs/adr/ADR-0004-blindness-guard-glob-through-symlinks.md", None, "Status", "Proposed")]
setcov("adrs", "partial", "ADR-0001 to 0003 and ADR-0005 are accepted; ADR-0004 (blindness guard and symlinks) is proposed and needs a decision. ADR-0005 supersedes ADR-0003's role count (seven to eight) and model proposals.",
       ["deal and CrossHair from ADR-0002 are still unused by production code; the z3 solver gate in factory/verify covers a small pure subset", "ADR-0003's own text still says roles and hooks are not built"])

# verification engine and evals: drop the stale size and count claims
setsum("verification-engine", "A small deterministic Python package behind the sf command: it classifies architectural doors, locks test baselines against reward hacking, runs a gated synthesis loop around the Claude CLI, transpiles with a proved equivalence and, through the tool groups, carries the intake, slice, structure, contract, QA, hitl, install and ops commands.")
setcov("verification-engine", "built", "Implemented and tested; governance fails closed and the CLI exposes the tool groups. " + EV_DOC,
       ["The semantic verifier is Unity, which an earlier audit found ledger-specific; this was not re-run. The honest solver gate for a pure subset is factory/verify (sf contracts)", "tests marked requires_unity need the sibling Unity repo", "One intermittent failure of the transpiler parity test was seen once and not explained"])
setcov("evals-gate", "built", "The agent-layer eval suite (golden and diagnostic tiers) runs and its golden gate is the pass criterion; one diagnostic case, TB06-D-035, is open on purpose pending ADR-0004. " + EV_DOC,
       ["TB06-D-035 is open pending ADR-0004", "Results are gitignored (evals/agents/results/)", "Cases were edited for the eight-role shape under " + ADR5 + " section 4 (no deletions or loosening, per that ADR)"])
setsum("evals-gate", "Evals are authored from published contracts before any implementer exists, then locked. Golden cases must pass, diagnostic cases are reported; an independent audit found the first golden gate not collectively exhaustive and its blocking findings were closed. Counts live in docs/sf-flow.md and ADR-0005.")
nodes["evals-gate"]["diagram"] = [l.replace("Eval cases<br/>129 golden, 1,173 diagnostic", "Eval cases<br/>golden and diagnostic tiers") for l in nodes["evals-gate"]["diagram"]]
setcov("eval-cases", "built", "Cases exist across TB-01 to TB-14 and the SFN slices (evals/native), with per-TB coverage notes; counts are in docs/sf-flow.md.", ["TB06-D-035 is open on purpose (ADR-0004)"])
setsum("audit-verdict", "MECE: FAIL at audit time (2026-09-24): 1,302 cases, 129 golden blocked, 1,173 diagnostic blocked, 0 failed, golden verdict NOT GREEN. Historical: the findings were closed afterwards.")

# sf toolchain children: cite test files, not counts
setcov("intake-gate", "partial", "Implemented and tested (tests/test_intake.py, test_intake_seeds.py, test_intake_experiments.py). The sweep and the value-extraction pass are model procedure; only recording and gating are deterministic. The gate has not run in a real session.",
       ["Minesweeper's locator format could not be confirmed; every integer in a locator is read as a source line", "The register schema is copied from the live skill and can drift", "Not run in a real session (" + NV20 + ")"])
setcov("slice-format", "built", "Implemented and tested (tests/test_slices.py). OpenSpec's own validator accepted the fixture layout (run in a throwaway directory with telemetry off); compatibility beyond that is not claimed.", nodes["slice-format"]["coverage"]["gaps"])
setcov("structure-scan", "built", "Implemented and tested (tests/test_structure.py, test_structure_hardening.py); run on this repo's own factory/ package. Adversarial acceptance report: docs/acceptance/verify-structure-report.md.", ["Python only; never a complete call graph"])
setcov("contract-verify", "built", "Implemented and tested (tests/test_verify_*.py and tests/acceptance/verify, including a differential test of the z3 model against real Python); demonstrated end to end on a labelled minimal fixture (examples/dogfood-limits). Adversarial acceptance report: docs/acceptance/verify-structure-report.md.",
       ["Supported subset only: no loops, calls, floats or containers; everything else must route to tests", "int64 is modelled as checked overflow, not wraparound", "Generated regression tests replay an absolute source path"])
setcov("blind-worktree", "built", "Tested (tests/test_implementer_worktree.py); used for the blind implementers of this build.", nodes["blind-worktree"]["coverage"]["gaps"])
setcov("qa-loop", "partial", "Implemented and tested (tests/test_qa_*.py, including a scripted fake-implementer simulation, tests/test_qa_sim.py). Policy defaults are configurable. The qa role's write limits were verified in a real headless session; the loop has not run with a real implementer and a real QA agent.",
       ["Full QA loop with real agents not yet run (" + NV20 + " 'Not covered')", "Tamper detection misses someone who rewrites the logs and the state together"])
setcov("resource-limits", "built", "Tested (tests/test_resource_limits.py); the test runs for this explorer refresh used scripts/bounded-pytest.sh.", nodes["resource-limits"]["coverage"]["gaps"])
setcov("human-stop", "built", "Implemented and unit-tested (tests/test_hitl.py); obeyed in a real session: slice done refused (exit 5), release refused, stop still open (" + NV19 + ").", nodes["human-stop"]["coverage"]["gaps"])
setcov("sf-toolchain", "partial", "Implemented and tested; used by this very build. The deterministic parts are built; the intake gate and the full QA loop have not run in a real session.",
       ["Intake gate, full QA loop and reviewer amendments not yet run in a real session", "Not yet applied to a product project"])

# ---- eight roles, Sonnet (item 6)
nodes["role-specs"]["title"] = "Eight role specs"
setsum("role-specs", "Orchestrator, Research, Design, Audit, Implement, QA, Test and Review, each with a model (always sonnet), tools, skills, MCP servers and hooks, loaded and validated from factory/agents/roles/*.yaml.")
nodes["role-specs"]["design"] = [D("Narrow tools, one model for every role", "Every subagent inherits the plugin and skill listing, so each role lists at most 20 tools. ADR-0005 fixes Sonnet for all roles; load_roles, the installer and sf install doctor reject any other model unless it is explicitly allowed.", "Per-role tiers (Opus to author, Haiku to run) from the 2026-09-24 design")]
nodes["role-specs"]["files"] = [F("factory/agents/roles.py", None, "def load_roles", "Loader; rejects a non-sonnet model unless allowed"), F("factory/agents/roles/qa.yaml", None, "writes: qa_paths", "The role added by ADR-0005"), F("docs/hooks/roles.md", None, "## Writes class `qa_paths`", "Role data, qa_paths and the Sonnet rule"), F("docs/contracts/roles-and-generation.md", "5-7", "RoleSpec")]
setcov("role-specs", "built", "Eight role files load and validate; generated agents follow them. Real headless sessions resolved all eight generated agents (" + NV20 + ").")
addchildren("role-specs", "role-qa", diagram=[
    '  role-implement -->|"supervised by"| role-qa["QA<br/>runs suites, feedback, no code"]',
    '  role-qa -->|"runs the protected suites via"| role-test',
    '  role-qa -.->|"loops back to"| role-implement'])
for rid, (yml, wr) in {"role-orchestrator": ("orchestrator", "none"), "role-research": ("research", "research_dir"), "role-design": ("design", "design_dirs"), "role-audit": ("audit", "audit_dir"), "role-implement": ("implement", "app"), "role-test": ("test", "eval_paths"), "role-review": ("review", "none")}.items():
    n = nodes[rid]
    n["detail"] = ["Model: sonnet (ADR-0005; every role file declares it). Writes class: %s." % wr, n["detail"][1]]
    n["files"] = [F("factory/agents/roles/%s.yaml" % yml, None, "model: sonnet", "Role data")] + n["files"]
    setcov(rid, "built", "Implemented as role data and loaded by factory/agents/roles.py; a generated agent file is emitted from it and resolved in real headless sessions.")
nodes["role-review"]["summary"] = "Independent read of the diff, traces and passes; drift against requirements. Read-only; verdict only. Carries implementation-review, code-review, mermaid-nesting-dolls, minesweeper and doc-sync."
nodes["role-review"]["files"] = [F("factory/agents/roles/review.yaml", None, "mermaid-nesting-dolls", "The reviewer's skills")] + [f for f in nodes["role-review"]["files"] if f["path"].startswith("docs")]
setcov("role-review", "partial", "Role data and skills are implemented; the reviewer has not amended a slice in a real session.", ["Cross-vendor review is not configured: every role is Sonnet by owner decision (ADR-0005)", "Reviewer amendments (sf slice amend --role reviewer) not yet exercised by a real reviewer agent"])
nodes["role-design"]["summary"] = "Brief to PRD (prd-writer), axioms and contracts, one-way-door check, ADR. Runs behind gates G0, G1 and G2."
N("role-qa", "QA", "Supervises the implementer: runs the protected suites, writes behavioural feedback in criterion terms, records attempts, proposes regression cases and marks tasks verified. Never edits application code or writes test source.", kind="role",
  detail=["Model: sonnet (ADR-0005). Writes class qa_paths: only **/qa-notes.md, **/qa-feedback/** and .sf/qa/**. Bash is full so it can run suites, but path_guard denies it every command bash_guard flags.", "Skills: qa-supervisor and superpowers:verification-before-completion."],
  design=[D("A QA role between implement and test, enforced by path_guard", "QA must run suites and write feedback without being able to edit code or test source; a writes class plus the hook, not a prompt, enforces it.", "Folding QA into the Test role, which freezes evals")],
  files=[F("factory/agents/roles/qa.yaml", None, "writes: qa_paths", "Role data"), F("factory/hooks/path_guard.py", None, "if writes == \"qa_paths\"", "Enforcement (C-41.2)"), F("docs/hooks/roles.md", None, "## Writes class `qa_paths`", "Contract")],
  cov=C("built", "Implemented; in a real headless session the generated qa agent could write its QA notes and was blocked from writing src/hack.py and from git add -A by the real hooks (" + NV20 + ", S7).",
        ["A full QA loop with a real implementer and a real QA agent has not run"]))

setsum("agent-layer", "Eight agent definitions (orchestrator, research, design, audit, implement, qa, test, review), all pinned to Sonnet, with tool allowlists and hooks, generated from a project profile so nothing names a specific project. Implemented in factory/agents and factory/hooks and acceptance-tested.")
setcov("agent-layer", "partial", "All 14 tracer bullets are implemented and pass their acceptance cases; ADR-0005 added the qa role, the Sonnet-only rule and the doctor role-skill and external-pin checks. One diagnostic case is open pending ADR-0004. Counts: docs/sf-flow.md.",
       ["TB06-D-035 open (ADR-0004)", "Not exercised in an interactive session (C-34); command-text guards have documented residual risk", "Each sub-agent stop is recorded twice (subagent_stop and ledger_audit both emit), noted in " + NV20])
nodes["agent-layer"]["detail"] = ["Eight roles, eight hook ids, a profile loader, a stage graph (default order orchestrate, research, design, audit, implement, qa, test, review; loops qa to implement and review to implement), an agent file generator, a settings emitter, a tamper-evident ticket ledger and an end-to-end simulation with a shadow routing log exist as code. Implementers were mechanically blind to the evals (sparse worktrees without evals/), and an independent runner graded each slice; clarifications C-36 to C-41 record what the iterations found. docs/adr/ADR-0005 lists the test and eval edits for the eight-role shape."]
nodes["agent-layer"]["files"] += [F("factory/agents/default_graph.yaml", None, "loops:", "Stage order and the two loop-backs"), F(ADR5, None, "## 2. Decision", "Eight roles, Sonnet only")]
nodes["agent-layer"]["diagram"] = [l.replace("Seven role specs", "Eight role specs") for l in nodes["agent-layer"]["diagram"]]

setsum("hooks", "Eight hook ids share one core: a payload parser and decision type, then guards for paths (including the qa_paths class), blindness, secrets, Bash and stop, the sub-agent stop validator, the ledger audit and the session-start summary. Guards fail closed on malformed input.")
setcov("hooks", "built", "Eight hook ids are implemented behind one registry (factory/agents/generate.py HOOK_REGISTRATION); every guard has acceptance cases; security-review hardening recorded as clarifications C-36 to C-39 and the qa_paths class as C-41.")
nodes["hooks"]["files"] += [F("factory/agents/generate.py", None, "HOOK_REGISTRATION", "Hook ids, events and matchers")]
addchildren("hooks", "ledger-audit", "session-start", diagram=[
    '  hook-core -->|"SubagentStop: audit trail"| ledger-audit["Ledger audit<br/>ticket Audit Trail + event"]',
    '  hook-core -->|"SessionStart"| session-start["Session start<br/>ticket summary"]'])
N("ledger-audit", "Ledger audit", "At SubagentStop appends an entry (agent type, id, the first 200 characters of the last message, secret shapes removed) to the current ticket's ledger; it always allows. Its recording step also leaves a subagent-stop stage event for the dashboard.", kind="TB-11",
  files=[F("factory/hooks/ledger_audit.py", None, "def decide", "Always allows"), F("factory/hooks/ledger_audit.py", None, "emit(cfg.project_root, \"subagent-stop\"", "The ops event")],
  cov=C("built", "Implemented; the event emission was seen in a real session.", ["Double counting with subagent_stop: both emit one subagent-stop event per stop"]))
N("session-start", "Session start", "At SessionStart gives a new session the current ticket's ledger summary, or 'No ticket is active.'; it always allows.", kind="TB-11",
  files=[F("factory/hooks/session_start.py", None, "NO_TICKET", "Summary or the no-ticket line")], cov=C("built", "Implemented with acceptance cases."))
nodes["subagent-validators"]["files"] += [F("factory/hooks/subagent_stop.py", None, "def record", "Leaves a subagent-stop stage event")]
setsum("path-guard", "Each role may write only its own folders (Research under research/, Design under docs/prd, spec and adr, Audit under docs/audit, Review nowhere, QA only qa-notes and qa-feedback and .sf/qa through the qa_paths class). Only Implement writes application code.")
nodes["path-guard"]["files"] += [F("factory/hooks/path_guard.py", None, "C-41.2: the only paths a `qa_paths` role may write", "The qa_paths globs; configuration may override them"), F("factory/hooks/path_guard.py", None, "C-41.3: qa gets the implement-style git restrictions", "Bash limits for qa")]
nodes["path-guard"]["coverage"]["note"] += " The qa_paths class (C-41.2) was added by ADR-0005."

# ---- native install: doctor checks and pin-external
nodes["native-install"]["summary"] = "sf install writes the generated agents, settings-level hooks with absolute verified commands, the Sonnet-only pin and a manifest into a project, and rejects any non-Sonnet role model unless --allow-model; doctor executes every hook command and also checks that each role's skills resolve and that external skills match their pins; pin-external rewrites the pins."
nodes["native-install"]["design"] = [D("Doctor fails when a hook cannot run, a role skill does not resolve or an external pin is missing", "A hook that cannot run fails open, so the check executes the command; unresolved skills and unpinned externals would silently change behaviour.", "Trusting that files exist")]
nodes["native-install"]["files"] += [F("factory/install/doctor.py", None, "def check_external", "External skills versus docs/external-skills.json"), F("factory/install/core.py", None, "def pin_external", "Rewrites the pins from the installed copies; exit 2 without --yes"), F("docs/external-skills.json", None, "\"skills\"", "The pins")]
setcov("native-install", "built", "Implemented and unit-tested (tests/test_install.py, test_install_native.py); verified in real headless Claude Code sessions: skills (including eli12-docs and lsf) and all eight generated agents resolve, hooks block in subagents, the pin overrides an inherited default (" + NV19 + ", " + NV20 + ").",
       ["Interactive (non -p) use not exercised", "The user-level default model is deliberately unchanged; sessions elsewhere without --model sonnet or a project pin still inherit it", "A hook parser guard is not OS isolation", "doctor WARNs (not FAILs) when an external skill changed since it was pinned"])

# ---- lsf (item 1)
LSF = "skills/lsf/scripts/lsf.py"
DASH = "skills/lsf/assets/dashboard.html"
N("lsf", "Lite factory (lsf)",
  "/sf made fast: the owner's flow (brief, minesweep, research, experiments, tracer PRDs, evals, blind build, QA, mechanistic review, docs and drift) run in about an hour on a laptop with Python 3.9+ and git. A phase clock, telemetry, human checkpoints and an offline dashboard make every step visible.",
  kind="subsystem",
  detail=["One CLI (skills/lsf/scripts/lsf.py, standard library only) writes a .lsf folder in the project: a profile, an events log, a phase log and a hash-chained stop ledger. The dashboard (skills/lsf/assets/dashboard.html) is served from 127.0.0.1 by the same script and reads the project's own files, so nothing is fabricated for it.",
          "Phase ids are an alias map onto the /sf stages, so events from both tools read the same (see the flow node under the build loop)."],
  design=[D("A separate lite tool, not a mode of sf", "It must install on a Mac with only python3 and git (no virtualenv, no solver) and be demonstrable live in an hour.", "Running the full sf toolchain with its z3 and Unity dependencies"),
          D("Human checkpoints are a procedure with an audit trail, not proof of identity", "The release route needs a token the agent is told never to read; the ledger is cross-checked against the event log. The skill says plainly that no software check can prove who clicked.", "Claiming the stop cannot be bypassed")],
  files=[F("skills/lsf/SKILL.md", None, "# lsf: the lite software factory", "The skill: flow, per-phase procedure, rules"), F(LSF, None, "def main", "Entry point"), F("docs/prds/SFN-06-lsf-lite.md", None, "# SFN-06", "The PRD")],
  cov=C("partial", "Implemented and tested here: tests/lsf ran with one failure (test_parity_with_factory_collectors). It has not been driven by Claude Code in a real session (" + NV20 + " 'Not covered').",
        ["tests/lsf/test_hooks_collect.py::test_parity_with_factory_collectors fails on this checkout: lsf's experiments collector omits kind: experiment and returns the whole resolved.json instead of the four fields factory/ops/collect.py returns",
         "The lsf skill has not been driven by Claude Code in a real session",
         "Human stop release is friction with an audit trail, not proof (docs/reviews/2026-10-20-lsf-review.md)"]),
  diagram=[
      "flowchart LR",
      "  lsf-install[\"Installer<br/>install.sh, bundle\"] -->|\"skill + lsf wrapper\"| lsf-cli[\"lsf CLI<br/>init, phase, event, budget, cost, doctor\"]",
      "  lsf-cli -->|\"phase start/end, events\"| lsf-clock[\"Phase clock and budget<br/>11 phases, 3 groups\"]",
      "  lsf-cli -->|\"hitl request/status\"| lsf-stops[\"Stop ledger and human checkpoints\"]",
      "  lsf-stops -->|\"open stop: phase start exits 3\"| lsf-clock",
      "  lsf-hooks[\"Hooks and telemetry<br/>SubagentStop, Stop, commit, guard\"] -->|\"events.jsonl\"| lsf-clock",
      "  lsf-cli -->|\"serve\"| lsf-server[\"Dashboard server<br/>127.0.0.1, routes\"]",
      "  lsf-server -->|\"/api/state, /api/file, /api/at\"| lsf-ui[\"Dashboard UI<br/>ten tabs\"]",
      "  lsf-ui -->|\"Approve: POST /api/hitl/release\"| lsf-stops",
  ],
  children=["lsf-cli", "lsf-clock", "lsf-stops", "lsf-hooks", "lsf-server", "lsf-ui", "lsf-install"])
N("lsf-cli", "lsf CLI", "One argparse program with the commands init, phase, event, hitl, status, budget, serve, bundle, hooks, doctor and cost. Every command takes --root; exit codes are 0 ok, 1 a check failed, 2 usage, 3 refused by a human stop.", kind="module",
  files=[F(LSF, None, "def build_parser", "All commands"), F(LSF, None, "def cmd_init", "Writes .lsf/profile.json"), F(LSF, None, "def cmd_phase", "start and end; start refuses under an open stop"), F(LSF, None, "def cmd_doctor", "python, git, repository, port and the self-check"), F(LSF, None, "def cmd_bundle", "Prints which dashboard tabs have data")],
  cov=C("built", "Implemented; tests/lsf/test_core.py passes here."))
N("lsf-clock", "Phase clock and budget", "Eleven phases in three groups (align 0-intake to 6-decide, build 7-implement and 8-qa, review 9-review and 10-docs) with default weights 60 / 20 / 20 of the session minutes. budget compares planned with actual minutes per group and subtracts time spent waiting on a human stop.", kind="module",
  design=[D("Waiting on a human is not charged to the work", "A checkpoint can sit open for minutes; counting it would make every group look over budget.", "Wall-clock phase time only")],
  files=[F(LSF, None, "PHASES = [", "Phase ids and groups"), F(LSF, None, "SF_ALIAS = {", "lsf phase to /sf stage"), F(LSF, None, "DEFAULT_WEIGHTS", "60 / 20 / 20"), F(LSF, None, "def budget_data", "Planned versus actual, minus waiting"), F(LSF, None, "def wait_intervals", "Time under an open stop")],
  cov=C("built", "Implemented; the clock can be overridden with LSF_NOW for rehearsals and tests (documented in SKILL.md).", ["Actual minutes are 'under (not measured)' until phases have been started and ended"]))
N("lsf-stops", "Stop ledger and human checkpoints", "A hash-chained ledger under .lsf/stops with a head file: hitl request opens a named stop, ending an alignment phase opens <phase>-review automatically (the default; the profile can change it), hitl release records who and how (dashboard, cli-tty or cli-nontty). The ledger is cross-checked against the event log, and repair quarantines a failed ledger and rebuilds its valid prefix.", kind="module",
  design=[D("Release is a human act with a recorded channel", "Agents must never run release or repair; --strict-hitl refuses them without a real terminal; the guard hook denies them in Bash.", "A boolean approved flag an agent could set")],
  files=[F(LSF, None, "def hitl_open", "Opens a stop"), F(LSF, None, "def hitl_release", "Records the release and its channel"), F(LSF, None, "def hitl_repair", "Quarantine and rebuild"), F(LSF, None, "def cross_check", "Ledger versus events.jsonl"), F(LSF, None, "def require_tty_if_strict", "--strict-hitl")],
  cov=C("built", "Implemented; tests/lsf/test_core.py and test_review_fixes.py pass here.", ["Friction, not proof: the unkeyed chain and head file can be forged by anything that can write .lsf; the adversarial review lists the residual cases (docs/reviews/2026-10-20-lsf-review.md)"]))
N("lsf-server", "Dashboard server and routes", "A ThreadingHTTPServer bound to 127.0.0.1 only. GET / serves the dashboard with a restrictive Content-Security-Policy, GET /api/state the whole state, GET /api/file a repository file (path-checked, size-capped), GET /api/at?sha= the historical tabs at a commit, and POST /api/hitl/release (the only write) needs the per-run token in X-LSF-Token. Host and Origin must be loopback.", kind="module",
  files=[F(LSF, None, "def make_handler", "Handler with every route"), F(LSF, None, "def cmd_serve", "Prints the URL with #token= once"), F(LSF, None, "def read_repo_file", "Path and size checks for /api/file"), F(LSF, None, "def resolve_sha", "Used by /api/at")],
  cov=C("built", "Implemented; tests/lsf/test_serve.py passes here.", ["The agent must never run serve or read the token: that is procedure, not enforcement"]))
N("lsf-ui", "Dashboard UI tabs", "One offline page with ten tabs: Now, Telemetry, Research, Experiments, ADRs, PRD, Architecture, Docs, Evals & bugs and Git. The tabs read the collectors (research, experiments, adrs, bug_log, prd_journeys, architecture, git, docs) and a commit selector shows the historical tabs at a past commit while Now and Telemetry stay live. File references open the editor through the inlined editor-links function.", kind="module",
  files=[F(DASH, None, "var TABS=", "The ten tabs"), F(DASH, None, "function renderNow", "Now tab: clock, stops, Approve button"), F(DASH, None, "function renderTelemetry", "Telemetry tab"), F(DASH, None, "function renderArch", "Architecture tab (the explorer in an iframe)"), F(DASH, None, "function renderDocs", "Docs tab (reads docs/eli12/index.json)"), F(LSF, None, "COLLECTORS = [", "Collectors behind the tabs"), F(LSF, None, "def c_experiments", "Experiments and resolved.json")],
  cov=C("partial", "Implemented; tests/lsf/test_dashboard.py passes here. The experiments collector disagrees with factory/ops (parity test fails).", ["lsf's experiments rows lack kind: experiment and carry the whole resolved.json", "Architecture and Docs tabs show 'not available' unless docs/explorer/*.model.json and docs/eli12/index.json exist; they are not faked"]))
N("lsf-hooks", "Hooks and telemetry", "hooks install prints a diff of settings and --apply writes four hooks: SubagentStop and Stop (events), PostToolUse on Bash (git commit events) and a PreToolUse guard that denies hitl release, hitl repair, the release route and writes to .lsf/stops. Events are redacted and truncated; hooks write only into a project that already has .lsf.", kind="module",
  files=[F(LSF, None, "def hooks_config", "The four hooks"), F(LSF, None, "def cmd_hook", "Always exits 0 except the guard's denial"), F(LSF, None, "def guard_reason", "What the guard denies"), F(LSF, None, "def emit_event", "Telemetry write; LSF_EVENTS=off disables"), F(LSF, None, "def redact", "Secret shapes removed"), F(LSF, None, "def cmd_hooks", "print, install, uninstall")],
  cov=C("partial", "Implemented; tests/lsf/test_hooks_collect.py passes except the collector parity test. Hooks are opt-in (--apply) and have not been exercised in a real Claude Code session.", ["The guard is friction, not proof (SKILL.md)", "Not run in a real session"]))
N("lsf-install", "Installer and bundle", "install.sh copies the skill to ~/.claude/skills/lsf and writes an lsf wrapper in ~/.local/bin; running it twice changes nothing and a different older copy is moved to skills-backups, never inside the skills folder. scripts/make-lsf-bundle.sh zips lsf, eli12-docs and mermaid-nesting-dolls with an install-bundle.sh for a machine with only python3 and git.", kind="script",
  files=[F("skills/lsf/install.sh", None, "WRAP=$BIN/lsf", "Wrapper and idempotence"), F("skills/lsf/install.sh", None, "BKDIR=$SKILLS/../skills-backups", "Backup outside the skills folder"), F("scripts/make-lsf-bundle.sh", None, "for s in lsf eli12-docs mermaid-nesting-dolls", "What the bundle holds")],
  cov=C("partial", "install.sh is tested (tests/lsf/test_install_skill.py passes here). make-lsf-bundle.sh has no test of its own.", ["The bundle script was not run in this refresh", "Mac behaviour is described in SKILL.md but was verified on Linux only"]))

# ---- docs tools: eli12-docs and the explorer with editor links (items 2, 3)
N("skills-docs", "Docs tools", "eli12-docs writes and checks plain-English module docs; mermaid-nesting-dolls builds this explorer and opens its files in the editor.", kind="skills",
  cov=C("built", "Both tools are implemented and tested; see the children."),
  diagram=["flowchart LR",
           "  eli12-docs[\"ELI12 docs<br/>eli12.py scaffold, check, index\"] -->|\"index.json maps each file to its page\"| dolls-explorer[\"Explorer and editor links<br/>nesting_dolls.py\"]"],
  children=["eli12-docs", "dolls-explorer"])
addchildren("skills-library", "skills-docs", diagram=['  skills-ship -->|"documented by"| skills-docs["Docs tools<br/>eli12-docs, explorer"]'])
E12 = "skills/eli12-docs/scripts/eli12.py"
N("eli12-docs", "ELI12 docs", "A script that creates, refreshes and checks one Markdown page per Python module under docs/eli12/ in a fixed format: what it does, what it expects, what it gives back, who uses it, what it depends on. It computes the who-uses-who lines from the code and leaves TODO for the words only a person can write.", kind="skill",
  design=[D("The tool computes facts, a person writes meaning", "Signatures, callers and callees must not be guessed; the sig fingerprint and the Used by / Depends on lists are computed, and the check fails when they drift.", "A model rewriting the docs on every change")],
  files=[F("skills/eli12-docs/SKILL.md", None, "## The format", "The page format and rules"), F(E12, None, "def main", "scaffold, check, index"), F("docs/prds/SFN-07-eli12-docs.md", None, "# SFN-07", "The PRD")],
  cov=C("built", "Implemented; tests/test_eli12.py passes here. lsf ships an identical copy of the script (tests compare them).", ["Only Python modules are covered", "Whether the sentences are plain enough for a 12-year-old is a human judgement the check cannot make (it checks length, labels, jargon list)"]),
  diagram=["flowchart LR",
           "  eli12-format[\"Page format<br/>docs/eli12/MODULE.md\"] -->|\"template for\"| eli12-scaffold[\"scaffold<br/>creates or refreshes\"]",
           "  eli12-scaffold -->|\"pages with TODO\"| eli12-check[\"check<br/>finding codes\"]",
           "  eli12-scaffold --> eli12-index[\"index<br/>INDEX.md + index.json\"]"],
  children=["eli12-format", "eli12-scaffold", "eli12-check", "eli12-index"])
N("eli12-format", "Page format", "Line one is the .py path; then one sentence; then per public class or function (methods as Class.method) the labelled lines What it does, Expects, Gives back, Used by, Depends on and an optional Watch out, in that order, with a sig comment. Jargon words need a GLOSSARY entry.", kind="rule",
  files=[F("skills/eli12-docs/SKILL.md", None, "## The format", "Example page"), F(E12, None, "LABELS = [", "Label order"), F(E12, None, "def parse_doc", "Parser of a page")],
  cov=C("built", "Implemented and enforced by check."))
N("eli12-scaffold", "scaffold", "Creates or refreshes a page: on an existing page it only refreshes sig, Used by and Depends on and adds missing sections, so written sentences are never overwritten. Calls it cannot pin to one project symbol are listed with (maybe).", kind="command",
  files=[F(E12, None, "def scaffold_module", "Whole page"), F(E12, None, "def scaffold_entry", "One entry; keeps old sentences"), F(E12, None, "class Project", "Computes callers and callees")],
  cov=C("built", "Implemented.", ["Unresolved calls are only marked (maybe); a person must check them"]))
N("eli12-check", "check and finding codes", "Exit 0 clean, 1 findings, 2 usage. Each finding is path:line: code: message with a code from missing-entry, orphan-entry, stale-signature, stale-dependencies, todo, format, too-long, bad-param, jargon and unparseable. --changed GITREF limits it to changed modules plus modules whose lists mention them.", kind="command",
  files=[F(E12, None, "def run_check", "Runs the checks"), F(E12, None, "\"stale-signature\"", "Signature drift"), F(E12, None, "\"stale-dependencies\"", "Used by / Depends on drift"), F(E12, None, "\"bad-param\"", "Parameter line shape"), F(E12, None, "def changed_files", "--changed GITREF")],
  cov=C("built", "Implemented; the todo, format and jargon codes are listed in SKILL.md and produced inside check_doc and check_entry."))
N("eli12-index", "index", "Writes docs/eli12/INDEX.md and docs/eli12/index.json (module path to page path) so the explorer and the dashboards can link each file to its page; scaffold refreshes index.json too.", kind="command",
  files=[F(E12, None, "def build_index", "Builds the mapping"), F(E12, None, "def write_index", "Writes both files")],
  cov=C("built", "Implemented.", ["docs/eli12/ does not exist in this repository yet, so the lsf Docs tab reports 'not available' here"]))

ND = "skills/mermaid-nesting-dolls/scripts/nesting_dolls.py"
EL = "skills/mermaid-nesting-dolls/assets/editor-links.js"
N("dolls-explorer", "Explorer and editor links", "The nesting-dolls builder turns a model.json into this one-file explorer. Each file in a node's panel is a link that opens the editor at the first line of its range, with a Copy path button; editor and checkout root are set at build time (--workspace-root, --editor) or per view (?editor=&root=).", kind="skill",
  design=[D("One pure link builder, inlined in every surface", "assets/editor-links.js is the single source; its text between the begin/end markers is copied into the viewer template, the ops shell and the lsf dashboard, and a check fails if a copy drifts.", "Each surface writing its own link code")],
  files=[F("skills/mermaid-nesting-dolls/SKILL.md", None, "## Opening files in your editor", "Usage"), F(EL, None, "function editorUrl", "The pure function"), F("docs/prds/SFN-08-editor-links.md", None, "# SFN-08", "The PRD")],
  cov=C("built", "Implemented; tests/test_editor_links.py passes here and the committed explorer was rebuilt and checked with --assets in this refresh.", ["The committed HTML has no workspace root, so it shows Copy path only until ?editor=&root= or a rebuild with --workspace-root is used", "Opening the editor from the page was not clicked in this refresh (no desktop editor registered on this host)"]),
  diagram=["flowchart LR",
           "  editor-links[\"editor-links.js<br/>editorUrl(editor, root, path, line)\"] -->|\"inlined between markers\"| editor-copies[\"Inlined copies<br/>viewer, ops shell, lsf dashboard\"]",
           "  dolls-options[\"Build options<br/>--workspace-root, --editor, ?editor=&root=\"] -->|\"workspace in the model\"| editor-copies",
           "  editor-copies -->|\"check --assets\"| asset-check[\"Drift check<br/>two copies\"]"],
  children=["editor-links", "editor-copies", "dolls-options", "asset-check"])
N("editor-links", "editor-links.js", "A dependency-free ES5 function editorUrl(editor, root, relPath, line) for vscode, cursor, windsurf, zed, idea, sublime and textmate. It returns null for an absolute or .. path, a backslash, a NUL, a scheme prefix or a non-absolute root, and percent-encodes each path segment.", kind="module",
  files=[F(EL, None, "function editorUrl", "Builder"), F(EL, None, "function validRel", "Path safety")],
  cov=C("built", "Implemented; tests/test_editor_links.py exercises it."))
N("editor-copies", "Inlined copies", "The function text between /* editor-links:begin */ and /* editor-links:end */ appears in the viewer template, ops/shell/index.html and skills/lsf/assets/dashboard.html, and skills/lsf/assets/editor-links.js is a copy of the source.", kind="module",
  files=[F("skills/mermaid-nesting-dolls/assets/template.html", None, "editor-links:begin", "Viewer copy"), F("ops/shell/index.html", None, "editor-links:begin", "Ops shell copy"), F(DASH, None, "editor-links:begin", "lsf dashboard copy"), F("skills/lsf/assets/editor-links.js", None, "editor-links:begin", "lsf asset copy")],
  cov=C("built", "All four copies are covered by tests (tests/lsf/test_dashboard.py, evals/native/sfn06/test_static.py)."))
N("dolls-options", "Build options and view overrides", "build and check accept --workspace-root DIR and --editor NAME, stored as model.workspace and validated (absolute root, known editor or none). In the browser ?editor= and ?root= override the model and an invalid root is ignored.", kind="module",
  files=[F(ND, None, "--workspace-root", "Build and check options"), F(ND, None, "def validate_workspace", "Validation"), F("skills/mermaid-nesting-dolls/assets/template.html", None, "ed=w.editor||\"none\"", "View-time override")],
  cov=C("built", "Implemented."))
N("asset-check", "Drift check (--assets)", "check --assets fails if the inlined copy in the viewer template or in ops/shell/index.html differs from assets/editor-links.js. The two lsf copies are not covered by this command; tests cover them.", kind="module",
  files=[F(ND, None, "def check_assets", "The comparison")],
  cov=C("partial", "Implemented for two of the four copies.", ["skills/lsf copies are guarded by tests, not by check --assets"]))

# ---- ops: events, emission, cli, tab sources, banners (items 4, 5)
OPS = "factory/ops"
setsum("ops-dashboard", "factory.ops bundles historical development artifacts per commit from the git object database, collects runtime telemetry separately with measured / not-measured labels, records stage events as the commands run, and a static shell offers a commit selector, tabs and banners for staleness and open human stops.")
nodes["ops-dashboard"]["files"] = [F("docs/ops-events.md", None, "# Ops events and the live dashboard", "Events and what emits them"), F("docs/ops-tabs.md", None, "# Ops dashboard tabs", "Where each tab reads from")]
setcov("ops-dashboard", "partial", "Built and tested (tests/test_ops*.py); a real headless session ran sf ops init and sf slice check and the stage event appeared without anyone calling a script (" + NV20 + ", S6). Not deployed.",
       ["Not deployed", "Runtime telemetry covers only what its config declares; most figures are 'not measured' without configuration", "Langfuse and CI figures are reported only when configured", "Per-product use not done"])
nodes["ops-dashboard"]["diagram"] = [
    "flowchart LR",
    "  ops-emission[\"Event emission<br/>run_tool, hooks\"] -->|\"one JSON line per stage\"| ops-events[\"events.jsonl<br/>ops/events.py\"]",
    "  ops-events -->|\"stage hitl events\"| ops-tab-sources[\"Tab sources<br/>collectors\"]",
    "  qa-notes[\"QA notes<br/>qa promote-notes\"] -->|\"qa-notes.md\"| ops-tab-sources",
    "  ops-cli[\"sf ops<br/>init, backfill, status, autobundle\"] -->|\"snapshots\"| ops-bundle[\"Bundle<br/>content-addressed blobs\"]",
    "  ops-tab-sources -->|\"tabs per commit\"| ops-bundle",
    "  ops-runtime-collector[\"Runtime telemetry<br/>repo_head, behind, stops, Langfuse\"] -->|\"runtime.json\"| ops-shell[\"Shell<br/>tabs, banners\"]",
    "  ops-bundle --> ops-shell"]
nodes["ops-dashboard"]["children"] = ["ops-bundle", "ops-events", "ops-emission", "ops-cli", "ops-runtime-collector", "ops-tab-sources", "qa-notes", "ops-shell"]
N("ops-bundle", "Bundle", "Writes per-commit snapshots under ops/snapshots/<sha>/ as content-addressed blobs read from the git object database (or the working tree), builds the viewer and installs the shell.", kind="module",
  files=[F(OPS + "/bundle.py", None, "def put_blob", "Content-addressed blob"), F(OPS + "/bundle.py", None, "def build_viewer", "Viewer from the dolls template")],
  cov=C("built", "Implemented; tests/test_ops.py passes here."))
N("ops-events", "Stage events", "emit(root, stage, slice, verdict, note, source, role) appends one JSON line to ops/events.jsonl under an exclusive lock: notes are cut to 2,000 characters, control characters and secret shapes are removed, a symlink that leaves the root is refused, and a failure returns False and never raises. SF_EVENTS=off writes nothing.", kind="module",
  files=[F(OPS + "/events.py", None, "def emit", "The writer"), F(OPS + "/events.py", None, "def _redact", "Secret shapes"), F("docs/ops-events.md", None, "## Stage events", "Contract")],
  cov=C("built", "Implemented; tests/test_ops_events.py and test_ops_security.py pass here."))
N("ops-emission", "Where events come from", "factory/cli.py run_tool emits one event after a delegated tool group finishes (pass on exit 0, else fail, note exit=N; nothing for exit 2); the subagent_stop and ledger_audit hooks each emit a subagent-stop event. The exit code and the hook decision are never changed.", kind="module",
  files=[F("factory/cli.py", None, "def _record_event", "Telemetry only; never raises"), F("factory/cli.py", None, "def run_tool", "Calls _record_event after the tool"), F("factory/hooks/subagent_stop.py", None, "def record", "Hook emission"), F("factory/hooks/ledger_audit.py", None, "emit(cfg.project_root", "Hook emission"), F("docs/ops-events.md", None, "## Which commands leave an event", "Command to stage table")],
  cov=C("built", "Implemented; seen in a real headless session (S6).", ["Each sub-agent stop is recorded twice (both hooks emit); the agent-stop tile would double count (" + NV20 + ")"]))
N("ops-cli", "sf ops commands", "init creates ops/config.json and events.jsonl, installs the viewer and bundles HEAD (optionally recording a Langfuse host); backfill bundles commits without a snapshot; status says how far the newest snapshot is behind HEAD (exit 4 when behind or none); autobundle installs, removes or reports a post-commit hook block that runs sf ops bundle --sha HEAD.", kind="module",
  files=[F(OPS + "/cli.py", None, "def _init", "init"), F(OPS + "/cli.py", None, "def _backfill", "backfill"), F(OPS + "/cli.py", None, "def _status", "status; BEHIND exit 4"), F(OPS + "/cli.py", None, "def _autobundle", "autobundle")],
  cov=C("built", "Implemented; tests/test_ops_cli_native.py passes here; init and status were run in a real session (S6)."))
N("ops-runtime-collector", "Runtime telemetry", "collect_runtime measures what the config declares and labels each figure measured or not measured. repo_state reports repo_head and how many commits the newest snapshot is behind (behind, None when unknown); stops reads open human stops through the hitl store with the hash chain verified and reports a failed ledger as an open entry; langfuse says 'not measured' with the reason instead of a number it does not have.", kind="module",
  design=[D("Not measured is shown, never a zero", "A dashboard that prints 0 traces when it never asked is lying; every runtime figure carries a source and a label.", "Defaulting missing figures to zero")],
  files=[F(OPS + "/runtime.py", None, "def repo_state", "repo_head and behind"), F(OPS + "/runtime.py", None, "def stops", "Open human stops, chain verified"), F(OPS + "/runtime.py", None, "def langfuse", "Host shown when configured; traces not measured"), F(OPS + "/runtime.py", None, "def collect_runtime", "Assembles runtime.json")],
  cov=C("built", "Implemented; tests/test_ops.py and test_ops_content.py pass here.", ["Trace ingestion is not checked by the collector: Langfuse traces stay 'not measured'"]))
N("ops-tab-sources", "Tab sources", "Collectors for the historical tabs, each returning items or 'not available' with the paths searched, never an empty success: the one-page PRD journeys, experiments including resolved.json, the bug log and QA notes, and the human stops history.", kind="module",
  files=[F(OPS + "/collect.py", None, "COLLECTORS = {", "All tab collectors"), F("docs/ops-tabs.md", None, "# Ops dashboard tabs", "Source per tab")],
  cov=C("built", "Implemented; tests/test_ops_content.py passes here."),
  diagram=["flowchart LR",
           "  tab-prd[\"PRD journeys<br/>docs/prd/onepager.md\"] --> tab-experiments[\"Experiments<br/>results.json, resolved.json\"]",
           "  tab-experiments --> tab-bugs[\"Evals and bugs<br/>docs/bugs, qa-notes.md\"]",
           "  tab-bugs --> tab-hitl[\"Human stops<br/>ADRs + hitl events\"]"],
  children=["tab-prd", "tab-experiments", "tab-bugs", "tab-hitl"])
N("tab-prd", "One-page PRD journeys", "Reads docs/prd/onepager.md (## Journey: name, a Slices line, one to five steps), flags an id with no docs/slices/<id>/, and warns when the page is over 80 lines without cutting anything; the slice proposals and docs/prds follow.", kind="module",
  files=[F(OPS + "/collect.py", None, "def _onepager", "Parser"), F(OPS + "/collect.py", None, "def prd_journeys", "Tab source")], cov=C("built", "Implemented."))
N("tab-experiments", "Resolved experiments", "experiments/<id>/results.json is kind experiment; experiments/<id>/resolved.json {question, resolved_by, sources, as_of} is kind resolved, so a choice settled by research is shown without a fake experiment. sf intake experiments check validates both.", kind="module",
  files=[F(OPS + "/collect.py", None, "def experiments", "Tab source"), F("factory/intake/cli.py", None, "experiments", "The check accepts resolved.json")], cov=C("built", "Implemented."))
N("tab-bugs", "Bug log", "Reads docs/bugs/*.md (Status: open, fixed or wontfix, else invalid), docs/bug-log.jsonl and the signature blocks of docs/slices/*/qa-notes.md.", kind="module",
  files=[F(OPS + "/collect.py", None, "def bug_log", "Tab source"), F(OPS + "/collect.py", None, "def _qa_notes", "QA note blocks")], cov=C("built", "Implemented."))
N("tab-hitl", "Human stops history", "Historical view of open decisions: ADRs whose status is Proposed or Pending, and ops/events.jsonl events with stage hitl up to the snapshot's commit date. Open stops never enter a snapshot; the live ones come from the runtime collector.", kind="module",
  files=[F(OPS + "/collect.py", None, "def hitl", "Tab source")], cov=C("built", "Implemented."))
N("qa-notes", "QA notes (promote-notes)", "sf qa promote-notes --slice DIR writes DIR/qa-notes.md from the local .sf attempt log: one signature block with attempt count, criteria, the observed and expected text and the regression proposal. The leak check runs first (exit 1, nothing written); an unchanged re-run does not rewrite the file.", kind="module",
  files=[F("factory/qa/notes.py", None, "def promote", "Commits the notes"), F("factory/qa/notes.py", None, "def build", "Builds the Markdown"), F("docs/ops-tabs.md", None, "## Committing QA notes", "Contract")],
  cov=C("built", "Implemented; tests/test_qa_notes.py passes here.", ["The notes exist only after a real QA loop has recorded failures; none have been produced by a real session"]))
N("ops-shell", "Shell: tabs and banners", "ops/shell/index.html is the static viewer: twelve tabs (overview, human stops, ops, architecture, research, experiments, ADRs, PRD journeys, Langfuse, evals and bugs, dev journey, git history), a stops banner ('N open human stop(s)' or 'human stops unknown') and a staleness banner ('Snapshot is N commits behind the repository') driven by runtime.json.", kind="module",
  files=[F("ops/shell/index.html", None, "var TABS=[", "The twelve tabs"), F("ops/shell/index.html", None, "function renderStops", "Stops banner"), F("ops/shell/index.html", None, "commits behind the repository", "Staleness banner"), F("ops/shell/index.html", None, "function hitlHtml", "Human stops tab")],
  cov=C("built", "Implemented; verified in a real browser against this repository's history in the earlier build.", ["Not deployed"]))

# ---- flow: sf stages versus lsf phases and loop-backs (item 8)
N("flow-compare", "Flow: sf stages vs lsf phases",
  "The owner's flow as two runners. sf (left) has the stages 0 to 12 with the deterministic gates; lsf (right) has eleven phases that alias onto the same stages. The four loop-backs are drawn as clickable boxes: qa to implement, qa to evals, review to implement and inbound to slice.",
  kind="process",
  design=[D("Loop-backs are explicit, evidence-bearing edges", "A flow that only runs forward hides the rework the owner cares about; each loop-back names the command or file that makes it happen.", "A linear stage list")],
  files=[F("docs/sf-flow.md", None, "flowchart TD", "The sf flow with its legend"), F(LSF, None, "SF_ALIAS = {", "lsf phase to /sf stage"), F("factory/agents/default_graph.yaml", None, "loops:", "Declared loops of the role graph")],
  cov=C("partial", "The sf stages, the alias map and the role-graph loops are code or documents; the loop-backs qa to evals, review to implement and inbound to slice have not been exercised by real agents.",
        ["Loop-backs have not run in a real session"]),
  diagram=[
      "flowchart TD",
      "  subgraph sfg[\"sf stages\"]",
      "    direction TB",
      "    s0[\"0 Intake gate\"] --> s1[\"1 Research\"] --> s2[\"2 Experiments\"] --> s3[\"3 Decide: ADR\"] --> s4[\"4 Slice, UX stories first\"] --> s5[\"5 Evals first, frozen\"] --> s6[\"6 Blind implement\"] --> s7[\"7 QA\"] --> s8[\"8 Gate, 8b Review\"] --> s9[\"9 Drift\"] --> s10[\"10 Docs\"] --> s11[\"11 Commit + snapshot\"] --> s12[\"12 Inbound\"]",
      "  end",
      "  subgraph lsfg[\"lsf phases\"]",
      "    direction TB",
      "    p0[\"0-intake, 1-sweep\"] --> p2[\"2-research\"] --> p3[\"3-experiments\"] --> p4[\"4-prd\"] --> p5[\"5-evals\"] --> p6[\"6-decide\"] --> p7[\"7-implement\"] --> p8[\"8-qa\"] --> p9[\"9-review\"] --> p10[\"10-docs\"]",
      "  end",
      "  p0 -.->|\"aliases stage 0\"| s0",
      "  p2 -.-> s1",
      "  p3 -.-> s2",
      "  p6 -.-> s3",
      "  p4 -.-> s4",
      "  p5 -.-> s5",
      "  p7 -.-> s6",
      "  p8 -.-> s7",
      "  p9 -.-> s8",
      "  p10 -.-> s10",
      "  s7 -->|\"fail: feedback\"| flow-lb-qa-impl{{\"Loop 1<br/>QA to implement\"}}",
      "  flow-lb-qa-impl --> s6",
      "  s7 -->|\"same signature again\"| flow-lb-qa-evals{{\"Loop 2<br/>QA to evals\"}}",
      "  flow-lb-qa-evals --> s5",
      "  s8 -->|\"finding\"| flow-lb-review-impl{{\"Loop 3<br/>review to implement\"}}",
      "  flow-lb-review-impl --> s6",
      "  s12 -->|\"new text, ranked\"| flow-lb-inbound-slice{{\"Loop 4<br/>inbound to slice\"}}",
      "  flow-lb-inbound-slice --> s4",
      "  flow-phase-map[\"Alias map<br/>lsf phase to sf stage\"] -.-> lsfg"],
  children=["flow-lb-qa-impl", "flow-lb-qa-evals", "flow-lb-review-impl", "flow-lb-inbound-slice", "flow-phase-map"])
N("flow-lb-qa-impl", "Loop 1: QA to implement", "A failed gate gives behavioural feedback (criterion terms, no test source, leak-checked) and the same tier retries; at the policy point the model tier escalates; at the cap the case is handed to the reviewer. The role graph declares the loop [qa, implement].", kind="loop",
  files=[F("factory/agents/default_graph.yaml", None, "- [qa, implement]", "Declared loop"), F("factory/qa/decide.py", None, "def decide(", "Retry, escalate, hand off"), F("docs/qa-loop.md", None, "`rerun_for_flake`", "Actions")],
  cov=C("partial", "Implemented and simulated with a scripted implementer; not run with real agents.", ["Real implementer and QA agent loop not yet run"]))
N("flow-lb-qa-evals", "Loop 2: QA to evals", "When the same failure signature recurs, QA proposes a regression case (sf qa regression-propose, written append-only to regression-proposals/<signature>.md) which goes back to the evals stage; the evals stay frozen except through an additive amendment.", kind="loop",
  files=[F("docs/qa-loop.md", None, "regression-proposals", "Where proposals go"), F("factory/qa/decide.py", None, "propose_regression", "The decision")],
  cov=C("partial", "Implemented and simulated; not run with real agents. The role graph declares no qa to evals back-edge: this loop is the proposal artifact plus a human or orchestrator step.", ["Real run not done"]))
N("flow-lb-review-impl", "Loop 3: review to implement", "A reviewer finding becomes a triaged task or criterion through sf slice amend --role reviewer (additive only; weakening needs an explicit approval marker) and re-opens implement and QA. The role graph declares the loop [review, implement]; in lsf, 9-review failures amend the PRD and go back to 7 and 8.", kind="loop",
  files=[F("factory/agents/default_graph.yaml", None, "- [review, implement]", "Declared loop"), F("factory/slices/cli.py", None, "def cmd_amend", "Reviewer amendment"), F("skills/lsf/SKILL.md", None, "failures amend the PRD and go back to 7 and 8", "lsf wording")],
  cov=C("partial", "The command and the graph loop are implemented and tested; a real reviewer has not amended a slice.", ["Reviewer amendments not yet run in a real session"]))
N("flow-lb-inbound-slice", "Loop 4: inbound to slice", "Stage 12 looks at what arrived while working, ranks it into the ledger or backlog (sf intake gate --since GITREF re-checks changed requirement text), states 'nothing new' explicitly and the next slice is chosen from the ledger, not a queue.", kind="loop",
  files=[F("docs/sf-flow.md", None, "inbound --> slice", "In the flow diagram"), F("factory/intake/cli.py", None, "--since", "Gate on changed source"), X(SF, "223-252", "Check the inbound sources", "Stage 12 text in the installed skill")],
  cov=C("partial", "The gate option exists; the ranking is model procedure and not yet run in a real session.", ["Not run in a real session", "The ranking and the 'nothing new' statement are written procedure with no mechanical check"]))
N("flow-phase-map", "Alias map: lsf phase to sf stage", "0-intake and 1-sweep map to stage 0, 2-research to 1, 3-experiments to 2, 4-prd to 4, 5-evals to 5, 6-decide to 3, 7-implement to 6, 8-qa to 7, 9-review to 8b and 10-docs to 10, so events from both tools read the same.", kind="config",
  files=[F(LSF, None, "SF_ALIAS = {", "The map"), F("skills/lsf/SKILL.md", None, "| lsf phase | group |", "The table with the /sf stage column")],
  cov=C("built", "Implemented as data.", ["lsf has no phase for stages 8 (impact and solver gate), 11 or 12; they exist only in sf"]))
addchildren("build-loop", "flow-compare", diagram=['  build-hygiene -.->|"drawn against lsf"| flow-compare["Flow: sf vs lsf<br/>loop-backs"]'])

# ---- fill missing line ranges from the quoted text (python def/class extent, markdown section, bracket balance)
def _span(path, contains, repo="."):
    p = os.path.join(repo, path)
    if not os.path.isfile(p):
        return None
    L = open(p, encoding="utf-8", errors="replace").read().splitlines()
    k = next((i for i, t in enumerate(L) if contains in t), None)
    if k is None:
        return None
    s = L[k].strip()
    ind = len(L[k]) - len(L[k].lstrip())
    last = k
    if path.endswith(".py") and _re.match(r"(async\s+def|def|class)\s", s):
        for j in range(k + 1, len(L)):
            if not L[j].strip():
                continue
            if len(L[j]) - len(L[j].lstrip()) <= ind and not L[j].lstrip().startswith((")", "]", "}")):
                break
            last = j
    elif path.endswith(".md") and s.startswith("#"):
        lvl = len(s) - len(s.lstrip("#"))
        for j in range(k + 1, len(L)):
            m = _re.match(r"(#+)\s", L[j])
            if m and len(m[1]) <= lvl:
                break
            if L[j].strip():
                last = j
    else:
        bal = 0
        for j in range(k, min(k + 80, len(L))):
            bal += sum(L[j].count(c) for c in "{[(") - sum(L[j].count(c) for c in "}])")
            last = j
            if bal <= 0:
                break
        if bal > 0:
            last = k
    return f"{k + 1}-{last + 1}" if last > k else str(k + 1)

def _fill_lines():
    for n in nodes.values():
        for f in n.get("files", []):
            if f.get("lines") or not f.get("contains") or f.get("external") or f["path"].startswith("~"):
                continue
            sp = _span(f["path"], f["contains"])
            if sp:
                f["lines"] = sp
    # start every range at the first line that holds the quoted text, so the editor link lands on it
    for n in nodes.values():
        for f in n.get("files", []):
            if f.get("external") or f["path"].startswith("~") or not f.get("contains") or not f.get("lines") or not os.path.isfile(f["path"]):
                continue
            m = _re.fullmatch(r"(\d+)(?:-(\d+))?", f["lines"])
            L = open(f["path"], encoding="utf-8", errors="replace").read().splitlines()
            if not m:
                continue
            lo, hi = int(m[1]), int(m[2] or m[1])
            k = next((i for i in range(lo, min(hi, len(L)) + 1) if f["contains"] in L[i - 1]), None)
            if k and k > lo:
                f["lines"] = f"{k}-{hi}" if hi > k else str(k)

# ---- re-anchor cited line ranges to where the quoted text now is (keeps the model honest as files change)
import os, re as _re
def _reanchor(repo="."):
    for nid, n in nodes.items():
        for f in n.get("files", []):
            c, ln, p = f.get("contains"), f.get("lines"), f["path"]
            if not c:
                continue
            ext = f.get("external") or p.startswith("~")
            path = os.path.expanduser(p) if ext else os.path.join(repo, p)
            if not os.path.isfile(path):
                continue
            lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
            m = _re.fullmatch(r"(\d+)(?:-(\d+))?", str(ln)) if ln else None
            lo, hi = (int(m[1]), int(m[2] or m[1])) if m else (1, len(lines))
            if hi <= len(lines) and lo <= hi and c in "\n".join(lines[lo - 1:hi]):
                continue
            for k, text in enumerate(lines, 1):
                if c in text:
                    span = max(hi - lo, 0)
                    f["lines"] = f"{k}-{min(k + span, len(lines))}" if span else str(k)
                    break
_fill_lines()
_reanchor()
MODEL = {
    "meta": {"title": "Claude Software Factory: workflow, design choices, coverage",
             "subtitle": "Nesting-dolls explorer of the software-factory repository",
             "repo": "software-factory", "commit": sys.argv[1] if len(sys.argv) > 1 else "", "generated": "2026-10-20"},
    "root": "factory",
    "nodes": nodes,
}
json.dump(MODEL, sys.stdout if len(sys.argv) > 2 and sys.argv[2] == "-" else open(sys.argv[2] if len(sys.argv) > 2 else "model.json", "w"), indent=1, ensure_ascii=False)
