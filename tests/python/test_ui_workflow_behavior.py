"""Run the actual JavaScript state rules and filter behavior under Node in CI."""
import subprocess
from pathlib import Path


def test_workbench_behavior():
    root = Path(__file__).resolve().parents[2]
    subprocess.run(['node', '--test', str(root / 'tests' / 'ui_workflow.test.cjs'),
                    str(root / 'tests' / 'library_browser.test.cjs'),
                    str(root / 'tests' / 'welcome.test.cjs'),
                    str(root / 'tests' / 'content_scan_state.test.cjs'),
                    str(root / 'tests' / 'preview_state.test.cjs'),
                    str(root / 'tests' / 'disc_inspection.test.cjs'),
                    str(root / 'tests' / 'm3u_state.test.cjs'),
                    str(root / 'tests' / 'storage_state.test.cjs'),
                    str(root / 'tests' / 'rom_storage_state.test.cjs'),
                    str(root / 'tests' / 'chd_deployment_state.test.cjs'),
                    str(root / 'tests' / 'artwork_dialog.test.cjs')], cwd=root, check=True)
