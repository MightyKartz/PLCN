"""Check UI scripts, their page load order and inline event handlers with Node."""
from pathlib import Path
import html as html_parser
import re
import subprocess


def main():
    page = Path(__file__).resolve().parents[1] / 'src' / 'templates' / 'plcn.html'
    html = page.read_text(encoding='utf-8')
    scripts = []
    for attrs, body in re.findall(r'<script\b([^>]*)>(.*?)</script>', html, re.S | re.I):
        source = re.search(r'\bsrc="/assets/([^"/]+)"', attrs)
        scripts.append((page.parent / source.group(1)).read_text(encoding='utf-8') if source else body)
    if not scripts:
        raise RuntimeError('No UI scripts found')
    # Checking the combined program also catches duplicate global lexical declarations.
    subprocess.run(['node', '--check'], input='\n'.join(scripts), encoding='utf-8', check=True)
    for script in page.parent.glob('*.js'):
        subprocess.run(['node', '--check', str(script)], check=True)
    handlers = re.findall(r'\bon\w+="([^"]*)"', html)
    subprocess.run(['node', '--check'], input='\n'.join(
        'function handler' + str(index) + '(event) {\n' + html_parser.unescape(body) + '\n}'
        for index, body in enumerate(handlers)
    ), encoding='utf-8', check=True)
    print(f'JavaScript syntax OK ({len(scripts)} script blocks, {len(handlers)} event handlers)')


if __name__ == '__main__':
    main()
