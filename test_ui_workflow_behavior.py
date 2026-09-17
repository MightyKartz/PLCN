"""Run the actual JavaScript state rules and filter behavior under Node in CI."""
import subprocess
from pathlib import Path


def test_workbench_behavior():
    root = Path(__file__).resolve().parent
    subprocess.run(['node', '--test', str(root / 'tests/ui_workflow.test.cjs'),
                    str(root / 'tests/library_browser.test.cjs'),
                    str(root / 'tests/welcome.test.cjs'),
                    str(root / 'tests/artwork_dialog.test.cjs')], cwd=root, check=True)
