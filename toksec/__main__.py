import argparse
import json
from pathlib import Path

from toksec import campaign, controller, runner
from toksec.specification import publish


def main():
    parser = argparse.ArgumentParser(description='Public, independent Rust HTTP experiments with a shared $5 campaign cap.')
    commands = parser.add_subparsers(dest='command', required=True)
    pub = commands.add_parser('publish', help='Generate all five complete contracts. No API call.')
    pub.add_argument('--output', type=Path, default=Path('tasks/v3'))
    for name in ('init', 'status', 'upgrade'):
        cmd = commands.add_parser(name)
        cmd.add_argument('--campaign', type=Path, required=True)
    prepare = commands.add_parser('prepare', help='Prepare an independent level. No API call.')
    prepare.add_argument('--campaign', type=Path, required=True)
    prepare.add_argument('--level', type=int, choices=range(1, 6), required=True)
    prepare.add_argument('--model', choices=['gpt-6-luna', 'gpt-6.1-terra'], default='gpt-6-luna')
    prepare.add_argument('--wall-seconds', type=int, default=1800)
    for name in ('preflight', 'run', 'submit', 'benchmark', 'export', 'test'):
        cmd = commands.add_parser(name)
        cmd.add_argument('--run', type=Path, required=True)
        if name in ('submit', 'test'):
            cmd.add_argument('--source', type=Path, required=True)
        if name == 'run':
            cmd.add_argument('--key-file', type=Path)
    args = parser.parse_args()
    try:
        if args.command == 'publish':
            publish(args.output)
            result = {'published': str(args.output.resolve())}
        elif args.command == 'init':
            result = campaign.initialize(args.campaign)
        elif args.command == 'status':
            result = campaign.status(args.campaign)
        elif args.command == 'upgrade':
            result = campaign.upgrade(args.campaign)
        elif args.command == 'prepare':
            result = controller.prepare(args.campaign, args.level, args.wall_seconds, args.model)
        elif args.command == 'preflight':
            result = runner.preflight(args.run)
        elif args.command == 'run':
            result = runner.run_loop(args.run, runner.Responses(runner.credentials(args.key_file)))
        elif args.command == 'submit':
            with campaign.locked(controller.read(args.run, 'manifest.json')['campaign'], owner=True):
                result = controller.submit(args.run, args.source.read_text())
        elif args.command == 'test':
            with campaign.locked(controller.read(args.run, 'manifest.json')['campaign'], owner=True):
                result = controller.test_source(args.run, args.source.read_text())
        elif args.command == 'benchmark':
            with campaign.locked(controller.read(args.run, 'manifest.json')['campaign'], owner=True):
                result = controller.measure(args.run)
        else:
            result = controller.export(args.run)
        print(json.dumps(result, indent=2, allow_nan=False))
        return 2 if result.get('launch_allowed') is False else 0
    except (OSError, ValueError, RuntimeError) as error:
        print(json.dumps({'error': str(error)}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
