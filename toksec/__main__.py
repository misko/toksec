import argparse
import json
from pathlib import Path

from toksec import campaign, controller, runner, reporting, evaluate, releases
from toksec.specification import publish
from toksec.stage_dispatch import SUPPORTED_STAGES, operation_lock


def main(argv=None):
    parser = argparse.ArgumentParser(description='Independent Rust/C++ HTTP experiments with a shared campaign cap; Stage 10 coverage is partial.')
    commands = parser.add_subparsers(dest='command', required=True)
    check = commands.add_parser('check', help='Sandboxed compile and independent checks without API calls')
    check.add_argument('--source', type=Path, required=True)
    check.add_argument('--output', type=Path, required=True)
    check.add_argument('--stage', '--level', dest='stage', type=int, choices=SUPPORTED_STAGES, required=True)
    check.add_argument('--performance', action='store_true')
    pub = commands.add_parser('publish', help='Generate stage packets; Stage 10 remains experimental. No API call.')
    pub.add_argument('--output', type=Path, default=None)
    pub.add_argument('--language', choices=('rust', 'cpp'), default='rust')
    pub.add_argument('--stage', '--level', dest='stage', type=int, choices=SUPPORTED_STAGES, help='One stage; omit for all Stage 1–5 packets')
    check.add_argument('--language', choices=('rust', 'cpp'), default='rust')
    for name in ('init', 'status', 'upgrade'):
        cmd = commands.add_parser(name)
        cmd.add_argument('--campaign', type=Path, required=True)
        if name == 'init':
            cmd.add_argument('--budget-usd', default='3', help='Start a fresh campaign without importing historical charges')
    prepare = commands.add_parser('prepare', help='Prepare an independent stage. No API call.')
    prepare.add_argument('--campaign', type=Path, required=True)
    prepare.add_argument('--stage', '--level', dest='stage', type=int, choices=SUPPORTED_STAGES, required=True)
    prepare.add_argument('--model', choices=['gpt-6-luna', 'gpt-6.1-terra'], default=None, help='Defaults to Terra for Stage 10 and Luna for Stages 1–5')
    prepare.add_argument('--language', choices=('rust', 'cpp'), default='rust')
    prepare.add_argument('--starter', type=Path)
    prepare.add_argument('--spend-target-usd', help='Stages 1–5: soft settled-spend target (a call may cross it). Stage 10: hard run allocation, at most $2')
    prepare.add_argument('--wall-seconds', type=int, default=7200)
    for name in ('preflight', 'run', 'submit', 'benchmark', 'export', 'test', 'report', 'revalidate', 'init-repository', 'release', 'releases', 'grade'):
        cmd = commands.add_parser(name)
        cmd.add_argument('--run', type=Path, required=True)
        if name == 'benchmark':
            cmd.add_argument('--workload', help='One declared workload ID; omit for full matrix')
        if name == 'release':
            cmd.add_argument('--note', required=True)
        if name == 'grade':
            cmd.add_argument('--output', type=Path)
            cmd.add_argument('--performance', action='store_true')
        if name == 'revalidate':
            cmd.add_argument('--target', choices=['incumbent', 'latest'], default='incumbent')
        if name in ('submit', 'test'):
            cmd.add_argument('--source', type=Path, required=True)
        if name == 'run':
            cmd.add_argument('--key-file', type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == 'check':
            result = evaluate.evaluate(args.source, args.output, args.stage, args.performance, language=args.language)
            print(json.dumps(result, indent=2))
            return evaluate.exit_code(result, args.performance)
        elif args.command == 'publish':
            output = args.output or Path('.generated/packets') / args.language
            publish(output, args.language, args.stage)
            result = {'published': str(output.resolve())}
        elif args.command == 'init':
            result = campaign.initialize(args.campaign, args.budget_usd)
        elif args.command == 'status':
            result = campaign.status(args.campaign)
            from toksec.accounting.run_allocations import status as stage10_status
            result['stage10'] = stage10_status(args.campaign)
        elif args.command == 'upgrade':
            result = campaign.upgrade(args.campaign)
        elif args.command == 'prepare':
            result = controller.prepare(args.campaign, args.stage, args.wall_seconds, args.model, args.starter, args.spend_target_usd, language=args.language)
        elif args.command in ('init-repository', 'release'):
            with operation_lock(args.run):
                result = releases.initialize(args.run) if args.command == 'init-repository' else releases.publish(args.run, args.note)
        elif args.command == 'releases':
            result = {'releases': releases.list_releases(args.run)}
        elif args.command == 'grade':
            with operation_lock(args.run):
                result = releases.grade(args.run, args.output, args.performance)
            print(json.dumps(result, indent=2))
            return evaluate.exit_code(result, args.performance)
        elif args.command == 'report':
            print(reporting.markdown(args.run))
            return 0
        elif args.command == 'revalidate':
            with operation_lock(args.run):
                result = controller.revalidate(args.run, args.target)
        elif args.command == 'preflight':
            result = runner.preflight(args.run)
        elif args.command == 'run':
            result = runner.run_loop(args.run, runner.Responses(runner.credentials(args.key_file)))
        elif args.command == 'submit':
            with operation_lock(args.run):
                result = controller.submit(args.run, args.source.read_text())
        elif args.command == 'test':
            with operation_lock(args.run):
                result = controller.test_source(args.run, args.source.read_text())
        elif args.command == 'benchmark':
            with operation_lock(args.run):
                result = controller.measure(args.run, args.workload)
        else:
            result = controller.export(args.run)
        print(json.dumps(result, indent=2, allow_nan=False))
        return 2 if result.get('launch_allowed') is False else 0
    except (OSError, ValueError, RuntimeError) as error:
        print(json.dumps({'error': str(error)}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
