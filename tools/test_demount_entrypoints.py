# -*- coding: utf-8 -*-
"""Drives the demount entry points through adisp semantics that actually match
the client, and fails if a click would silently do nothing.

The bug this exists for: decorating an entry point with @adisp_async as well as
@adisp_process turns it into a deferred that only runs when somebody yields it.
The click handlers call these directly, so the body never executed and the
button looked dead. The old harness called the generator by hand, so it could
not see that; this one calls each entry point exactly the way the client does.

    D:\\Python\\Python_2.7.18\\python.exe tools\\test_demount_entrypoints.py
"""

import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import test_improved_demount as B

PY = B  # the stubs, the fakes and the loaders all live there


# ---------------------------------------------------------------------------
# adisp, with the semantics the client actually has
# ---------------------------------------------------------------------------

class Deferred(object):
    """What adisp_async returns: a job waiting for somebody to yield it."""

    def __init__(self, func, args, kwargs):
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self.started = False

    def run(self):
        self.started = True
        return self.func(*self.args, **self.kwargs)


def install_adisp():
    """Replaces the test stub's identity decorators with honest ones.

    adisp_process: runs the generator immediately, driving every yielded step.
    adisp_async:  returns a Deferred that does NOTHING until it is yielded -
                  which is exactly why an entry point must not have it.
    """
    module = sys.modules['adisp']

    def adisp_async(func):
        def wrapper(*args, **kwargs):
            return Deferred(func, args, kwargs)
        wrapper.is_deferred = True
        return wrapper

    def adisp_process(func):
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            if not isinstance(result, types.GeneratorType):
                return result
            return _drive(result)
        return wrapper

    module.adisp_async = adisp_async
    module.adisp_process = adisp_process


def _drive(gen):
    """Runs a generator to completion and returns its `return` value.

    The first send() must be next() - sending a value into a generator that has
    not started yet raises TypeError - and every step is resolved before its
    value is sent back, or the yields that carry real results (a demount count,
    a success code) would all arrive as None.

    The return value matters: adisp_async steps report their result with
    `return X`, which adisp hands back as the value of the yield. Dropping it
    makes every count None and the run dies on `removed += count`.

    Python 2 has no StopIteration.value, so the value is read back out of the
    generator that just finished: `callback(removed)` in the house style means
    the last local named for the result is what the caller gets. Steps here
    always funnel their result through a local called `removed` or `result`;
    anything else legitimately returns None."""
    steps = 0
    capture = {}
    try:
        yielded = next(gen)
        while True:
            steps += 1
            if steps > 10000:
                raise RuntimeError('runaway generator')
            if isinstance(yielded, Deferred):
                value = _resolve(yielded.run())
            elif isinstance(yielded, types.GeneratorType):
                raise RuntimeError(
                    'yielded a plain generator instead of an adisp step - '
                    'adisp cannot drive this')
            else:
                value = yielded
            # Snapshot the frame before send(): once the generator finishes its
            # gi_frame is None and every local is gone.
            if gen.gi_frame is not None:
                capture = dict(gen.gi_frame.f_locals)
            yielded = gen.send(value)
    except StopIteration:
        for name in ('removed', 'obtained', 'cleared', 'keep_going', 'result'):
            if name in capture:
                return capture[name]
        return None


def _resolve(result):
    if isinstance(result, types.GeneratorType):
        return _drive(result)
    return result


def reload_carousel():
    """Reimports carousel_menu so it decorates with the honest adisp."""
    for name in ('auto_equip.carousel_menu', 'auto_equip.apply',
                 'auto_equip.cleanup', 'auto_equip.rpc'):
        if name in sys.modules:
            del sys.modules[name]
    for name in ('rpc', 'apply', 'cleanup', 'carousel_menu'):
        B.T._load(name)
    return sys.modules['auto_equip.carousel_menu']


# ---------------------------------------------------------------------------
# Recording the effects a real click would produce
# ---------------------------------------------------------------------------

class Recorder(object):
    def __init__(self):
        self.veils = 0
        self.hidden = 0
        self.messages = []
        self.demounts = []


def wire(carousel, vehicles, devices, improved_free):
    """Fake garage + recorded user-visible effects. Returns a Recorder."""
    rec = Recorder()

    B.install_fakes(vehicles, devices,
                    B.make_free_rules(improved_is_free=improved_free))
    inventory = sys.modules['auto_equip.inventory']
    messages = sys.modules['auto_equip.messages']

    def show_waiting(*args, **kwargs):
        rec.veils += 1
        return True

    def hide_waiting(*args, **kwargs):
        rec.hidden += 1

    def push_info(text, **kwargs):
        rec.messages.append(('info', text))

    def push_warning(text, **kwargs):
        rec.messages.append(('warning', text))

    messages.show_waiting = show_waiting
    messages.hide_waiting = hide_waiting
    messages.push_info = push_info
    messages.push_warning = push_warning

    # Record the actual demount RPC instead of talking to a server.
    rpc = sys.modules['auto_equip.rpc']

    def equip_device(veh_inv_id, device_cd, slot_idx, all_setups, finance,
                     callback=None, *a):
        rec.demounts.append((veh_inv_id, slot_idx))
        if callback is not None:
            callback(0, None)

    rpc.equip_device = equip_device
    rpc.pause = lambda seconds, callback=None: callback(None) if callback else None
    rpc.change_setup_index = lambda veh, idx, callback=None: (
        callback(0) if callback else None)
    rpc.is_success = lambda code: code >= 0

    # Two-slot vehicles with a purple device in slot 0 on the first one.
    for vehicle in vehicles:
        vehicle._devices = list(vehicle._devices) + [0] * (2 - len(vehicle._devices))
    return rec


class FakeVehicle(object):
    def __init__(self, inv_id, name, devices, level=10, locked=False):
        self.invID = inv_id
        self.userName = name
        self.level = level
        self.isLocked = locked
        self._devices = list(devices)


class FakeDevice(object):
    def __init__(self, name, deluxe=False, trophy=False, removable=False):
        self.userName = name
        self.name = name
        self.isDeluxe = deluxe
        self.isTrophy = trophy
        self.isRemovable = removable


PURPLE = FakeDevice(u'Improved Exhaust', deluxe=True)
BOUNTY = FakeDevice(u'Bounty Rammer', trophy=True)


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def check_entry_is_not_deferred(carousel, name):
    """The decorator question, asked directly: calling the entry point the way a
    click handler does must return something that has already run, not a
    Deferred waiting for a yield that will never come."""
    func = getattr(carousel, name)
    assert not getattr(func, 'is_deferred', False), (
        '%s is wrapped in adisp_async - the click handler calls it directly, so '
        'its body would never run (this is the "button does nothing" bug)' % name)
    print('   %-28s not a deferred: OK' % name)


def check_improved_click_does_something(carousel):
    vehicles = [FakeVehicle(1, u'A', [1])]
    rec = wire(carousel, vehicles, [PURPLE], improved_free=True)
    B.reset_toggles(demountImproved=True)
    B.config.set_icon_menu_row_enabled('demountImproved', True)
    B.config.set_icon_menu_row_enabled('demountBounty', False)

    result = carousel.demount_all_improved()

    assert rec.veils >= 1, 'no waiting veil - the body did not run'
    assert rec.demounts, 'no demount RPC was issued'
    assert rec.messages, 'nothing was reported to the player'
    print('   360 China click ran: veil=%d demounts=%d messages=%d: OK'
          % (rec.veils, len(rec.demounts), len(rec.messages)))


def check_bounty_click_does_something(carousel):
    """The regression that shipped: the bounty row was dead too."""
    vehicles = [FakeVehicle(1, u'A', [1])]
    rec = wire(carousel, vehicles, [BOUNTY], improved_free=True)
    B.reset_toggles(demountBounty=True)
    B.config.set_icon_menu_row_enabled('demountBounty', True)

    carousel.demount_all_trophy()

    assert rec.veils >= 1, 'no waiting veil - the bounty body did not run'
    assert rec.demounts, 'no demount RPC was issued for bounty equipment'
    print('   bounty click ran: veil=%d demounts=%d: OK'
          % (rec.veils, len(rec.demounts)))


def check_improved_unsupported_reports(carousel):
    """On a realm without free Improved demount the click must say so, not go
    silent."""
    vehicles = [FakeVehicle(1, u'A', [1])]
    rec = wire(carousel, vehicles, [PURPLE], improved_free=False)
    B.config.set_icon_menu_row_enabled('demountImproved', True)

    carousel.demount_all_improved()

    assert rec.messages, 'WG click reported nothing at all'
    assert not rec.demounts, 'demounted an Improved device on WG anyway'
    print('   WG click explains itself and demounts nothing: OK')


def check_single_vehicle_click(carousel):
    vehicles = [FakeVehicle(1, u'A', [1])]
    rec = wire(carousel, vehicles, [PURPLE], improved_free=True)
    B.config.set_carousel_menu_row_enabled('demountImproved', True)

    carousel.demount_improved_equipment(1)

    assert rec.veils >= 1, 'single-vehicle Improved body did not run'
    assert rec.demounts, 'single-vehicle Improved issued no demount'
    print('   single-vehicle Improved click ran: OK')


def main():
    PY.T._load_package()
    for name in ('log', 'config', 'hangar', 'usage', 'mode_sets', 'inventory',
                 'rpc', 'messages'):
        PY.T._load(name)
    B.config.load_for_account(1000)

    install_adisp()
    carousel = reload_carousel()
    # reload_carousel reimports modules, so rebind the handles the fakes use.
    sys.modules['auto_equip.config'].load_for_account(1000)

    failures = 0
    checks = (
        ('entry points are not deferred',
         lambda: [check_entry_is_not_deferred(carousel, n) for n in (
             'demount_all_trophy', 'demount_all_improved',
             'demount_trophy_equipment', 'demount_improved_equipment',
             'demount_free_equipment')]),
        ('Improved click runs', lambda: check_improved_click_does_something(carousel)),
        ('bounty click runs', lambda: check_bounty_click_does_something(carousel)),
        ('WG click explains itself', lambda: check_improved_unsupported_reports(carousel)),
        ('single-vehicle click runs', lambda: check_single_vehicle_click(carousel)),
    )
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
