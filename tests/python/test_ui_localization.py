"""Static interface text must opt into translation; user data is outside this boundary."""
from html.parser import HTMLParser
from pathlib import Path
import re


def test_static_chinese_labels_and_attributes_have_translation_markers():
    missing = []

    class Labels(HTMLParser):
        def __init__(self):
            super().__init__()
            self.stack = []

        def handle_starttag(self, tag, attributes):
            attrs = dict(attributes)
            for attribute in ('placeholder', 'title', 'aria-label'):
                if re.search(r'[\u4e00-\u9fff]', attrs.get(attribute, '')):
                    if 'data-i18n-' + attribute not in attrs:
                        missing.append((tag, attribute, attrs[attribute]))
            if tag not in ('input', 'img', 'link', 'meta', 'br', 'hr'):
                self.stack.append((tag, attrs))

        def handle_endtag(self, tag):
            for index in range(len(self.stack) - 1, -1, -1):
                if self.stack[index][0] == tag:
                    self.stack = self.stack[:index]
                    break

        def handle_data(self, text):
            if not re.search(r'[\u4e00-\u9fff]', text):
                return
            if any(tag in ('script', 'style', 'title') or 'data-i18n' in attrs or attrs.get('lang') == 'zh'
                   for tag, attrs in self.stack):
                return
            missing.append(text.strip())

    Labels().feed((Path(__file__).resolve().parents[2] / 'src/templates/plcn.html').read_text(encoding='utf-8'))
    assert not missing, missing
