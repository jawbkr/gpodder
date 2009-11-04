#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# gPodder - A media aggregator and podcast client
# Copyright (c) 2005-2009 Thomas Perl and the gPodder Team
#
# gPodder is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# gPodder is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

# Soundcloud.com API client module for gPodder
# Thomas Perl <thpinfo.com>; 2009-11-03

import gpodder

from gpodder import model

try:
    # For Python < 2.6, we use the "simplejson" add-on module
    # XXX: Mark as dependency
    import simplejson as json
except ImportError:
    # Python 2.6 already ships with a nice "json" module
    import json

import os
import urllib2
import sys
import time

import re
import email
import email.Header


def urlopen(url):
    """URL request wrapper with User-Agent

    A simple replacement for urllib2.urlopen() that
    takes care of adding the User-Agent header.
    """
    request = urllib2.Request(url, headers={'User-Agent': gpodder.user_agent})
    return urllib2.urlopen(request)

def soundcloud_parsedate(s):
    """Parse a string into a unix timestamp

    Only strings provided by Soundcloud's API are
    parsed with this function (2009/11/03 13:37:00).
    """
    m = re.match(r'(\d{4})/(\d{2})/(\d{2}) (\d{2}):(\d{2}):(\d{2})', s)
    return time.mktime([int(x) for x in m.groups()]+[0, 0, -1])

def get_param(s, param='filename', header='content-disposition'):
    """Get a parameter from a string of headers

    By default, this gets the "filename" parameter of
    the content-disposition header. This works fine
    for downloads from Soundcloud.
    """
    msg = email.message_from_string(s)
    if header in msg:
        value = msg.get_param(param, header=header)
        decoded_list = email.Header.decode_header(value)
        value = []
        for part, encoding in decoded_list:
            if encoding:
                value.append(part.decode(encoding))
            else:
                value.append(unicode(part))
        return u''.join(value)

    return None

def get_metadata(url):
    """Get file download metadata

    Returns a (size, type, name) from the given download
    URL. Will use the network connection to determine the
    metadata via the HTTP header fields.
    """
    track_fp = urlopen(url)
    headers = track_fp.info()
    filesize = headers['content-length'] or '0'
    filetype = headers['content-type'] or 'application/octet-stream'
    headers_s = '\n'.join('%s:%s'%(k,v) for k, v in headers.items())
    filename = get_param(headers_s) or os.path.basename(os.path.dirname(url))
    track_fp.close()
    return filesize, filetype, filename

def get_coverart(username):
    cache_file = os.path.join(gpodder.home, 'soundcloud.cache')
    if os.path.exists(cache_file):
        try:
            cache = json.load(open(cache_file, 'r'))
        except:
            cache = {}
    else:
        cache = {}

    if username in cache:
        return cache[username]

    image = None
    try:
        json_url = 'http://api.soundcloud.com/users/%s.json' % username
        user_info = json.load(urlopen(json_url))
        image = user_info.get('avatar_url', None)
        cache[username] = image
    finally:
        json.dump(cache, open(cache_file, 'w'))

    return image

def get_tracks(username):
    """Get a generator of tracks from a SC user

    The generator will give you a dictionary for every
    track it can find for its user."""
    cache_file = os.path.join(gpodder.home, 'soundcloud.cache')
    if os.path.exists(cache_file):
        try:
            cache = json.load(open(cache_file, 'r'))
        except:
            cache = {}
    else:
        cache = {}

    try:
        json_url = 'http://api.soundcloud.com/users/%s/tracks.json' % username
        tracks = (track for track in json.load(urlopen(json_url)) \
                if track['downloadable'])

        for track in tracks:
            url = track['download_url']
            if url not in cache:
                cache[url] = get_metadata(url)
            filesize, filetype, filename = cache[url]

            yield {
                'title': track.get('title', track.get('permalink', 'Unknown track')),
                'link': track.get('permalink_url', 'http://soundcloud.com/'+username),
                'description': track.get('description', 'on Soundcloud'),
                'url': track['download_url'],
                'length': int(filesize),
                'mimetype': filetype,
                'guid': track.get('permalink', track.get('id')),
                'pubDate': soundcloud_parsedate(track.get('created_at', None)),
            }
    finally:
        json.dump(cache, open(cache_file, 'w'))

class SoundcloudFeed(object):
    def __init__(self, username):
        self.username = username

    def get_title(self):
        return '%s on Soundcloud' % self.username

    def get_image(self):
        return get_coverart(self.username)

    def get_link(self):
        return 'http://soundcloud.com/%s' % self.username

    def get_description(self):
        return 'Tracks published by %s on Soundcloud.' % self.username

    def get_new_episodes(self, channel, guids):
        tracks = [t for t in get_tracks(self.username) if t['guid'] not in guids]
        for track in tracks:
            episode = model.PodcastEpisode(channel)
            episode.update_from_dict(track)
            episode.save()

        return len(tracks)


def soundcloud_handler(url):
    # XXX: Proper regular expression matching here, please
    if url.startswith('http://soundcloud.com/') or \
            url.startswith('http://www.soundcloud.com/'):
        username = os.path.basename(url.rstrip('/'))
        raise model.CustomFeed(SoundcloudFeed(username))

# Register our URL handler with the gPodderFetcher service
model.gPodderFetcher.custom_handlers.append(soundcloud_handler)

