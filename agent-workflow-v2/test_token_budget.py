"""Verify that serialized counting includes extra backend headroom."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from token_budget import count_request


class AdmissionTests(unittest.TestCase):
    def test_margin_rejects_payload_that_only_bare_count_would_allow(self):
        """The budget protects the demonstrated JSON/backend tokenizer mismatch."""
        with tempfile.TemporaryDirectory() as folder:
            request = Path(folder) / 'request.json'; request.write_text('{"messages":[]}')
            tokenizer = Mock(); tokenizer.encode.return_value.ids = list(range(6000))
            with patch('token_budget.Tokenizer.from_file', return_value=tokenizer):
                result = count_request(request, 7000, Path('/unused'))
            self.assertEqual(result['admission_tokens'], 7756)
            self.assertFalse(result['passed'])


if __name__ == '__main__':
    unittest.main()
