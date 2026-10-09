"""Fault injection against the actual checkpoint C code using fake flash/NVS."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import wasmtime


class CheckpointTests(unittest.TestCase):
    def test_power_loss_and_resume(self):
        root = Path(__file__).resolve().parents[1]
        main = (root / 'main/main.c').read_text(encoding='utf-8')
        start = main.index('typedef struct {')
        row_type = main[start:main.index('} report_row_t;', start) + len('} report_row_t;')]
        harness = (root / 'tests/checkpoint_harness.c').read_text().replace('/*ROW_TYPE*/', row_type)
        with tempfile.TemporaryDirectory() as temp:
            source, output = Path(temp)/'test.c', Path(temp)/'test.wasm'
            source.write_text(harness, encoding='utf-8')
            subprocess.run([shutil.which('clang'), '--target=wasm32', '-nostdlib', '-fno-builtin', '-O1',
                '-Wl,--no-entry', '-Wl,--export=check', '-I', str(root/'main'), str(source), '-o', str(output)], check=True)
            engine = wasmtime.Engine(); store = wasmtime.Store(engine)
            instance = wasmtime.Instance(store, wasmtime.Module.from_file(engine, str(output)), [])
            names = ['restore 2000 rows', 'skip repeated interrupted image', 'torn payload',
                     'missing commit', 'committed row before reset', 'changed experiment',
                     'full partition preserves data', 'failed NVS commit']
            for mode, name in enumerate(names):
                with self.subTest(name=name):
                    self.assertEqual(instance.exports(store)['check'](store,mode),0)


if __name__ == '__main__': unittest.main()
