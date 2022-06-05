
import re
import os
import socket
import json
from XoneK2_DJ.tinytag import TinyTag
from urllib.parse import unquote

class BrowserItem():
    def __init__(self, live_browser_item):
        self._item = live_browser_item
        self._file_name = self._uri_to_path(self._item.uri)
        self._tags = TinyTag.get(self._file_name)
        self._duration = "%d:%02d" % (int(self._tags.duration)/60, int(self._tags.duration) % 60)
        self._bpm = self._tags.extra['bpm'] if 'bpm' in self._tags.extra else "none"
        self._key = self._tags.extra['initial_key'] if 'initial_key' in self._tags.extra else "none"

    def _uri_to_path(self, uri):
        path = re.sub('^query:UserLibrary#', '~/Music/Ableton/User Library/', uri)
        path = re.sub(':','/', path)
        path = unquote(path)
        return path

    @property
    def filename(self):
        return self._file_name

    def item(self):
        return self._item

    @property
    def artist(self):
        return self._tags.artist

    @property
    def title(self):
        return self._tags.title

    @property
    def duration(self):
        return self._duration

    @property
    def key(self):
        return self._key

    @property
    def bpm(self):
        return self._bpm

    @property
    def genre(self):
        return self._tags.genre or "undefined"


class BrowserRepresentation():

    SOCKET_IN = "/tmp/LiveMusicBrowser.src.socket"
    SOCKET_OUT = "/tmp/LiveMusicBrowser.ui.socket"

    def __init__(self, browser):
        self._browser = browser
        self._parents = []
        self._current = []
        self._current_index = 0
        self._iterate_and_find_audio(browser.user_library)

        if os.path.exists(self.SOCKET_IN):
            os.remove(self.SOCKET_IN)

        self._socket = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self._socket.bind(self.SOCKET_IN)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 250*1024)
       # os.system("/Users/sam/Projects/GeoLEDic/build/GeoLEDic.app/Contents/MacOS/GeoLEDic&")
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
        if down_not_up and self._current_index < len(self._current) - 1:
            self._current_index = self._current_index + 1
        elif not down_not_up and self._current_index > 0:
            self._current_index = self._current_index - 1
        self._update()

    def preview(self):
        self._browser.preview_item(
            self._current[self._current_index].item())

    def load(self):
        self._browser.load_item(
            self._current[self._current_index].item())

    def _update(self):
        
        d = {
            "sel_ix": self._current_index,
            "cols": [
                "Artist",
                "Title",
                "Genre",
                "Duration",
                "BPM",
                "Key"
            ],
            "rows": []
        }

        for item in self._current:
            r = []
            for k in d["cols"]:
                r.append(getattr(item, k.lower()))
            d["rows"].append(r)

        try:
            self._socket.sendto(json.dumps(d, indent=1).encode('utf-8'), self.SOCKET_OUT)
        except:
            pass