# coding: utf-8
# Created on: 17.03.2016
# Author: Roman Miroshnychenko aka Roman V.M. (romanvm@yandex.ua)
# License: GPL v. 3 <http://www.gnu.org/licenses/gpl-3.0.en.html>

import xbmc
from xbmcgui import Dialog
from commands import sync_library, sync_new_items, login, addon
from gui import ui_string
# Here ``addon`` is imported from another module to prevent a bug
# when username and hash are not stored in the addon settings.

dialog = Dialog()


class UpdateMonitor(xbmc.Monitor):
    """
    Monitors updating Kodi library
    """
    def onScanFinished(self, library):
        if library == 'video':
            sync_new_items()
            xbmc.log('next-episode.net: new items updated', xbmc.LOGNOTICE)


def initial_prompt():
    """
    Show login prompt at first start
    """
    if (addon.getSetting('prompt_shown') != 'true' and
            not addon.getSetting('username') and
            dialog.yesno(ui_string(32012),
                         ui_string(32013),
                         ui_string(32014),
                         ui_string(32015))):
        if login() and dialog.yesno(ui_string(32016),
                                    ui_string(32017),
                                    ui_string(32018)):
            sync_library()
        addon.setSetting('prompt_shown', 'true')
