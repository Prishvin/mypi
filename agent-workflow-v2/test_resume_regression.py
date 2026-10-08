"""Real Node discovery may include unfinished tests; accepted failures still block."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from resume_regression import check
from runner_evidence import regression


@unittest.skipUnless(shutil.which('node'), 'Node is required for real discovery checks')
class ResumeDiscovery(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        base=Path(self.tmp.name);self.root=base/'project';self.root.mkdir()
        self.folder=base/'run';self.folder.mkdir();tests=self.root/'test';tests.mkdir()
        self.old=tests/'accepted.test.mjs';self.old.write_text("import test from 'node:test';import assert from 'node:assert/strict';test('accepted',()=>assert.equal(1,1));")
        self.new=tests/'pending.test.mjs';self.new.write_text("import test from 'node:test';import assert from 'node:assert/strict';test('pending',()=>assert.equal(1,2));")
        shadow=base/'shadow';shadow.mkdir();(shadow/'manifest.json').write_text(json.dumps({'files':[{'path':'test/accepted.test.mjs'}]}))
        (base/'task-state.json').write_text(json.dumps({'shadow':str(shadow)}))
        self.completed=[{'id':'accepted','files':['test/accepted.test.mjs'],'evidence':str(base/'gate.json'),
                         'tests':[['node','--test','test']], 'execution':{'test_timeout_seconds':10}}]
        self.pending=[{'id':'pending','files':['test/pending.test.mjs']}]

    def test_resume_passes_without_modifying_project_but_full_acceptance_still_fails(self):
        before={p.name:p.read_bytes() for p in (self.root/'test').iterdir()}
        result=check(self.root,self.completed,self.pending,self.folder)
        self.assertTrue(result['passed']);self.assertEqual(result['pending_discovery_files'],['test/pending.test.mjs'])
        self.assertEqual(before,{p.name:p.read_bytes() for p in (self.root/'test').iterdir()})
        self.assertFalse(regression(self.root,self.completed,self.folder)['passed'])

    def test_real_accepted_failure_still_blocks(self):
        self.old.write_text(self.old.read_text().replace('1,1','1,2'))
        self.assertFalse(check(self.root,self.completed,self.pending,self.folder)['passed'])

    def test_undeclared_new_test_is_not_omitted(self):
        self.assertFalse(check(self.root,self.completed,[],self.folder)['passed'])

    def test_previously_accepted_file_cannot_be_omitted(self):
        self.completed[0]['files'].append('test/pending.test.mjs')
        self.assertFalse(check(self.root,self.completed,self.pending,self.folder)['passed'])

    def test_explicit_failed_command_is_not_reinterpreted_as_discovery(self):
        self.completed[0]['tests']=[['node','--test','test/pending.test.mjs']]
        self.assertFalse(check(self.root,self.completed,self.pending,self.folder)['passed'])


if __name__=='__main__':unittest.main()
