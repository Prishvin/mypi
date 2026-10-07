"""A missing native request must not look like complete benchmark evidence."""
import unittest
from metrics_coverage import summarize


class CoverageTests(unittest.TestCase):
    def test_missing_native_call_and_zero_reasoning_usage_are_visible(self):
        events = [{'type': 'request_start', 'request_id': f'run-{i}'} for i in range(3)]
        events += [{'type': 'request_end', 'request_id': 'run-0', 'usage': {'reasoning': 20}},
                   {'type': 'first_token', 'request_id': 'run-1', 'kind': 'thinking_delta'},
                   {'type': 'request_end', 'request_id': 'run-1', 'usage': {'reasoning': 0}}]
        native = [{'request_id': 'chatcmpl-run-0', 'decode_tok_s': 20},
                  {'request_id': 'chatcmpl-run-2', 'request_cancelled': True, 'decode_tok_s': 18}]
        result = summarize(events, native)
        self.assertEqual(result['native_matched_requests'], 2)
        self.assertEqual(result['native_missing_request_ids'], ['run-1'])
        self.assertFalse(result['native_complete'])
        self.assertEqual(result['completed_requests_with_decode_speed'], 1)
        self.assertFalse(result['completed_speed_coverage_complete'])
        self.assertEqual(result['reasoning_usage_missing_request_ids'], ['run-1'])
        self.assertTrue(result['reasoning_usage_observed_incomplete'])

    def test_completed_speeds_can_be_complete_with_cancelled_request(self):
        events = [{'type': 'request_end', 'request_id': 'run-1'},
                  {'type': 'request_end', 'request_id': 'run-2', 'partial': True}]
        result = summarize(events, [{'request_id': 'chatcmpl-run-1', 'decode_tok_s': 10},
                                   {'request_id': 'run-2', 'request_cancelled': True}])
        self.assertTrue(result['native_complete'])
        self.assertTrue(result['completed_speed_coverage_complete'])
        self.assertEqual(result['completed_requests_with_ids'], 1)

    def test_missing_speed_and_unidentified_legacy_usage_are_not_complete(self):
        result = summarize([{'type': 'request_end', 'request_id': 'run-1'}, {'type': 'request_end'}],
                           [{'request_id': 'run-1', 'decode_tok_s': None}])
        self.assertEqual(result['unidentified_provider_results'], 1)
        self.assertFalse(result['native_complete'])
        self.assertFalse(result['completed_speed_coverage_complete'])
        empty = summarize([], [])
        self.assertFalse(empty['native_complete'])

    def test_ids_are_exact_and_duplicates_do_not_inflate_coverage(self):
        event = {'type': 'request_end', 'request_id': 'run-1'}
        result = summarize([event, event], [{'request_id': 'other-run-1', 'decode_tok_s': 99},
                                           {'request_id': 'run-10', 'decode_tok_s': 99}])
        self.assertEqual(result['completed_requests_with_ids'], 1)
        self.assertEqual(result['native_matched_requests'], 0)

    def test_positive_reasoning_and_text_only_zero_are_not_flagged(self):
        events = [{'type': 'first_token', 'request_id': 'a', 'kind': 'thinking_delta'},
                  {'type': 'request_end', 'request_id': 'a', 'usage': {'reasoning': 5}},
                  {'type': 'first_token', 'request_id': 'b', 'kind': 'text_delta'},
                  {'type': 'request_end', 'request_id': 'b', 'usage': {'reasoning': 0}}]
        self.assertFalse(summarize(events, [])['reasoning_usage_observed_incomplete'])


if __name__ == '__main__':
    unittest.main()
