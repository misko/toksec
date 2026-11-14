import argparse
import json
from pathlib import Path

from toksec import campaign, controller, runner, reporting, evaluate, releases
from toksec.specification import publish


def main():
    parser = argparse.ArgumentParser(description='Public, independent Rust HTTP experiments with a shared campaign spending cap.')
    commands = parser.add_subparsers(dest='command', required=True)
    check = commands.add_parser('check', help='Sandboxed compile and public tests without API calls')
    check.add_argument('--source', type=Path, required=True)
    check.add_argument('--output', type=Path, required=True)
    check.add_argument('--level', type=int, choices=range(1,6), required=True)
    check.add_argument('--performance', action='store_true')
    pub = commands.add_parser('publish', help='Generate all five complete contracts. No API call.')
    pub.add_argument('--output', type=Path, default=Path('tasks/v6'))
    for name in ('init', 'status', 'upgrade'):
        cmd = commands.add_parser(name)
        cmd.add_argument('--campaign', type=Path, required=True)
        if name == 'init':
            cmd.add_argument('--budget-usd', default='3', help='Start a fresh campaign without importing historical charges')
    prepare = commands.add_parser('prepare', help='Prepare an independent level. No API call.')
    prepare.add_argument('--campaign', type=Path, required=True)
    prepare.add_argument('--level', type=int, choices=range(1, 6), required=True)
    prepare.add_argument('--model', choices=['gpt-6-luna', 'gpt-6.1-terra'], default='gpt-6-luna')
    prepare.add_argument('--starter', type=Path)
    prepare.add_argument('--spend-target-usd', help='Stop this run after settled spending reaches this target; a call can cross it')
    prepare.add_argument('--wall-seconds', type=int, default=7200)
    for name in ('preflight', 'run', 'submit', 'benchmark', 'export', 'test', 'report', 'revalidate', 'init-repository', 'release', 'releases', 'grade'):
        cmd = commands.add_parser(name)
        cmd.add_argument('--run', type=Path, required=True)
        if name == 'release':
            cmd.add_argument('--note', required=True)
        if name == 'grade':
            cmd.add_argument('--output', type=Path, required=True)
            cmd.add_argument('--performance', action='store_true')
        if name == 'revalidate':
            cmd.add_argument('--target', choices=['incumbent', 'latest'], default='incumbent')
        if name in ('submit', 'test'):
            cmd.add_argument('--source', type=Path, required=True)
        if name == 'run':
            cmd.add_argument('--key-file', type=Path)
    args = parser.parse_args()
    try:
        if args.command == 'check':
            result = evaluate.evaluate(args.source, args.output, args.level, args.performance)
            print(json.dumps(result, indent=2))
            return 0 if result.get('checks', {}).get('passed') else 2
        elif args.command == 'publish':
            publish(args.output)
            result = {'published': str(args.output.resolve())}
        elif args.command == 'init':
            result = campaign.initialize(args.campaign, args.budget_usd)
        elif args.command == 'status':
            result = campaign.status(args.campaign)
        elif args.command == 'upgrade':
            result = campaign.upgrade(args.campaign)
        elif args.command == 'prepare':
            result = controller.prepare(args.campaign, args.level, args.wall_seconds, args.model, args.starter, args.spend_target_usd)
        elif args.command in ('init-repository', 'release'):
            with campaign.locked(controller.read(args.run, 'manifest.json')['campaign'], owner=True):
                result = releases.initialize(args.run) if args.command == 'init-repository' else releases.publish(args.run, args.note)
        elif args.command == 'releases':
            result = {'releases': releases.list_releases(args.run)}
        elif args.command == 'grade':
            with campaign.locked(controller.read(args.run, 'manifest.json')['campaign'], owner=True):
                result = releases.grade(args.run, args.output, args.performance)
            print(json.dumps(result, indent=2))
            return 0 if result.get('checks', {}).get('passed') else 2
        elif args.command == 'report':
            print(reporting.markdown(args.run))
            return 0
        elif args.command == 'revalidate':
            with campaign.locked(controller.read(args.run, 'manifest.json')['campaign'], owner=True):
                result = controller.revalidate(args.run, args.target)
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
