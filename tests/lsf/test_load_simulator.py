"""The simulator must propagate demand, expose invalid assumptions, and never send traffic."""
import shutil
import subprocess
import pytest
from conftest import SKILL


def test_capacity_model_and_failure_propagation():
    node = shutil.which('node')
    if not node:
        pytest.skip('node unavailable')
    source = SKILL / 'assets/load-simulator.js'
    script = r'''
const assert=require('node:assert/strict'),sim=require(process.argv[1]);
const m={entry:'api',nodes:[{id:'api',capacity_rps:1000},{id:'cache',capacity_rps:1000},{id:'db',capacity_rps:100}],edges:[{from:'api',to:'cache',factor:0.8},{from:'cache',to:'db',factor:0.1},{from:'api',to:'db',factor:0.2}]};
let r=sim.simulate(m,1000,1,1,[]);
assert.equal(r.nodes[0].demand,1000);
assert.ok(Math.abs(r.nodes[2].demand-280)<1e-8); // merging cache misses and direct writes
assert.equal(r.bottleneck,'db');
assert.ok(Math.abs(r.maxUsers-100/0.28)<1e-8);
assert.equal(r.nodes[2].saturated,true);
assert.equal(r.edges[0].affected,true); // entry at capacity
r=sim.simulate(m,10,1,1,['cache']);
assert.equal(r.nodes[1].capacity,0);
assert.equal(r.nodes[2].affected,true);
assert.equal(r.maxUsers,0);
assert.equal(sim.simulate(m,0,1,1,[]).nodes[2].demand,0);
assert.equal(sim.simulate(m,10,0,1,[]).maxUsers,null);
assert.throws(()=>sim.simulate(m,-1,1,1,[]),/nonnegative/);
assert.throws(()=>sim.simulate(m,Infinity,1,1,[]),/finite/);
assert.throws(()=>sim.validate({...m,edges:[...m.edges,{from:'db',to:'api',factor:1}]}),/Cycles/);
assert.throws(()=>sim.validate({...m,edges:[{from:'bad',to:'db',factor:1}]}),/endpoints/);
assert.throws(()=>sim.validate({...m,nodes:[{id:'api',capacity_rps:-1}]}),/capacity/);
assert.equal(sim.simulate({entry:'__proto__',nodes:[{id:'__proto__',capacity_rps:10}],edges:[]},1,1,1,[]).nodes[0].demand,1);
'''
    subprocess.run([node, '-e', script, str(source)], check=True, capture_output=True, text=True)


def test_inline_model_matches_and_has_no_network_or_execution_apis():
    js = (SKILL / 'assets/load-simulator.js').read_text().strip()
    html = (SKILL / 'assets/dashboard.html').read_text()
    assert js in html
    for forbidden in ('fetch(', 'XMLHttpRequest', 'WebSocket', 'sendBeacon', 'eval(', 'innerHTML'):
        assert forbidden not in js
    assert '["load","Load simulator"]' in html
    assert 'SIMULATED ESTIMATES ONLY' in html


def test_repo_model_collection_and_invalid_json(repo):
    import json
    from conftest import run
    model = repo / 'docs/load-model.json'
    model.parent.mkdir()
    model.write_text('{broken')
    data = json.loads(run(repo, 'bundle', '--json').stdout)['tabs']['load_model']
    assert data['available'] is False
    assert 'invalid JSON' in data['reason']
    value = {'entry': 'cli', 'nodes': [{'id': 'cli', 'capacity_rps': 10}], 'edges': []}
    model.write_text(json.dumps(value))
    data = json.loads(run(repo, 'bundle', '--json').stdout)['tabs']['load_model']
    assert data['available'] is True
    assert data['items'] == [value]
