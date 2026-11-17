"""Run the actual JavaScript state rules and filter behavior under Node in CI."""
import subprocess
from pathlib import Path


def test_workbench_behavior():
    root = Path(__file__).resolve().parents[2]
    scripts = sorted((root / 'tests').glob('*.test.cjs'))
    subprocess.run(['node', '--test', *map(str, scripts)], cwd=root, check=True)
