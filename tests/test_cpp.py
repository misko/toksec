import json
import tempfile
import unittest
from pathlib import Path
from toksec import campaign, context, controller, releases, sandbox
from toksec.specification import packet, specification

SERVER = r'''
#include <sys/socket.h>
#include <netinet/in.h>
#include <unistd.h>
#include <string>
int main(){
 int s=socket(AF_INET,SOCK_STREAM,0),one=1;
 setsockopt(s,SOL_SOCKET,SO_REUSEADDR,&one,sizeof(one));
 sockaddr_in a{};a.sin_family=AF_INET;a.sin_port=htons(8080);a.sin_addr.s_addr=htonl(INADDR_LOOPBACK);
 if(bind(s,(sockaddr*)&a,sizeof(a))||listen(s,64))return 1;
 while(true){int c=accept(s,nullptr,nullptr);if(c<0)continue;
  char b[8192];int n=read(c,b,sizeof(b));
  if(n>0){std::string r="HTTP/1.1 200 OK\r\nContent-Length: 13\r\nConnection: close\r\n\r\nhello toksec\n";send(c,r.data(),r.size(),MSG_NOSIGNAL);}close(c);
 }
}
'''


class CppTests(unittest.TestCase):
    def test_language_contract_preserves_api_and_workloads(self):
        for level in range(1, 6):
            cpp=specification(level,'cpp');rust=specification(level)
            self.assertEqual(cpp['cases'],rust['cases'])
            self.assertEqual(cpp['benchmarks'],rust['benchmarks'])
            self.assertEqual(cpp['requirements'],rust['requirements'])
            text=packet(level,'cpp')
            self.assertIn('main.cpp',text)
            self.assertNotIn('main.rs',text)
            self.assertNotIn('rustc',text)
        with self.assertRaises(ValueError):
            specification(6,'cpp')

    def test_cpp_tests_are_sandboxed_and_assertions_enabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            source='#include <unistd.h>\n#include <cassert>\n#include <vector>\nint main(){assert(access("/home/mouse9911/.codexapi",F_OK)!=0);std::vector<int> v{1};assert(v[0]==1);}'
            report=sandbox.build(source,root/'good',1,test=True,language='cpp')
            self.assertTrue(report['passed'],report)
            self.assertTrue(sandbox.self_test(root/'good')['passed'])
            report=sandbox.build('#include <cassert>\nint main(){assert(false);}',root/'bad',1,test=True,language='cpp')
            self.assertTrue(report['passed'],report)
            self.assertFalse(sandbox.self_test(root/'bad')['passed'])

    def test_rejects_third_party_headers_and_dynamic_loading(self):
        with tempfile.TemporaryDirectory() as tmp:
            for index,source in enumerate(('#include <openssl/ssl.h>\nint main(){}', '#include <dlfcn.h>\nint main(){return dlopen("libssl.so.3",RTLD_NOW)?0:1;}', '#include "/home/mouse9911/.codexapi"\nint main(){}')):
                report=sandbox.build(source,Path(tmp)/str(index),1,language='cpp')
                self.assertFalse(report['passed'],report)

    def test_cpp_tag_checkpoint_and_full_grade(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            campaign.initialize(root/'campaign','3')
            run=Path(controller.prepare(root/'campaign',1,model=campaign.TERRA,language='cpp')['run'])
            report=controller.submit(run,SERVER)
            self.assertTrue(report['checks']['passed'],report)
            release=releases.initialize(run)
            self.assertEqual(release['language'],'cpp')
            self.assertTrue((run/'repository/main.cpp').is_file())
            self.assertFalse((run/'repository/main.rs').exists())
            checkpoint=context.checkpoint(run,packet(1,'cpp'))
            self.assertIn(SERVER,json.loads(checkpoint[-1]['content'])['candidates'][0]['source'])
            graded=releases.grade(run,root/'grade')
            self.assertEqual(graded['language'],'cpp')
            self.assertTrue(graded['build']['passed'])
            self.assertFalse(graded['checks']['passed'])
            self.assertEqual(graded['grading']['performance_credit'],0)
