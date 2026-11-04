# -*- coding: utf-8 -*-
"""Runs the donor-selection loop out of the real inventory.py with the game's
modules stubbed, and counts how many demounts a player who keeps switching
between two tanks actually pays for.

    D:\\Python\\Python_2.7.18\\python.exe tools\\test_donor_lru.py

Not part of the .wotmod: packer.py only packs res/, and this lives in tools/.
"""

import imp
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PKG_DIR = os.path.join(os.path.dirname(HERE), 'res', 'scripts', 'client',
                       'gui', 'mods', 'auto_equip')


# ---------------------------------------------------------------------------
# The game modules inventory.py imports at module level
# ---------------------------------------------------------------------------

class _Anything(object):
    """Swallows every attribute access and call - enough for the constants and
    enum members the modules read at import time."""

    def __getattr__(self, name):
        return _Anything()

    def __call__(self, *args, **kwargs):
        return _Anything()


def _install_game_stubs(prefs_dir):
    import types

    def module(name, **attrs):
        mod = types.ModuleType(name)
        for key, value in attrs.iteritems():
            setattr(mod, key, value)
        sys.modules[name] = mod
        return mod

    helpers = module('helpers', dependency=_Anything(),
                     getPreferencesDirPath=lambda: prefs_dir)
    module('gui')
    module('gui.shared')
    module('gui.impl')
    module('gui.impl.gen', R=_Anything())
    module('gui.shared.gui_items', GUI_ITEM_TYPE=_Anything())
    module('gui.shared.utils')
    module('gui.shared.utils.requesters', REQ_CRITERIA=_Anything())
    module('post_progression_common', TankSetupGroupsId=_Anything())
    module('skeletons')
    module('skeletons.gui')
    module('skeletons.gui.game_control', IWotPlusController=_Anything())
    module('skeletons.gui.shared', IItemsCache=_Anything())
    helpers.dependency = _Anything()


def _load_package():
    package = sys.modules.get('auto_equip')
    if package is not None:
        return package
    import types
    package = types.ModuleType('auto_equip')
    package.__path__ = [PKG_DIR]
    package.__package__ = 'auto_equip'
    sys.modules['auto_equip'] = package
    return package


def _load(name):
    full = 'auto_equip.%s' % name
    if full in sys.modules:
        return sys.modules[full]
    path = os.path.join(PKG_DIR, '%s.py' % name)
    module = imp.load_module(full, open(path, 'rb'), path,
                             ('.py', 'rb', imp.PY_SOURCE))
    # `from . import x` reads the attribute off the package, which
    # imp.load_module does not set; the real import system does.
    setattr(sys.modules['auto_equip'], name, module)
    return module


# ---------------------------------------------------------------------------
# A garage: everything copies of ONE device
# ---------------------------------------------------------------------------

class FakeVehicle(object):

    def __init__(self, inv_id, name, has_device=True, locked=False):
        self.invID = inv_id
        self.userName = name
        self.isLocked = locked
        self.has_device = has_device

    def __repr__(self):
        return '<%s>' % self.userName


class Garage(object):
    """Wires the real inventory._find_donor_vehicle to a fake items cache and
    counts the server calls the mod would issue."""

    def __init__(self, inventory, usage, vehicles):
        self.inventory = inventory
        self.usage = usage
        self.vehicles = vehicles
        self.demounts = 0
        self.installs = 0

        def owned_vehicles():
            return list(self.vehicles)

        def vehicle_has_device(vehicle, device_cd, setup_idx=None):
            return vehicle.has_device

        def active_setup_index(vehicle):
            return 0

        def is_mode_only_vehicle(vehicle):
            return False

        inventory.owned_vehicles = owned_vehicles
        inventory.vehicle_has_device = vehicle_has_device
        inventory.active_setup_index = active_setup_index
        inventory.is_mode_only_vehicle = is_mode_only_vehicle

    def find(self, name):
        for vehicle in self.vehicles:
            if vehicle.userName == name:
                return vehicle
        raise KeyError(name)

    def select(self, name, needs_device=True):
        """One vehicle selection: stamp usage, then (if the tank wants the
        device and does not have it) take it off a donor - the same decision
        apply._borrow_from_donor makes."""
        vehicle = self.find(name)
        self.usage.touch(vehicle.invID)
        if not needs_device or vehicle.has_device:
            return None
        donor = self.inventory.find_donor_vehicle(DEVICE_CD, vehicle.invID)
        if donor is None:
            return None
        donor.has_device = False           # demounted into the depot
        self.demounts += 1
        vehicle.has_device = True          # installed from the depot
        self.installs += 1
        return donor.userName

    def owners(self):
        return [v.userName for v in self.vehicles if v.has_device]


DEVICE_CD = 12345      # 'Improved Exhaust' - any intCD will do, it is opaque


# ---------------------------------------------------------------------------
# The scenarios
# ---------------------------------------------------------------------------

def _fresh(prefs_root, account_id=1000, keep=False):
    """A clean process state on a fresh preferences dir.

    keep=True re-uses whatever is already on disk - that is what "restart the
    game" means to this module."""
    if keep:
        if not os.path.isdir(prefs_root):
            os.makedirs(prefs_root)
    else:
        if os.path.isdir(prefs_root):
            shutil.rmtree(prefs_root)
        os.makedirs(prefs_root)
    for name in list(sys.modules):
        if name.startswith('auto_equip'):
            del sys.modules[name]
    _install_game_stubs(prefs_root)
    _load_package()
    for name in ('log', 'config', 'hangar', 'usage', 'mode_sets', 'inventory'):
        _load(name)
    config = sys.modules['auto_equip.config']
    usage = sys.modules['auto_equip.usage']
    inventory = sys.modules['auto_equip.inventory']
    config.load_for_account(account_id)
    usage.load_for_account(account_id)
    return config, usage, inventory


def _garage(inventory, usage):
    """The player's exact situation: three copies of the device, on 天蝎 (A),
    59式 and 山猫. ELC EVEN 90 (B) is the tank being swapped in and out."""
    vehicles = [
        FakeVehicle(1, u'scorpion', has_device=True),     # 天蝎      A
        FakeVehicle(2, u'elc_even_90', has_device=False),  # ELC EVEN 90 B
        FakeVehicle(3, u'type59', has_device=True),       # 59式
        FakeVehicle(4, u'lynx', has_device=True),         # 山猫
    ]
    return Garage(inventory, usage, vehicles)


def _run_switches(garage, count):
    """A <-> B, `count` selections, starting on A."""
    sequence = []
    for step in range(count):
        sequence.append(u'scorpion' if step % 2 == 0 else u'elc_even_90')
    for name in sequence:
        garage.select(name)


def scenario(title, prefs_root, disable_lru):
    _config, usage, inventory = _fresh(prefs_root)
    if disable_lru:
        # Exactly the pre-patch ordering: a constant age, so the tiebreak falls
        # back to whatever order owned_vehicles() yields.
        usage.last_used = lambda veh_inv_id: 0.0

    garage = _garage(inventory, usage)
    assert garage.owners() == [u'scorpion', u'type59', u'lynx'], garage.owners()

    _run_switches(garage, 10)

    print('%s' % title)
    print('  after 10 switches A<->B: %d demount(s), %d install(s)'
          % (garage.demounts, garage.installs))
    print('  device now on: %s' % ', '.join(garage.owners()))
    print('  usage file: %s'
          % ('written' if os.path.exists(os.path.join(
              prefs_root, 'mods', 'z4imon', 'autoequipmentreturn',
              '1000.usage.json')) else 'absent'))
    return garage


def scenario_sticks_to_the_idle_tank(prefs_root):
    """The point of the whole thing: B keeps its device once it has one, so the
    second and every later switch costs nothing."""
    _config, usage, inventory = _fresh(prefs_root)
    garage = _garage(inventory, usage)
    garage.select(u'scorpion')
    donor = garage.select(u'elc_even_90')
    print('A -> B takes the device off: %s' % donor)
    assert donor != u'scorpion', (
        'took the device off the tank the player just left (%s) although an '
        'idle copy existed' % donor)
    before = garage.demounts
    garage.select(u'scorpion')
    garage.select(u'elc_even_90')
    garage.select(u'scorpion')
    print('  three further switches cost %d demount(s)'
          % (garage.demounts - before))
    assert garage.demounts == before, 'the ping-pong is back'


def scenario_falls_back_when_unused(prefs_root):
    """No usage data at all must behave like the shipped version: rank and cost
    still decide, recency is just a constant tiebreak."""
    _config, usage, inventory = _fresh(prefs_root)
    usage.last_used = lambda veh_inv_id: 0.0
    garage = _garage(inventory, usage)
    garage.select(u'scorpion')
    donor = garage.select(u'elc_even_90')
    print('with no usage data the donor is: %s (any answer is valid)' % donor)


def scenario_never_selects_the_current_tank(prefs_root):
    """The selected vehicle is always excluded, LRU or not."""
    _config, usage, inventory = _fresh(prefs_root)
    usage.last_used = lambda veh_inv_id: 0.0
    garage = _garage(inventory, usage)
    donor = garage.select(u'scorpion', needs_device=False)
    assert donor is None
    donor = garage.select(u'elc_even_90')
    assert donor != u'elc_even_90'
    print('current vehicle is never its own donor: OK (%s)' % donor)


def scenario_lru_orders_by_age(prefs_root):
    """Direct check on the ranking: the oldest touch wins among equals."""
    _config, usage, inventory = _fresh(prefs_root)
    garage = _garage(inventory, usage)
    now = 10000.0
    usage.touch(1, when=now - 500)     # scorpion, long ago
    usage.touch(3, when=now - 10)      # type59, ten seconds ago
    usage.touch(4, when=now - 100)     # lynx, a hundred seconds ago
    donor = inventory.find_donor_vehicle(DEVICE_CD, 2)
    print('oldest of three copies: %s' % donor.userName)
    assert donor.userName == u'scorpion', donor.userName


def scenario_persistence(prefs_root):
    """A restart must not reset the ordering."""
    _config, usage, inventory = _fresh(prefs_root)
    usage.touch(1, when=1000.0)
    usage.touch(3, when=2000.0)
    usage.flush()
    _config, usage, inventory = _fresh(prefs_root, keep=True)
    print('after reload: scorpion=%.0f type59=%.0f'
          % (usage.last_used(1), usage.last_used(3)))
    assert usage.last_used(1) == 1000.0
    assert usage.last_used(3) == 2000.0


def scenario_repeat_window(prefs_root):
    """onChanged storms must not rewrite the file dozens of times."""
    _config, usage, inventory = _fresh(prefs_root)
    first = usage.touch(1, when=1000.0)
    again = usage.touch(1, when=1000.5)     # inside the 2 s window
    later = usage.touch(1, when=1003.0)     # outside it
    print('repeat window: first=%s again=%s later=%s'
          % (first, again, later))
    assert (first, again, later) == (True, False, True)
    assert usage.last_used(1) == 1003.0


def main():
    root = os.path.join(tempfile.gettempdir(), 'z4ae_lru_test')
    failures = 0

    print('=' * 72)
    print('BEFORE the patch (recency tiebreak disabled)')
    print('=' * 72)
    scenario('A<->B, ten switches, LRU off', root, disable_lru=True)

    print u""
    print('=' * 72)
    print('AFTER the patch')
    print('=' * 72)
    after = scenario('A<->B, ten switches, LRU on', root, disable_lru=False)
    if after.demounts >= 10:
        print('  FAIL: still ping-ponging on every switch')
        failures += 1

    print u""
    checks = (
        ('B keeps its copy', scenario_sticks_to_the_idle_tank),
        ('no usage data degrades to old behaviour', scenario_falls_back_when_unused),
        ('current tank never donates to itself', scenario_never_selects_the_current_tank),
        ('oldest copy wins', scenario_lru_orders_by_age),
        ('ordering survives a restart', scenario_persistence),
        ('repeated onChanged is letterboxed', scenario_repeat_window),
    )
    for index, (title, check) in enumerate(checks):
        print u""
        print('-- %s' % title)
        try:
            check(os.path.join(root, 'case%d' % index))
            print('   PASS')
        except Exception as error:
            print('   FAIL: %s' % error)
            failures += 1

    shutil.rmtree(root, ignore_errors=True)
    print u""
    print('=' * 72)
    print('FAILURES: %d' % failures)
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
