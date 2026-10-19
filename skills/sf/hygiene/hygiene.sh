#!/usr/bin/env bash
# hygiene.sh - disk and memory hygiene for long autonomous build-loop runs.
#
#   hygiene.sh scan  [--agents N]                 read-only report; exit 0 ok, 1 warn, 2 act, 3 emergency
#   hygiene.sh plan  [--emergency] [--out FILE]   read-only; writes a JSON plan of exactly what apply may do
#   hygiene.sh apply PLAN [--execute] [--approve ID,ID]
#                                                 re-verifies every item; dry-run unless --execute
#   hygiene.sh register PID [label]               record a run-owned process (PID + start time + command line)
#
# Global options (before the subcommand): --repo DIR, --profile FILE.
# macOS-first. No sudo, no network. Never deletes branches. Never force-removes worktrees.
# Policy and design: see DESIGN.md next to this file. Config: "## Hygiene" in .claude/build-loop.md.
set -euo pipefail
command -v python3 >/dev/null || { echo "hygiene.sh: python3 required" >&2; exit 64; }
SRC="$(awk 'f{print} /^__PYTHON__$/{f=1}' "$0")"
exec python3 -c "$SRC" "$@"
exit 0
__PYTHON__
import os, sys, re, json, time, glob, fnmatch, argparse, subprocess, datetime, shutil

GB = 1024 ** 3
LEVELS = ["ok", "warn", "act", "emergency"]
DEFAULTS = dict(
    protected=[], scratch_dirs=[], scratch_max_age_days=3, worktree_roots=[".claude/worktrees"],
    cache_names=[".next", "dist", ".vitest", ".turbo"], protected_branches=[],
    disk_warn_gb=20, disk_act_gb=10, disk_emergency_gb=3,
    disk_warn_pct=15, disk_act_pct=8, disk_emergency_pct=3,
    mem_warn_free_pct=25, mem_crit_free_pct=10, ports=[], process_patterns=[],
    run_registry=".claude/run-registry.tsv", shared_build_dir="target",
    worktree_min_age_min=20, agent_headroom_gb=3, log="~/.claude/hygiene/hygiene.log",
)
LIST_KEYS = {"protected", "scratch_dirs", "worktree_roots", "cache_names", "protected_branches", "ports", "process_patterns"}
INT_KEYS = {k for k, v in DEFAULTS.items() if isinstance(v, (int, float))}
# Denylist: basenames that are never deleted and never allow their container to be deleted.
DENY_NAMES = [".env", ".env.*", "*.env", "*.pem", "*.key", "id_rsa*", "id_ed25519*", "keys", "keypair*.json",
              "*-keypair.json", "evidence", "memory", ".ssh", ".gnupg", "credentials*", "secrets", "secrets.*"]
DENY_PATHS_HOME = ["~/.config/solana", "~/.ssh", "~/.gnupg", "~/.claude/projects"]
ALLOW_IGNORED = {"target", "node_modules", ".next", "dist", ".vitest", ".turbo", ".DS_Store"}
PRUNE = {".git", "node_modules", "target"}


def sh(cmd, cwd=None, timeout=120):
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout,
                           env=dict(os.environ, GIT_OPTIONAL_LOCKS="0"))
        return r.returncode, r.stdout, r.stderr
    except Exception as e:  # missing binary, timeout
        return 127, "", str(e)


def gib(n):
    return "%.1f GB" % (n / GB) if n >= GB / 10 else "%.0f MB" % (n / 1048576)


def now():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


# ---------------------------------------------------------------- context
class Ctx:
    def __init__(self, repo, profile):
        start = os.path.realpath(repo or os.getcwd())
        rc, out, err = sh(["git", "-C", start, "rev-parse", "--path-format=absolute", "--git-common-dir"])
        if rc != 0:
            die("not inside a git repository: %s" % start)
        self.main = os.path.dirname(os.path.realpath(out.strip()))
        self.profile_path = profile or os.path.join(self.main, ".claude", "build-loop.md")
        self.cfg = self.load_cfg()
        c = self.cfg
        self.scratch = [os.path.realpath(os.path.expanduser(p)) for p in c["scratch_dirs"]]
        self.roots = [os.path.realpath(self.rel(p)) for p in c["worktree_roots"]]
        self.registry = self.rel(c["run_registry"])
        self.shared_target = os.path.realpath(self.rel(c["shared_build_dir"]))
        self.log_path = os.path.expanduser(os.environ.get("HYGIENE_LOG", c["log"]))
        self._cwds = None
        self._wts = None

    def rel(self, p):
        p = os.path.expanduser(p)
        return p if os.path.isabs(p) else os.path.join(self.main, p)

    def load_cfg(self):
        cfg = dict(DEFAULTS)
        cfg["_has_section"] = False
        try:
            lines = open(self.profile_path, encoding="utf-8").read().splitlines()
        except OSError:
            return cfg
        sect, on = [], False
        for ln in lines:
            if re.match(r"^##\s+Hygiene\b", ln):
                on = True
                continue
            if on and re.match(r"^##\s", ln):
                break
            if on:
                sect.append(ln)
        if not on:
            return cfg
        cfg["_has_section"] = True
        for ln in sect:
            m = re.match(r"^\s*(?:[-*]\s*)?`?([a-z_]+)`?\s*[:=]\s*(.*?)\s*$", ln)
            if not m or m.group(1) not in DEFAULTS:
                continue
            k, v = m.group(1), m.group(2).strip().strip("`")
            if k in LIST_KEYS:
                cfg[k] = [x.strip().strip("`") for x in re.split(r"\s*,\s*", v) if x.strip()] if k != "process_patterns" \
                    else [x.strip().strip("`") for x in v.split(" ;; ") if x.strip()]
            elif k in INT_KEYS:
                try:
                    cfg[k] = float(v) if "." in v else int(v)
                except ValueError:
                    pass
            else:
                cfg[k] = v
        return cfg

    # --- worktrees
    def worktrees(self):
        if self._wts is not None:
            return self._wts
        rc, out, _ = sh(["git", "-C", self.main, "worktree", "list", "--porcelain"])
        wts, cur = [], None
        for ln in out.splitlines() + [""]:
            if not ln:
                if cur:
                    wts.append(cur)
                cur = None
            elif ln.startswith("worktree "):
                cur = dict(path=os.path.realpath(ln[9:]), branch=None, head=None, locked=None, prunable=False)
            elif cur is not None:
                if ln.startswith("HEAD "):
                    cur["head"] = ln[5:]
                elif ln.startswith("branch "):
                    cur["branch"] = ln[7:].replace("refs/heads/", "")
                elif ln == "locked" or ln.startswith("locked "):
                    cur["locked"] = ln[7:] or "(no reason)"
                elif ln.startswith("prunable"):
                    cur["prunable"] = True
        self._wts = wts
        return wts

    def linked(self):
        return [w for w in self.worktrees() if w["path"] != self.main]

    def wt_for(self, path):
        best = None
        for w in self.linked():
            if path == w["path"] or path.startswith(w["path"] + "/"):
                if best is None or len(w["path"]) > len(best["path"]):
                    best = w
        return best

    def prot_branches(self):
        c = self.cfg["protected_branches"]
        if not c:
            first = self.worktrees()[0] if self.worktrees() else {}
            c = [b for b in [first.get("branch"), "main", "master"] if b]
        out = []
        for b in dict.fromkeys(c):
            if sh(["git", "-C", self.main, "rev-parse", "--verify", "-q", "refs/heads/" + b])[0] == 0:
                out.append(b)
        return out

    # --- processes
    def cwds(self):
        if self._cwds is None:
            rc, out, _ = sh(["lsof", "-a", "-d", "cwd", "-Fpn"], timeout=60)
            res, pid = [], None
            for ln in out.splitlines():
                if ln.startswith("p"):
                    pid = int(ln[1:])
                elif ln.startswith("n") and pid:
                    res.append((pid, ln[1:]))
            self._cwds = res
        return self._cwds

    def in_use(self, path):
        for pid, d in self.cwds():
            if d == path or d.startswith(path + "/"):
                return pid
        return None

    # --- protection
    def deny_hit(self, path):
        """Return a reason string if path itself (or a parent below main) is on the denylist, else None."""
        p = path
        for hp in DENY_PATHS_HOME:
            hp = os.path.realpath(os.path.expanduser(hp))
            if p == hp or p.startswith(hp + "/") or hp.startswith(p + "/"):
                return "denylist path " + hp
        if p == self.main or self.main.startswith(p + "/"):
            return "main checkout"
        if p == os.path.join(self.main, ".git") or p.startswith(os.path.join(self.main, ".git") + "/"):
            return "main checkout .git"
        if p == os.path.join(self.main, ".claude", "worktrees"):
            return "worktrees root"
        for g in self.cfg["protected"]:
            if self.glob_match(p, g):
                return "protected glob " + g
        return None

    def glob_match(self, p, g):
        g = os.path.expanduser(g)
        if os.path.isabs(g):
            pats = [g, g.rstrip("/") + "/*"]
        else:
            pats = [os.path.join(self.main, g), os.path.join(self.main, g).rstrip("/") + "/*", "*/" + g, "*/" + g.rstrip("/") + "/*"]
        return any(fnmatch.fnmatch(p, x) for x in pats)

    def name_denied(self, name):
        return any(fnmatch.fnmatch(name, d) for d in DENY_NAMES)

    # --- logging
    def log(self, **kw):
        try:
            os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
            with open(self.log_path, "a") as f:
                f.write(json.dumps(dict(ts=now(), repo=self.main, **kw)) + "\n")
        except OSError as e:
            print("warning: cannot write log: %s" % e, file=sys.stderr)


def die(msg, code=64):
    print("hygiene.sh: " + msg, file=sys.stderr)
    sys.exit(code)


# ---------------------------------------------------------------- measurement
def walk(path, scan_prune=PRUNE):
    """Hard-link-aware size walk. Returns dict(du, reclaim, newest, deny, files).
    du = bytes of unique inodes (like du). reclaim = bytes of inodes whose every link lies inside `path`.
    newest/deny only look outside scan_prune directory names (build output, VCS, deps)."""
    seen, nlink, cnt = {}, {}, {}
    newest, deny = 0.0, []
    stack = [(path, False)]
    while stack:
        d, pruned = stack.pop()
        try:
            it = os.scandir(d)
        except OSError:
            continue
        with it:
            for e in it:
                try:
                    st = e.stat(follow_symlinks=False)
                except OSError:
                    continue
                isdir = e.is_dir(follow_symlinks=False)
                if not pruned:
                    newest = max(newest, st.st_mtime)
                    if any(fnmatch.fnmatch(e.name, x) for x in DENY_NAMES):
                        deny.append(e.path)
                if isdir:
                    stack.append((e.path, pruned or e.name in scan_prune))
                else:
                    k = (st.st_dev, st.st_ino)
                    cnt[k] = cnt.get(k, 0) + 1
                    nlink[k] = st.st_nlink
                    seen[k] = st.st_blocks * 512
    du = sum(seen.values())
    rec = sum(sz for k, sz in seen.items() if cnt[k] >= nlink[k])
    return dict(du=du, reclaim=rec, newest=newest, deny=deny)


def disk_free(path):
    u = shutil.disk_usage(path)
    return u.free, u.total


def disk_level(cfg, free, total):
    pct = 100.0 * free / total if total else 100
    fg = free / GB
    if fg < cfg["disk_emergency_gb"] or pct < cfg["disk_emergency_pct"]:
        return 3
    if fg < cfg["disk_act_gb"] or pct < cfg["disk_act_pct"]:
        return 2
    if fg < cfg["disk_warn_gb"] or pct < cfg["disk_warn_pct"]:
        return 1
    return 0


def memory(cfg):
    m = dict(level=0, free_pct=None, swap=None, source=[])
    fake = os.environ.get("HYGIENE_FAKE_MEM_LEVEL")  # test hook: 0 normal, 1 warn, 2 critical
    if fake in ("0", "1", "2"):
        m["level"] = int(fake)
        m["source"].append("FAKE level via HYGIENE_FAKE_MEM_LEVEL")
        return m
    rc, out, _ = sh(["sysctl", "-n", "kern.memorystatus_vm_pressure_level"])
    if rc == 0 and out.strip().isdigit():
        m["level"] = {1: 0, 2: 1, 4: 2}.get(int(out.strip()), 0)
        m["source"].append("sysctl=%s" % out.strip())
    rc, out, _ = sh(["memory_pressure"], timeout=20)
    mm = re.search(r"free percentage:\s*(\d+)%", out)
    if mm:
        m["free_pct"] = int(mm.group(1))
        m["source"].append("memory_pressure=%d%% free" % m["free_pct"])
        if m["free_pct"] < cfg["mem_crit_free_pct"]:
            m["level"] = max(m["level"], 2)
        elif m["free_pct"] < cfg["mem_warn_free_pct"]:
            m["level"] = max(m["level"], 1)
    rc, out, _ = sh(["sysctl", "-n", "vm.swapusage"])
    if rc == 0:
        m["swap"] = out.strip()
    return m


# ---------------------------------------------------------------- git helpers
def git(ctx, wt, *args):
    return sh(["git", "-C", wt] + list(args))


def wt_state(ctx, w):
    """Returns dict: dirty, ignored(list of top-level ignored paths), merged, unique, why."""
    p = w["path"]
    rc, out, err = git(ctx, p, "status", "--porcelain=v1", "--ignored", "-z")
    st = dict(ok=rc == 0, dirty=[], ignored=[], merged=False, unique=None)
    if rc != 0:
        st["why"] = "git status failed: " + err.strip()[:80]
        return st
    ent = out.split("\0")
    i = 0
    while i < len(ent):
        e = ent[i]
        i += 1
        if len(e) < 4:
            continue
        x, path = e[:2], e[3:]
        if x[0] in "RC":
            i += 1
        if x == "!!":
            st["ignored"].append(path.rstrip("/"))
        else:
            st["dirty"].append(path)
    head = git(ctx, p, "rev-parse", "HEAD")[1].strip()
    for b in ctx.prot_branches():
        if git(ctx, p, "merge-base", "--is-ancestor", head, "refs/heads/" + b)[0] == 0:
            st["merged"] = True
            st["via"] = "ancestor of " + b
            break
        rc, out, _ = git(ctx, p, "cherry", "refs/heads/" + b, head)
        if rc == 0 and not any(l.startswith("+") for l in out.splitlines()):
            st["merged"] = True
            st["via"] = "all commits patch-equivalent on " + b + " (git cherry)"
            break
    if not st["merged"]:
        b = (ctx.prot_branches() or ["HEAD"])[0]
        rc, out, _ = git(ctx, p, "cherry", "refs/heads/" + b, head)
        st["unique"] = sum(1 for l in out.splitlines() if l.startswith("+")) if rc == 0 else None
    return st


def wt_age_min(ctx, w):
    ts = []
    p = w["path"]
    for f in (os.path.join(p, ".git"),):
        try:
            ts.append(os.stat(f).st_mtime)
        except OSError:
            pass
    rc, out, _ = git(ctx, p, "rev-parse", "--absolute-git-dir")
    if rc == 0:
        for n in ("HEAD", "index", "logs/HEAD"):
            try:
                ts.append(os.stat(os.path.join(out.strip(), n)).st_mtime)
            except OSError:
                pass
    return (time.time() - max(ts)) / 60 if ts else 0


def is_ignored_untracked(ctx, container, path):
    if git(ctx, container, "check-ignore", "-q", "--no-index", path)[0] != 0:
        return False
    rc, out, _ = git(ctx, container, "ls-files", "--", path)
    return rc == 0 and not out.strip()


def find_named(root, names, skip=()):
    """Find directories named in `names` under root, not descending into matches, .git, or skip paths."""
    found, stack = [], [root]
    while stack:
        d = stack.pop()
        try:
            it = os.scandir(d)
        except OSError:
            continue
        with it:
            for e in it:
                try:
                    if not e.is_dir(follow_symlinks=False):
                        continue
                except OSError:
                    continue
                if e.path in skip or e.name == ".git":
                    continue
                if e.name in names:
                    found.append(e.path)
                elif e.name != "node_modules" or "node_modules" in names:
                    stack.append(e.path)
    return found


# ---------------------------------------------------------------- verification (shared by plan and apply)
def classify_in_wt(path):
    b = os.path.basename(path)
    return "worktree_target" if b == "target" else "worktree_node_modules" if b == "node_modules" else "cache"


def verify(ctx, item, emergency, approved):
    """Re-check every precondition now. Returns (ok, reason, extra)."""
    cls, path = item.get("class"), item.get("path", "")
    cfg = ctx.cfg
    if cls == "process":
        return verify_process(ctx, item)
    if cls not in ("worktree", "worktree_target", "worktree_node_modules", "cache", "scratch", "shared_target"):
        return False, "class %r is not on the allowlist" % cls, {}
    if not path or not os.path.isabs(path):
        return False, "path not absolute", {}
    if os.path.islink(path) or not os.path.isdir(path):
        return False, "path missing, not a directory, or a symlink", {}
    if os.path.realpath(path) != path:
        return False, "path is not canonical", {}
    r = ctx.deny_hit(path)
    if r:
        return False, "protected: " + r, {}
    pid = ctx.in_use(path)
    if pid:
        return False, "a process (pid %d) has its working directory inside" % pid, {}
    extra = {}

    if cls == "worktree":
        w = next((x for x in ctx.linked() if x["path"] == path), None)
        if not w:
            return False, "not a linked worktree of this repo", {}
        if not any(path.startswith(rt + "/") for rt in ctx.roots):
            return False, "outside configured worktree_roots (not an agent worktree)", {}
        if w["locked"]:
            return False, "worktree is locked: " + w["locked"], {}
        age = wt_age_min(ctx, w)
        if age < cfg["worktree_min_age_min"]:
            return False, "worktree touched %.0f min ago (< %s min)" % (age, cfg["worktree_min_age_min"]), {}
        st = wt_state(ctx, w)
        if not st["ok"]:
            return False, st["why"], {}
        if st["dirty"]:
            return False, "dirty: %d uncommitted/untracked paths (e.g. %s)" % (len(st["dirty"]), st["dirty"][0]), {}
        if not st["merged"]:
            return False, "HEAD has %s commits not on a protected branch" % (st["unique"] if st["unique"] is not None else "unknown"), {}
        unk = [i for i in st["ignored"] if os.path.basename(i) not in ALLOW_IGNORED and os.path.basename(i) not in cfg["cache_names"]]
        if unk:
            return False, "ignored files not on the allowlist would be lost: " + ", ".join(unk[:4]), {}
        extra["via"] = st["via"]
        return True, "clean, merged (%s)" % st["via"], extra

    if cls in ("worktree_target", "worktree_node_modules", "cache"):
        w = ctx.wt_for(path)
        base = os.path.basename(path)
        if cls != classify_in_wt(path) and w:
            return False, "class does not match directory name", {}
        if cls == "cache" and base not in cfg["cache_names"]:
            return False, "%s is not an allowlisted cache name" % base, {}
        if cls == "worktree_target" and base != "target" or cls == "worktree_node_modules" and base != "node_modules":
            return False, "class does not match directory name", {}
        if cls != "cache" and not w:
            return False, "target/node_modules only deletable inside a linked worktree", {}
        if path == ctx.shared_target or path.startswith(ctx.shared_target + "/"):
            return False, "is the shared build directory", {}
        if w:
            if w["locked"]:
                return False, "worktree is locked: " + w["locked"], {}
            if not any(w["path"].startswith(rt + "/") for rt in ctx.roots):
                return False, "outside configured worktree_roots", {}
            if ctx.in_use(w["path"]):
                return False, "a process has its working directory inside the worktree", {}
            if not emergency:
                st = wt_state(ctx, w)
                if not st["ok"] or st["dirty"] or not st["merged"]:
                    return False, "worktree is not clean and merged (only emergency mode clears caches elsewhere)", {}
            container = w["path"]
        else:
            if not path.startswith(ctx.main + "/"):
                return False, "outside main checkout", {}
            if not emergency and not approved:
                return False, "main-checkout cache needs approval (or emergency mode)", {}
            container = ctx.main
        if not is_ignored_untracked(ctx, container, path):
            return False, "not git-ignored, or contains tracked files", {}
        return True, "regenerable build output", {}

    if cls == "shared_target":
        if path != ctx.shared_target:
            return False, "not the configured shared build dir", {}
        if not (emergency and approved):
            return False, "shared build dir needs emergency mode and explicit approval", {}
        rc, out, _ = sh(["ps", "-axww", "-o", "comm="])
        if any(os.path.basename(l.strip()) in ("cargo", "rustc") for l in out.splitlines()):
            return False, "cargo/rustc is running", {}
        return True, "shared build dir, no cargo/rustc running", {}

    if cls == "scratch":
        parent = os.path.dirname(path)
        if parent not in ctx.scratch:
            return False, "parent is not a configured scratch dir", {}
        if os.path.isfile(os.path.join(path, ".git")):
            return False, "is a git worktree checkout; handled as a worktree", {}
        info = walk(path)
        if info["deny"]:
            return False, "contains denylisted names: " + ", ".join(os.path.basename(x) for x in info["deny"][:4]), {}
        for e in os.listdir(path):
            if ctx.deny_hit(os.path.join(path, e)):
                return False, "contains protected path " + e, {}
        age_d = (time.time() - info["newest"]) / 86400 if info["newest"] else 999
        need = cfg["scratch_max_age_days"]
        if age_d < need:
            if not (emergency and age_d * 24 >= 1 and approved):
                return False, "newest file %.1f days old (< %s days)" % (age_d, need), {}
        if os.path.isdir(os.path.join(path, ".git")):
            head = git(ctx, path, "rev-parse", "HEAD")[1].strip()
            known = head and git(ctx, ctx.main, "cat-file", "-e", head + "^{commit}")[0] == 0
            merged = known and any(git(ctx, ctx.main, "merge-base", "--is-ancestor", head, "refs/heads/" + b)[0] == 0
                                   for b in ctx.prot_branches())
            if not merged and not approved:
                return False, "scratch repo HEAD not in protected history (possible unique commits); needs approval", {}
        return True, "scratch dir, newest file %.1f days old" % age_d, {}
    return False, "unreachable", {}


def verify_process(ctx, item):
    try:
        pid = int(item["pid"])
    except (KeyError, ValueError):
        return False, "bad pid", {}
    if pid <= 1 or pid in ancestors():
        return False, "refusing pid %d (init or own process chain)" % pid, {}
    live = ps_row(pid)
    if not live:
        return False, "pid %d no longer exists" % pid, {}
    reg = load_registry(ctx).get(pid)
    if not reg:
        return False, "pid %d is not in the run registry" % pid, {}
    if live["lstart"] != reg["lstart"]:
        return False, "pid %d start time differs from registration (pid reused)" % pid, {}
    if live["command"] != reg["command"]:
        return False, "pid %d command line changed since registration (now: %s)" % (pid, live["command"][:70]), {}
    if item.get("command") and item["command"] != live["command"]:
        return False, "pid %d command line differs from the plan" % pid, {}
    return True, "registered, start time and command line match", {}


def ancestors():
    out, pid = {os.getpid()}, os.getppid()
    for _ in range(30):
        if pid <= 1 or pid in out:
            break
        out.add(pid)
        rc, o, _ = sh(["ps", "-o", "ppid=", "-p", str(pid)])
        try:
            pid = int(o.strip())
        except ValueError:
            break
    return out


PS_RE = re.compile(r"^\s*(\d+)\s+(\w{3} \w{3}\s+\d+ [\d:]{8} \d{4})\s+(.*)$")


def ps_all():
    rc, out, _ = sh(["ps", "-axww", "-o", "pid=,lstart=,command="])
    rows = {}
    for ln in out.splitlines():
        m = PS_RE.match(ln)
        if m:
            rows[int(m.group(1))] = dict(pid=int(m.group(1)), lstart=m.group(2), command=m.group(3))
    return rows


def ps_row(pid):
    rc, out, _ = sh(["ps", "-ww", "-o", "pid=,lstart=,command=", "-p", str(pid)])
    for ln in out.splitlines():
        m = PS_RE.match(ln)
        if m and int(m.group(1)) == pid:
            return dict(pid=pid, lstart=m.group(2), command=m.group(3))
    return None


def load_registry(ctx):
    reg = {}
    try:
        for ln in open(ctx.registry):
            f = ln.rstrip("\n").split("\t")
            if len(f) >= 3 and f[0].isdigit():
                reg[int(f[0])] = dict(pid=int(f[0]), lstart=f[1], command=f[2], label=f[3] if len(f) > 3 else "")
    except OSError:
        pass
    return reg


# ---------------------------------------------------------------- scan
def cmd_scan(ctx, a):
    c = ctx.cfg
    free, total = disk_free(ctx.main)
    dl = disk_level(c, free, total)
    mem = memory(c)
    print("hygiene scan  repo=%s  profile=%s" % (ctx.main, "## Hygiene found" if c["_has_section"] else "no ## Hygiene section (defaults)"))
    print("DISK   free %s of %s (%.1f%% free)  level=%s" % (gib(free), gib(total), 100.0 * free / total, LEVELS[dl]))
    print("       thresholds: warn <%sGB|<%s%%, act <%sGB|<%s%%, emergency <%sGB|<%s%%" % (
        c["disk_warn_gb"], c["disk_warn_pct"], c["disk_act_gb"], c["disk_act_pct"], c["disk_emergency_gb"], c["disk_emergency_pct"]))
    print("MEMORY level=%s  %s  swap: %s" % (["normal", "warn", "critical"][mem["level"]], ", ".join(mem["source"]) or "n/a", mem["swap"] or "n/a"))
    code = max(dl, 2 if mem["level"] == 2 else mem["level"] if mem["level"] else 0)
    if a.agents:
        need = a.agents * c["agent_headroom_gb"] * GB
        ok = free - need >= c["disk_act_gb"] * GB
        print("PREFLIGHT %d agents x %s GB headroom = %.0f GB; free after = %.1f GB (must stay >= %s GB): %s" % (
            a.agents, c["agent_headroom_gb"], need / GB, (free - need) / GB, c["disk_act_gb"], "OK" if ok else "INSUFFICIENT"))
        if not ok:
            code = max(code, 2)
    print("WORKTREES (du is an upper bound: hard links to shared stores are counted per tree)")
    for w in ctx.linked():
        p = w["path"]
        short = os.path.relpath(p, ctx.main) if p.startswith(ctx.main) else p
        if w["locked"]:
            print("  %-48s LOCKED (%s)" % (short, w["locked"][:70]))
            continue
        st = wt_state(ctx, w)
        rc, out, _ = sh(["du", "-sk", p], timeout=300)
        kb = int(out.split()[0]) * 1024 if rc == 0 and out.split() else 0
        flags = []
        flags.append("dirty" if st["dirty"] else "clean")
        flags.append("merged" if st["merged"] else "UNIQUE-COMMITS(%s)" % st["unique"])
        flags.append("agent-root" if any(p.startswith(r + "/") for r in ctx.roots) else "not-agent-root")
        pid = ctx.in_use(p)
        if pid:
            flags.append("in-use pid %d" % pid)
        print("  %-48s %8s  %s" % (short, gib(kb), " ".join(flags)))
    if not ctx.linked():
        print("  (none)")
    print("SCRATCH")
    if not ctx.scratch:
        print("  (no scratch_dirs configured: nothing scratch-related is ever deleted)")
    for s in ctx.scratch:
        if not os.path.isdir(s):
            print("  %s (missing)" % s)
            continue
        kids = [os.path.join(s, e) for e in sorted(os.listdir(s))]
        rc, out, _ = sh(["du", "-sk", s], timeout=300)
        print("  %s  %d entries  du %s" % (s, len(kids), gib(int(out.split()[0]) * 1024) if rc == 0 and out.split() else "?"))
    print("PROCESSES")
    reg = load_registry(ctx)
    rows = ps_all()
    live = mism = dead = 0
    for pid, r in reg.items():
        lv = rows.get(pid)
        if not lv:
            dead += 1
        elif lv["lstart"] == r["lstart"] and lv["command"] == r["command"]:
            live += 1
        else:
            mism += 1
            print("  registry pid %d (%s): live command differs; will NOT be killed" % (pid, r["label"]))
    print("  registry %s: %d live+matching, %d changed/reused, %d dead" % (ctx.registry, live, mism, dead))
    pats = [re.compile(x) for x in c["process_patterns"]]
    unreg = [r for r in rows.values() if r["pid"] not in ancestors() and any(p.search(r["command"]) for p in pats) and r["pid"] not in reg]
    if unreg:
        print("  %d process(es) match process_patterns but are NOT in the registry (never killed):" % len(unreg))
        for r in unreg[:8]:
            print("    pid %d  %s" % (r["pid"], r["command"][:90]))
    for port in c["ports"]:
        rc, out, _ = sh(["lsof", "-nP", "-iTCP:%s" % port, "-sTCP:LISTEN", "-Fpc"])
        pids = [int(l[1:]) for l in out.splitlines() if l.startswith("p")]
        if not pids:
            print("  port %s: free" % port)
        for pid in pids:
            tag = "registered (run-owned)" if pid in reg else "NOT registered: foreign listener, do not reuse or kill"
            print("  port %s: pid %d %s" % (port, pid, tag))
    print("RESULT level=%s exit=%d" % (LEVELS[code], code))
    return code


# ---------------------------------------------------------------- plan
def cmd_plan(ctx, a):
    c = ctx.cfg
    emer = a.emergency
    free, total = disk_free(ctx.main)
    mem = memory(c)
    items, skipped = [], []

    def add(cls, path, reason, info, judgment=False, **kw):
        items.append(dict(cls_=cls, **{"class": cls}, path=path, reason=reason, du_bytes=info["du"],
                          reclaim_bytes=info["reclaim"], needs_judgment=judgment, approved=False, **kw))

    def skip(path, reason):
        skipped.append(dict(path=path, reason=reason))

    # --- worktrees
    for w in ctx.linked():
        p = w["path"]
        ok, why, ex = verify(ctx, dict({"class": "worktree", "path": p}), emer, False)
        if ok:
            add("worktree", p, "remove merged worktree: " + why + "; branch %s is kept" % (w["branch"] or "(detached)"), walk(p))
            continue
        skip(p, "worktree kept: " + why)
        if w["locked"] or ctx.in_use(p) or not any(p.startswith(r + "/") for r in ctx.roots):
            continue
        st = wt_state(ctx, w)
        if not st["ok"]:
            continue
        clean_merged = st["merged"] and not st["dirty"]
        if not (clean_merged or emer):
            continue
        if wt_age_min(ctx, w) < c["worktree_min_age_min"]:
            continue
        for d in find_named(p, {"target", "node_modules"} | set(c["cache_names"])):
            cls = classify_in_wt(d)
            ok2, why2, _ = verify(ctx, {"class": cls, "path": d}, emer, False)
            if ok2:
                add(cls, d, "regenerable %s in kept worktree (%s)" % (os.path.basename(d), "merged" if clean_merged else "emergency"), walk(d))
            else:
                skip(d, why2)
    # --- caches in main checkout
    prune = {w["path"] for w in ctx.linked()} | {ctx.shared_target}
    for d in find_named(ctx.main, set(c["cache_names"]), skip=prune):
        ok, why, _ = verify(ctx, {"class": "cache", "path": d}, emer, False)
        if ok:
            add("cache", d, "regenerable build cache in main checkout (emergency)", walk(d))
        else:
            ok2, _, _ = verify(ctx, {"class": "cache", "path": d}, True, True)
            if ok2:
                add("cache", d, "regenerable build cache in main checkout; rebuild cost is yours to weigh", walk(d), judgment=True)
            else:
                skip(d, why)
    # --- shared target (emergency, judgment only)
    if emer and os.path.isdir(ctx.shared_target):
        ok, why, _ = verify(ctx, {"class": "shared_target", "path": ctx.shared_target}, True, True)
        if ok:
            add("shared_target", ctx.shared_target, "shared build dir: wipes every agent's incremental build; last resort", walk(ctx.shared_target), judgment=True)
        else:
            skip(ctx.shared_target, why)
    # --- scratch
    for s in ctx.scratch:
        if not os.path.isdir(s):
            continue
        for e in sorted(os.listdir(s)):
            p = os.path.join(s, e)
            if os.path.islink(p) or not os.path.isdir(p):
                continue
            p = os.path.realpath(p)
            ok, why, _ = verify(ctx, {"class": "scratch", "path": p}, emer, False)
            if ok:
                add("scratch", p, why, walk(p))
                continue
            if "possible unique commits" in why:
                add("scratch", p, "old scratch repo; " + why, walk(p), judgment=True)
                continue
            if emer:
                ok2, why2, _ = verify(ctx, {"class": "scratch", "path": p}, True, True)
                if ok2:
                    add("scratch", p, "emergency: younger than scratch_max_age_days but over 1 hour old", walk(p), judgment=True)
                    continue
            skip(p, why)
    # --- processes
    reg = load_registry(ctx)
    pressure = mem["level"] >= 1 or emer
    for pid, r in reg.items():
        ok, why, _ = verify_process(ctx, dict(pid=pid))
        if ok:
            if pressure:
                items.append({"class": "process", "pid": pid, "path": "pid:%d" % pid, "command": r["command"], "label": r["label"],
                              "reason": "run-owned process (%s); memory %s%s" % (r["label"] or "unlabelled", ["normal", "warn", "critical"][mem["level"]], ", emergency" if emer else ""),
                              "du_bytes": 0, "reclaim_bytes": 0, "needs_judgment": mem["level"] < 2 and not emer, "approved": False})
        elif ps_row(pid):
            skip("pid:%d" % pid, why)
    for i, it in enumerate(sorted(items, key=lambda x: -x["reclaim_bytes"]), 1):
        it["id"] = i
    items.sort(key=lambda x: x["id"])
    for it in items:
        it.pop("cls_", None)
    plan = dict(version=1, created=now(), repo=ctx.main, mode="emergency" if emer else "normal",
                free_bytes_before=free, disk_level=LEVELS[disk_level(c, free, total)], memory_level=mem["level"],
                total_reclaim_bytes=sum(i["reclaim_bytes"] for i in items if not i["needs_judgment"]),
                total_reclaim_judgment_bytes=sum(i["reclaim_bytes"] for i in items if i["needs_judgment"]),
                note="reclaim_bytes counts only inodes whose every hard link is inside the item; APFS clones are not detectable and may make it an over-estimate",
                items=items, skipped=skipped)
    out = a.out or os.path.join(os.environ.get("TMPDIR", "/tmp"), "hygiene-plan-%s.json" % time.strftime("%Y%m%d-%H%M%S"))
    with open(out, "w") as f:
        json.dump(plan, f, indent=2)
    print("hygiene plan  mode=%s  disk free %s (%s)  memory=%s" % (plan["mode"], gib(free), plan["disk_level"], ["normal", "warn", "critical"][mem["level"]]))
    for it in items:
        print("  #%-2d %-22s %9s  %s%s\n        %s" % (it["id"], it["class"], gib(it["reclaim_bytes"]) if it["class"] != "process" else "-",
                                                      it["path"], "   [NEEDS JUDGMENT]" if it["needs_judgment"] else "", it["reason"]))
    print("  skipped/protected: %d" % len(skipped))
    for s in skipped:
        print("    - %s: %s" % (s["path"], s["reason"]))
    print("  auto reclaim ~%s, plus ~%s if judgment items are approved (hard-link aware)" % (gib(plan["total_reclaim_bytes"]), gib(plan["total_reclaim_judgment_bytes"])))
    print("PLAN %s" % out)
    ctx.log(event="plan", file=out, mode=plan["mode"], items=len(items), skipped=len(skipped))
    return 0


# ---------------------------------------------------------------- apply
def cmd_apply(ctx, a):
    try:
        plan = json.load(open(a.plan))
    except (OSError, ValueError) as e:
        die("cannot read plan file: %s" % e)
    if plan.get("version") != 1 or "items" not in plan:
        die("not a hygiene plan")
    if os.path.realpath(plan.get("repo", "")) != ctx.main:
        die("plan was made for a different repo (%s)" % plan.get("repo"))
    age_h = (time.time() - datetime.datetime.fromisoformat(plan["created"]).timestamp()) / 3600
    if age_h > 6:
        die("plan is %.1f hours old; re-run plan" % age_h)
    emer = plan.get("mode") == "emergency"
    approve = {int(x) for x in (a.approve or "").split(",") if x.strip()}
    free0, _ = disk_free(ctx.main)
    done, skipped, failed = [], [], []
    ctx.log(event="apply_start", plan=a.plan, execute=a.execute, mode=plan.get("mode"), free_bytes=free0)
    for it in plan["items"]:
        label = "#%s %s %s" % (it.get("id"), it.get("class"), it.get("path"))
        approved = bool(it.get("approved")) or it.get("id") in approve
        if it.get("needs_judgment") and not approved:
            skipped.append((label, "needs judgment; not approved"))
            ctx.log(event="skip", item=label, reason="needs judgment, not approved")
            continue
        ctx.log_cwd = None
        ctx._cwds = None  # re-read working directories: state may have changed since plan time
        ctx._wts = None
        ok, why, _ = verify(ctx, it, emer, approved)
        if not ok:
            skipped.append((label, "re-verification failed: " + why))
            ctx.log(event="refuse", item=label, reason=why)
            continue
        if not a.execute:
            done.append((label, "would remove (dry-run); " + why))
            continue
        err = execute(ctx, it)
        if err:
            failed.append((label, err))
            ctx.log(event="fail", item=label, error=err)
        else:
            done.append((label, why))
            ctx.log(event="removed", item=label, reason=it.get("reason"), est_reclaim_bytes=it.get("reclaim_bytes"))
    free1, _ = disk_free(ctx.main)
    ctx.log(event="apply_end", executed=a.execute, removed=len(done), skipped=len(skipped), failed=len(failed), free_bytes_before=free0, free_bytes_after=free1)
    print("hygiene apply (%s)  free before %s, after %s" % ("EXECUTED" if a.execute else "DRY-RUN; add --execute to act", gib(free0), gib(free1)))
    for l, r in done:
        print("  DONE    %s  [%s]" % (l, r))
    for l, r in skipped:
        print("  SKIPPED %s  [%s]" % (l, r))
    for l, r in failed:
        print("  FAILED  %s  [%s]" % (l, r))
    return 1 if failed else 0


def execute(ctx, it):
    cls, path = it["class"], it["path"]
    if cls == "process":
        pid = int(it["pid"])
        try:
            os.kill(pid, 15)
        except OSError as e:
            return "SIGTERM failed: %s" % e
        for _ in range(10):
            time.sleep(0.5)
            if not ps_row(pid):
                return None
        ok, why, _ = verify_process(ctx, it)  # re-verify before escalating
        if not ok:
            return None if not ps_row(pid) else "still running but no longer verifiable: " + why
        try:
            os.kill(pid, 9)
        except OSError as e:
            return "SIGKILL failed: %s" % e
        return None
    if cls == "worktree":
        rc, out, err = sh(["git", "-C", ctx.main, "worktree", "remove", path], timeout=600)  # never --force
        if rc != 0:
            return "git worktree remove refused: " + (err.strip() or out.strip())[:200]
        return None
    if not path or path == "/" or path.count("/") < 3:
        return "refusing suspicious path"
    rc, out, err = sh(["rm", "-rf", "--", path], timeout=1800)
    if rc != 0 or os.path.exists(path):
        return "rm failed: " + err.strip()[:200]
    return None


def cmd_register(ctx, a):
    row = ps_row(a.pid)
    if not row:
        die("pid %d not running" % a.pid)
    os.makedirs(os.path.dirname(ctx.registry), exist_ok=True)
    with open(ctx.registry, "a") as f:
        f.write("%d\t%s\t%s\t%s\n" % (a.pid, row["lstart"], row["command"].replace("\t", " "), (a.label or "").replace("\t", " ")))
    print("registered pid %d in %s" % (a.pid, ctx.registry))
    return 0


def main():
    ap = argparse.ArgumentParser(prog="hygiene.sh")
    ap.add_argument("--repo")
    ap.add_argument("--profile")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan")
    s.add_argument("--agents", type=int, default=0)
    p = sub.add_parser("plan")
    p.add_argument("--emergency", action="store_true")
    p.add_argument("--out")
    ap_ = sub.add_parser("apply")
    ap_.add_argument("plan")
    ap_.add_argument("--execute", action="store_true")
    ap_.add_argument("--approve")
    r = sub.add_parser("register")
    r.add_argument("pid", type=int)
    r.add_argument("label", nargs="?")
    a = ap.parse_args()
    ctx = Ctx(a.repo, a.profile)
    sys.exit({"scan": cmd_scan, "plan": cmd_plan, "apply": cmd_apply, "register": cmd_register}[a.cmd](ctx, a))


main()
