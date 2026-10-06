"""No-Git initialization preserves files and creates a fresh prototype shadow."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import bootstrap

class Bootstrap(unittest.TestCase):
    def test_initialization_accepts_existing_large_architecture_without_editing_it(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(bootstrap,'BASE',Path(folder)/'workflow'):
            root=Path(folder)/'project';root.mkdir()
            doc=root/'architecture.md'
            original=('Existing architecture and module responsibilities.\n'*400).encode()
            doc.write_bytes(original)
            state=bootstrap.initialize(root)
            self.assertTrue(state['shadow_snapshot'])
            self.assertEqual(doc.read_bytes(),original)

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
