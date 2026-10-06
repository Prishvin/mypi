"""Exercise pinned artifacts, resume, guards and ownership without a model load."""
import hashlib
import json
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import model_download
import qwen_config
import guard
import service


def safetensors(names):
    """Small genuine header/payload fixture, not a model weight download."""
    header = json.dumps({name: {'dtype': 'F32', 'shape': [1], 'data_offsets': [4 * n, 4 * (n + 1)]}
                         for n, name in enumerate(names)}).encode()
    return struct.pack('<Q', len(header)) + header + b'\0' * 4 * len(names)


class Artifacts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.directory = self.root / 'model'; self.directory.mkdir()
        self.raw = {'config.json': b'{"bits":8}',
                    'model.safetensors': safetensors(['weights']), 'mtp.safetensors': safetensors(['draft']),
                    'model.safetensors.index.json': b'{"weight_map":{"weights":"model.safetensors"}}'}
        entries = []
        for name, raw in self.raw.items():
            large = name.endswith('.safetensors')
            entries.append({'rfilename': name, 'size': len(raw),
                            'lfs': {'sha256': hashlib.sha256(raw).hexdigest()} if large else None,
                            'blob_id': hashlib.sha1(f'blob {len(raw)}\0'.encode() + raw).hexdigest()})
        self.model = {'repo': 'fixture/model', 'revision': 'frozen-revision', 'files': entries,
                      'total_bytes': sum(len(v) for v in self.raw.values())}
        self.calls = []

    def downloader(self, repo, filename, **kwargs):
        self.calls.append((repo, filename, kwargs))
        (kwargs['local_dir'] / filename).write_bytes(self.raw[filename])

    def download(self, **kwargs):
        return model_download.download(self.model, self.directory, self.root / 'state',
                                       downloader=self.downloader, **kwargs)

    def test_pinned_sequential_resume_skips_verified_file_and_repairs_partial(self):
        (self.directory / 'config.json').write_bytes(self.raw['config.json'])
        (self.directory / 'model.safetensors').write_bytes(b'partial')
        report = self.download()
        self.assertEqual([r[1] for r in self.calls], list(self.raw)[1:])
        self.assertTrue(self.calls[0][2]['force_download'])
        self.assertTrue(all(c[2]['revision'] == 'frozen-revision' for c in self.calls))
        self.assertEqual(report['indexed_tensors'], 1); self.assertFalse(report['model_loaded'])
        self.calls.clear(); self.download()
        self.assertEqual(self.calls, [])

    def test_verify_only_detects_same_size_corruption_without_redownload(self):
        self.download(); self.calls.clear()
        path = self.directory / 'model.safetensors'; raw = path.read_bytes()
        path.write_bytes(raw[:-1] + b'1')
        with self.assertRaisesRegex(ValueError, 'checksum'): self.download(verify_only=True)
        self.assertEqual(self.calls, [])

    def test_index_and_mtp_are_checked_without_materializing_payloads(self):
        self.download()
        (self.directory / 'model.safetensors.index.json').write_text('{"weight_map":{"absent":"model.safetensors"}}')
        with self.assertRaisesRegex(ValueError, 'Indexed tensor missing'): model_download.verify_index(self.directory)
        (self.directory / 'model.safetensors.index.json').write_bytes(self.raw['model.safetensors.index.json'])
        (self.directory / 'mtp.safetensors').write_bytes(safetensors([]))
        with self.assertRaisesRegex(ValueError, 'Empty MTP'): model_download.verify_index(self.directory)

    def test_manifest_cannot_escape_or_follow_a_symlink(self):
        with self.assertRaises(ValueError): model_download.target(self.directory, {'rfilename': '../outside'})
        (self.directory / 'alias').symlink_to(self.root / 'outside')
        with self.assertRaises(ValueError): model_download.target(self.directory, {'rfilename': 'alias'})


class Recipe(unittest.TestCase):
    def test_command_and_child_environment_match_measured_parameters(self):
        settings = {'root': '/host', 'model_dir': '/models/quality', 'port': 8000}
        argv = qwen_config.command(settings, Path('/logs'))
        for flag, value in {'--context-window': '98304', '--max-tokens': '32768', '--depth': '3',
                            '--generation-mode': 'mtp', '--paged-kv-quantization': 'off', '--memory-limit': '48G',
                            '--preserve-thinking': 'auto', '--reasoning-effort': 'medium', '--profile': 'turbo'}.items():
            self.assertEqual(argv[argv.index(flag) + 1], value)
        with patch.dict(os.environ, {'MTPLX_EXPERIMENT': 'bad', 'MTPLX_THINKING_BUDGET': '999'}):
            env = qwen_config.environment(Path('/logs'))
        self.assertNotIn('MTPLX_EXPERIMENT', env)
        self.assertEqual(env['MTPLX_THINKING_BUDGET'], '4096')
        self.assertEqual(env['MTPLX_PI_THINKING_CAPS'], '1')

    def test_memory_boundary_includes_swapout_growth_and_pressure(self):
        baseline = {'pressure': 1, 'swap_used_bytes': 100, 'swapouts_bytes': 200}
        limit = 8 * 1024**3
        self.assertFalse(guard.exceeds({**baseline, 'swap_used_bytes': 100 + limit}, baseline))
        self.assertTrue(guard.exceeds({**baseline, 'swapouts_bytes': 201 + limit}, baseline))
        self.assertTrue(guard.exceeds({**baseline, 'pressure': 4}, baseline))

    def test_same_package_name_does_not_bypass_server_source_hash(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / '.venv/lib/python3.12/site-packages/mtplx/server/openai.py'
            path.parent.mkdir(parents=True); path.write_text('unreviewed source')
            with self.assertRaisesRegex(ValueError, 'differs'): qwen_config.verify_server_source(folder)

    def test_linux_cannot_accidentally_install_a_metal_host(self):
        with patch('qwen_config.platform.system', return_value='Linux'):
            with self.assertRaisesRegex(ValueError, 'Apple Silicon'): qwen_config.supported_host()

    def test_service_reuses_only_matching_model_and_controls(self):
        settings = {'model_dir': '/models/quality'}
        good = {'ok': True, 'model': 'mtplx-quality', 'model_path': '/models/quality',
                'context_window': 98304, 'generation_mode': 'mtp', 'depth': 3,
                'paged_kv_quantization': 'off', 'preserve_thinking': 'auto'}
        self.assertTrue(service.compatible(good, settings))
        for key, value in [('depth', 1), ('context_window', 65536), ('paged_kv_quantization', 'q4'),
                           ('model_path', '/models/different'), ('preserve_thinking', 'off')]:
            self.assertFalse(service.compatible({**good, key: value}, settings))

    def test_stop_refuses_an_independently_owned_current_model(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch('service.health', return_value={'ok': True}), patch('service.os.kill') as kill:
                with self.assertRaisesRegex(ValueError, 'another launcher'):
                    service.stop({'root': folder, 'port': 8000})
                kill.assert_not_called()

    def test_ownership_needs_matching_live_nonce_and_guard_command(self):
        result = type('Result', (), {'returncode': 0, 'stdout': f'python {service.BASE}/guard.py --identity mine'})()
        with patch('service.subprocess.run', return_value=result):
            self.assertTrue(service.owned({'guard_pid': 100, 'identity': 'mine'}))
            self.assertFalse(service.owned({'guard_pid': 100, 'identity': 'other'}))
            self.assertFalse(service.owned({'guard_pid': 1, 'identity': 'mine'}))


if __name__ == '__main__': unittest.main()
