# Global instructions

## Git commits: atomic, one logical change each

When working in a git repository, commit as you go so the history lets the user step through each change made during a session. You do not need to wait to be asked before committing, and you may push without asking, because version control and CI provide the safety net. Still pause for the genuinely irreversible or outward-facing: force-pushing over shared history, rewriting published commits, deleting branches, opening or merging pull requests, or publishing packages.

- Make each commit one self-contained logical change: a single bug fix, refactor, feature step, config change, or test addition. Do not bundle unrelated changes, and do not split one change across commits in a way that leaves the tree broken between them.
- Commit each change as soon as it is complete, before starting the next one. Do not save everything for one large commit at the end.
- Keep refactors and formatting separate from behavior changes, so a behavior change reads cleanly in its own diff.
- Where practical, each commit should build and pass the relevant tests on its own.
- Stage files explicitly by path (or with `git add -p` equivalents for partial files). Never use `git add -A` or `git add .`, and never sweep in pre-existing uncommitted changes that were not part of your work; leave those for the user.
- If you are on the repository's default branch (such as `main` or `master`), create a descriptively named branch before the first commit.
- Write the subject line in the imperative mood, under about 72 characters, describing what the commit does (for example "Fix null check in patient lookup"). Add a body only when the reason for the change is not obvious from the diff.
- Do not amend, squash, rebase, or force-push commits unless the user asks.


## Software Factory runtime on this Mac

For `/sf` and its supporting skills, the checkout is `__HOME__/Projects/software-factory` and `sf` resolves through `~/.local/bin/sf`. Run Python helper scripts with `__HOME__/Projects/software-factory/.venv/bin/python`, including when a skill example says `python3`; the system Python is older and does not have these dependencies. This isolated environment includes Unity, Z3, Tree-sitter and the minesweeper schema libraries. Use `sf install install --project DIR` to generate project agents/hooks, then `sf install doctor --project DIR` to verify them. This does not authorize starting a task or installing into unrelated projects.
