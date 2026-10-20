# Ponytail review rubric

Plain-text questions the reviewer applies to every changed file. They stand in for the `ponytail` plugin, which is not loaded into subagents. Every finding cites a file, a line and a concrete case.

- Does it need to exist?
- Is it already in the codebase?
- Is there a standard library or installed-dependency way?
- Is any code unreachable or speculative?
- Is every new non-trivial branch covered?

How to answer: name the requirement or criterion that demands the code; name an existing helper or pattern that already does the job; name the standard library or installed-dependency alternative (a new dependency for a few lines is a finding); list options, parameters or branches no caller or criterion uses; point at the test that exercises each new branch, loop or parser.

End with `Verdict:` and a `Not checked:` line.
