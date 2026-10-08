"""Memory evidence survives backend shape differences without inventing RAM usage."""
from io import BytesIO
import json
import unittest
from unittest.mock import patch
from memory_metrics import sample, summarize
from remote_metrics import snapshot


class MemoryMetricsTests(unittest.TestCase):
    def test_native_footprint_does_not_become_rss_or_lifetime_peak(self):
        data = {'mem': {'phys_footprint_bytes': 500, 'active_memory_bytes': 300,
                        'peak_memory_bytes': 900, 'prompt_preview': 'PRIVATE'},
                'in_flight': [{'prompt_preview': 'ALSO PRIVATE'}]}
        with patch('memory_metrics.server_config.get', return_value={'ok': True}), \
                patch('memory_metrics.snapshot', return_value=data):
            row = sample()
        self.assertIsNone(row['server_rss_bytes'])
        self.assertEqual(row['native_memory']['phys_footprint_bytes'], 500)
        self.assertNotIn('PRIVATE', json.dumps(row))
        result = summarize([row])
        self.assertEqual(result['server_phys_footprint_peak_sampled_bytes'], 500)
        self.assertEqual(result['active_allocation_peak_sampled_bytes'], 300)

    def test_health_and_native_fail_independently(self):
        with patch('memory_metrics.server_config.get', side_effect=OSError('offline')), \
                patch('memory_metrics.snapshot', return_value={'mem': {'phys_footprint_bytes': 45}}):
            self.assertEqual(sample()['native_memory']['phys_footprint_bytes'], 45)
        with patch('memory_metrics.server_config.get', return_value={'server_rss_bytes': 31,
                   'active_memory_bytes': 20}), patch('memory_metrics.snapshot', side_effect=ValueError('unsupported')):
            row = sample()
        self.assertEqual(row['server_rss_bytes'], 31)
        self.assertEqual(row['native_memory'], {'active_memory_bytes': 20})

    def test_unknown_and_invalid_are_not_false_zero_measurements(self):
        with patch('memory_metrics.server_config.get', return_value={'server_rss_bytes': True}), \
                patch('memory_metrics.snapshot', return_value={'mem': {
                    'phys_footprint_bytes': '123', 'active_memory_bytes': -1, 'cache_memory_bytes': False}}):
            row = sample()
        self.assertIsNone(row['server_rss_bytes'])
        self.assertEqual(row['native_memory'], {})
        result = summarize([row, {'native_memory': None}])
        self.assertIsNone(result['server_phys_footprint_peak_sampled_bytes'])
        self.assertEqual(result['server_phys_footprint_samples'], 0)
        self.assertEqual(result['memory_sample_count'], 2)

    def test_sample_maxima_ignore_missing_values_and_keep_zero(self):
        rows = [{'native_memory': {'phys_footprint_bytes': n}} for n in (0, 14, 8)] + [{}]
        result = summarize(rows)
        self.assertEqual(result['server_phys_footprint_peak_sampled_bytes'], 14)
        self.assertEqual(result['server_phys_footprint_samples'], 3)
        self.assertIsNone(result['active_allocation_peak_sampled_bytes'])


class SnapshotTests(unittest.TestCase):
    def test_reads_one_snapshot_closes_stream_and_preserves_auth(self):
        stream = BytesIO(b': heartbeat\n' + b'data: {"mem":{"active_memory_bytes":12}}\n')
        with patch('remote_metrics.urllib.request.urlopen', return_value=stream) as get:
            self.assertEqual(snapshot('http://local:8000/v1', {'Authorization': 'Bearer test'})['mem'],
                             {'active_memory_bytes': 12})
        self.assertTrue(stream.closed)
        request = get.call_args.args[0]
        self.assertEqual(request.full_url, 'http://local:8000/v1/mtplx/metrics/stream')
        self.assertEqual(request.get_header('Authorization'), 'Bearer test')
        self.assertEqual(get.call_args.kwargs['timeout'], 2)

    def test_malformed_empty_and_excessive_snapshots_fail_boundedly(self):
        for raw in (b'', b'data: []\n', b'data: broken\n', b': ping\n' * 11,
                    b'data: ' + b'x' * 2097152 + b'\n'):
            with self.subTest(size=len(raw)), patch('remote_metrics.urllib.request.urlopen', return_value=BytesIO(raw)):
                with self.assertRaises(ValueError): snapshot('http://local', {})


if __name__ == '__main__':
    unittest.main()
