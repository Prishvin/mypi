"""No-Git initialization preserves files and creates a fresh prototype shadow."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import bootstrap

class Bootstrap(unittest.TestCase):
    def test_initialize_without_git_or_plan_is_repeatable(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(bootstrap,'BASE',Path(folder)/'workflow'):
            root=Path(folder)/'project';root.mkdir();source=root/'math.py'
            source.write_text('def add(a,b):\n    """Add two values."""\n    return a+b\n')
            before=source.read_bytes();one=bootstrap.initialize(root,'Add a tested small feature.')
            two=bootstrap.initialize(root,'Add a tested small feature.')
            self.assertTrue((root/'.git').exists());self.assertEqual(source.read_bytes(),before)
            self.assertEqual(one['shadow_snapshot'],two['shadow_snapshot'])
            self.assertFalse((root/'plan.json').exists())
            with self.assertRaises(ValueError):bootstrap.initialize(root,'Different request')

if __name__=='__main__':unittest.main()
