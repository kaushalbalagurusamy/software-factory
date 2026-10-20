"""Readiness must bind an explicit completion signal to a clean exact commit."""
import importlib.util
from pathlib import Path
import pytest

P = Path(__file__).resolve().parents[2] / 'scripts/watch-vps-lsf.py'
spec = importlib.util.spec_from_file_location('vps_watch', P)
watch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watch)
SHA = 'a' * 40


def test_ready_exact_clean_commit():
    assert watch.ready_commit(dict(marker=dict(ready=True, commit=SHA), head=SHA, dirty='')) == SHA


@pytest.mark.parametrize('marker,head,dirty', [
    ('invalid', SHA, ''), ({'ready': True, 'commit': None}, SHA, ''),
    (None, SHA, ''), ({'commit': SHA}, SHA, ''),
    ({'ready': True, 'commit': SHA}, 'b' * 40, ''),
    ({'ready': True, 'commit': SHA}, SHA, ' M skills/lsf/scripts/lsf.py'),
    ({'ready': True, 'commit': '../bad'}, '../bad', ''),
])
def test_refuses_partial_stale_dirty_or_invalid_completion(marker, head, dirty):
    assert watch.ready_commit(dict(marker=marker, head=head, dirty=dirty)) is None
