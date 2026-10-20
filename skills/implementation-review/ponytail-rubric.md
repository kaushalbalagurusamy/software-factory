# Ponytail review rubric

Plain-text questions the reviewer applies to every changed file. They stand in for the `ponytail` plugin, which is not loaded into subagents. Every finding cites a file, a line and a concrete case.

1. Does it need to exist? Name the requirement or criterion that demands this code; if none, it is a finding.
2. Is it already in the codebase? Search for an existing helper, component or pattern that does the same job and say which.
3. Is there a standard-library or installed-dependency way? Name it; a new dependency for a few lines is a finding.
4. Is any code unreachable or speculative? Options, parameters, branches or hooks "for later" that no caller or criterion uses.
5. Is every new non-trivial branch covered? For each new branch, loop or parser, point at the test that exercises it; an untested risky branch is a finding.

End with `Verdict:` and a `Not checked:` line.
