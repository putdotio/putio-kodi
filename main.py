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
import urlparse
import requests

import xbmc
import xbmcgui
import xbmcaddon
import xbmcplugin
import resources.lib.putio as putio

__url__ = sys.argv[0]  # base URL ('plugin://plugin.video.putiov2/')
__handle__ = int(sys.argv[1])  # process handle, as a numeric string
__args__ = urlparse.parse_qs(sys.argv[2].lstrip('?'))  # query string, ('?action=list&item=3')

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
        if item.is_audio or item.is_video or item.is_folder:
            return True
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


def build_url(action, item):
    return '{0}?action={1}&item={2}'.format(__url__, action, item)


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

        # url when a delete action is triggered
        delete_ctx_url = build_url(action='delete', item=item.id)

        if item.is_folder:
            url = build_url(action='list', item=item.id)
        else:  # video or audio, no other types are available here
            url = build_url(action='play', item=item.id)
            li.setProperty(key='isplayable', value='true')

            # resumetime and totaltime are needed for Kodi to decide the file as watched or not.
            # FIXME: get total-time of the file and set to 'totaltime'
            li.setProperty(key='resumetime', value=str(item.start_from))
            li.setProperty(key='totaltime', value=str(20 * 60))

            # http://kodi.wiki/view/InfoLabels
            type_ = 'video' if item.is_video else 'audio'
            li.setInfo(type=type_, infoLabels={'size': item.size, 'title': item.name})

        li.addContextMenuItems([
            (__lang__(32040), 'Container.Refresh'),  # refresh
            (__lang__(32041), 'Action(ParentDir)'),  # go-up
            (__lang__(32042), 'XBMC.RunPlugin(%s)' % delete_ctx_url),  # delete
        ])
        list_items.append((url, li, item.is_folder))

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
    li.setProperty(key='IsPlayable', value='true')

    li.setSubtitles([item.subtitles()])

    player = Player()
    player.play(item=item.stream_url(), listitem=li)


def delete(item):
    """Deletes the given item and refreshes the current directory."""
    if item.id == 0:
        return

    response = xbmcgui.Dialog().yesno(heading=__lang__(32060), line1=__lang__(32061))

    # yes=1, no=0
    if response == 0:
        return

    item.delete()
    xbmc.executebuiltin('Container.Refresh')


def main():
    """Dispatches the commands."""
    handler = PutioApiHandler()
    item_id = __args__.get('item')
    if not item_id:
        populate_dir(handler.list(parent=0))
        return

    item_id = item_id[0]
    item = handler.get(id_=item_id)
    if not item.content_type:
        return

    # Dispatch commands
    action = __args__.get('action')
    if not action:
        return

    action = action[0]
    if action == 'list':
        populate_dir(handler.list(parent=item_id))
        return

    if action == 'delete':
        delete(item=item)
        return

    if action == 'play':
        play(item=item)
        return


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
