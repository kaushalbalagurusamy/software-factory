# scripts/lsf-vps.py

Keeps coding work on the remote computer while this Mac shows matching files for review.

## paths
<!-- sig:243a5f6b -->

**What it does:** Builds separate local and remote locations from a checked project name.

**Expects:**
- name (str): a short project name, such as peak6

**Gives back:** dict: project folders and separate session names

**Used by:**
- scripts.lsf-vps.main (scripts/lsf-vps.py:264)

**Depends on:** nothing

## run
<!-- sig:ffede4d9 -->

**What it does:** Runs a command and stops with an error when it fails.

**Expects:**
- args (list): the command name and its separate arguments
- **kw (dict): extra command options, such as where it runs

**Gives back:** CompletedProcess: the command result and any captured output

**Used by:**
- scripts.lsf-vps.dashboard (scripts/lsf-vps.py:245)
- scripts.lsf-vps.main (scripts/lsf-vps.py:270)
- scripts.lsf-vps.prepare (scripts/lsf-vps.py:120)
- scripts.lsf-vps.remote (scripts/lsf-vps.py:37)
- scripts.lsf-vps.shallow_boundary (scripts/lsf-vps.py:58)
- scripts.lsf-vps.snapshot (scripts/lsf-vps.py:170)

**Depends on:** nothing

## remote
<!-- sig:b036f749 -->

**What it does:** Runs a small Python program on the remote computer with data kept separate from commands.

**Expects:**
- code (str): Python instructions to run remotely
- data (dict): named values for those instructions

**Gives back:** object or None: the remote program output read as JSON, or nothing

**Used by:**
- scripts.lsf-vps.dashboard (scripts/lsf-vps.py:219)
- scripts.lsf-vps.fingerprint (scripts/lsf-vps.py:150)
- scripts.lsf-vps.main (scripts/lsf-vps.py:284)
- scripts.lsf-vps.pin_runtime (scripts/lsf-vps.py:66)
- scripts.lsf-vps.prepare (scripts/lsf-vps.py:121)
- scripts.lsf-vps.snapshot (scripts/lsf-vps.py:193)
- scripts.lsf-vps.start (scripts/lsf-vps.py:203)

**Depends on:**
- scripts.lsf-vps.run (scripts/lsf-vps.py:30)

## copy_args
<!-- sig:b417714a -->

**What it does:** Builds a file copy command that leaves dependencies, version-control files and root credentials behind.

**Expects:**
- source (str): the folder to copy from
- destination (str): the folder to copy into

**Gives back:** list: file copy arguments, without a delete option

**Used by:**
- scripts.lsf-vps.prepare (scripts/lsf-vps.py:141)
- scripts.lsf-vps.snapshot (scripts/lsf-vps.py:184)

**Depends on:** nothing

## publish_snapshot
<!-- sig:db7108b8 -->

**What it does:** Switches the review shortcut to a complete new copy without deleting earlier copies.

**Expects:**
- current (Path): the stable local review shortcut
- snapshot (Path): the complete new review folder

**Gives back:** nothing

**Used by:**
- scripts.lsf-vps.snapshot (scripts/lsf-vps.py:191)

**Depends on:** nothing

## shallow_boundary
<!-- sig:21de55b5 -->

**What it does:** Reads where a shortened copy of the project history begins.

**Expects:**
- source (Path): the local project folder

**Gives back:** str or None: history boundary identifiers, or nothing for complete history

**Used by:**
- scripts.lsf-vps.prepare (scripts/lsf-vps.py:139)

**Depends on:**
- scripts.lsf-vps.run (scripts/lsf-vps.py:30)

## pin_runtime
<!-- sig:150639f0 -->

**What it does:** Keeps this project on one tested factory version so later factory edits cannot change its tools.

**Expects:**
- p (dict): the project locations returned by paths

**Gives back:** dict: the tested version and tool locations

**Used by:**
- scripts.lsf-vps.main (scripts/lsf-vps.py:267)
- scripts.lsf-vps.prepare (scripts/lsf-vps.py:144)

**Depends on:**
- scripts.lsf-vps.remote (scripts/lsf-vps.py:34)

## prepare
<!-- sig:7ecdd5c2 -->

**What it does:** Copies project history and current files into a new remote folder, then prepares a local review copy.

**Expects:**
- p (dict): the project locations returned by paths
- source (Path): the original local project folder

**Gives back:** nothing

**Used by:**
- scripts.lsf-vps.main (scripts/lsf-vps.py:265)

**Depends on:**
- scripts.lsf-vps.copy_args (scripts/lsf-vps.py:42)
- scripts.lsf-vps.pin_runtime (scripts/lsf-vps.py:65)
- scripts.lsf-vps.remote (scripts/lsf-vps.py:34)
- scripts.lsf-vps.run (scripts/lsf-vps.py:30)
- scripts.lsf-vps.shallow_boundary (scripts/lsf-vps.py:57)
- scripts.lsf-vps.snapshot (scripts/lsf-vps.py:166)

## fingerprint
<!-- sig:049e2bf9 -->

**What it does:** Checks the remote commit and file contents so a changing copy is not presented as a stable review.

**Expects:**
- p (dict): the project locations returned by paths

**Gives back:** dict: the remote commit identifier and a content check value

**Used by:**
- scripts.lsf-vps.main (scripts/lsf-vps.py:291)
- scripts.lsf-vps.snapshot (scripts/lsf-vps.py:168)

**Depends on:**
- scripts.lsf-vps.remote (scripts/lsf-vps.py:34)

## snapshot
<!-- sig:fdcb50f3 -->

**What it does:** Builds a fresh local review copy, including remote changes, and keeps earlier review notes safe.

**Expects:**
- p (dict): the project locations returned by paths

**Gives back:** nothing

**Used by:**
- scripts.lsf-vps.main (scripts/lsf-vps.py:266)
- scripts.lsf-vps.prepare (scripts/lsf-vps.py:145)

**Depends on:**
- scripts.lsf-vps.copy_args (scripts/lsf-vps.py:42)
- scripts.lsf-vps.fingerprint (scripts/lsf-vps.py:149)
- scripts.lsf-vps.publish_snapshot (scripts/lsf-vps.py:49)
- scripts.lsf-vps.remote (scripts/lsf-vps.py:34)
- scripts.lsf-vps.run (scripts/lsf-vps.py:30)

## start
<!-- sig:642bec26 -->

**What it does:** Starts a separate remote Claude session without a task, or preserves the session already running.

**Expects:**
- p (dict): the project locations returned by paths
- model (str): the requested Claude model, normally sonnet

**Gives back:** nothing

**Used by:**
- scripts.lsf-vps.main (scripts/lsf-vps.py:277)

**Depends on:**
- scripts.lsf-vps.remote (scripts/lsf-vps.py:34)

## dashboard
<!-- sig:c16b3db1 -->

**What it does:** Connects the remote dashboard to a local address and can open its approval page privately.

**Expects:**
- p (dict): the project locations returned by paths
- port (int): the local browser port, such as 8890
- open_browser (bool): whether to open the owner approval page

**Gives back:** nothing

**Used by:**
- scripts.lsf-vps.main (scripts/lsf-vps.py:281)

**Depends on:**
- scripts.lsf-vps.remote (scripts/lsf-vps.py:34)
- scripts.lsf-vps.run (scripts/lsf-vps.py:30)

## main
<!-- sig:ff123372 -->

**What it does:** Reads the requested action and calls the matching project helper.

**Expects:** nothing

**Gives back:** nothing

**Used by:**
- scripts.lsf-vps.<module> (scripts/lsf-vps.py:295)

**Depends on:**
- scripts.lsf-vps.dashboard (scripts/lsf-vps.py:218)
- scripts.lsf-vps.fingerprint (scripts/lsf-vps.py:149)
- scripts.lsf-vps.paths (scripts/lsf-vps.py:20)
- scripts.lsf-vps.pin_runtime (scripts/lsf-vps.py:65)
- scripts.lsf-vps.prepare (scripts/lsf-vps.py:118)
- scripts.lsf-vps.remote (scripts/lsf-vps.py:34)
- scripts.lsf-vps.run (scripts/lsf-vps.py:30)
- scripts.lsf-vps.snapshot (scripts/lsf-vps.py:166)
- scripts.lsf-vps.start (scripts/lsf-vps.py:202)
