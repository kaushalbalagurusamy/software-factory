#!/usr/bin/env python3
"""Launch an interactive, subscription-backed lightweight factory session."""
import argparse
import os
from pathlib import Path
import shutil
import sys


def prepare(argv, binary, cwd, environment):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', '-m', default='sonnet')
    parser.add_argument('--name', default='lsf-' + cwd.name)
    parser.add_argument('task', nargs='*')
    args = parser.parse_args(argv)
    prompt = (
        '/lsf\n'
        'Owner launch instructions: invoke the away-mode skill first. On macOS, '
        'keep this plugged-in, open Mac awake indefinitely for this session. '
        'On Linux, verify the persistent host/session instead of Mac power settings. Remote Control '
        'and bypass permissions are enabled by the launcher. When initializing a new '
        'project, use --editor antigravity-ide for dashboard code links. Use the selected '
        'model for subagents as well. When lsf-vps-test is on PATH, run test commands '
        'through it so process-tree memory and wall time are bounded; serialize heavy tests. '
        'Follow /lsf including its human checkpoints; '
        'never approve a checkpoint on behalf of the owner. '
    )
    if args.task:
        prompt += '\nOwner task:\n' + ' '.join(args.task)
    else:
        prompt += ('\nNo task has been supplied. Complete away-mode setup, then wait '
                   'for the owner brief before initializing the phase clock. '
                   'Do not invent a task or initialize a project yet.')
    env = dict(environment)
    for key in ('ANTHROPIC_API_KEY', 'ANTHROPIC_AUTH_TOKEN', 'ANTHROPIC_MODEL'):
        env.pop(key, None)
    env['CLAUDE_CODE_SUBAGENT_MODEL'] = args.model
    env['CLAUDE_CODE_SUBAGENT_MODEL_FORCE'] = '1'
    return [binary, '--dangerously-skip-permissions', '--remote-control', args.name,
            '--name', args.name, '--model', args.model, '--', prompt], env


def main():
    binary = os.environ.get('CLAUDE_LSF_BIN') or shutil.which('claude')
    if not binary:
        sys.exit('Claude Code is not on PATH. Install it before running claude -lsf.')
    command, env = prepare(sys.argv[1:], binary, Path.cwd(), os.environ)
    if sys.platform == 'darwin':
        command = ['/usr/bin/caffeinate', '-ims'] + command
    os.execvpe(command[0], command, env)


if __name__ == '__main__':
    main()
