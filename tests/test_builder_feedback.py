import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_cpp import SERVER
from toksec import campaign, context, controller, releases, runner
from toksec.provenance import checkout


CLIENT = r'''
#include <arpa/inet.h>
#include <sys/socket.h>
#include <unistd.h>
#include <string>
int main() {
    if (access("/candidate/server", F_OK) == 0 || access("/fixtures", F_OK) == 0 ||
        access("/home", F_OK) == 0 || access("/test-client", X_OK) != 0) return 21;
    int fd = socket(AF_INET, SOCK_STREAM, 0);
    sockaddr_in target{};
    target.sin_family = AF_INET;
    target.sin_port = htons(8080);
    target.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    if (connect(fd, (sockaddr*)&target, sizeof(target)) != 0) return 22;
    std::string request = "GET /hello.txt HTTP/1.1\r\nHost: alpha.test\r\nConnection: close\r\n\r\n";
    if (write(fd, request.data(), request.size()) != (ssize_t)request.size()) return 23;
    std::string response;
    char buf[512];
    ssize_t n;
    while ((n = read(fd, buf, sizeof(buf))) > 0) response.append(buf, n);
    close(fd);
    return response.ends_with("hello toksec\n") ? 0 : 7;
}
'''


class BuilderFeedbackTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        directory = Path(temp.name) / 'campaign'
        campaign.initialize(directory, '3', request_profile='bounded-32k')
        # This local no-provider test can also run inside a working-tree diff.
        with patch('toksec.controller.checkout', return_value=checkout()):
            self.run = Path(controller.prepare(directory, 14, model=campaign.TERRA, language='cpp')['run'])

    def test_candidate_identity_release_and_recovery_feedback(self):
        first = runner.dispatch(self.run, 'submit_candidate', {'source': SERVER, 'release_note': 'first server'})
        tip = first['release']
        self.assertEqual((tip['tag'], tip['publication']), ('release/000001', 'published'), first)
        digest = first['source_sha256']
        test = {'source': CLIENT, 'source_sha256': digest}
        good = runner.dispatch(self.run, 'run_candidate_test', test)
        self.assertTrue(good['passed'] and good['tests']['passed'], good)
        self.assertEqual(good['test_sha256'], hashlib.sha256(CLIENT.encode()).hexdigest())
        self.assertEqual((good['binary_sha256'], good['tests']['exit_code']), (first['binary_sha256'], 0))
        self.assertTrue(good['tests']['ready'])

        old = 'hello toksec'
        second = runner.dispatch(self.run, 'edit_candidate', {
            'source_sha256': digest, 'old': old, 'new': 'other toksec', 'release_note': 'candidate B'})
        self.assertTrue(second['build']['passed'])
        self.assertEqual(second['release']['publication'], 'rejected')
        self.assertEqual(len(releases.list_releases(self.run)), 1)
        stale_edit = {'source_sha256': digest, 'old': old, 'new': 'x', 'release_note': None}
        with self.assertRaisesRegex(ValueError, 'latest'):
            runner.dispatch(self.run, 'edit_candidate', stale_edit)
        second_test = runner.dispatch(self.run, 'run_candidate_test', {**test, 'source_sha256': second['source_sha256']})
        self.assertEqual(second_test['tests']['exit_code'], 7, second_test)
        self.assertEqual(second_test['test_sha256'], good['test_sha256'])
        self.assertNotEqual(second_test['binary_sha256'], good['binary_sha256'])
        self.assertTrue(runner.dispatch(self.run, 'run_candidate_test', test)['tests']['passed'])

        saved = json.loads(context.checkpoint(self.run, 'frozen contract')[1]['content'])
        self.assertEqual(saved['last_failed_test']['source_sha256'], second['source_sha256'])
        self.assertEqual(saved['capacity']['last_tag']['commit'], tip['commit'])
        self.assertEqual(saved['capacity']['latest_source_sha256'], second['source_sha256'])
        self.assertEqual(releases.initialize(self.run)['publication'], 'already_published')
        rolled_back = runner.dispatch(self.run, 'edit_candidate', {
            'source_sha256': second['source_sha256'], 'old': 'other toksec',
            'new': old, 'release_note': 'restore working source'})
        self.assertEqual(rolled_back['release']['publication'], 'already_published')
        self.assertEqual(len(releases.list_releases(self.run)), 1)

    def test_bounded_read_and_failed_compile(self):
        source = '/*' + ('a' * 25000) + '*/\nint main() {broken;}\n'
        first = runner.dispatch(self.run, 'submit_candidate', {'source': source})
        self.assertFalse(first['build']['passed'])
        args = {'source_sha256': first['source_sha256'], 'line_count': 1, 'start_line': 1, 'start_column': 1}
        read = runner.dispatch(self.run, 'read_source', args)
        self.assertTrue(read['truncated'])
        self.assertEqual(len(read['text']), 24000)
        tail = runner.dispatch(self.run, 'read_source', {**args, 'start_column': 24001})
        self.assertEqual(read['text'] + tail['text'], source.splitlines(keepends=True)[0])
        self.assertEqual(runner.dispatch(self.run, 'read_source', {**args, 'start_line': 2})['text'],
                         'int main() {broken;}\n')
        saved = json.loads(context.checkpoint(self.run, 'contract')[1]['content'])
        self.assertNotIn('source', saved['candidates'][0])
        with self.assertRaisesRegex(ValueError, 'did not compile'):
            runner.dispatch(self.run, 'run_candidate_test', {'source_sha256': first['source_sha256'], 'source': CLIENT})
        with self.assertRaisesRegex(ValueError, 'source_sha256'):
            runner.dispatch(self.run, 'run_candidate_test', {'source_sha256': None, 'source': CLIENT})


if __name__ == '__main__':
    unittest.main()
