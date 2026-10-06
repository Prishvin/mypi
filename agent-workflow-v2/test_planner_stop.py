"""A stopped planner must still have a valid, unchanged structured contract."""
import hashlib
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
import plans
from planner_stop import exit_code
from test_plan_runner import todo


class PlannerStopTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        base=Path(self.temp.name);self.root=base/'project';self.root.mkdir()
        subprocess.run(['git','init','-q',str(self.root)],check=True)
        (self.root/'slug.py').write_text('def slugify(text):\n    """Normalize text."""\n    return text\n')
        self.session=base/'session';self.session.mkdir();self.path=base/'plan.json'
        task=todo();task['tests']=[[sys.executable,'-c',"from slug import slugify; assert slugify('ABC') == 'abc'"]]
        plans.save(self.root,['.'],{'plan_version':3,'goal':'Normalize','architecture':'Pure function','tasks':[task]},self.path)
        self.mark()

    def mark(self):
        (self.session/'planning-stop.json').write_text(json.dumps({'plan':str(self.path),
            'sha256':hashlib.sha256(self.path.read_bytes()).hexdigest()}))

    def test_matching_valid_plan_allows_deliberate_stop_but_never_timeout(self):
        self.assertEqual(exit_code(1,self.root,self.path,self.session),0)
        self.assertEqual(exit_code(124,self.root,self.path,self.session),124)
        self.assertEqual(exit_code(-15,self.root,self.path,self.session),-15)

    def test_missing_or_changed_plan_marker_cannot_hide_failure(self):
        self.path.write_text(self.path.read_text()+' ')
        self.assertEqual(exit_code(1,self.root,self.path,self.session),1)
        self.mark();(self.session/'planning-stop.json').unlink()
        self.assertEqual(exit_code(1,self.root,self.path,self.session),1)

    def test_matching_hash_does_not_bypass_contract_validation(self):
        plan=json.loads(self.path.read_text());plan['tasks'][0]['coverage']=[]
        self.path.write_text(json.dumps(plan));self.mark()
        self.assertEqual(exit_code(1,self.root,self.path,self.session),1)


if __name__=='__main__':unittest.main()
