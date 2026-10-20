#!/usr/bin/env python3
"""Keep Claude/tests on the VPS and review their source in local Antigravity."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
import time

HOST = 'vultr-claude'
HOME = Path.home()
BASE = HOME / 'Projects/lsf-vps'


def paths(name):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,47}', name):
        raise ValueError('Use a name of 1-48 letters, digits, underscores or hyphens; start with a letter or digit')
    local = BASE / name
    return dict(name=name, local=local, review=local/'current', cache=local/'cache.git',
                remote='/home/linuxuser/Projects/lsf-vps/'+name+'/repo',
                agent='lsf-vps-'+name, dashboard='lsf-dash-'+name,
                runtime='/home/linuxuser/.cache/lsf-vps/'+name)


def run(args, **kw):
    return subprocess.run([str(x) for x in args], check=True, **kw)


def remote(code, data):
    # JSON is data, never shell source. Only this fixed Python invocation reaches SSH.
    prefix = 'import json\ndata=json.loads('+repr(json.dumps(data))+')\n'
    r = run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10',HOST,'python3','-'],
            input=prefix+code, capture_output=True, text=True, timeout=60)
    return json.loads(r.stdout) if r.stdout.strip() else None


def copy_args(source, destination):
    return ['rsync','-az','--safe-links','--exclude=.git/','--exclude=node_modules/',
            '--exclude=.venv/','--exclude=venv/','--exclude=__pycache__/',
            '--exclude=/.env','--exclude=/.env.*','--exclude=/.DS_Store',
            str(source),str(destination)]


def publish_snapshot(current, snapshot):
    if not snapshot.is_dir():
        raise ValueError('Incomplete snapshot; previous review checkout is unchanged')
    temp = current.with_name('.current-'+str(os.getpid()))
    temp.symlink_to(snapshot)
    temp.replace(current)


def shallow_boundary(source):
    result = run(['git','-C',source,'rev-parse','--git-path','shallow'], capture_output=True, text=True)
    boundary = Path(result.stdout.strip())
    if not boundary.is_absolute():
        boundary = Path(source) / boundary
    return boundary.read_text() if boundary.exists() else None


def pin_runtime(p):
    result = remote("""from pathlib import Path
import subprocess,tempfile,re,os,hashlib
repo=Path('/home/linuxuser/Projects/software-factory')
marker=Path('/home/linuxuser/.cache/lsf-ready-for-codex-20261020.json')
ready=json.loads(marker.read_text())
personal=marker.with_name('lsf-personal-ready.json')
if personal.exists():
 overlay=json.loads(personal.read_text())
 if overlay.get('ready') is True and overlay.get('base_commit')==ready.get('commit'):ready=overlay
sha=ready.get('commit','')
if ready.get('ready') is not True or not re.fullmatch('[0-9a-f]{40}',sha):raise SystemExit('No tested LSF runtime is marked ready')
versions=Path('/home/linuxuser/.local/share/lsf-vps/versions');versions.mkdir(parents=True,exist_ok=True)
target=versions/sha
if not target.exists():
 with tempfile.TemporaryDirectory(dir=versions) as tmp:
  stage=Path(tmp)/'source';stage.mkdir();archive=Path(tmp)/'skills.tar'
  with archive.open('wb') as out:
   subprocess.run(['git','-C',str(repo),'archive',sha,'skills/lsf','skills/eli12-docs','skills/mermaid-nesting-dolls'],stdout=out,check=True)
  subprocess.run(['tar','-xf',str(archive),'-C',str(stage)],check=True)
  stage.rename(target)
guard_source=data['guard_source']
guard_sha=hashlib.sha256(guard_source.encode()).hexdigest()
tools=versions.parent/'tools';tools.mkdir(exist_ok=True)
guard=tools/('resource-'+guard_sha+'.py')
guard.write_text(guard_source)
config={'commit':sha,'source':str(target),'bin':str(Path(data['runtime'])/'bin'),'resource_guard_sha':guard_sha}
config_file=Path(data['runtime'])/'runtime.json'
old=json.loads(config_file.read_text()) if config_file.exists() else None
live=any(subprocess.run(['tmux','has-session','-t','='+data[key]],capture_output=True).returncode==0 for key in ('agent','dashboard'))
if old and old.get('commit')!=sha and live:raise SystemExit('Running project stays pinned; use a new project name for a newer runtime')
Path(config['bin']).mkdir(parents=True,exist_ok=True)
w=Path(config['bin'])/'lsf'
w.write_text('#!/bin/sh\\nexec python3 "'+str(target/'skills/lsf/scripts/lsf.py')+'" "$@"\\n');w.chmod(0o755)
guarded=Path(config['bin'])/'lsf-vps-test'
guarded.write_text('#!/bin/sh\\nexec python3 "'+str(guard)+'" --memory-mb "${LSF_TEST_MEM_MB:-4096}" --wall-s "${LSF_TEST_WALL_S:-180}" --lock /tmp/sf-factory-pytest.lock -- "$@"\\n');guarded.chmod(0o755)
legacy_bin=target/'bin';legacy_bin.mkdir(exist_ok=True)
compat=legacy_bin/'lsf-vps-test'
if not compat.exists():compat.write_text(guarded.read_text());compat.chmod(0o755)
project=Path(data['remote'])/'.claude/skills';project.mkdir(parents=True,exist_ok=True)
for name in ('lsf','eli12-docs','mermaid-nesting-dolls'):
 dest=project/name;wanted=target/'skills'/name
 if dest.is_symlink() and dest.resolve()==wanted:continue
 if dest.is_symlink() and versions in dest.resolve().parents and not live:
  temp=dest.with_name('.'+name+'-next');temp.symlink_to(wanted);temp.replace(dest);continue
 if dest.exists() or dest.is_symlink():raise SystemExit('Existing project skill differs; refusing to replace '+str(dest))
 dest.symlink_to(wanted)
ex=Path(data['remote'])/'.git/info/exclude'
text=ex.read_text() if ex.exists() else ''
for line in ('/.lsf/','/.claude/skills/lsf','/.claude/skills/eli12-docs','/.claude/skills/mermaid-nesting-dolls'):
 if line not in text.splitlines():text+='\\n'+line+'\\n'
ex.write_text(text)
runtime=Path(data['runtime']);runtime.mkdir(parents=True,exist_ok=True)
(runtime/'runtime.json').write_text(json.dumps(config,indent=2)+'\\n')
print(json.dumps(config))
""", {'remote':p['remote'],'runtime':p['runtime'],'agent':p['agent'],'dashboard':p['dashboard'],
          'guard_source':(Path(__file__).resolve().parents[1]/'factory/resource_limits.py').read_text()})
    print('Pinned tested LSF runtime:',result['commit'][:12])
    return result


def prepare(p, source):
    source = source.resolve()
    run(['git','-C',source,'rev-parse','--show-toplevel'], capture_output=True)
    remote('''from pathlib import Path
p=Path(data['remote'])
if p.exists(): raise SystemExit('Remote project already exists; use snapshot/start to resume it')
p.mkdir(parents=True)
''', {'remote':p['remote']})
    with tempfile.TemporaryDirectory(prefix='lsf-vps-') as tmp:
        bundle = Path(tmp)/'repo.bundle'
        run(['git','-c','pack.threads=1','-c','pack.windowMemory=32m',
             '-c','pack.deltaCacheSize=16m','-C',source,'bundle','create',bundle,'HEAD'], capture_output=True)
        run(['scp',bundle,HOST+':'+p['remote']+'/../initial.bundle'],capture_output=True)
        remote('''import subprocess
from pathlib import Path
p=Path(data['remote'])
subprocess.run(['git','clone',str(p.parent/'initial.bundle'),str(p)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
subprocess.run(['git','-C',str(p),'remote','remove','origin'],check=True)
if data.get('shallow'):(p/'.git/shallow').write_text(data['shallow'])
subprocess.run(['git','-C',str(p),'fsck','--connectivity-only'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
(p.parent/'initial.bundle').unlink()
''', {'remote':p['remote'],'shallow':shallow_boundary(source)})
    # Only the new isolated remote directory receives local working-tree files.
    run(copy_args(str(source)+'/',HOST+':'+p['remote']+'/'),capture_output=True)
    p['local'].mkdir(parents=True,exist_ok=True)
    (p['local']/'source.json').write_text(json.dumps({'source':str(source),'remote':p['remote']},indent=2)+'\n')
    pin_runtime(p)
    snapshot(p)
    print('Prepared isolated remote repo:',p['remote'])


def fingerprint(p):
    return remote('''import subprocess,hashlib
from pathlib import Path
r=Path(data['remote'])
def git(*a): return subprocess.check_output(['git','-C',str(r),*a])
h=hashlib.sha256(git('diff','--binary','HEAD'))
for raw in git('ls-files','--others','--exclude-standard','-z').split(b'\\0'):
 if not raw: continue
 p=r/raw.decode()
 h.update(raw)
 if p.is_file() and not p.is_symlink():
  with p.open('rb') as f:
   for chunk in iter(lambda:f.read(1048576),b''):h.update(chunk)
print(json.dumps(dict(head=git('rev-parse','HEAD').decode().strip(),content=h.hexdigest())))
''', {'remote':p['remote']})


def snapshot(p):
    p['local'].mkdir(parents=True,exist_ok=True)
    before = fingerprint(p)
    if not p['cache'].exists():
        run(['git','init','--bare',p['cache']],capture_output=True)
        run(['git','--git-dir',p['cache'],'config','gc.auto','0'])
    run(['git','--git-dir',p['cache'],'fetch','--update-shallow',HOST+':'+p['remote'],'HEAD'],capture_output=True)
    fetched = run(['git','--git-dir',p['cache'],'rev-parse','FETCH_HEAD'],capture_output=True,text=True).stdout.strip()
    run(['git','--git-dir',p['cache'],'update-ref','refs/heads/review',fetched])
    run(['git','--git-dir',p['cache'],'symbolic-ref','HEAD','refs/heads/review'])
    snap = p['local']/'snapshots'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    snap.parent.mkdir(exist_ok=True)
    run(['git','clone','--shared','--no-checkout',p['cache'],snap],capture_output=True)
    run(['git','-C',snap,'checkout','--detach',before['head']],capture_output=True)
    patch = run(['ssh',HOST,shlex.join(['git','-C',p['remote'],'diff','--binary','HEAD'])],
                capture_output=True).stdout
    if patch:
        run(['git','-C',snap,'apply','--binary','-'],input=patch,capture_output=True)
    run(copy_args(HOST+':'+p['remote']+'/',str(snap)+'/'),capture_output=True)
    after = fingerprint(p)
    if before != after:
        raise ValueError('Remote code changed during the snapshot. Retry when Claude is paused at HITL; previous checkout retained')
    (snap/'.git/info/exclude').open('a').write('\n/.lsf/\n/.lsf-vps-review.json\n')
    (snap/'.lsf-vps-review.json').write_text(json.dumps(dict(before, remote=p['remote'],
        captured_at=datetime.now(timezone.utc).isoformat(),purpose='Review snapshot; send requested edits to VPS Claude'),indent=2)+'\n')
    publish_snapshot(p['review'],snap)
    # Profile root affects links only; the CLI still operates in the real VPS repo.
    remote('''from pathlib import Path
p=Path(data['remote'])/'.lsf/profile.json'
if p.exists():
 d=json.loads(p.read_text());d['editor']='antigravity-ide';d['workspace_root']=data['review']
 temp=p.with_suffix('.json.tmp');temp.write_text(json.dumps(d,indent=2)+'\\n');temp.replace(p)
''', {'remote':p['remote'],'review':str(p['review'])})
    print('Review snapshot:',p['review'],'at',before['head'][:12])


def start(p, model):
    result = remote('''import subprocess,shlex
from pathlib import Path
if not (Path(data['remote'])/'.git').is_dir():raise SystemExit('Prepare the repo first')
exists=subprocess.run(['tmux','has-session','-t','='+data['agent']],capture_output=True).returncode==0
if not exists:
 import os
 cfg=json.loads((Path(data['runtime'])/'runtime.json').read_text())
 cmd=shlex.join(['/usr/bin/env','PATH='+cfg['bin']+':/home/linuxuser/.local/bin:'+os.environ.get('PATH','/usr/bin:/bin'),'/home/linuxuser/.local/bin/claude-lsf','--model',data['model'],'--name',data['agent']])
 subprocess.run(['tmux','new-session','-d','-s',data['agent'],'-c',data['remote'],cmd],check=True)
print(json.dumps({'already_running':exists}))
''', {'remote':p['remote'],'agent':p['agent'],'model':model,'runtime':p['runtime']})
    print('Existing session preserved.' if result['already_running'] else 'Started remote Claude; no task supplied.')
    print('Attach with: lsf-vps attach '+p['name'])


def dashboard(p, port, open_browser):
    state = remote('''from pathlib import Path
import subprocess,shlex,os,re,time
runtime=Path(data['runtime']);runtime.mkdir(parents=True,exist_ok=True);runtime.chmod(0o700)
log=runtime/'dashboard.log'
exists=subprocess.run(['tmux','has-session','-t','='+data['dashboard']],capture_output=True).returncode==0
if not exists:
 log.write_text('');log.chmod(0o600)
 cfg=json.loads((runtime/'runtime.json').read_text())
 cmd=shlex.join(['/usr/bin/python3','-u',cfg['source']+'/skills/lsf/scripts/lsf.py','serve','--root',data['remote'],'--port','0'])+' > '+shlex.quote(str(log))+' 2>&1'
 subprocess.run(['tmux','new-session','-d','-s',data['dashboard'],cmd],check=True)
for _ in range(100):
 text=log.read_text() if log.exists() else ''
 m=re.search(r'http://127.0.0.1:(\\d+)/#token=([a-f0-9]+)',text)
 if m:
  print(json.dumps({'port':int(m[1]),'token':m[2]}));break
 time.sleep(.1)
else: raise SystemExit('Dashboard failed to start; inspect its private log')
''', {'runtime':p['runtime'],'dashboard':p['dashboard'],'remote':p['remote']})
    sock = p['local']/'tunnel.sock'
    old = p['local']/'tunnel.json'
    check = subprocess.run(['ssh','-S',str(sock),'-O','check',HOST],capture_output=True)
    if check.returncode == 0:
        prior=json.loads(old.read_text())
        if prior != {'local_port':port,'remote_port':state['port']}:
            raise ValueError('Existing tunnel has different ports; use tunnel-stop before reopening')
    else:
        run(['ssh','-M','-S',sock,'-fnNT','-o','ExitOnForwardFailure=yes',
             '-o','ServerAliveInterval=30','-o','ServerAliveCountMax=3',
             '-L','127.0.0.1:%d:127.0.0.1:%d'%(port,state['port']),HOST],capture_output=True)
        old.write_text(json.dumps({'local_port':port,'remote_port':state['port']}))
    url='http://127.0.0.1:%d/'%port
    print('VPS dashboard through local SSH tunnel:',url)
    if open_browser:
        run(['open',url+'#token='+state['token']],capture_output=True)
        print('Opened the owner approval URL in your browser; token omitted from output.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='action',required=True)
    prep=sub.add_parser('prepare');prep.add_argument('name');prep.add_argument('source',type=Path)
    for action in ('snapshot','pin','fetch','review','attach','status','tunnel-stop'):
        sub.add_parser(action).add_argument('name')
    s=sub.add_parser('start');s.add_argument('name');s.add_argument('--model',default='sonnet')
    d=sub.add_parser('dashboard');d.add_argument('name');d.add_argument('--port',type=int,default=8890);d.add_argument('--open',action='store_true')
    args=parser.parse_args();p=paths(args.name)
    if args.action=='prepare':prepare(p,args.source)
    elif args.action=='snapshot':snapshot(p)
    elif args.action=='pin':pin_runtime(p)
    elif args.action=='review':
        if not p['review'].is_dir():raise ValueError('Create a review snapshot first')
        run(['/Applications/Antigravity IDE.app/Contents/Resources/app/bin/antigravity-ide',
             '--new-window',p['review']],capture_output=True)
    elif args.action=='fetch':
        source=Path(json.loads((p['local']/'source.json').read_text())['source'])
        run(['git','-C',source,'fetch','--update-shallow',HOST+':'+p['remote'],
             'HEAD:refs/remotes/lsf-vps/'+p['name']])
        print('Remote commits fetched; original branch and working files are unchanged.')
    elif args.action=='start':start(p,args.model)
    elif args.action=='attach':os.execvp('ssh',['ssh','-t',HOST,'tmux attach-session -t '+shlex.quote('='+p['agent'])])
    elif args.action=='dashboard':
        if not 1024<=args.port<=65535:raise ValueError('Choose an unprivileged local port from 1024 to 65535')
        dashboard(p,args.port,args.open)
    elif args.action=='tunnel-stop':run(['ssh','-S',p['local']/'tunnel.sock','-O','exit',HOST])
    elif args.action=='status':
        state=remote('''from pathlib import Path
import subprocess
p=Path(data['runtime'])/'runtime.json'
print(json.dumps(dict(runtime=json.loads(p.read_text()) if p.exists() else None,
 agent_running=subprocess.run(['tmux','has-session','-t','='+data['agent']],capture_output=True).returncode==0,
 dashboard_running=subprocess.run(['tmux','has-session','-t','='+data['dashboard']],capture_output=True).returncode==0)))
''', {'runtime':p['runtime'],'agent':p['agent'],'dashboard':p['dashboard']})
        print(json.dumps(dict(project=fingerprint(p),**state),indent=2))


if __name__=='__main__':
    try:main()
    except (ValueError,subprocess.CalledProcessError) as exc:raise SystemExit(str(exc))
