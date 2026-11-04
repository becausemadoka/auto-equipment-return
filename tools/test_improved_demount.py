# -*- coding: utf-8 -*-
"""Checks the Improved-demount feature (issue #42) without a game client.

What matters here is the GATING, not the demount itself (that reuses the bounty
path verbatim): the feature must be invisible and inert on WG, and available on
360 China where Plus demounts Improved devices for free.

    D:\\Python\\Python_2.7.18\\python.exe tools\\test_improved_demount.py
"""

import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import test_donor_lru as T

PREFS = os.path.join(os.environ['TEMP'], 'z4ae_improved')
T._install_game_stubs(PREFS)

ANY = T._Anything()


def stub(name, **attrs):
    parts = name.split('.')
    for index in range(1, len(parts)):
        parent = '.'.join(parts[:index])
        if parent not in sys.modules:
            sys.modules[parent] = types.ModuleType(parent)
    module = types.ModuleType(name)
    for key, value in attrs.iteritems():
        setattr(module, key, value)
    sys.modules[name] = module
    if len(parts) > 1:
        setattr(sys.modules['.'.join(parts[:-1])], parts[-1], module)
    return module


stub('ResMgr', openSection=lambda path: None, isFile=lambda path: False)
stub('BigWorld', player=lambda: ANY, callback=lambda *a, **k: 0,
     wg_openWebBrowser=lambda url: None)
stub('adisp', adisp_async=lambda func: func, adisp_process=lambda func: func)
stub('PlayerEvents', g_playerEvents=ANY)
stub('CurrentVehicle', g_currentVehicle=ANY)
stub('gui')
stub('gui.SystemMessages', pushMessage=lambda *a, **k: None)
stub('gui.Scaleform')
stub('gui.Scaleform.Waiting', Waiting=ANY)
stub('gui.shared')
stub('gui.shared.notifications', NotificationPriorityLevel=ANY,
     NotificationGuiSettings=ANY)
stub('gui.modsListApi', g_modsListApi=ANY)
stub('gui.shared.utils', getPlayerDatabaseID=lambda: 1000)
stub('gui.impl')
stub('gui.impl.gen', R=ANY)
stub('helpers', getPreferencesDirPath=lambda: PREFS,
     getClientLanguage=lambda: 'en', dependency=ANY)
stub('helpers.i18n', makeString=lambda key: key)
stub('constants', AUTH_REALM='EU')
# carousel_menu hooks the legacy Scaleform context menu.
stub('gui.Scaleform.daapi')
stub('gui.Scaleform.daapi.view')
stub('gui.Scaleform.daapi.view.lobby')
stub('gui.Scaleform.daapi.view.lobby.hangar')
stub('gui.Scaleform.daapi.view.lobby.hangar.hangar_cm_handlers',
     VehicleContextMenuHandler=type('VehicleContextMenuHandler', (object,), {
         '_generateOptions': lambda self, ctx=None: [],
         'onOptionSelect': lambda self, optionId: None,
     }))

T._load_package()
for name in ('log', 'config', 'hangar', 'usage', 'mode_sets', 'inventory',
             'rpc', 'messages'):
    T._load(name)

config = sys.modules['auto_equip.config']
inventory = sys.modules['auto_equip.inventory']
messages = sys.modules['auto_equip.messages']
carousel = T._load('carousel_menu')

config.load_for_account(1000)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class FakeDevice(object):
    """An optional device. isDeluxe is Improved (purple), isTrophy is bounty."""

    def __init__(self, name, deluxe=False, trophy=False, removable=False,
                 free=True, upgraded=False):
        self.userName = name
        self.name = name
        self.isDeluxe = deluxe
        self.isTrophy = trophy
        self.isRemovable = removable
        self.isUpgraded = upgraded
        self._free = free


IMPROVED = FakeDevice(u'Improved Exhaust', deluxe=True)
BOUNTY = FakeDevice(u'Bounty Rammer', trophy=True)
STANDARD = FakeDevice(u'Rammer')


class FakeVehicle(object):

    def __init__(self, inv_id, name, devices, level=10, locked=False):
        self.invID = inv_id
        self.userName = name
        self.level = level
        self.isLocked = locked
        self._devices = list(devices)


def install_fakes(vehicles, devices, free_function):
    """Points the mod at a fake garage and fake free-demount rules."""
    by_cd = dict((index + 1, device) for index, device in enumerate(devices))
    inventory.device_by_cd = lambda cd: by_cd.get(cd)
    inventory.owned_vehicles = lambda: list(vehicles)
    inventory.vehicle_by_inv_id = lambda inv_id: next(
        (v for v in vehicles if v.invID == inv_id), None)
    inventory.is_mode_only_vehicle = lambda v: False
    inventory.setup_indices = lambda v: [0]
    inventory.slot_capacity = lambda v: len(v._devices)
    inventory.active_setup_index = lambda v: 0
    inventory.setup_device_cds = lambda v, idx: list(v._devices)
    inventory.is_free_to_demount = free_function
    inventory.has_wot_plus = lambda: True
    # improved_demount_is_free is what the gate actually calls; the real one
    # probes the subscription controller, which does not exist here.
    inventory.improved_demount_is_free = free_function.improved


def make_free_rules(improved_is_free):
    def is_free(item):
        if item.isDeluxe:
            return improved_is_free
        return True
    is_free.improved = lambda: improved_is_free
    return is_free


def reset_toggles(**icon):
    for row in config._ICON_MENU_ROW_KEYS:
        config.set_icon_menu_row_enabled(row, icon.get(row, False))


def demount_all_improved(vehicles):
    """Kept for manual driving of the real adisp chain; adisp_process returns a
    generator whose yields hand back the inner step to drive in turn."""
    return carousel.demount_all_improved


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def check_gate_off_on_wg():
    """WG: Plus does not free-demount Improved, so the gate must say no."""
    install_fakes([FakeVehicle(1, u'A', [1])], [IMPROVED],
                  make_free_rules(improved_is_free=False))
    assert carousel.improved_demount_available() is False, (
        'WG reported Improved demount as available')
    print('   WG gate closed: OK')


def check_gate_on_360():
    install_fakes([FakeVehicle(1, u'A', [1])], [IMPROVED],
                  make_free_rules(improved_is_free=True))
    assert carousel.improved_demount_available() is True, (
        '360 China reported Improved demount as unavailable')
    print('   360 China gate open: OK')


def check_only_improved_selected():
    """The Improved scan must pick purple devices only - never bounty or plain."""
    install_fakes([FakeVehicle(1, u'A', [1, 2, 3]), FakeVehicle(2, u'B', [2, 3])],
                  [IMPROVED, BOUNTY, STANDARD], make_free_rules(True))
    found = carousel._deluxe_vehicles()
    names = [v.userName for v in found]
    assert names == [u'A'], names
    print('   only the tank with a purple device listed: OK (%s)' % names)


def check_carousel_option_hidden_on_wg():
    """No row on WG even with the toggle on - the gate wins."""
    install_fakes([FakeVehicle(1, u'A', [1])], [IMPROVED], make_free_rules(False))
    reset_toggles(demountImproved=True)
    config.set_carousel_menu_row_enabled('demountImproved', True)
    item = carousel._demount_all_improved_option(_Handler(1))
    assert item is None, 'a WG client was offered the Improved row'
    print('   WG: no carousel row: OK')


def check_carousel_option_shown_on_360():
    install_fakes([FakeVehicle(1, u'A', [1])], [IMPROVED], make_free_rules(True))
    reset_toggles(demountImproved=True)
    config.set_carousel_menu_row_enabled('demountImproved', True)
    item = carousel._demount_all_improved_option(_Handler(1))
    assert item is not None, '360 China did not get the Improved row'
    print('   360 China: carousel row built: OK')


def check_carousel_option_needs_toggle():
    """Opt-in like the bounty row: the default must not show it."""
    install_fakes([FakeVehicle(1, u'A', [1])], [IMPROVED], make_free_rules(True))
    reset_toggles()      # everything off
    config.set_carousel_menu_row_enabled('demountImproved', False)
    item = carousel._demount_all_improved_option(_Handler(1))
    assert item is None, 'row appeared without the player opting in'
    print('   opt-in respected: OK')


def check_bounty_path_unaffected():
    """The shared refactor must not change what the bounty scan selects."""
    install_fakes([FakeVehicle(1, u'A', [1, 2]), FakeVehicle(2, u'B', [3])],
                  [IMPROVED, BOUNTY, STANDARD], make_free_rules(True))
    found = carousel._trophy_vehicles()
    assert [v.userName for v in found] == [u'A'], [v.userName for v in found]
    print('   bounty scan still picks trophy tanks only: OK')


class _Handler(object):
    """Minimal VehicleContextMenuHandler stand-in."""

    def __init__(self, inv_id):
        self._inv_id = inv_id

    def getVehInvID(self):
        return self._inv_id

    def _makeItem(self, option_id, label, data):
        return {'id': option_id, 'label': label, 'data': data}


def main():
    checks = (
        ('WG gate closed', check_gate_off_on_wg),
        ('360 gate open', check_gate_on_360),
        ('purple-only scan', check_only_improved_selected),
        ('WG: row hidden', check_carousel_option_hidden_on_wg),
        ('360: row shown', check_carousel_option_shown_on_360),
        ('opt-in required', check_carousel_option_needs_toggle),
        ('bounty path intact', check_bounty_path_unaffected),
    )
    failures = 0
    for title, check in checks:
        print('-- %s' % title)
        try:
            check()
        except Exception as error:
            failures += 1
            print('   FAIL: %s: %s' % (type(error).__name__, error))
    print()
    print('FAILURES: %d' % failures)
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
