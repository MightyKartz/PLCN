"""Check the actual inline UI scripts with Node, without running the application."""
from pathlib import Path
import re
import subprocess


def main():
    page = Path(__file__).resolve().parents[1] / 'src' / 'templates' / 'plcn.html'
    scripts = re.findall(r'<script\b[^>]*>(.*?)</script>', page.read_text(encoding='utf-8'), re.S | re.I)
    if not scripts:
        raise RuntimeError('No inline scripts found')
    subprocess.run(['node', '--check'], input='\n'.join(scripts), encoding='utf-8', check=True)
    print(f'JavaScript syntax OK ({len(scripts)} inline script blocks)')


if __name__ == '__main__':
    main()
