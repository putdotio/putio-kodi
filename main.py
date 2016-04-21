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

__url__ = sys.argv[0]  # base URL ('plugin://plugin.video.putiov2/')
__handle__ = int(sys.argv[1])  # process handle, as a numeric string
__item__ = sys.argv[2].lstrip('?')  # query string, ('?foo=bar&baz=quux')

__settings__ = xbmcaddon.Addon(id='plugin.video.putiov2')
__lang__ = __settings__.getLocalizedString

PUTIO_KODI_ENDPOINT = 'https://put.io/xbmc'
RESOURCE_PATH = os.path.join(__settings__.getAddonInfo('path'), 'resources', 'media')


class PutioAuthFailureException(Exception):
    """An authentication error occured."""

    def __init__(self, header, message, duration=10000, icon='error.png'):
        self.header = header
        self.message = message
        self.duration = duration
        self.icon = icon


class PutioApiHandler(object):
    """A Put.io API client helper."""

    def __init__(self):
        oauth2_token = __settings__.getSetting('oauth2_token').replace('-', '')
        if not oauth2_token:
            raise PutioAuthFailureException(header=__lang__(30001), message=__lang__(30002))
        self.apiclient = putio.Client(oauth2_token)

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


# callbacks are not working at all! we need them to save the videos last position.
# See: http://mirrors.kodi.tv/docs/python-docs/16.x-jarvis/xbmc.html#Player
class Player(xbmc.Player):
    """An XBMC Player. Callbacks are not working though."""

    def __init__(self):
        xbmc.Player.__init__(self)

    def onPlayBackStarted(self):
        xbmc.log('********** started')

    def onPlayBackPaused(self):
        xbmc.log('********** paused')

    def onPlayBackResumed(self):
        xbmc.log('********** resumed')

    def onPlayBackSeek(self, time, offset):
        xbmc.log('********** seeked to %s' % time)

    def onPlayBackStopped(self):
        xbmc.log('********** stopped')

    def onPlayBackEnded(self):
        xbmc.log('********** ended')


def get_resource_path(filename):
    """Returns special path of the given filename."""
    if not filename:
        return
    return os.path.join(RESOURCE_PATH, filename)


def populate_dir(files):
    """Fills a directory listing with put.io files."""
    list_items = []
    for item in files:
        thumbnail = item.screenshot or get_resource_path('mid-folder.png')

        li = xbmcgui.ListItem(label=item.name,
                              label2=item.name,
                              iconImage=thumbnail,
                              thumbnailImage=thumbnail)

        # http://kodi.wiki/view/InfoLabels
        # I think they don't have any effect at all.
        li.setInfo(type=item.content_type, infoLabels={'size': item.size, 'title': item.name, })
        li.addContextMenuItems([
            (__lang__(32040), 'Container.Refresh'),  # refresh
            (__lang__(32041), 'Action(ParentDir)'),  # go-up
        ])

        is_folder = item.content_type == 'application/x-directory'
        url = '%s?%s' % (__url__, item.id)

        list_items.append((url, li, is_folder))

    xbmcplugin.addDirectoryItems(handle=__handle__, items=list_items, totalItems=len(list_items))
    xbmcplugin.addSortMethod(handle=__handle__, sortMethod=xbmcplugin.SORT_METHOD_LABEL_IGNORE_THE)
    xbmcplugin.addSortMethod(handle=__handle__, sortMethod=xbmcplugin.SORT_METHOD_SIZE)
    xbmcplugin.endOfDirectory(handle=__handle__)


def play(item):
    """Plays the given item from where it was left off"""
    thumbnail = item.screenshot or item.icon

    li = xbmcgui.ListItem(label=item.name,
                          label2=item.name,
                          iconImage=thumbnail,
                          thumbnailImage=thumbnail)
    li.setInfo(type='video', infoLabels={'size': item.size, 'title': item.name, })
    # resume where it was left off
    li.setProperty(key='startoffset', value=str(item.start_from))

    # Put.io API doesn't provide video total time, so we have a silly hack here.
    # resumetime and totaltime are needed for Kodi to decide the file as watched or not.
    # 30 seconds is totally arbitrary. No magic.
    li.setProperty(key='resumetime', value=str(item.start_from))
    if item.start_from < 30:
        li.setProperty(key='totaltime', value=str(item.start_from))

    li.setSubtitles([item.subtitles()])

    player = Player()
    player.play(item=item.stream_url(), listitem=li)


def main():
    """Dispatches the commands."""
    handler = PutioApiHandler()
    if not __item__:
        populate_dir(handler.list(parent=0))
        return

    item = handler.get(id_=__item__)
    if not item.content_type:
        return

    if item.content_type == 'application/x-directory':
        populate_dir(handler.list(parent=__item__))
        return
    play(item)


if __name__ == '__main__':
    try:
        main()
    except PutioAuthFailureException as e:
        # FIXME: request might fail
        r = requests.get(PUTIO_KODI_ENDPOINT + '/getuniqueid')
        # FIXME: json parsing might fail
        uniqueid = r.json()['id']

        oauth2_token = __settings__.getSetting('oauth2_token')
        if not oauth2_token:
            dialog = xbmcgui.Dialog()
            dialog.ok('OAuth2 Key Required',
                      'Visit put.io/xbmc and enter this code: %s\nthen press OK.' % uniqueid)

        while not oauth2_token:
            try:
                # now we'll try getting oauth key by giving our uniqueid
                r = requests.get(PUTIO_KODI_ENDPOINT + '/k/%s' % uniqueid)
                oauth2_token = r.json()['oauthtoken']
                if oauth2_token:
                    __settings__.setSetting('oauth2_token', str(oauth2_token))
                    main()
            except Exception as e:
                dialog = xbmcgui.Dialog()
                dialog.ok('OAuth2 Token Error', str(e))
                raise e
            time.sleep(1)
