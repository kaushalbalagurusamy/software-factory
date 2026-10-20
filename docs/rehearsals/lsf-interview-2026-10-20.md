# Interview workflow comparison and rehearsal

Compared against VPS snapshot ae3a425, while its owner continued HITL work.
The rehearsal pinned that snapshot rather than modifying the live installation.

| Intended factory behavior | Lightweight implementation | Practical gap |
| --- | --- | --- |
| Business intent, then minesweeping | Intake and sweep phases; draft onepager created at intake | Revise the draft after the sweep; brownfield-explorer must be explicitly requested alongside minesweeper |
| SOTA research and justified experiments | Research and experiment phases with source-backed resolved records | Timebox research; no experiment is needed when existing evidence settles the question |
| Prioritized UX tracer bullets, MECE acceptance surface, ADRs | PRD, eval and decision phases with file artifacts | Phase markers alone do not prove artifact quality or completeness |
| Blind implementation and independent QA with feedback | Implementation, QA and review phases; review findings loop to implementation | Blindness and independent judgment depend on agent orchestration; not an OS security boundary |
| Mechanistic review using minesweeper, dolls and Ponytail | Review skill instructions and explorer artifacts | A tiny slice may need only a scoped map; tools do not replace checking source and actual behavior |
| Living documentation and drift checks | Final ELI12 documentation and ADR synchronization | Requires supporting eli12-docs skill; keep changes proportional to interview scope |
| One dashboard with reports and human decisions | Offline dashboard, event log, report paths, bundle, checkpoints | It is not a hosted Claude artifact; loopback URL is not reachable from phone Remote Control |
| Human approval gates | Open checkpoints block phase start; dashboard or human terminal releases | Hook guards provide friction and an audit trail, not identity proof under bypass permissions |
| One-hour supervised build | Clock and phase weights | Default 60/20/20 allocates 36 minutes to alignment and only 12 to building; agree an appropriate budget with interviewer |

Order: intake -> sweep -> research -> experiments/resolution -> PRD -> evals ->
decisions -> implementation -> QA -> review -> docs. QA/review failures return
to the relevant PRD and implementation/QA loop. Human checkpoints stop the next
phase. Reports live in research/, experiments/, docs/requirements/, docs/prds/,
docs/slices/, docs/adr/, docs/bugs/, docs/explorer/ and docs/eli12/; dashboard tabs
and the JSON bundle collect these artifacts alongside the live event stream.

## Brownfield exercise

Official python-dotenv baseline: 0b2880591780a426b0551436f47a17e7a76d954f.
Disposable VPS repository: /home/linuxuser/Projects/lsf-rehearsals/python-dotenv-prefix.
Feature: case-sensitive literal `dotenv list --prefix PREFIX`, preserving all four
output formats, legacy empty-prefix behavior, quoting, null semantics and input bytes.
Sonnet 5.5 completed all eleven phases, explicitly used minesweeper and
brownfield-explorer, dispatched independent QA and review, and generated a scoped
nesting-dolls artifact. QA caught the missing README example; implementation added it.

An external behavioral suite was written before the implementation and kept
outside the project: 14 failed on baseline (missing option), 14 passed afterward.
The coding rehearsal deliberately used checkpoints=none. A separate checkpoint
exercise verified an open intake checkpoint refuses the next phase with exit 3.
This does not establish end-to-end browser approval/resume or a hosted artifact.

Independent full-suite rerun with the project's venv on PATH: 305 passed,
1 skipped in 2.16 seconds. An initial supervisor invocation omitted venv/bin
from PATH, so 20 subprocess-based tests could not find the dotenv executable;
correcting PATH resolved those environment failures without changing code.

Local launcher smoke verified Sonnet 5.5 / Claude Max, active Remote Control,
bypass permissions and caffeinate assertions tied to Claude. Away-mode completed
and the agent waited without creating .lsf or starting the phase clock.
VPS HEAD 8e612b4 had no changes to the three pinned skill directories at final
comparison; its newer decision-record contract is separate from this launcher.

## Dashboard screenshots

Captured from a local server using the real committed VPS rehearsal artifacts
and its `.lsf` event log; the checkpoint image uses the separate gate exercise.
Chrome rendered the actual pages. No checkpoint was approved and no approval
token appears in the screenshots.

- [Overview and phase completion](screenshots/lsf-overview.png)
- [UX stories and prioritized PRD](screenshots/lsf-prd.png)
- [Architecture and nesting-dolls entry points](screenshots/lsf-architecture.png)
- [Evaluation verdicts](screenshots/lsf-evals.png)
- [Pending human checkpoint](screenshots/lsf-checkpoint.png)

The first evaluation capture exposed a collector limitation: a free-form
`qa-notes.md` exists but is omitted because only `## Signature` blocks are parsed.
The verdict stream remains visible. This was reported to the active VPS Claude
for its next integration pass; do not interpret the empty QA list as a missing report.
