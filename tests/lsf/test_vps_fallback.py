"""A remote fallback must keep local work and existing remote sessions isolated."""
import importlib.util
from pathlib import Path
import pytest

SOURCE = Path(__file__).resolve().parents[2] / 'scripts/lsf-vps.py'


def load():
    spec = importlib.util.spec_from_file_location('lsf_vps', SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('bad', ['../repo', 'a b', '$(touch bad)', '-other', '', 'a' * 49])
def test_rejects_names_that_can_escape_the_isolated_workspace(bad):
    with pytest.raises(ValueError):
        load().paths(bad)


def test_separates_agent_dashboard_and_review_paths():
    p = load().paths('peak6')
    assert p['remote'].endswith('/lsf-vps/peak6/repo')
    assert p['agent'] == 'lsf-vps-peak6'
    assert p['dashboard'] == 'lsf-dash-peak6'
    assert str(p['review']).endswith('/lsf-vps/peak6/current')


def test_rsync_excludes_dependencies_git_and_root_credentials_without_delete():
    args = load().copy_args('/tmp/original/', 'vultr-claude:/safe/repo/')
    assert '--delete' not in args
    assert '--safe-links' in args
    assert '--exclude=node_modules/' in args
    assert '--exclude=/.env' in args
    assert '--exclude=.git/' in args
    assert args[-2:] == ['/tmp/original/', 'vultr-claude:/safe/repo/']


def test_failed_snapshot_does_not_replace_current_review(tmp_path):
    m = load()
    old = tmp_path / 'old'
    old.mkdir()
    current = tmp_path / 'current'
    current.symlink_to(old)
    missing = tmp_path / 'missing'
    with pytest.raises(ValueError):
        m.publish_snapshot(current, missing)
    assert current.resolve() == old


def test_preserves_shallow_history_boundary(tmp_path):
    import subprocess
    source = tmp_path / 'source'
    subprocess.run(['git','init','-q',str(source)],check=True)
    for key,value in [('user.name','test'),('user.email','test@example.invalid')]:
        subprocess.run(['git','-C',str(source),'config',key,value],check=True)
    for n in range(2):
        subprocess.run(['git','-C',str(source),'commit','--allow-empty','-qm',str(n)],check=True)
    shallow = tmp_path / 'shallow'
    subprocess.run(['git','clone','-q','--depth','1',source.as_uri(),str(shallow)],check=True)
    boundary = load().shallow_boundary(shallow)
    assert boundary == (shallow/'.git/shallow').read_text()
    assert load().shallow_boundary(source) is None
