# Project intake: starting requirements + repository

Before phase 0, collect the starting PRD/brief and repository context together.
Reuse answers already supplied; ask only for missing information. Do not start
research, implementation or the phase clock in an unrelated launch directory.

Ask in one compact intake:

1. **Starting requirements:** PRD/assignment/brief text, file or URL; intended
   outcome and acceptance/rubric constraints. If none exists, collect the idea
   and draft an initial PRD for confirmation. Preserve the original separately
   from the refined PRD produced after exploration/minesweeping.
2. **Mode:** greenfield (new codebase) or brownfield (existing codebase).
3. **Source, if brownfield:** source repo URL or existing local checkout, plus
   branch/commit. A PDF/PRD alone does not identify the source repo.
4. **Owned destination:** GitHub or GitLab, owner/organization, repo name and
   visibility; an existing owned repo URL can satisfy this. Follow the owner's
   explicit sharing requirements and the assignment's submission instructions.
5. **Execution:** local builder or VPS builder, local checkout folder and time
   budget. Keep an Antigravity-accessible local checkout in either case.

## Greenfield

Create the repo under the specified owner on GitHub/GitLab using the available
authenticated CLI/API, then clone it locally (or initialize the agreed new local
folder and connect it). An initial README is fine; do not scaffold product code
before minesweeping/plan approval. Confirm the local root and owned remote.
A launch from the home folder must not turn the home folder into the project.
If hosting/auth details are missing, ask for those details rather than guessing.

## Brownfield

Clone the source into a fresh local folder, or use the provided existing checkout
without overwriting local work. Record the source URL, branch and baseline SHA.
Set up the specified owned destination: prefer a supported fork when appropriate,
otherwise create an owned repo and push the agreed branch with its history.

For a **new clone only**, a useful arrangement is `upstream` = original source
and `origin` = owned destination. Rename the initial clone's origin to upstream
before adding the owned origin. Inspect existing remotes before acting; never
blindly rename or replace remotes in an existing checkout. Don't force-push,
rewrite source history, push to the source accidentally, or push every remote
branch/tag by default. Follow source licensing and supplied interview rules.
If those require a different submission arrangement, surface that mismatch to
the owner and record the chosen destination before publishing.

## Bootstrap handoff

Before finishing intake, verify and record in `docs/requirements/intake.md`:

- original PRD/brief path (`docs/requirements/brief.md` holds its verbatim text);
- greenfield/brownfield, source URL/branch/baseline SHA when applicable;
- absolute local checkout root, owned destination URL and visibility;
- inspected fetch/push remotes and destination verification result;
- local/VPS execution mode, time budget and unresolved access/setup blockers.

Once the checkout and PRD are available, enter that repo and run `lsf doctor`,
then initialize or resume its profile without resetting existing decisions.
The phase-0 one-pager is a draft; exploration/minesweeping can refine it, with
owner review at the configured post-sweep stop. The refined developer-facing
PRD and eval surface still precede implementation.

For VPS mode, prepare from this **local checkout** using `lsf-vps prepare NAME
"$PWD"`. The helper removes its temporary Git-bundle origin; that VPS clone does
not automatically inherit a writable owned remote. Its `source.json` points back
to the original local checkout. Keep the owned destination on the original local
checkout, fetch remote work with `lsf-vps fetch NAME`, then review/integrate and
push from there. Do not claim VPS preparation itself created an owned hosted repo.

If Claude is already running on the VPS, it cannot directly create a checkout on
this Mac. Ask the owner/Codex to perform missing local bootstrap steps and provide
the resulting paths/remotes; do not treat a Linux clone as the local IDE checkout.
