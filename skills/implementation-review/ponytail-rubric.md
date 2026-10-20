# Ponytail review rubric

Plain-text questions the reviewer applies to every changed file. They stand in for the `ponytail` plugin, which is not loaded into subagents. Every finding cites a file, a line and a concrete case.

- Does it need to exist? Name the requirement or criterion that demands this code.
- Is it already in the codebase? Name an existing helper, component or pattern that does the same job.
- Is there a standard-library or installed-dependency way? Name it; a new dependency for a few lines is a finding.
- Is any code unreachable or speculative? Look for options, parameters or branches no caller or criterion uses.
- Is every new non-trivial branch covered? Point at the test that exercises each new branch, loop or parser.

End with `Verdict:` and a `Not checked:` line.
