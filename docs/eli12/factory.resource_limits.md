# factory/resource_limits.py

Runs a command with a shared turn-taking lock, a memory budget and a time budget.

## tree_rss
<!-- sig:56bd56e4 -->

**What it does:** Adds up memory used by a process and its children.

**Expects:**
- pid (int): the starting process identifier

**Gives back:** int: total resident memory in bytes

**Used by:**
- factory.resource_limits.run (factory/resource_limits.py:68)

**Depends on:**
- factory.hooks.bash_guard.Lexer.add (factory/hooks/bash_guard.py:152) (maybe)
- factory.hooks.blindness_guard._Lexer.add (factory/hooks/blindness_guard.py:404) (maybe)
- factory.qa.store.SliceStore.append (factory/qa/store.py:108) (maybe)
- factory.verify.gate.GateReport.add (factory/verify/gate.py:57) (maybe)

**Watch out:** Names marked (maybe) are unconfirmed links, not known calls.

## run
<!-- sig:8b18d6c3 -->

**What it does:** Runs one command at a time and stops it if its memory or time budget is exceeded.

**Expects:**
- command (list): the program and its arguments
- memory_mb (int): maximum sampled memory in MiB; zero disables this check
- wall_s (float): maximum elapsed seconds; zero disables this check
- lock (str or Path): the shared lock file
- lock_wait_s (float): how long to wait for another command to finish

**Gives back:** int: the command exit code, 124 for timeout, or 137 for a memory stop

**Used by:**
- factory.resource_limits.main (factory/resource_limits.py:91)

**Depends on:**
- factory.resource_limits._terminate (factory/resource_limits.py:39)
- factory.resource_limits.tree_rss (factory/resource_limits.py:17)

## main
<!-- sig:ff123372 -->

**What it does:** Reads command options and returns the bounded command exit code.

**Expects:** nothing

**Gives back:** int: the exit code for the calling shell

**Used by:**
- factory.resource_limits.<module> (factory/resource_limits.py:99)

**Depends on:**
- factory.resource_limits.run (factory/resource_limits.py:47)
- factory.structure.__main__._Parser.error (factory/structure/__main__.py:23) (maybe)

**Watch out:** Names marked (maybe) are unconfirmed links, not known calls.
