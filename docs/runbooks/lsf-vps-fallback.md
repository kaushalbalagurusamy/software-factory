# VPS fallback for the supervised build

Claude and tests run on Vultr. Codex stays in this Mac terminal, the dashboard
comes through an SSH tunnel, and Antigravity opens matching local review copies.
Existing local projects and remote sessions are preserved. Default model: Sonnet.

## Start with the interview repository

Inside its local checkout:

```sh
lsf-vps prepare peak6 "$PWD"
lsf-vps start peak6
lsf-vps attach peak6
```

`prepare` creates a separate remote repo, copying committed history and current
working files. It excludes dependency folders and root `.env` files from the
working-file copy. It preserves shallow-history boundaries. It pins the last
VPS-coordinator-tested LSF, ELI12 and nesting-dolls version for the project.

`start` runs the remote `claude-lsf` launcher with Remote Control and bypass
permissions. It supplies no task. `attach` opens that tmux session: accept the
first workspace trust prompt, then give Claude the brief. Detach with Ctrl-b d;
the remote session continues. Repeating `start` preserves an existing session.

Once Claude has initialized LSF and paused at its first human checkpoint:

```sh
lsf-vps snapshot peak6
lsf-vps review peak6
lsf-vps dashboard peak6 --open
```

This opens the VPS dashboard at http://127.0.0.1:8890/ through SSH, including its
private approval fragment. The token is omitted from command output. No public
listener or firewall change is needed. Use `--port 8891` for a second project.
The dashboard remains on VPS if the Mac's terminal disconnects. Re-run the
command to reconnect a dropped tunnel; `tunnel-stop` closes only this project's
local tunnel.

## Review and supervise

At each HITL pause, run `lsf-vps snapshot peak6`. The local review shortcut is:

```
~/Projects/lsf-vps/peak6/current
```

The dashboard's Antigravity editor links use that location. Confirm the Editor
is `antigravity-ide` and Workspace root matches this path. Code changes made on
the VPS, including tracked deletions and uncommitted files, are included. A
fingerprint check rejects a copy if remote code changes during transfer.
Snapshots have Git history for reviewing diffs. Their metadata records the
remote commit, content check and capture time in `.lsf-vps-review.json`.

`review` opens the matching folder in a separate Antigravity window, preserving
the current window and enabling native file search and Git diffs for the mirror.
It is optional if direct file links are enough.

Earlier snapshots are retained. Local notes or edits in an earlier snapshot
are never overwritten. These are review copies: edits do not automatically
write back to the VPS. Send findings through Codex to the remote implementer.
Refresh and click the current link again before reviewing a later decision;
an already open editor tab may still show an earlier snapshot.

The human remains the interviewer/build approver. Codex may act as delegated
HITL for the owner's rehearsals, with that delegation recorded in the approval
note. Checkpoint answers should progress Asked -> Answered -> Recorded -> Applied.

## Inspect state and retrieve commits

```sh
lsf-vps status peak6
lsf-vps fetch peak6
```

`fetch` brings remote commits into the original local repo under
`refs/remotes/lsf-vps/peak6`; it does not merge, switch branches or change files.
Review and integrate them explicitly afterward. No push remote is configured
by this helper.

A running project stays pinned when newer factory code is published. Use a
new project name for a newer runtime; `pin NAME` can refresh an idle project
that has only managed skill links. It refuses to replace custom project skills
or change a different runtime beneath a running agent/dashboard.

## What was verified

- Sonnet 5.5 running in a separate VPS tmux session with Remote Control enabled.
- Existing AEA, Riverside, Qrypt, SF and other sessions preserved.
- Loopback-only dashboard accessible through local SSH port 8890.
- Antigravity links mapped to a verified local checkout.
- Delegated checkpoint approval through the actual HTTP API, ADR recording,
  21 passing remote tests, then Applied evidence. Tests used a 4 GiB address-space
  limit and 60-second timeout; actual output and exit status were read independently.
- Pending checkpoint refused phase start with exit 3.
- Fresh shallow-repo transfer; tracked deletion and untracked-file preservation;
  previous local notes retained; fetching did not change the original local branch/files.
- Shared LSF checks passed locally after fixing an HTTP test-client portability issue.

Rehearsal: `fallback-rehearsal`. The first approval exposed a wrong transport
label (`cli-nontty` for the dashboard route); its existing audit history is
retained, and a regression-tested fix was sent to the VPS coordinator for new
releases. Native IDE window inspection was unavailable; protocol registration,
URL construction and OS dispatch were checked separately.
