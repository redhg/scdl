#!/usr/bin/env python3
# -*- encoding: utf-8 -*-

"""scdl allow you to download music from soundcloud

Usage:
    scdl -l <track_url> [-a | -f | -t | -p][-c][-o <offset>]\
[--hidewarnings][--debug | --error][--path <path>][--addtofile][--onlymp3]
    scdl me (-s | -a | -f | -t | -p)[-c][-o <offset>]\
[--hidewarnings][--debug | --error][--path <path>][--addtofile][--onlymp3]
    scdl -h | --help
    scdl --version


Options:
    -h --help          Show this screen
    --version          Show version
    me                 Use the user profile from the auth_token
    -l [url]           URL can be track/playlist/user
    -s                 Download the stream of an user (token needed)
    -a                 Download all track of an user (including repost)
    -t                 Download all upload of an user
    -f                 Download all favorite of an user
    -p                 Download all playlist of an user
    -c                 Continue if a music already exist
    -o [offset]        Begin with a custom offset
    --path [path]      Use a custom path for this time
    --hidewarnings     Hide Warnings. (use with precaution)
    --addtofile        Add the artist name to the filename if it isn't in the filename already
    --onlymp3          Download only the mp3 file even if the track is Downloadable
    --error            Only print debug information (Error/Warning)
    --debug            Print every information and
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import json
import logging
import os
import signal
import sys
import time
import urllib.request
import warnings

import configparser
import mutagen
import wget
from docopt import docopt
from requests.exceptions import HTTPError

from scdl import __version__
from scdl import soundcloud, utils

logging.basicConfig(level=logging.INFO, format='%(asctime)-15s %(name)-5s %(levelname)-8s %(message)s')
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addFilter(utils.ColorizeFilter())
logger.newline = print

arguments = None
token = ''
path = ''
offset = 0
scdl_client_id = '95a4c0ef214f2a4a0852142807b54b35'

client = soundcloud.Client(client_id=scdl_client_id)


def main():
    """
    Main function, call parse_url
    """
    signal.signal(signal.SIGINT, signal_handler)
    global offset
    global arguments

    # import conf file
    get_config()

    # Parse argument
    arguments = docopt(__doc__, version=__version__)

    if arguments['--debug']:
        logger.level = logging.DEBUG
    elif arguments['--error']:
        logger.level = logging.ERROR

    logger.info('Soundcloud Downloader')
    logger.debug(arguments)

    if arguments['-o'] is not None:
        try:
            offset = int(arguments['-o'])
        except:
            logger.error('Offset should be an Integer...')
            sys.exit()

    if arguments['--hidewarnings']:
        warnings.filterwarnings('ignore')

    if arguments['--path'] is not None:
        if os.path.exists(arguments['--path']):
            os.chdir(arguments['--path'])
        else:
            logger.error('Invalid path in arguments...')
            sys.exit()
    logger.debug('Downloading to '+os.getcwd()+'...')

    logger.newline()
    if arguments['-l']:
        parse_url(arguments['-l'])
    elif arguments['me']:
        if arguments['-a']:
            download_all_user_tracks(who_am_i())
        elif arguments['-f']:
            download_all_of_user(who_am_i(), 'favorite', download_track)
        elif arguments['-t']:
            download_all_of_user(who_am_i(), 'track', download_track)
        elif arguments['-p']:
            download_all_of_user(who_am_i(), 'playlist', download_playlist)


def get_config():
    """
    read the path where to store music
    """
    global token
    config = configparser.ConfigParser()
    config.read(os.path.join(os.path.expanduser('~'), '.config/scdl/scdl.cfg'))
    try:
        token = config['scdl']['auth_token']
        path = config['scdl']['path']
    except:
        logger.error('Are you sure scdl.cfg is in $HOME/.config/scdl/ ?')
        sys.exit()
    if os.path.exists(path):
        os.chdir(path)
    else:
        logger.error('Invalid path in scdl.cfg...')
        sys.exit()


def get_item(track_url):
    """
    Fetches metadata for an track or playlist
    """

    try:
        item = client.get('/resolve', url=track_url)
    except Exception:
        logger.error('Error resolving url, retrying...')
        time.sleep(5)
        try:
            item = client.get('/resolve', url=track_url)
        except Exception as e:
            logger.error('Could not resolve url {0}'.format(track_url))
            logger.exception(e)
            sys.exit(0)
    return item


def parse_url(track_url):
    """
    Detects if the URL is a track or playlists, and parses the track(s) to the track downloader
    """
    global arguments
    item = get_item(track_url)

    if not item:
        return
    elif isinstance(item, soundcloud.resource.ResourceList):
        download_all(item)
    elif item.kind == 'track':
        logger.info('Found a track')
        download_track(item)
    elif item.kind == 'playlist':
        logger.info('Found a playlist')
        download_playlist(item)
    elif item.kind == 'user':
        logger.info('Found an user profile')
        if arguments['-f']:
            download_all_of_user(item, 'favorite', download_track)
        elif arguments['-t']:
            download_all_of_user(item, 'track', download_track)
        elif arguments['-a']:
            download_all_user_tracks(item)
        elif arguments['-p']:
            download_all_of_user(item, 'playlist', download_playlist)
        else:
            logger.error('Please provide a download type...')
    else:
        logger.error('Unknown item type')


def who_am_i():
    """
    display to who the current token correspond, check if the token is valid
    """
    global client
    client = soundcloud.Client(access_token=token, client_id=scdl_client_id)

    try:
        current_user = client.get('/me')
    except:
        logger.error('Invalid token...')
        sys.exit(0)
    logger.info('Hello {0.username}!'.format(current_user))
    logger.newline()
    return current_user


def download_all_user_tracks(user):
    """
    Find track & repost of the user
    """
    global offset
    user_id = user.id

    url = 'https://api.sndcdn.com/e1/users/{0}/sounds.json?limit=1&offset={1}&client_id={2}'.format(user_id, offset, scdl_client_id)
    response = urllib.request.urlopen(url)
    data = response.read()
    text = data.decode('utf-8')
    json_data = json.loads(text)
    while str(json_data) != '[]':
        offset += 1
        try:
            this_url = json_data[0]['track']['uri']
        except:
            this_url = json_data[0]['playlist']['uri']
        logger.info('Track n°{0}'.format(offset))
        parse_url(this_url)

        url = 'https://api.sndcdn.com/e1/users/{0}/sounds.json?limit=1&offset={1}&client_id={2}'.format(user_id, offset, scdl_client_id)
        response = urllib.request.urlopen(url)
        data = response.read()
        text = data.decode('utf-8')
        json_data = json.loads(text)


def download_all_of_user(user, name, download_function):
    """
    Download all items of an user. Can be playlist or track, or whatever handled by the download function.
    """
    logger.info('Retrieving {1}s of user {0.username}...'.format(user, name))
    items = client.get_all('/users/{0.id}/{1}s'.format(user, name))
    logger.info('Retrieved {0} {1}s'.format(len(items), name))
    for counter, item in enumerate(items, 1):
        try:
            logger.info('{1} n°{0}'.format(counter, name.capitalize()))
            download_function(item)
        except Exception as e:
            logger.exception(e)
    logger.info('Downloaded all {1}s of user {0.username}!'.format(user, name))


def download_my_stream():
    """
    DONT WORK FOR NOW
    Download the stream of the current user
    """
    client = soundcloud.Client(access_token=token, client_id=scdl_client_id)
    activities = client.get('/me/activities')
    logger.debug(activities)


def download_playlist(playlist):
    """
    Download a playlist
    """
    count = 0
    invalid_chars = '\/:*?|<>"'

    playlist_name = playlist.title.encode('utf-8', 'ignore').decode('utf-8')
    playlist_name = ''.join(c for c in playlist_name if c not in invalid_chars)

    if not os.path.exists(playlist_name):
        os.makedirs(playlist_name)
    os.chdir(playlist_name)

    for track_raw in playlist.tracks:
        count += 1
        mp3_url = get_item(track_raw['permalink_url'])
        logger.info('Track n°{0}'.format(count))
        download_track(mp3_url, playlist.title)

    os.chdir('..')


def download_all(tracks):
    """
    Download all song of a page
    Not recommended
    """
    logger.error('NOTE: This will only download the songs of the page.(49 max)')
    logger.error('I recommend you to provide an user link and a download type.')
    count = 0
    for track in tracks:
        count += 1
        logger.newline()
        logger.info('Track n°{0}'.format(count))
        download_track(track)


def alternative_download(track):
    logger.debug('alternative_download used')
    track_id = str(track.id)
    url = 'http://api.soundcloud.com/i1/tracks/{0}/streams?client_id=a3e059563d7fd3372b49b37f00a00bcf'.format(track_id)
    res = urllib.request.urlopen(url)
    data = res.read().decode('utf-8')
    json_data = json.loads(data)
    try:
        mp3_url = json_data['http_mp3_128_url']
    except KeyError:
        logger.error('http_mp3_128_url not found in json response, report to developer.')
        mp3_url = None
    return mp3_url


def download_track(track, playlist_name=None):
    """
    Downloads a track
    """
    global arguments

    if track.streamable:
        try:
            stream_url = client.get(track.stream_url, allow_redirects=False)
            url = stream_url.location
        except HTTPError:
            url = alternative_download(track)
    else:
        logger.error('{0.title} is not streamable...'.format(track))
        logger.newline()
        return
    title = track.title
    title = title.encode('utf-8', 'ignore').decode(sys.stdout.encoding)
    logger.info('Downloading {0}'.format(title))

    #filename
    if track.downloadable and not arguments['--onlymp3']:
        logger.info('Downloading the orginal file.')
        url = '{0.download_url}?client_id={1}'.format(track, scdl_client_id)

        filename = urllib.request.urlopen(url).info()['Content-Disposition'].split('filename=')[1]
        if filename[0] == '"' or filename[0] == "'":
            filename = filename[1:-1]
    else:
        invalid_chars = '\/:*?|<>"'
        if track.user['username'] not in title and arguments['--addtofile']:
            title = '{0.user[username]} - {1}'.format(track, title)
        title = ''.join(c for c in title if c not in invalid_chars)
        filename = title + '.mp3'

    # Download
    if not os.path.isfile(filename):
        wget.download(url, filename)
        logger.newline()
        if '.mp3' in filename:
            try:
                if playlist_name is None:
                    settags(track, filename)
                else:
                    settags(track, filename, playlist_name)
            except:
                logger.error('Error trying to set the tags...')
        else:
            logger.error("This type of audio doesn't support tagging...")
    else:
        if arguments['-c']:
            logger.info('{0} already Downloaded'.format(title))
            logger.newline()
            return
        else:
            logger.newline()
            logger.error('Music already exists ! (exiting)')
            sys.exit(0)

    logger.newline()
    logger.info('{0} Downloaded.'.format(filename))
    logger.newline()


def settags(track, filename, album='Soundcloud'):
    """
    Set the tags to the mp3
    """
    logger.info('Settings tags...')
    user = client.get('/users/{0.user_id}'.format(track), allow_redirects=False)

    artwork_url = track.artwork_url
    if artwork_url is None:
        artwork_url = user.avatar_url
    artwork_url = artwork_url.replace('large', 't500x500')
    urllib.request.urlretrieve(artwork_url, '/tmp/scdl.jpg')

    audio = mutagen.File(filename)
    audio['TIT2'] = mutagen.id3.TIT2(encoding=3, text=track.title)
    audio['TALB'] = mutagen.id3.TALB(encoding=3, text=album)
    audio['TPE1'] = mutagen.id3.TPE1(encoding=3, text=user.username)
    audio['TCON'] = mutagen.id3.TCON(encoding=3, text=track.genre)
    if artwork_url is not None:
        audio['APIC'] = mutagen.id3.APIC(encoding=3, mime='image/jpeg', type=3, desc='Cover',
                                         data=open('/tmp/scdl.jpg', 'rb').read())
    else:
        logger.error('Artwork can not be set.')
    audio.save()


def signal_handler(signal, frame):
    """
    handle keyboardinterrupt
    """
    time.sleep(1)
    files = os.listdir()
    for f in files:
        if not os.path.isdir(f) and '.tmp' in f:
            os.remove(f)

    logger.newline()
    logger.info('Good bye!')
    sys.exit(0)

if __name__ == '__main__':
    main()
