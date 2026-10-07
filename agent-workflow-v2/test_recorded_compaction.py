"""Historical recovery settings stay accurate across compaction-policy updates."""
import json
from pathlib import Path
import tempfile
import unittest
from recovery_controls import compaction_trigger


class RecordedCompactionTests(unittest.TestCase):
    def test_old_and_new_session_thresholds_are_read_without_exposing_other_settings(self):
        with tempfile.TemporaryDirectory() as folder:
            session = Path(folder)
            config = session / 'pi-config'
            config.mkdir()
            (config / 'models.json').write_text(json.dumps({'providers': {'local-qwen-workflow': {
                'apiKey': 'private', 'models': [{'contextWindow': 65536}]}}}))
            for reserve, expected in [(50176, 15360), (46080, 19456)]:
                (config / 'settings.json').write_text(json.dumps({'compaction': {'reserveTokens': reserve}}))
                self.assertEqual(compaction_trigger(session), expected)

    def test_missing_or_invalid_settings_are_not_invented(self):
        with tempfile.TemporaryDirectory() as folder:
            session = Path(folder)
            self.assertIsNone(compaction_trigger(session))
            config = session / 'pi-config'
            config.mkdir()
            (config / 'models.json').write_text(json.dumps({'providers': {'local-qwen-workflow': {
                'models': [{'contextWindow': 65536}]}}}))
            for reserve in [None, True, -1, 65536, '50000']:
                (config / 'settings.json').write_text(json.dumps({'compaction': {'reserveTokens': reserve}}))
                self.assertIsNone(compaction_trigger(session))


if __name__ == '__main__':
    unittest.main()
