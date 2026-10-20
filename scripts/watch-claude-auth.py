#!/usr/bin/env python3
"""Check both subscription logins and notify the Mac on confirmed logout."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import time

STATE = Path.home() / '.claude/auth-monitor'


def check(command):
    env = dict(os.environ)
    for key in ('ANTHROPIC_API_KEY', 'ANTHROPIC_AUTH_TOKEN'):
        env.pop(key, None)
    try:
        result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=30)
        value = json.loads(result.stdout).get('loggedIn')
        return value if isinstance(value, bool) else None
    except (subprocess.SubprocessError, OSError, ValueError):
        return None


def poll(binary):
    STATE.mkdir(parents=True, exist_ok=True)
    path = STATE / 'status.json'
    try:
        previous = json.loads(path.read_text())
    except (OSError, ValueError):
        previous = {}
    state = {'checked_at': datetime.now(timezone.utc).isoformat(), 'devices': {}}
    commands = {
        'Mac': [binary, 'auth', 'status'],
        'VPS': ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', 'vultr-claude',
                'env -u ANTHROPIC_API_KEY -u ANTHROPIC_AUTH_TOKEN ~/.local/bin/claude auth status'],
    }
    for device, command in commands.items():
        value = check(command)
        old = previous.get('devices', {}).get(device, {})
        entry = {'status': 'signed_in' if value is True else 'logged_out' if value is False else 'unreachable_or_unknown',
                 'last_known_logged_in': value if value is not None else old.get('last_known_logged_in')}
        if value is False and old.get('last_known_logged_in') is not False:
            # Static strings only: do not interpolate command output into AppleScript.
            note = 'Claude on ' + device + ' is logged out. Run claude auth login on that machine.'
            result = subprocess.run(['osascript', '-e', 'display notification ' + json.dumps(note)
                                     + ' with title "Claude login alert"'], capture_output=True, timeout=15)
            entry['notification_command_succeeded'] = result.returncode == 0
        state['devices'][device] = entry
    temp = STATE / 'status.tmp'
    temp.write_text(json.dumps(state, indent=2) + '\n')
    temp.replace(path)
    print(json.dumps(state), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--claude', required=True, help='Absolute path to the local Claude executable')
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    while True:
        poll(args.claude)
        if args.once:
            return
        time.sleep(300)


if __name__ == '__main__':
    main()
