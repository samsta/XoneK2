
import re
import os
import socket
import json
import pathlib
import time
import select
from XoneK2_DJ.tinytag import TinyTag
from urllib.parse import unquote

MUSIC_TO_OPEN_KEY = {
    'Am':  '1m',
    'C':   '1d',
    'Em':  '2m',
    'G':   '2d',
    'Bm':  '3m',
    'D':   '3d',
    'F#m': '4m',
    'Gbm': '4m',
    'A':   '4d',
    'Dbm': '5m',
    'C#m': '5m',
    'E':   '5d',
    'Abm': '6m',
    'G#m': '6m',
    'B':   '6d',
    'Ebm': '7m',
    'D#m': '7m',
    'F#':  '7d',
    'Gb':  '7d',
    'Bbm': '8m',
    'A#m': '8m',
    'Db':  '8d',
    'C#':  '8d',
    'Fm':  '9m',
    'Ab':  '9d',
    'G#':  '9d',
    'Cm':  '10m',
    'Eb':  '10d',
    'D#':  '10d',
    'Gm':  '11m',
    'Bb':  '11d',
    'A#':  '11d',
    'Dm':  '12m',
    'F':   '12d'
}

OPEN_TO_MUSICAL_KEY = {
     '1m':  'Am',
     '1d':  'C',
     '2m':  'Em',
     '2d':  'G',
     '3m':  'Bm',
     '3d':  'D',
     '4m':  'F#m',
     '4d':  'A',
     '5m':  'C#m',
     '5d':  'E',
     '6m':  'G#m',
     '6d':  'B',
     '7m':  'D#m',
     '7d':  'F#',
     '8m':  'A#m',
     '8d':  'C#',
     '9m':  'Fm',
     '9d':  'G#',
     '10m': 'Cm',
     '10d': 'D#',
     '11m': 'Gm',
     '11d': 'A#',
     '12m': 'Dm', 
     '12d': 'F' 
}

def uri_to_path(uri):
    path = re.sub('^query:UserLibrary#', '~/Music/Ableton/User Library/', uri)
    path = re.sub(':','/', path)
    path = unquote(path)
    return path

def key_distance(from_key, to_key):
    # key distances are as follows:
    # -1: unknown
    #  0: same key
    #  1: neighbouring key on circle
    #  2: opposite key on circle
    #  3: same number, but change d <-> m
    if from_key == to_key:
        return 0

    try:
        from_dm = from_key[-1]
        to_dm = to_key[-1]
        from_num = int(from_key[0:-1])
        to_num = int(to_key[0:-1])
    except:
        return -1

    if from_dm != to_dm:
        # only accept same number if changing from major to mayor and vice versa
        if from_num == to_num:
            return 3
        else:
            return 12

    d = (12 + from_num - to_num) % 12

    if (d == 6):
        #exactly opposite on wheel
        return 2

    if (d > 6):
        d = 12 - 6

    if (d <= 1):
        return d
    return 12

class TaggedFile():
    def __init__(self, filename):
        self._file_name = filename
        self._tags = TinyTag.get(self._file_name)
        self._duration = "%d:%02d" % (int(self._tags.duration)/60, int(self._tags.duration) % 60)
        self._bpm = self._tags.extra['bpm'] if 'bpm' in self._tags.extra else "none"
        self._key = self._tags.extra['initial_key'] if 'initial_key' in self._tags.extra else "none"
        self._key_distance = -1
        self._normaliseKey()

    def _normaliseKey(self):
        self._open_key = ""
        self._musical_key = ""
        if re.match("[0-9]{1,2}[dm]", self._key):
            self._open_key = self._key
            self._musical_key = OPEN_TO_MUSICAL_KEY[self._key] if self._key in OPEN_TO_MUSICAL_KEY.keys() else "?"
        else:
            key = re.sub('maj', '', self._key)
            key = re.sub('min','m', key)
            self._musical_key = key
            self._open_key = MUSIC_TO_OPEN_KEY[key] if key in MUSIC_TO_OPEN_KEY.keys() else "?"

    def updateDistanceTo(self, key):
        if key == None:
            self._key_distance = -1
        else:
            self._key_distance = key_distance(self.open_key, key)

    @property
    def filename(self):
        return self._file_name

    @property
    def artist(self):
        return self._tags.artist or "unknown"

    @property
    def title(self):
        return self._tags.title or self.filename.split('/')[-1]

    @property
    def duration(self):
        return self._duration

    @property
    def open_key(self):
        return self._open_key

    @property
    def key(self):
        return self._open_key + " / " + self._musical_key

    @property
    def bpm(self):
        return float(self._bpm) if self._bpm != "none" else 0.0

    @property
    def genre(self):
        return self._tags.genre or "unknown"

    @property
    def keydistance(self):
        return self._key_distance


class BrowserItem(TaggedFile):
    def __init__(self, live_browser_item):
        super(BrowserItem, self).__init__(uri_to_path(live_browser_item.uri))
        self._item = live_browser_item

    def item(self):
        return self._item

class BrowserRepresentation():

    SOCKET_IN = "/tmp/LiveMusicBrowser.src.socket"
    SOCKET_OUT = "/tmp/LiveMusicBrowser.ui.socket"

    def __init__(self, browser, log):
        self._browser = browser
        self._log = log
        self._parents = []
        self._current = []
        self._filtered = []
        self._current_index = 0
        self._iterate_and_find_audio(browser.user_library)
        self._playing_tracks = {}

        if os.path.exists(self.SOCKET_IN):
            os.remove(self.SOCKET_IN)

        self._socket = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self._socket.bind(self.SOCKET_IN)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 250*1024)
        self._bpm_lower = 0.0
        self._bpm_upper = 1000.0
        self._bpm = 100.0
        self._bpm_tolerance_percent = 5.0
        self._filter_by_bpm = True
        self._filter_by_key = True
        self._start_ui()
        self._apply_filter()
        self._update()

    def _iterate_and_find_audio(self, node):
        for n in node.iter_children:
            if n.is_folder:
                self._iterate_and_find_audio(n)
            elif n.uri.endswith("aiff") or n.uri.endswith("mp3"):
                self._current.append(BrowserItem(n))           

    def scroll_horizontal(self, right_not_left):
        pass

    def scroll_vertical(self, down_not_up):
        if down_not_up and self._current_index < len(self._filtered) - 1:
            self._current_index = self._current_index + 1
        elif not down_not_up and self._current_index > 0:
            self._current_index = self._current_index - 1
        self._update()

    def preview(self):
        self._browser.preview_item(
            self._filtered[self._current_index].item())

    def load(self):
        self._browser.load_item(
            self._filtered[self._current_index].item())

    def tempo(self, bpm):
        self._bpm = float(bpm)
        self._apply_filter()
        self._update()

    def _filter(self, item):
        return (not self._filter_by_bpm or (item.bpm > self._bpm_lower and item.bpm < self._bpm_upper)) and \
               (not self._filter_by_key or item.keydistance < 4)

    def _apply_filter(self):
        try:
            current_sel = self._filtered[self._current_index]
        except:
            current_sel = None

        fac = (100.0 + self._bpm_tolerance_percent)/100.0
        self._bpm_upper = self._bpm * fac
        self._bpm_lower = self._bpm / fac

        self._filtered = list(filter(lambda item: self._filter(item), self._current))

        try:
            self._current_index = self._filtered.index(current_sel)
        except:
            self._current_index = 0

    def _update_key_distance(self):
        self._playing_key = None
        for i in self._playing_tracks.keys():
            self._playing_key = self._playing_tracks[i].open_key
            break 

        for item in self._current:
            item.updateDistanceTo(self._playing_key)

    def _update(self):
        d = {
            "sel_ix": self._current_index,
            "cols": [
                "Artist",
                "Title",
                "Genre",
                "Duration",
                "BPM",
                "Key",
                "KeyDistance"
            ],
            "rows": [],
            "playing": {},
            "bpm_filter": self._filter_by_bpm,
            "bpm_percent": self._bpm_tolerance_percent,
            "key_filter": self._filter_by_key
        }

        for item in self._filtered:
            r = []
            for k in d["cols"]:
                r.append(getattr(item, k.lower()))
            d["rows"].append(r)

        for track_ix in self._playing_tracks.keys():
            d["playing"][track_ix] = []
            for k in d["cols"]:
                d["playing"][track_ix].append(getattr(self._playing_tracks[track_ix], k.lower()))

        try:
            self._socket.sendto(json.dumps(d, indent=1).encode('utf-8'), self.SOCKET_OUT)
        except:
            pass

    def set_playing_tracks(self, playing_tracks):
        p = {}
        for i in playing_tracks.keys():
            p[i] = TaggedFile(playing_tracks[i])
        self._playing_tracks = p
        self._update_key_distance()
        self._apply_filter()
        self._update()

    def _start_ui(self):
        pwd = pathlib.Path(__file__).parent.resolve()
        os.system("'%s/build/LiveMusicBrowser' &" % pwd)
        timeout = 10
        while (timeout > 0 and not os.path.exists(self.SOCKET_OUT)):
            time.sleep(0.1)
            timeout = timeout - 1
    
    def poll(self):
        ready = select.select([self._socket], [], [], 0)
        if ready[0]:
            data = self._socket.recv(4096)
            self._log("Received: %s" % data)
            data = json.loads(data)
            filter_changed = False
            if "bpm_filter" in data:
                filter_changed = filter_changed or self._filter_by_bpm != data["bpm_filter"]
                self._filter_by_bpm = data["bpm_filter"]
            if "key_filter" in data:
                filter_changed = filter_changed or self._filter_by_key != data["key_filter"]
                self._filter_by_key = data["key_filter"]
            elif "bpm_percent" in data:
                filter_changed = filter_changed or self._bpm_tolerance_percent != data["bpm_percent"]
                self._bpm_tolerance_percent = data["bpm_percent"]

            if filter_changed:
                self._apply_filter()
                self._update()


    def _quit_ui(self):
        try:
            self._socket.sendto(json.dumps({"quit": True}).encode('utf-8'), self.SOCKET_OUT)
        except:
            pass

    def __del__(self):
        self._quit_ui()

    def disconnect(self):
        self._quit_ui()