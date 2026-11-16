"""Join a MAME XML catalog and tab-separated Chinese game list by ROM-set ID."""
import argparse
import csv
from pathlib import Path
import re
import xml.etree.ElementTree as ET


def build(xml_path, chinese_path, output):
    chinese = {}
    for line in Path(chinese_path).read_text(encoding='utf-8-sig').splitlines():
        fields = line.split('\t')
        if len(fields) >= 2 and fields[0] and fields[1]:
            chinese[fields[0]] = re.split(r'[（(]', fields[1], maxsplit=1)[0].strip()
    root = ET.parse(xml_path).getroot()
    records = [(game.attrib['name'], game.findtext('description'), chinese[game.attrib['name']])
               for game in root.findall('game') if game.attrib.get('name') in chinese and game.findtext('description')]
    with Path(output).open('w', encoding='utf-8', newline='') as handle:
        writer = csv.writer(handle, lineterminator='\n')
        writer.writerow(['MAME Name', 'EN Name', 'CN Name'])
        writer.writerows(sorted(records))
    return len(records)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('xml')
    parser.add_argument('chinese')
    parser.add_argument('output')
    args = parser.parse_args()
    print(build(args.xml, args.chinese, args.output))
