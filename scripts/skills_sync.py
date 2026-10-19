#!/usr/bin/env python3
"""Keep the repo's versioned skills and the live ~/.claude/skills in step.

Subcommands:
  status   compare each repo skill with the installed one
  check    validate repo skills (frontmatter, no bytecode, no secrets)
  install  symlink DIR/<name> -> repo skills/<name>, never clobbering

Stdlib only. Nothing is ever deleted; --adopt moves an existing directory
into a timestamped backup before linking.
"""
import argparse
import difflib
import filecmp
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

REPO_SKILLS = Path(__file__).resolve().parent.parent / "skills"
DEFAULT_LIVE = Path.home() / ".claude" / "skills"
DEFAULT_BACKUP = Path.home() / ".claude" / "skills-backups"
IGNORED = {"__pycache__"}

SECRET_PATTERNS = [
    ("openai-style key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}")),
    ("github token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}")),
    ("gitlab token", re.compile(r"\bglpat-[A-Za-z0-9_-]{10,}")),
    ("aws access key", re.compile(r"\bAKIA[0-9A-Z]{12,}")),
    ("slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{10,}\.")),
    ("credential assignment", re.compile(
        r"(?i)\b(api[_-]?key|secret|token|passwd|password)\b[\"']?\s*[:=]\s*[\"'][A-Za-z0-9_\-+/=]{20,}[\"']")),
]


# ---------------------------------------------------------------- helpers
def skill_names(repo):
    """Top-level skill directories that hold a SKILL.md (archive excluded)."""
    return sorted(p.name for p in repo.iterdir()
                  if p.is_dir() and not p.name.startswith("_") and (p / "SKILL.md").is_file())


def files_of(root):
    out = []
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        if any(part in IGNORED for part in rel.parts) or p.suffix == ".pyc":
            continue
        if p.is_file():
            out.append(rel)
    return out


def trees_identical(a, b):
    fa, fb = files_of(a), files_of(b)
    if fa != fb:
        return False
    return all(filecmp.cmp(a / r, b / r, shallow=False) for r in fa)


def classify(name, repo, live):
    src, dst = repo / name, live / name
    if dst.is_symlink():
        if dst.resolve() == src.resolve():
            return "installed-is-link-to-repo"
        return "installed-is-other-link"
    if not dst.exists():
        return "missing-installed"
    return "identical" if trees_identical(src, dst) else "differs"


def tree_diff(a, b):
    lines = []
    fa, fb = set(files_of(a)), set(files_of(b))
    for rel in sorted(fa | fb):
        pa, pb = a / rel, b / rel
        if rel not in fb:
            lines.append(f"only in repo: {rel}")
            continue
        if rel not in fa:
            lines.append(f"only in installed: {rel}")
            continue
        if filecmp.cmp(pa, pb, shallow=False):
            continue
        try:
            ta, tb = pa.read_text().splitlines(), pb.read_text().splitlines()
        except UnicodeDecodeError:
            lines.append(f"binary files differ: {rel}")
            continue
        lines.extend(difflib.unified_diff(ta, tb, f"repo/{rel}", f"installed/{rel}", lineterm=""))
    return lines


# ---------------------------------------------------------------- status
def cmd_status(args):
    repo, live = args.repo_skills, args.skills_dir
    for name in skill_names(repo):
        state = classify(name, repo, live)
        print(f"{name:28s} {state}")
        if args.diff and state == "differs":
            for line in tree_diff(repo / name, live / name):
                print("    " + line)
    return 0


# ---------------------------------------------------------------- check
def parse_frontmatter(text):
    """Minimal YAML subset: top-level `key: value`, with >- / | block scalars."""
    if not text.startswith("---"):
        return None
    parts = text.split("\n---", 1)
    if len(parts) < 2:
        return None
    data, key = {}, None
    for line in parts[0].splitlines()[1:]:
        m = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if m:
            key, val = m.group(1), m.group(2).strip()
            data[key] = "" if val in (">", ">-", "|", "|-", ">+", "|+") else val.strip("\"'")
        elif key and line.startswith((" ", "\t")):
            data[key] = (data[key] + " " + line.strip()).strip()
    return data


def check_skill_md(path):
    problems = []
    try:
        fm = parse_frontmatter(path.read_text())
    except UnicodeDecodeError:
        return [f"{path}: not valid UTF-8"]
    if fm is None:
        return [f"{path}: missing or malformed frontmatter"]
    if not fm.get("name"):
        problems.append(f"{path}: frontmatter has no name")
    elif fm["name"] != path.parent.name:
        problems.append(f"{path}: name '{fm['name']}' does not match directory '{path.parent.name}'")
    if not fm.get("description"):
        problems.append(f"{path}: frontmatter has no description")
    return problems


def cmd_check(args):
    repo = args.repo_skills
    problems = []
    for p in sorted(repo.rglob("*")):
        rel = p.relative_to(repo.parent)
        if p.name == "__pycache__" or p.suffix == ".pyc":
            problems.append(f"{rel}: bytecode cache must not be committed")
            continue
        if p.is_symlink() or not p.is_file():
            continue
        if p.name == "SKILL.md":
            problems.extend(check_skill_md(p))
        try:
            text = p.read_text()
        except UnicodeDecodeError:
            continue
        for label, rx in SECRET_PATTERNS:
            if rx.search(text):
                problems.append(f"{rel}: looks like a secret ({label})")
    for line in problems:
        print(line)
    if problems:
        print(f"check FAILED: {len(problems)} problem(s)")
        return 1
    print(f"check ok: {len(skill_names(repo))} skills")
    return 0


# ---------------------------------------------------------------- install
def cmd_install(args):
    repo, live, backup_root = args.repo_skills, args.skills_dir, args.backup_dir
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dry = "[dry-run] " if args.dry_run else ""
    refused = []
    if not args.dry_run:
        live.mkdir(parents=True, exist_ok=True)
    for name in skill_names(repo):
        src, dst = (repo / name).resolve(), live / name
        state = classify(name, repo, live)
        if state == "installed-is-link-to-repo":
            print(f"{name}: already linked")
            continue
        if state == "missing-installed" and not dst.is_symlink():
            print(f"{dry}{name}: link {dst} -> {src}")
            if not args.dry_run:
                dst.symlink_to(src)
            continue
        if not args.adopt:
            print(f"{name}: REFUSED, {dst} exists ({state}); rerun with --adopt to back it up and link")
            refused.append(name)
            continue
        dest = backup_root / stamp / name
        print(f"{dry}{name}: move {dst} -> {dest}, then link -> {src}")
        if not args.dry_run:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(dst), str(dest))
            dst.symlink_to(src)
    if refused:
        print("\nstatus of refused skills:")
        for name in refused:
            print(f"  {name:28s} {classify(name, repo, live)}")
        return 1
    return 0


# ---------------------------------------------------------------- cli
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo-skills", type=Path, default=REPO_SKILLS, help="repo skills dir (default: ./skills)")
    ap.add_argument("--skills-dir", type=Path, default=DEFAULT_LIVE, help="live skills dir (default: ~/.claude/skills)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("status"); s.add_argument("--diff", action="store_true")
    sub.add_parser("check")
    i = sub.add_parser("install")
    i.add_argument("--adopt", action="store_true")
    i.add_argument("--dry-run", action="store_true")
    i.add_argument("--backup-dir", type=Path, default=DEFAULT_BACKUP)
    # accept the shared options after the subcommand too
    for p in (s, sub.choices["check"], i):
        p.add_argument("--repo-skills", type=Path, default=argparse.SUPPRESS)
        p.add_argument("--skills-dir", type=Path, default=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    return {"status": cmd_status, "check": cmd_check, "install": cmd_install}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
