"""Recover published reviews without regenerating them or resetting repair limits."""
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import test_recovery_runner as fixtures
from recovery_runner import execute
from runner_process import read,save
from recovery_accept import accept


class AcceptanceTests(unittest.TestCase):
    setUp=fixtures.RecoveryTests.setUp
    packet=fixtures.RecoveryTests.packet
    runner=fixtures.RecoveryTests.runner
    reviewer=fixtures.RecoveryTests.reviewer

    def stopped(self):
        def published(root,evidence,output,provider,timeout):
            self.reviewer(root,evidence,output,provider,timeout)
            session=self.base/'session';session.mkdir()
            save(session/'launch.json',{'role':'architect','project':str(root),'plan':str(output)})
            save(session/'replan-evidence.json',read(evidence))
            save(session/'planning-stop.json',{'plan':str(output),'sha256':hashlib.sha256(output.read_bytes()).hexdigest()})
            return {'passed':False,'exit_code':124,'session':str(session),'plan':str(output)}
        with patch('role_selection.load',return_value={'planner':'qwen'}):
            result=execute(self.root,self.path,self.folder,executor=self.runner,reviewer=published)
        self.assertEqual(result['code'],20)
        return read(self.folder/'recovery-state.json')

    def test_saved_review_continues_once_preserving_timeout_and_allowance(self):
        before=self.stopped()
        with patch('role_selection.load',return_value={'planner':'qwen'}):
            result=execute(self.root,self.path,self.folder,resume=True,accept_review=True,
                           executor=self.runner,reviewer=self.reviewer)
        self.assertEqual(result['code'],0);self.assertEqual(len(self.runs),2)
        self.assertFalse(self.runs[-1][-1]);self.assertEqual(len(self.reviews),1)
        after=read(self.folder/'recovery-state.json')
        self.assertEqual(after['spent_ids'],before['spent_ids'])
        self.assertEqual(after['repairs'][0]['review_result_original']['exit_code'],124)
        self.assertTrue(after['repairs'][0]['review_result']['passed'])

    def test_failed_corrective_execution_still_asks_user(self):
        self.stopped();self.codes=[20]
        with patch('role_selection.load',return_value={'planner':'qwen'}):
            result=execute(self.root,self.path,self.folder,accept_review=True,
                           executor=self.runner,reviewer=self.reviewer)
        self.assertEqual(result['code'],20);self.assertEqual(len(self.reviews),1)

    def test_changed_output_source_and_wrong_session_binding_cannot_be_adopted(self):
        state=self.stopped();plan=Path(state['repairs'][0]['plan']);original=plan.read_bytes()
        plan.write_bytes(original+b' ')
        with self.assertRaisesRegex(ValueError,'changed'):accept(self.root,self.folder,state)
        plan.write_bytes(original)
        launch=self.base/'session/launch.json';data=read(launch);save(launch,{**data,'project':'/wrong'})
        with self.assertRaisesRegex(ValueError,'different'):accept(self.root,self.folder,state)
        save(launch,data);(self.root/'one.py').write_text('changed=1\n')
        with self.assertRaisesRegex(ValueError,'stale'):accept(self.root,self.folder,state)
        self.assertFalse((self.folder/'accepted-saved-review.json').exists())


if __name__=='__main__':unittest.main()
