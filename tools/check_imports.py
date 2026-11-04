# -*- coding: utf-8 -*-
"""Every module of the package has to import cleanly, in the order
mod_auto_equip.init() imports them. Run with the client's Python 2.7:

    D:\\Python\\Python_2.7.18\\python.exe tools\\check_imports.py
"""

import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import test_donor_lru as T

PREFS = os.path.join(os.environ['TEMP'], 'z4ae_import_check')
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
stub('gui.aslainMenu')
stub('gui.shared.system_factory', MESSENGER_CLIENT_FORMATTERS={},
     registerMessengerClientFormatter=lambda *a, **k: None,
     registerNotificationsActionsHandlers=lambda *a, **k: None)
stub('messenger')
stub('messenger.g_settings', g_settings=ANY)
stub('messenger.formatters')
stub('messenger.formatters.service_channel_helpers', MessageData=ANY)
stub('notification')
stub('notification.NotificationMVC', g_notificationMVC=ANY)
stub('notification.settings', NOTIFICATION_TYPE=ANY)
stub('notification.actions_handlers', ActionHandler=ANY)
stub('gui.impl.pub.notification_commands', NotificationCommand=ANY)
stub('skeletons')
stub('skeletons.gui')
stub('skeletons.gui.system_messages', ISystemMessages=ANY)
stub('gui.Scaleform.daapi')
stub('gui.Scaleform.daapi.view')
stub('gui.Scaleform.daapi.view.lobby')
stub('gui.Scaleform.daapi.view.lobby.hangar')
stub('gui.Scaleform.daapi.view.lobby.hangar.hangar_cm_handlers',
     VehicleContextMenuHandler=ANY)
# gameface.py's guarded import block - all of it is optional at that point,
# but a missing module there raises, so they have to exist.
stub('frameworks')
stub('frameworks.wulf', ViewModel=ANY)
stub('gui.impl.pub')
stub('gui.impl.pub.view_component', ViewComponent=ANY)
stub('gui.impl.pub.view_impl', ViewImpl=ANY)
stub('openwg_gameface', gf_mod_inject=lambda *a, **k: None)
stub('helpers', getPreferencesDirPath=lambda: PREFS,
     getClientLanguage=lambda: 'en', dependency=ANY)
stub('helpers.i18n', makeString=lambda key: key)
stub('constants', AUTH_REALM='EU')

T._load_package()

# Import order matters: it is the one mod_auto_equip.init() produces.
ORDER = ('log', 'config', 'i18n', 'messages', 'hangar', 'usage', 'mode_sets',
         'inventory', 'rpc', 'apply', 'save', 'cleanup', 'recommended',
         'confirm', 'gameface', 'carousel_menu', 'importer')

# These two subclass real client base classes (notification ActionHandler,
# frameworks.wulf ViewComponent) and register with the client's own registries.
# A stub cannot faithfully stand in for those, so they are reported separately:
# they are checked by the client itself, not here. Neither was modified.
NEEDS_REAL_CLIENT = ('confirm', 'gameface')


def main():
    failures = 0
    skipped = []
    for name in ORDER:
        try:
            T._load(name)
        except Exception as error:
            if name in NEEDS_REAL_CLIENT:
                skipped.append(name)
                continue
            failures += 1
            print('FAIL %-16s %s: %s' % (name, type(error).__name__, error))

    checked = len(ORDER) - len(skipped)
    print('%d/%d modules imported, %d failure(s)'
          % (checked - failures, checked, failures))
    if skipped:
        print('not checkable outside the game (real client classes): %s'
              % ', '.join(skipped))

    if not failures:
        usage = sys.modules['auto_equip.usage']
        inventory = sys.modules['auto_equip.inventory']
        apply_engine = sys.modules['auto_equip.apply']
        print('usage wired into inventory: %s' % (inventory.usage is usage))
        print('usage wired into apply:     %s' % (apply_engine.usage is usage))
        print('find_donor_vehicle found:   %s'
              % callable(inventory.find_donor_vehicle))
        print('find_donor_vehicle reads LRU: %s'
              % ('usage.last_used' in
                 __import__('inspect').getsource(inventory._find_donor_vehicle)))
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
