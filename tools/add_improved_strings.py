# -*- coding: utf-8 -*-
"""Adds the Improved-demount strings to every language file.

en and zh_cn get real translations; the other 26 get the English text as a
placeholder, matching how a missing key already falls back at runtime but
without leaving the files inconsistent with one another.

    D:\\Python\\Python_2.7.18\\python.exe tools\\add_improved_strings.py [--check]

--check only reports which files are missing any of the keys.
"""

import glob
import io
import json
import os
import sys
from collections import OrderedDict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LANG_DIR = os.path.join(ROOT, 'res', 'gui', 'maps', 'icons', 'z4imon')

# key -> (english, chinese). The Chinese wording mirrors the existing bounty
# entries ("赏金配件") so the two rows read as siblings (issue #42).
NEW_KEYS = [
    ('demountAllImproved',
     u'Demount all improved equipment',
     u'\u4e00\u952e\u62c6\u5378\u6539\u8fdb\u578b\u88c5\u5907\u5230\u4ed3\u5e93'),
    ('demountAllImprovedWaiting',
     u'Demounting improved equipment\u2026',
     u'\u6b63\u5728\u62c6\u5378\u6539\u8fdb\u578b\u88c5\u5907\u2026'),
    ('demountAllImprovedDone',
     u'AutoEquipmentReturn: %(count)d improved item(s) demounted from '
     u'%(vehicles)d vehicle(s)',
     u'AutoEquipmentReturn: \u5df2\u4ece %(vehicles)d \u8f86\u5766\u514b\u4e0a'
     u'\u62c6\u5378 %(count)d \u4ef6\u6539\u8fdb\u578b\u88c5\u5907'),
    ('demountAllImprovedNothing',
     u'AutoEquipmentReturn: no improved equipment found that can be demounted '
     u'for free',
     u'AutoEquipmentReturn: \u6ca1\u6709\u627e\u5230\u53ef\u514d\u8d39\u62c6'
     u'\u5378\u7684\u6539\u8fdb\u578b\u88c5\u5907'),
    ('demountAllImprovedUnsupported',
     u'AutoEquipmentReturn: this server does not allow demounting improved '
     u'equipment for free',
     u'AutoEquipmentReturn: \u5f53\u524d\u670d\u52a1\u5668\u4e0d\u652f\u6301'
     u'\u514d\u8d39\u62c6\u5378\u6539\u8fdb\u578b\u88c5\u5907'),
    ('cmDemountImproved',
     u'Demount improved equipment',
     u'\u62c6\u5378\u6539\u8fdb\u578b\u88c5\u5907'),
    ('featureToggleDemountAllImproved',
     u'@demountAllImproved',
     u'@demountAllImproved'),
    ('featureToggleDemountAllImprovedCarousel',
     u'@cmDemountImproved',
     u'@cmDemountImproved'),
]

# Where each key belongs in the file, so the diff stays readable: right after
# its bounty counterpart instead of appended to the end.
ANCHORS = {
    'demountAllImproved': 'demountAllTrophy',
    'demountAllImprovedWaiting': 'demountAllTrophyWaiting',
    'demountAllImprovedDone': 'demountAllTrophyDone',
    'demountAllImprovedNothing': 'demountAllTrophyNothing',
    'demountAllImprovedUnsupported': 'demountAllTrophyNothing',
    'cmDemountImproved': 'cmDemountTrophy',
    'featureToggleDemountAllImproved': 'featureToggleDemountAllBounty',
    'featureToggleDemountAllImprovedCarousel': 'featureToggleDemountAllBountyCarousel',
}


def load(path):
    """A Python 2 dict has no order, so a plain json.load() would rewrite every
    language file in hash order - a whole-file diff for eight new keys. Ordered
    so the file keeps its existing sequence and the diff stays readable."""
    with io.open(path, 'r', encoding='utf-8') as handle:
        return json.load(handle, object_pairs_hook=OrderedDict)


def dump(path, data):
    """Rewrites the file in the format it already has: UTF-8, no BOM, and a
    single trailing newline. Line endings follow the file being replaced, so a
    CRLF file does not turn into a whole-file diff."""
    with io.open(path, 'rb') as handle:
        eol = u'\r\n' if b'\r\n' in handle.read() else u'\n'
    lines = [u'{']
    items = list(data.items())
    for index, (key, value) in enumerate(items):
        comma = u',' if index < len(items) - 1 else u''
        lines.append(u'    %s: %s%s' % (json.dumps(key),
                                        json.dumps(value, ensure_ascii=False),
                                        comma))
    lines.append(u'}')
    with io.open(path, 'w', encoding='utf-8', newline='') as handle:
        handle.write(eol.join(lines) + eol)


def ordered(data, additions):
    """`data` with `additions` inserted after their anchor key."""
    out = OrderedDict()
    pending = OrderedDict(additions)
    for key, value in data.items():
        out[key] = value
        for new_key, new_value in list(pending.items()):
            if ANCHORS.get(new_key) == key:
                out[new_key] = new_value
                del pending[new_key]
    # Anything whose anchor did not exist still has to land somewhere.
    for new_key, new_value in pending.items():
        out[new_key] = new_value
    return out


def main():
    check_only = '--check' in sys.argv
    files = sorted(glob.glob(os.path.join(LANG_DIR, 'lang_*.json')))
    if not files:
        print('no language files found in %s' % LANG_DIR)
        return 1

    incomplete = 0
    for path in files:
        code = os.path.basename(path)[len('lang_'):-len('.json')]
        data = load(path)
        missing = [(key, en, zh) for key, en, zh in NEW_KEYS if key not in data]

        if check_only:
            if missing:
                incomplete += 1
                print('%-8s missing %d key(s)' % (code, len(missing)))
            continue

        if not missing:
            continue
        additions = [(key, zh if code == 'zh_cn' else en)
                     for key, en, zh in missing]
        dump(path, ordered(data, additions))
        print('%-8s added %d key(s)%s'
              % (code, len(additions), ' (translated)' if code == 'zh_cn' else ''))

    if check_only:
        print('%d/%d files complete' % (len(files) - incomplete, len(files)))
        return 1 if incomplete else 0
    return 0


if __name__ == '__main__':
    sys.exit(main())
