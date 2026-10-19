#!/usr/bin/env bash
# Sandbox test for hygiene.sh. Builds a throwaway repo, runs plan/apply, asserts exactly the allowed items
# were removed and every protected item survived. Cleans up on exit. Usage: test-hygiene.sh [sandbox-dir]
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
H="$HERE/hygiene.sh"
SB="${1:-/private/tmp/claude-501/-Users-kaushal-Projects/5c5615e4-532a-4bbc-80e9-f00e1c5b5031/scratchpad/hygiene-sandbox}"
SB="$(mkdir -p "$SB" && cd "$SB" && pwd -P)"
case "$SB" in */hygiene-sandbox*) ;; *) echo "refusing sandbox path $SB"; exit 64;; esac
rm -rf "$SB"; mkdir -p "$SB"
M="$SB/main"; WT="$M/.claude/worktrees"; SC="$SB/scratch"; REG="$SB/registry.tsv"
export HYGIENE_LOG="$SB/hygiene.log"
export HYGIENE_FAKE_MEM_LEVEL=1   # warn: makes the result independent of this host's real memory state
PASS=0; FAIL=0
ok()   { PASS=$((PASS+1)); echo "  PASS  $*"; }
bad()  { FAIL=$((FAIL+1)); echo "  FAIL  $*"; }
gone() { [ ! -e "$1" ] && ok "removed:   ${1#$SB/}" || bad "should be removed: ${1#$SB/}"; }
kept() { [ -e "$1" ] && ok "survived:  ${1#$SB/}${2:+   ($2)}" || bad "should survive: ${1#$SB/}"; }
alive(){ kill -0 "$1" 2>/dev/null && ok "alive:     pid $1 ($2)" || bad "pid $1 should be alive ($2)"; }
dead() { sleep 0.3; kill -0 "$1" 2>/dev/null && bad "pid $1 should be dead ($2)" || ok "killed:    pid $1 ($2)"; }
# test-only helper: evaluates trusted, literal expressions written in this file against plan JSON
jq_() { python3 -c "import json,sys;d=json.load(open(sys.argv[1]));print(eval(sys.argv[2]))" "$1" "$2"; }
G() { git -C "$M" -c user.name=t -c user.email=t@example.invalid -c commit.gpgsign=false "$@"; }
GW() { local d="$1"; shift; git -C "$d" -c user.name=t -c user.email=t@example.invalid -c commit.gpgsign=false "$@"; }
fake() { mkdir -p "$1"; head -c "${2:-2000000}" /dev/urandom > "$1/blob.bin"; }   # fake build output
unique_ok() { local o; o="$(GW "$WT/unique" log --oneline)"; [[ "$o" == *"unique work"* ]]; }
cleanup() { for p in ${PIDS:-}; do kill "$p" 2>/dev/null; done; rm -rf "$SB"; echo "sandbox removed: $([ -e "$SB" ] && echo NO || echo yes)"; }
trap cleanup EXIT

echo "== build sandbox"
git init -q -b main "$M"; G config core.hooksPath /dev/null
mkdir -p "$M/docs/evidence" "$M/.claude"
printf 'target/\nnode_modules/\n.next/\ndist/\n.env\nkeys/\n.claude/\n' > "$M/.gitignore"
echo "evidence" > "$M/docs/evidence/run1.txt"; echo base > "$M/a.txt"
G add .gitignore docs a.txt; G commit -qm base
mkdir -p "$M/keys"; echo '[1,2,3]' > "$M/keys/id.json"; echo 'SECRET=x' > "$M/.env"
fake "$M/.next"; fake "$M/target" 3000000
cat > "$M/.claude/build-loop.md" <<EOF
# profile
## Hygiene
- protected: docs/evidence/*
- scratch_dirs: $SC
- scratch_max_age_days: 3
- worktree_min_age_min: 0
- run_registry: $REG
- process_patterns: sleep 3[0-9][0-9]
- ports: 59999
- shared_build_dir: target
## Other
- scratch_dirs: /nonexistent-must-not-be-read
EOF
# worktrees (all branches created at base)
for n in merged merged-env dirty unique locked inuse; do G worktree add -q -b "wt-$n" "$WT/$n"; done
# wt-merged and wt-merged-env: add a commit, cherry-pick it onto main (not an ancestor, but patch-equivalent)
for n in merged merged-env; do echo "$n" > "$WT/$n/$n.txt"; GW "$WT/$n" add "$n.txt"; GW "$WT/$n" commit -qm "work $n"; G cherry-pick "wt-$n" >/dev/null; done
echo "dirty-edit" >> "$WT/dirty/a.txt"
echo u > "$WT/unique/u.txt"; GW "$WT/unique" add u.txt; GW "$WT/unique" commit -qm "unique work"
G worktree lock --reason "claude agent test (pid 1 start now)" "$WT/locked"
for n in merged merged-env dirty unique locked inuse; do fake "$WT/$n/target"; mkdir -p "$WT/$n/node_modules"; echo x > "$WT/$n/node_modules/m.js"; done
echo 'WT_SECRET=y' > "$WT/merged-env/.env"
# hard links: wt-merged node_modules shares a 3 MB file with a store outside the tree (pnpm-style)
mkdir -p "$SB/store"; head -c 3000000 /dev/urandom > "$SB/store/pkg.bin"; ln "$SB/store/pkg.bin" "$WT/merged/node_modules/pkg.bin"
# scratch dirs
mkdir -p "$SC/old-big" "$SC/young" "$SC/old-with-keys" "$SC/old-repo"
fake "$SC/old-big" 4000000; fake "$SC/young" 1000000
fake "$SC/old-with-keys" 1000000; echo 'K=1' > "$SC/old-with-keys/.env"; mkdir "$SC/old-with-keys/keys"
git init -q -b main "$SC/old-repo"; echo z > "$SC/old-repo/z"; git -C "$SC/old-repo" add z
git -C "$SC/old-repo" -c user.name=t -c user.email=t@example.invalid -c commit.gpgsign=false commit -qm "scratch-only commit"
for d in old-big old-with-keys old-repo; do find "$SC/$d" -exec touch -t 202609010000 {} +; done
# processes
sleep 311 & PA=$!; sleep 312 & PB=$!; PIDS="$PA $PB"
"$H" --repo "$M" register "$PA" run-owned-validator >/dev/null
bash -c "\"$H\" --repo \"$M\" register \$\$ exec-changes >/dev/null; exec sleep 313" & PC=$!; PIDS="$PIDS $PC"
bash -c 'while [ ! -f "$0" ]; do sleep 0.2; done; exec sleep 315' "$SB/flag" & PD=$!; PIDS="$PIDS $PD"
sleep 0.5
"$H" --repo "$M" register "$PD" late-exec >/dev/null
(cd "$WT/inuse" && exec sleep 316) & PE=$!; PIDS="$PIDS $PE"
sleep 0.5
echo "pids: registered-ok=$PA unregistered=$PB exec-changed-before-plan=$PC changes-after-plan=$PD cwd-in-worktree=$PE"
echo "registry:"; cut -f1,3,4 "$REG" | sed 's/^/    /'

echo; echo "== 1. scan (read-only)"
"$H" --repo "$M" scan --agents 4 | sed 's/^/    /'
echo "    exit=${PIPESTATUS[0]}"

echo; echo "== 2. normal plan"
P1="$SB/plan1.json"
"$H" --repo "$M" plan --out "$P1" | sed 's/^/    /'
echo "-- assertions on plan 1"
cls() { jq_ "$P1" "[i['class'] for i in d['items'] if i['path'].endswith('$1')]"; }
[ "$(cls /merged)" = "['worktree']" ] && ok "plan lists wt-merged as a whole-worktree removal" || bad "wt-merged plan item: $(cls /merged)"
[ "$(jq_ "$P1" "[i['class'] for i in d['items'] if i['path'].endswith('merged-env/target')]")" = "['worktree_target']" ] && ok "plan strips wt-merged-env target (worktree kept: has .env)" || bad "merged-env target"
jq_ "$P1" "next(i for i in d['items'] if i['path'].endswith('/merged'))['du_bytes'] - next(i for i in d['items'] if i['path'].endswith('/merged'))['reclaim_bytes']" | awk '{ if ($1 >= 2900000) print "  PASS  hard-link accounting: du exceeds reclaim by " $1 " bytes (the shared 3 MB store file is not counted as freed)"; else print "  FAIL  hard-link accounting " $1 }'
for n in dirty unique locked inuse; do
  [ "$(jq_ "$P1" "[i for i in d['items'] if '/$n' in i['path']]")" = "[]" ] && ok "plan has no item for wt-$n" || bad "plan wrongly contains wt-$n"
done
jq_ "$P1" "[s['reason'][:90] for s in d['skipped'] if '/dirty' in s['path'] or '/unique' in s['path'] or '/locked' in s['path'] or '/inuse' in s['path']]" | sed 's/^/    skip reasons: /'
[ "$(jq_ "$P1" "[i['needs_judgment'] for i in d['items'] if i['path'].endswith('/.next')]")" = "[True]" ] && ok "main .next is flagged needs-judgment in normal mode" || bad ".next flag"
[ "$(jq_ "$P1" "[i['needs_judgment'] for i in d['items'] if i['path'].endswith('old-repo')]")" = "[True]" ] && ok "scratch repo with a HEAD outside protected history is flagged needs-judgment" || bad "old-repo flag"
for n in old-with-keys young; do [ "$(jq_ "$P1" "[i for i in d['items'] if i['path'].endswith('$n')]")" = "[]" ] && ok "plan has no item for scratch/$n" || bad "scratch/$n in plan"; done

echo; echo "== 3. apply without --execute (dry-run) changes nothing"
"$H" --repo "$M" apply "$P1" | sed 's/^/    /'
kept "$WT/merged" "dry-run"; kept "$SC/old-big" "dry-run"

echo; echo "== 4. tampered plan items are refused"
python3 - "$P1" "$SB/plan-tampered.json" "$M" <<'PY'
import json,sys
d=json.load(open(sys.argv[1])); m=sys.argv[3]
d['items']=[
 dict(id=1,**{"class":"cache"},path=m+"/keys",reason="t",needs_judgment=False,approved=True,du_bytes=0,reclaim_bytes=0),
 dict(id=2,**{"class":"scratch"},path=m+"/docs/evidence",reason="t",needs_judgment=False,approved=True,du_bytes=0,reclaim_bytes=0),
 dict(id=3,**{"class":"rm_rf"},path=m,reason="t",needs_judgment=False,approved=True,du_bytes=0,reclaim_bytes=0),
 dict(id=4,**{"class":"worktree"},path=m+"/.claude/worktrees/locked",reason="t",needs_judgment=False,approved=True,du_bytes=0,reclaim_bytes=0),
 dict(id=5,**{"class":"worktree"},path=m+"/.claude/worktrees/dirty",reason="t",needs_judgment=False,approved=True,du_bytes=0,reclaim_bytes=0),
 dict(id=6,**{"class":"worktree"},path=m+"/.claude/worktrees/unique",reason="t",needs_judgment=False,approved=True,du_bytes=0,reclaim_bytes=0),
 dict(id=7,**{"class":"worktree"},path=m+"/.claude/worktrees/merged-env",reason="t",needs_judgment=False,approved=True,du_bytes=0,reclaim_bytes=0),
 dict(id=8,**{"class":"scratch"},path=m.replace("main","scratch")+"/old-with-keys",reason="t",needs_judgment=False,approved=True,du_bytes=0,reclaim_bytes=0),
 dict(id=9,**{"class":"worktree"},path=m,reason="t",needs_judgment=False,approved=True,du_bytes=0,reclaim_bytes=0),
 dict(id=10,**{"class":"worktree"},path=m+"/.claude/worktrees/inuse",reason="t",needs_judgment=False,approved=True,du_bytes=0,reclaim_bytes=0)]
json.dump(d,open(sys.argv[2],'w'))
PY
"$H" --repo "$M" apply "$SB/plan-tampered.json" --execute | sed 's/^/    /'
for p in "$M/keys" "$M/docs/evidence" "$M/.env" "$WT/locked" "$WT/dirty" "$WT/unique" "$WT/merged-env" "$SC/old-with-keys" "$WT/inuse"; do kept "$p" "tampered plan"; done
kept "$M/a.txt" "main checkout intact"

echo; echo "== 5. normal plan: apply --execute"
"$H" --repo "$M" apply "$P1" --execute | sed 's/^/    /'
echo "-- removed"
gone "$WT/merged"; gone "$SC/old-big"; gone "$WT/merged-env/target"; gone "$WT/merged-env/node_modules"
echo "-- survived"
kept "$WT/merged-env" "has ignored .env, worktree kept"; kept "$WT/merged-env/.env" "ignored file preserved"
kept "$WT/dirty/target" "dirty worktree"; kept "$WT/dirty/a.txt"; grep -q dirty-edit "$WT/dirty/a.txt" && ok "dirty edit content intact" || bad "dirty edit lost"
kept "$WT/unique/target" "unique commit"; unique_ok && ok "unique commit intact" || bad "unique commit lost"
kept "$WT/locked" "locked"; kept "$WT/locked/target" "locked"; kept "$WT/inuse" "process cwd inside"; kept "$WT/inuse/target"
kept "$SC/young"; kept "$SC/old-with-keys" "contains .env and keys/"; kept "$SC/old-repo" "needs judgment, not approved"
kept "$M/.next" "needs judgment, not approved"; kept "$M/target" "shared build dir"
kept "$M/keys/id.json"; kept "$M/.env"; kept "$M/docs/evidence/run1.txt"
for b in wt-merged wt-merged-env wt-dirty wt-unique wt-locked wt-inuse; do G rev-parse --verify -q "refs/heads/$b" >/dev/null && ok "branch kept: $b" || bad "branch deleted: $b"; done
[[ "$(G worktree list)" == *"/merged "* ]] && bad "wt-merged still registered" || ok "wt-merged unregistered from git"
echo "-- processes: memory=warn, so registered kills are listed but flagged needs-judgment and not approved"
for pp in "$PA:registered" "$PB:unregistered" "$PC:exec-changed" "$PD:late-exec" "$PE:cwd"; do alive "${pp%%:*}" "${pp##*:}, normal mode"; done

echo; echo "== 6. emergency plan; process D changes its command line AFTER the plan is written"
P2="$SB/plan2.json"
"$H" --repo "$M" plan --emergency --out "$P2" | sed 's/^/    /'
touch "$SB/flag"; sleep 1   # PD now execs 'sleep 315': command line no longer matches its registration
echo "    (pid $PD now runs: $(ps -ww -o command= -p $PD))"
echo "-- apply emergency plan"
jq_ "$P2" "[i['id'] for i in d['items'] if i['class']=='scratch' and i['path'].endswith('old-repo')][0]" > "$SB/oldrepo.id"
"$H" --repo "$M" apply "$P2" --execute | sed 's/^/    /'
echo "-- removed"
gone "$M/.next"; gone "$WT/dirty/target"; gone "$WT/dirty/node_modules"; gone "$WT/unique/target"; gone "$WT/unique/node_modules"
dead "$PA" "registered, command line matched"
echo "-- survived"
kept "$WT/locked/target" "locked worktree, even in emergency"; kept "$WT/locked/node_modules"
kept "$WT/inuse/target" "process cwd inside"; kept "$M/target" "shared build dir needs approval"
kept "$WT/dirty" ; kept "$WT/dirty/a.txt"; grep -q dirty-edit "$WT/dirty/a.txt" && ok "dirty edit content intact" || bad "dirty edit lost"
unique_ok && ok "unique commit intact" || bad "unique commit lost"
kept "$SC/old-repo" "judgment unapproved"; kept "$SC/old-with-keys"; kept "$SC/young"
kept "$M/keys/id.json"; kept "$M/.env"; kept "$M/docs/evidence/run1.txt"
alive "$PB" "never registered"
alive "$PC" "command line changed by exec before plan"
alive "$PD" "command line changed after plan, caught at apply-time re-verification"
alive "$PE" "not registered"

echo; echo "== 7. approving a judgment item (scratch repo with unique commit) by id"
P3="$SB/plan3.json"; "$H" --repo "$M" plan --emergency --out "$P3" >/dev/null
ID=$(jq_ "$P3" "[i['id'] for i in d['items'] if i['path'].endswith('old-repo')][0]")
"$H" --repo "$M" apply "$P3" --execute --approve "$ID" | sed 's/^/    /'
gone "$SC/old-repo"; kept "$M/target" "shared build dir still not approved"

echo; echo "== 8. hygiene log (events)"
python3 - "$HYGIENE_LOG" <<'PY'
import json,sys
for l in open(sys.argv[1]):
    d=json.loads(l)
    if d['event'] in ('removed','refuse','fail','apply_end'):
        print("    %-9s %s" % (d['event'], (d.get('item') or '')[:70] + ((' :: '+d['reason'][:70]) if d.get('reason') and d['event']=='refuse' else (' free %s -> %s' % (d.get('free_bytes_before'), d.get('free_bytes_after')) if d['event']=='apply_end' else ''))))
PY

echo; echo "== result: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
