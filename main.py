# -*- coding: utf-8 -*-

# put.io kodi addon
# Copyright (C) 2009  Alper Kanat <alper@put.io>
# Copyright (C) 2016  Put.io Developers <devs@put.io>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

import os
import sys
import time
import requests

import xbmc
import xbmcgui
import xbmcaddon
import xbmcplugin
import resources.lib.putio as putio

# Arguments passed by Kodi
PLUGIN_URL = sys.argv[0]  # base URL ('plugin://plugin.video.putiov2/')
PLUGIN_HANDLE = int(sys.argv[1])  # process handle, as a numeric string
ITEM_ID = sys.argv[2].lstrip('?')  # query string, ('?foo=bar&baz=quux')

PUTIO_ADDON = xbmcaddon.Addon('plugin.video.putiov2')
RESOURCE_PATH = os.path.join(PUTIO_ADDON.getAddonInfo('path'), 'resources', 'images')
PUTIO_KODI_ENDPOINT = 'https://put.io/xbmc'


class PutioAuthFailureException(Exception):
    def __init__(self, header, message, duration=10000, icon='error.png'):
        self.header = header
        self.message = message
        self.duration = duration
        self.icon = icon


def get_resource_path(filename):
    if not filename:
        return
    return os.path.join(RESOURCE_PATH, filename)


def populate_dir(files):
    for item in files:
        if item.screenshot:
            screenshot = item.screenshot
        else:
            screenshot = get_resource_path('mid-folder.png')

        li = xbmcgui.ListItem(label=item.name,
                              label2=item.name,
                              iconImage=screenshot,
                              thumbnailImage=screenshot)
        # http://kodi.wiki/view/InfoLabels
        # I think they don't have any effect at all.
        li.setInfo(type=item.content_type,
                   infoLabels={
                       'size': item.size,
                       'title': item.name,
                   })

        url = '%s?%s' % (PLUGIN_URL, item.id)
        xbmcplugin.addDirectoryItem(handle=PLUGIN_HANDLE,
                                    url=url,
                                    listitem=li,
                                    isFolder='application/x-directory' == item.content_type)
        xbmcplugin.addSortMethod(handle=PLUGIN_HANDLE, sortMethod=xbmcplugin.SORT_METHOD_LABEL_IGNORE_THE)

    xbmcplugin.endOfDirectory(handle=PLUGIN_HANDLE)


def play(item):
    if item.screenshot:
        screenshot = item.screenshot
    else:
        screenshot = item.icon

    li = xbmcgui.ListItem(label=item.name,
                          label2=item.name,
                          iconImage=screenshot,
                          thumbnailImage=screenshot)
    li.setInfo(type='video',
               infoLabels={
                   'size': item.size,
                   'title': item.name,
               })
    li.setProperty('IsPlayable', 'true')

    player = xbmc.Player()
    player.play(item=item.stream_url(), listitem=li)


class PutioApiHandler(object):
    def __init__(self, pluginId):
        self.addon = xbmcaddon.Addon(pluginId)
        self.oauthkey = self.addon.getSetting('oauthkey').replace('-', '')
        if not self.oauthkey:
            raise PutioAuthFailureException(header=self.addon.getLocalizedString(30001),
                                            message=self.addon.getLocalizedString(30002))
        self.apiclient = putio.Client(self.oauthkey)

    def get(self, id_):
        return self.apiclient.File.get(id_)

    def list(self, parent=0):
        items = []
        for item in self.apiclient.File.list(parent_id=parent):
            if item.content_type and self.is_showable(item):
                items.append(item)
        return items

    def is_showable(self, item):
        if 'audio' in item.content_type:
            return True
        elif 'video' in item.content_type:
            return True
        elif 'application/x-directory' in item.content_type:
            return True
        else:
            return False


def main():
    putio = PutioApiHandler(PUTIO_ADDON.getAddonInfo('id'))
    if not ITEM_ID:
        populate_dir(putio.list(parent=0))
        return

    item = putio.get(id_=ITEM_ID)
    if not item.content_type:
        return

    if item.content_type == 'application/x-directory':
        populate_dir(putio.list(parent=ITEM_ID))
        return

    play(item)


if __name__ == '__main__':
    try:
        main()
    except PutioAuthFailureException as e:
        addonid = PUTIO_ADDON.getAddonInfo('id')
        addon = xbmcaddon.Addon(addonid)
        # FIXME: request might fail
        r = requests.get(PUTIO_KODI_ENDPOINT + '/getuniqueid')
        # FIXME: json parsing might fail
        uniqueid = r.json()['id']

        oauthtoken = addon.getSetting('oauthkey')

        if not oauthtoken:
            dialog = xbmcgui.Dialog()
            dialog.ok('Oauth2 Key Required',
                      'Visit put.io/xbmc and enter this code: %s\nthen press OK.' % uniqueid)

        while not oauthtoken:
            try:
                # now we'll try getting oauth key by giving our uniqueid
                r = requests.get(PUTIO_KODI_ENDPOINT + '/k/%s' % uniqueid)
                oauthtoken = r.json()['oauthtoken']
                if oauthtoken:
                    addon.setSetting('oauthkey', str(oauthtoken))
                    main()
            except Exception as e:
                dialog = xbmcgui.Dialog()
                dialog.ok('Oauth Key Error', str(e))
                raise e
            time.sleep(1)
