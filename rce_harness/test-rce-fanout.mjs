#!/usr/bin/env node
/**
 * test-rce-fanout — pins the round-verdict contract of scripts/rce_fanout.py:
 *   1. The prompt and HUNT_BRIEF both quote the marker text, so an echo must
 *      NOT count as a verdict (the bug: one round flagged confirmed AND negative).
 *   2. Only an anchored marker line is a verdict, and the last one wins.
 *   3. The brief in the runner stays in sync with the canonical document.
 * Exit 0 = all green.
 */
import { execFileSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(__dirname, '..');
const HARNESS = __dirname;

let pass = 0, fail = 0;
const eq = (label, got, want) =>
  (got === want ? (pass++, console.log(`  ok   ${label} = ${JSON.stringify(got)}`))
                : (fail++, console.log(`  BAD  ${label}: got ${JSON.stringify(got)} want ${JSON.stringify(want)}`)));

console.log('\n==== rce-fanout verdict tests ====\n');

const py = `
import importlib.util, json, sys
spec = importlib.util.spec_from_file_location('rf', 'rce_harness/rce_fanout.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
cases = {
    'echo_only': 'Last line of your reply: \`RCE CONFIRMED: <mechanism>\` or \`NO RCE FOUND: <family>\`.',
    'confirm': 'Built it.\\n\\nRCE CONFIRMED: spool overflow',
    'negative': 'Swept sizes.\\n\\nNO RCE FOUND: spool length E0 sweep',
    'blank_tail': 'done\\n\\nNO RCE FOUND: path admitted set\\n\\n',
    'tool_tail': 'RCE CONFIRMED: %n write\\n---\\n',
    'none': 'still hunting',
}
print(json.dumps({k: m.closing_marker(v) for k, v in cases.items()}))
`;

const out = JSON.parse(execFileSync('python3', ['-c', py], { cwd: REPO, encoding: 'utf8' }));
eq('brief echo alone is not a verdict', out.echo_only, null);
eq('explicit confirmation is parsed', out.confirm, 'RCE CONFIRMED');
eq('a properly scoped negative is parsed', out.negative, 'NO RCE FOUND');
eq('a blank trailing line still parses', out.blank_tail, 'NO RCE FOUND');
eq('a trailing tool artifact still parses', out.tool_tail, 'RCE CONFIRMED');
eq('no marker yields null', out.none, null);

try {
  execFileSync('python3', ['rce_harness/gen_hunt_brief.py', '--check'], { cwd: REPO, stdio: 'pipe' });
  pass++; console.log('  ok   brief matches the canonical document');
} catch {
  fail++; console.log('  BAD  brief drifted from RCE_HUNT_FINDERS.md');
}

console.log(`\n${pass} passed, ${fail} failed\n`);
process.exit(fail ? 1 : 0);
