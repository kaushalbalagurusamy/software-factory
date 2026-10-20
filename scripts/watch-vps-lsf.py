#!/usr/bin/env python3
"""Import one explicitly ready VPS LSF snapshot after bounded local verification."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

HOME = Path.home()
ROOT = Path(__file__).resolve().parents[1]
STATE = HOME / '.claude/lsf-vps-sync'
VPS_REPO = '/home/linuxuser/Projects/software-factory'
MARKER = '/home/linuxuser/.cache/lsf-ready-for-codex-20261020.json'
PYTHON = HOME / 'Projects/software-factory/.venv/bin/python'
LIMITER = HOME / 'Projects/software-factory/factory/resource_limits.py'


def write_status(status, **fields):
    STATE.mkdir(parents=True, exist_ok=True)
    data = dict(status=status, at=datetime.now(timezone.utc).isoformat(), **fields)
    temp = STATE / 'status.tmp'
    temp.write_text(json.dumps(data, indent=2) + '\n')
    temp.replace(STATE / 'status.json')
    print(json.dumps(data), flush=True)


def ready_commit(state):
    marker = state.get('marker') or {}
    if not isinstance(marker, dict):
        return None
    sha = marker.get('commit', '')
    if not isinstance(sha, str):
        return None
    if (marker.get('ready') is True and re.fullmatch(r'[0-9a-f]{40}', sha)
            and sha == state.get('head') and not state.get('dirty')):
        return sha
    return None


def remote_state():
    code = '''from pathlib import Path
import json, subprocess
root = Path(%r)
p = Path(%r)
try: marker = json.loads(p.read_text()) if p.exists() else None
except (ValueError, OSError): marker = None
print(json.dumps(dict(marker=marker,
 head=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip(),
 dirty=subprocess.check_output(['git','-C',str(root),'status','--porcelain'],text=True).strip())))
''' % (VPS_REPO, MARKER)
    result = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
                             'vultr-claude', 'python3', '-'], input=code,
                            capture_output=True, text=True, timeout=30, check=True)
    return json.loads(result.stdout)


def replace_skill_link(name, target):
    dest = HOME / '.claude/skills' / name
    if dest.is_symlink() and dest.resolve() == target.resolve():
        return
    if dest.exists() or dest.is_symlink():
        backups = HOME / '.claude/skills-backups'
        backups.mkdir(parents=True, exist_ok=True)
        dest.rename(backups / (name + '-vps-' + str(time.time_ns())))
    dest.symlink_to(target)


def install(sha):
    snapshots = STATE / 'snapshots'
    snapshots.mkdir(parents=True, exist_ok=True)
    staging = snapshots / (sha + '-staging')
    snapshot = snapshots / sha
    subprocess.run(['git', '-C', str(ROOT), 'fetch', 'vultr-claude:' + VPS_REPO, sha],
                   check=True, timeout=120)
    # Materialize only tracked committed content, never a live or dirty worktree.
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir()
    archive = STATE / 'snapshot.tar'
    with archive.open('wb') as out:
        subprocess.run(['git', '-C', str(ROOT), 'archive', sha], stdout=out,
                       check=True, timeout=60)
    subprocess.run(['tar', '-xf', str(archive), '-C', str(staging)], check=True, timeout=60)
    archive.unlink()
    # Keep the independently tested launcher while importing the native workflow.
    for relative in ('scripts/launch.py', 'LAUNCH.md'):
        shutil.copy2(ROOT / 'skills/lsf' / relative, staging / 'skills/lsf' / relative)
    subprocess.run([str(PYTHON), str(ROOT / 'scripts/add-antigravity-editor.py'), str(staging)],
                   check=True, timeout=15)
    checks = ['tests/lsf']
    for suite in ('evals/native/sfn09', 'tests/test_editor_links.py',
                  'skills/mermaid-nesting-dolls/tests/test_workspace.py'):
        if (staging / suite).exists():
            checks.append(suite)
    env = dict(os.environ, SF_TEST_MEM_MB='0')
    log = STATE / ('tests-' + sha + '.log')
    write_status('testing', commit=sha, test_log=str(log))
    with log.open('w') as out:
        subprocess.run([str(PYTHON), str(LIMITER), '--memory-mb', '4096', '--wall-s', '300',
                        '--lock', str(STATE / 'tests.lock'), '--', str(PYTHON), '-m', 'pytest',
                        *checks, '-q', '--tb=short'], cwd=staging, env=env, stdout=out,
                       stderr=subprocess.STDOUT, check=True, timeout=330)
    # The owner may have continued editing during verification; wait rather than
    # install a now-superseded snapshot.
    if ready_commit(remote_state()) != sha:
        write_status('waiting', reason='VPS advanced during verification', tested_commit=sha)
        return False
    if snapshot.exists():
        shutil.rmtree(snapshot)
    staging.rename(snapshot)
    subprocess.run(['sh', str(snapshot / 'skills/lsf/install.sh')], check=True, timeout=30)
    for name in ('eli12-docs', 'mermaid-nesting-dolls'):
        replace_skill_link(name, snapshot / 'skills' / name)
    subprocess.run([str(HOME / '.local/bin/lsf'), '--help'], check=True,
                   stdout=subprocess.DEVNULL, timeout=15)
    subprocess.run([str(HOME / '.local/bin/claude-lsf'), '--help'], check=True,
                   stdout=subprocess.DEVNULL, timeout=15)
    write_status('synced', commit=sha, test_log=str(log), snapshot=str(snapshot),
                 launcher_commit=subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip())
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--once', action='store_true', help='Check readiness once; import only if ready')
    args = ap.parse_args()
    write_status('watching', marker=MARKER)
    while True:
        try:
            state = remote_state()
        except (subprocess.SubprocessError, OSError, ValueError) as exc:
            write_status('retrying', reason=str(exc))
            if args.once:
                return 1
            time.sleep(30)
            continue
        try:
            sha = ready_commit(state)
            if sha and install(sha):
                return 0
            if not sha:
                write_status('waiting', head=state.get('head'), dirty=bool(state.get('dirty')),
                             reason='Waiting for the tested ready marker from VPS Claude')
        except (subprocess.SubprocessError, OSError, ValueError) as exc:
            write_status('failed', reason=str(exc))
            return 1
        if args.once:
            return 0
        time.sleep(30)


if __name__ == '__main__':
    sys.exit(main())
