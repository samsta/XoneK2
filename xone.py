import time
import os

from functools import partial

import Live
import MidiRemoteScript
from _Framework.ButtonElement import ButtonElement
from _Framework.ButtonMatrixElement import ButtonMatrixElement
from _Framework.ControlSurface import ControlSurface
from _Framework.DeviceComponent import DeviceComponent
from _Framework.EncoderElement import EncoderElement
from _Framework.InputControlElement import *
from _Framework.MixerComponent import MixerComponent
from _Framework.SessionComponent import SessionComponent
from _Framework.SliderElement import SliderElement
from _Framework.TransportComponent import TransportComponent
import _Framework.Task

from XoneK2_DJ.Browser import BrowserItem, BrowserRepresentation
g_logger = None
DEBUG = True

def log(msg):
    global g_logger
    if DEBUG:
        if g_logger is not None:
            g_logger(msg)


EQ_DEVICES = {
    'FilterEQ3': {
        'Gains': ['GainLo', 'GainMid', 'GainHi'],
        'Cuts': ['LowOn', 'MidOn', 'HighOn']
    }
}

# Channels are counted from 0. This is what people would normally call
# channel 15.
CHANNEL = 14

NUM_TRACKS = 4
NUM_SCENES = 4

ENCODERS = [0, 1, 2, 3]
PUSH_ENCODERS = [52, 53, 54, 55]
KNOBS1 = [4, 5, 6, 7]
BUTTONS1 = [48, 49, 50, 51]
KNOBS2 = [8, 9, 10, 11]
BUTTONS2 = [44, 45, 46, 47]
KNOBS3 = [12, 13, 14, 15]
BUTTONS3 = [40, 41, 42, 43]
FADERS = [16, 17, 18, 19]
GRID = [
    [36, 37, 38, 39],
    [32, 33, 34, 35],
    [28, 29, 30, 31],
    [24, 25, 26, 27],
]
ENCODER_LL = 20
PUSH_ENCODER_LL = 13
ENCODER_LR = 21
PUSH_ENCODER_LR = 14
BUTTON_LL = 12
BUTTON_LR = 15

class Color():
    RED = 0
    YELLOW = 36
    GREEN = 72

class ColorBottomRow():
    """
        The bottom row button 'Layer' and 'Exit Setup' have a slightly different note offset for the other colors
    """
    RED = 0
    YELLOW = 4
    GREEN = 8

class ClipState():
    STOPPED = 0
    STOPPED_NO_WARP = 1
    TRIGGERED = 2
    PLAYING = 3


class ButtonWithLight(ButtonElement):
    def __init__(self, notenr):
        super(ButtonWithLight, self).__init__(True, MIDI_NOTE_TYPE, CHANNEL, notenr)
        self.notenr = notenr

    def release_parameter(self):
        super(ButtonWithLight, self).release_parameter()
        self.send_midi((144 + CHANNEL, self.notenr, 0)) # for some reason send_value() doesn't work reliably, so send raw MIDI

class MultiShiftButton(ButtonElement):
    def __init__(self, notenr, max_states=4, colormap=ColorBottomRow()):
        super(MultiShiftButton, self).__init__(True, MIDI_NOTE_TYPE, CHANNEL, notenr)
        self._max_states = max_states
        self._state = 0
        self._notenr = notenr
        self._colormap = colormap
        self.add_value_listener(self._on_push)
        self._update_light()

    def state(self):
        return self._state

    def _on_push(self, value):
        if value > 0:
            self._state = (self._state + 1) % self._max_states
        self._update_light()

    def _update_light(self):
        if self._state == 0:
            self.send_midi((144 + CHANNEL, self._notenr + self._colormap.RED, 0))
            self.send_midi((144 + CHANNEL, self._notenr + self._colormap.YELLOW, 0))
            self.send_midi((144 + CHANNEL, self._notenr + self._colormap.GREEN, 0))
        elif self._state == 1:
            self.send_midi((144 + CHANNEL, self._notenr + self._colormap.RED, 127))
        elif self._state == 2:
            self.send_midi((144 + CHANNEL, self._notenr + self._colormap.YELLOW, 127))
        elif self._state == 3:
            self.send_midi((144 + CHANNEL, self._notenr + self._colormap.GREEN, 127))

class DetailViewButton(ButtonElement):
    def __init__(self, notenr, parent, tracknum):
        super(DetailViewButton, self).__init__(True, MIDI_NOTE_TYPE, CHANNEL, notenr)
        self._notenr = notenr
        self._parent = parent
        self._tracknum = tracknum
        self.add_value_listener(self._on_push)

    def _on_push(self, value):
        if value > 64:
            track = self._parent.song().visible_tracks[self._tracknum]
            if track.playing_slot_index >= 0:
                self._parent.song().view.detail_clip = track.clip_slots[track.playing_slot_index].clip
                # shouldn't have to do this, but for some reason the 'scene changed' event is not sent even though this changes the selected scene
                self._parent.on_scene_changed()
            self._parent.application().view.show_view('Detail/Clip')


def button(notenr, name=None):
    rv = ButtonWithLight(notenr)
    if name is not None:
        rv.name = name
    return rv

class EqGainEncoder(EncoderElement):
    """
    Gain encoder that maps values in a way so 0dB is in the center
    """
    def __init__(self, cc):
        super(EqGainEncoder,self).__init__(MIDI_CC_TYPE, CHANNEL, cc, Live.MidiMap.MapMode.absolute)
        self.add_value_listener(self.handle_encoder_turn)
        self.mapped_param = None

    def handle_encoder_turn(self, value):
        zero_db = 0.85
        minus_6_db = 0.7
        if value < 15:
            fval = minus_6_db * (value/15)
        elif value < 60:
            fval = minus_6_db + (zero_db - minus_6_db) * ((value-15)/45)
        elif value > 68:
            fval = zero_db + (1 - zero_db) * ((value - 68)/60)
        else:
            fval = zero_db

        if (self.mapped_parameter() != None):
            self.mapped_param = self.mapped_parameter()
            self.release_parameter()

        if self.mapped_param != None:
            self.mapped_param.value = fval

class Fader(SliderElement):
    def __init__(self, notenr, max=1.0):
        super(Fader,self).__init__(MIDI_CC_TYPE, CHANNEL, notenr)
        self.add_value_listener(self.handle_slider)
        self._max = max
        self._mapped_param = None

    def handle_slider(self, value):
        if (self.mapped_parameter() != None):
            self._mapped_param = self.mapped_parameter()
            self.release_parameter()

        if self._mapped_param != None:
            self._mapped_param.value = value * self._max / 127

def knob(cc):
    return EncoderElement(MIDI_CC_TYPE, CHANNEL, cc, Live.MidiMap.MapMode.absolute)


def encoder(cc):
    return EncoderElement(MIDI_CC_TYPE, CHANNEL, cc, Live.MidiMap.MapMode.absolute)



class DynamicEncoder(EncoderElement):
    def __init__(self, cc, target, growth=1.1, timeout=0.2):
        """
        target (DeviceParameter)
        growth (float): How much the paramter change accelerates with
            quick turns.
        timeout (float): Seconds. Acceleration will reset after this
            amount of time passes between encoder events.
        """
        self.growth = growth
        self.timeout = timeout
        if cc != None:
            self.encoder = encoder(cc)
            self.encoder.add_value_listener(self.handle_encoder_turn)
        self.sensitivity = 1.0
        self.last_event_value = None
        self.last_event_time = 0
        self.target = target

    def handle_encoder_turn(self, value):
        now = time.time()
        if now - self.last_event_time < self.timeout and value == self.last_event_value:
            self.sensitivity *= self.growth
        else:
            self.sensitivity = 1.0
        delta = (1 if value < 64 else -1)
        delta *= self.sensitivity
        if self.target is not None:
            delta *= float(self.target.max - self.target.min) / 150.0
            new_value = self.target.value + delta
            self.target.value = max(min(self.target.max, new_value), self.target.min)
        self.last_event_time = now
        self.last_event_value = value

class MultiplexedEncoder(EncoderElement):
    def __init__(self, encoders, shift_button, cc, button_cc):
        super(MultiplexedEncoder, self).__init__(MIDI_CC_TYPE, CHANNEL, cc, Live.MidiMap.MapMode.absolute)
        self._encoders = encoders
        self._shift_button = shift_button
        self._button = button(button_cc)
        self._button.add_value_listener(self._handle_button)
        self.add_value_listener(self._handle_encoder_turn)

    def _handle_encoder_turn(self, value):
        state = self._shift_button.state()
        if state < len(self._encoders):
            self._encoders[state].handle_encoder_turn(value)

    def _handle_button(self, value):
        state = self._shift_button.state()
        if state < len(self._encoders):
            enc = self._encoders[state]
            if hasattr(enc, 'handle_button'):
                enc.handle_button(value)


class TempoEncoder(DynamicEncoder):
    def __init__(self, transport, growth=1.15, timeout=0.2, max_sensitivity=100):
        """
        target (DeviceParameter)
        growth (float): How much the paramter change accelerates with
            quick turns.
        timeout (float): Seconds. Acceleration will reset after this
            amount of time passes between encoder events.
        """
        super(TempoEncoder, self).__init__(None, None, growth, timeout)
        self.sensitivity = 1.0
        self.last_event_value = None
        self.last_event_time = 0
        self.transport = transport
        self.max_sensitivity = max_sensitivity
        self.button_pressed = False

    def handle_button(self, value):
        self.button_pressed = value >= 64
        now = time.time()
        # tap if button pressed, but only if there hasn't been a turn (nudge/tempo change) in a while
        if self.button_pressed and now - self.last_event_time > 1:
            self.transport.song().tap_tempo()
        else:
            self.transport.song().nudge_up = False
            self.transport.song().nudge_down = False

    def handle_encoder_turn(self, value):
        now = time.time()

        # nudge if button pressed, otherwise adjust tempo
        if self.button_pressed:
            if value < 64:
                self.transport.song().nudge_up = True
                self.transport.song().nudge_down = False
            else:
                self.transport.song().nudge_down = True
                self.transport.song().nudge_up = False
        else:
            if now - self.last_event_time < self.timeout and value == self.last_event_value:
                if self.sensitivity < self.max_sensitivity:
                    self.sensitivity *= self.growth
                if self.sensitivity >= self.max_sensitivity:
                    self.sensitivity = self.max_sensitivity
            else:
                self.sensitivity = 1.0
            delta = (1 if value < 64 else -1)
            delta *= self.sensitivity/100
            new_value = self.transport.song().tempo + delta
            self.transport.song().tempo = max(min(250, new_value), 20)
        self.last_event_time = now
        self.last_event_value = value


class SceneSelector(DynamicEncoder):
    def __init__(self, song):
        super(SceneSelector, self).__init__(None, None)
        self.song = song

    def handle_button(self, value):
        if (value > 64):
            self.song.view.selected_scene.fire()

    def handle_encoder_turn(self, value):
        scene_index = list(self.song.scenes).index(self.song.view.selected_scene)
        if value < 64:
            scene_index += 1
        else:
            scene_index -= 1

        if scene_index in range(len(self.song.scenes)):
            self.song.view.selected_scene = self.song.scenes[scene_index]


class BrowserScroller(DynamicEncoder):
    HORIZONTAL = 0
    VERTICAL = 1

    def __init__(self, browser, direction):
        super(BrowserScroller, self).__init__(None, None)
        self._browser = browser
        self._direction = direction

    def handle_button(self, value):
        if self._direction == self.HORIZONTAL:
            self._browser.preview()
        else:
            self._browser.load()

    def handle_encoder_turn(self, value):
        if self._direction == self.VERTICAL:
            self._browser.scroll_vertical(value < 64)
        else:
            self._browser.scroll_horizontal(value >= 64)


class WaveformZoom(DynamicEncoder):
    def __init__(self, application, song):
        super(WaveformZoom, self).__init__(None, None)
        self._application = application
        self._song = song

    def handle_button(self, value):
        if (value > 64):
            self._song.view.follow_song = True

    def handle_encoder_turn(self, value):
        self._application.view.show_view('Detail/Clip')
        self._application.view.focus_view('Detail/Clip')
        if value < 64:
            # zoom in yuckily
            os.system("osascript -e 'tell application \"System Events\" to tell process \"Live\" to key code 24'")
        else:
            # zoom out yuckily
            os.system("osascript -e 'tell application \"System Events\" to tell process \"Live\" to key code 27'")

class PositionScroller(DynamicEncoder):
    def __init__(self, application, song):
        super(PositionScroller, self).__init__(None, None)
        self._application = application
        self._song = song

    def handle_encoder_turn(self, value):
        if value < 64:
            self._song.view.detail_clip.position = self._song.view.detail_clip.position + 32
        else:
            self._song.view.detail_clip.position = self._song.view.detail_clip.position - 32

class GlobalStopButton(ButtonElement):
    def __init__(self, button_cc, song):
        self.button = button(button_cc)
        self.button.add_value_listener(self.handle_button)
        self.song = song
        song.add_is_playing_listener(self.handle_song_is_playing)
        self.last_stop_button_time = 0
        log("song %s" % dir(song))

    def handle_song_is_playing(self):
        self.button.send_value(127 if self.song.is_playing else 0)

    def handle_button(self, value):
        if value == 0:
            return

        now = time.time()
        if now - self.last_stop_button_time < 0.4:
            self.song.is_playing = False
        self.song.stop_all_clips()
        
        self.last_stop_button_time = now

class MixerWithDevices(MixerComponent):
    def __init__(self, num_tracks, num_returns=0, device_select=None, device_encoders=None):
        self.devices = []
        self.eqs = []
        self.active_track = 0
        self.device_select = device_select
        MixerComponent.__init__(self, num_tracks, num_returns)
        self.encoders = [DynamicEncoder(cc, None) for cc in device_encoders]
        for i in range(len(self._channel_strips)):
            dev = {
                "cb": None,
                "component": DeviceComponent(),
                "track": None,
                "params": [],
                "toggle": None,
            }
            self.devices.append(dev)
            self.register_components(dev["component"])
            eq = {
                "component": DeviceComponent(),
                "cb": None,
                "track": None
            }
            self.eqs.append(eq)
            self.register_components(eq["component"])
        self._reassign_tracks()
        if device_select:
            for i, b in enumerate(device_select):
                b.add_value_listener(partial(self.on_device_select_push, i))

        self.song().view.add_selected_track_listener(self.on_track_selected)

    def on_track_selected(self):
        for i in range(len(self.song().visible_tracks)):
            if i > NUM_TRACKS:
                return
            
            if self.song().view.selected_track == self.song().visible_tracks[i]:
                self.active_track = i
                self.light_up(self.active_track)
                self.attach_encoders()

    def on_device_select_push(self, track, value):
        if value > 1:
            self.select_track(track)

    def select_track(self, track):
        self.song().view.selected_track = self.song().visible_tracks[track]
        self.application().view.show_view('Detail/DeviceChain')

    def light_up(self, which_track):
        if self.device_select:
            for i, b in enumerate(self.device_select):
                velocity = 127 if i == which_track else 0
                b.send_midi((144 + CHANNEL, b._msg_identifier, velocity))

    def attach_encoders(self):
        for control, target in zip(self.encoders, self.devices[self.active_track]["params"]):
            control.target = target

    def get_active_tracks(self):
        tracks_to_use = self.tracks_to_use()
        num_tracks = len(self._channel_strips)
        return tracks_to_use[self._track_offset:self._track_offset + num_tracks]

    def _reassign_tracks(self):
        super(MixerWithDevices, self)._reassign_tracks()

        # assign each DeviceComponent to the first device on its track
        # this could be called before we construct self.devices
        if self.devices:
            log("reassigning tracks")
            tracks_to_use = self.get_active_tracks()
            log("tracks_to_use has %d elements" % len(tracks_to_use))
            log("devices has %d" % len(self.devices))
            for i, dev in enumerate(self.devices):
                if i < len(tracks_to_use):
                    log("device %d gets a track %s" % (i, tracks_to_use[i].name))
                    self.assign_device_to_track(tracks_to_use[i], i)
                else:
                    log("device %d gets no track" % i)
                    self.assign_device_to_track(None, i)
        if self.eqs:
            log("reassigning tracks")
            tracks_to_use = self.get_active_tracks()
            log("tracks_to_use has %d elements" % len(tracks_to_use))
            log("devices has %d" % len(self.devices))
            for i, eq in enumerate(self.eqs):
                if i < len(tracks_to_use):
                    log("device %d gets a track %s" % (i, tracks_to_use[i].name))
                    self.assign_eq_to_track(tracks_to_use[i], i)
                else:
                    log("device %d gets no track" % i)
                    self.assign_eq_to_track(None, i)
        self.light_up(self.active_track)

    def assign_device_to_track(self, track, i):
        # nuke existing listener
        dev = self.devices[i]
        if dev["track"]:
            dev["track"].remove_devices_listener(dev["cb"])
            dev["track"] = None
            dev["cb"] = None
            dev["params"] = []
            dev["toggle"] = None
            dev["component"].set_lock_to_device(False, None)
            dev["component"].set_device(None)

        if track is not None:
            # listen for changes to the device chain
            def dcb():
                return self._on_device_changed(i)
            dev["cb"] = dcb
            dev["track"] = track
            track.add_devices_listener(dcb)

            # force an update to attach to any existing device
            dcb()

    def _on_device_changed(self, i):
        log("_on_device_changed %d" % i)
        # the device chain on track i changed-- reassign device if needed
        track = self.devices[i]["track"]
        device_comp = self.devices[i]["component"]
        device = None
        if track.devices:
            # Find the first non-EQ device.
            for dev in track.devices:
                log("examine device %s" % dev.class_name)
                if dev.class_name not in EQ_DEVICES:
                    device = dev
                    log("using %s" % device.class_name)
                    self.devices[i]["params"] = device.parameters[1:len(self.encoders)+1]
                    self.devices[i]["toggle"] = device.parameters[0]
                    break
        device_comp.set_lock_to_device(True, device)
        self.attach_encoders()
        self.update()
        self.light_up(self.active_track)

    def assign_eq_to_track(self, track, i):
        # nuke existing listener
        dev = self.eqs[i]
        if dev["track"]:
            dev["track"].remove_devices_listener(dev["cb"])
            dev["track"] = None
            dev["cb"] = None
            dev["component"].set_lock_to_device(False, None)
            dev["component"].set_device(None)

        if track is not None:
            # listen for changes to the device chain
            def dcb():
                return self._reassign_tracks()
            dev["cb"] = dcb
            dev["track"] = track
            track.add_devices_listener(dcb)
            device_comp = self.eqs[i]["component"]
            device = None
            if track.devices:
                # Find the first EQ device.
                for dev in track.devices:
                    log("examine device %s" % dev.class_name)
                    if dev.class_name in EQ_DEVICES:
                        log("using it")
                        device = dev
                        break
            device_comp.set_lock_to_device(True, device)
        self.update()

    def set_eq_controls(self, track_nr, controls):
        eq_comp = self.eqs[track_nr]["component"]
        eq_comp.set_parameter_controls(controls)
        eq_comp.update()

    def set_device_controls(self, track_nr, arm):
        device_comp = self.devices[track_nr]["component"]
        device_comp.set_on_off_button(arm)
        device_comp.update()


class ClipStartButton(ButtonElement):
    def __init__(self, tracknr, notenr, song):
        super(ClipStartButton, self).__init__(True, MIDI_NOTE_TYPE, CHANNEL, notenr)
        self._song = song
        self._tracknr = tracknr
        self._notenr = notenr
        self.add_value_listener(self._push_button)
        self._timer = None
        self._warning_toggle = False

    def set_clip_selected(self, is_selected, state):
        if self._timer:
            self._timer.stop()

        if is_selected:
            if state == ClipState.PLAYING:
                color = Color.RED
            elif state == ClipState.TRIGGERED:
                color = Color.YELLOW
            elif state == ClipState.STOPPED_NO_WARP:
                color = Color.GREEN
                self._timer = Live.Base.Timer(callback=self._flash_warp_warning, interval=200, repeat=True)
                self._timer.start()
            else:
                color = Color.GREEN

            self.send_midi((144 + CHANNEL, self._notenr + color, 127))    
        else:
            self.send_midi((144 + CHANNEL, self._notenr, 0))    

    def _flash_warp_warning(self):
        color = Color.GREEN if self._warning_toggle else Color.RED
        self._warning_toggle = not self._warning_toggle
        self.send_midi((144 + CHANNEL, self._notenr + color, 127))    

    def _push_button(self, value):
        if value > 1:
            self._song.view.selected_scene.clip_slots[self._tracknr].fire()


class TrackStopButton(ButtonElement):
    def __init__(self, tracknr, notenr, mixer):
        super(TrackStopButton, self).__init__(True, MIDI_NOTE_TYPE, CHANNEL, notenr)
        self.mixer = mixer
        self.tracknr = tracknr
        self.notenr = notenr
        self.add_value_listener(self.push_button)

    def set_track_playing(self, is_playing):
        if is_playing:
            self.send_midi((144 + CHANNEL, self.notenr, 127))    
        else:
            self.send_midi((144 + CHANNEL, self.notenr, 0))    

    def push_button(self, value):
        if value > 1:
            self.mixer.channel_strip(self.tracknr)._track.stop_all_clips()

class XoneK2_DJ(ControlSurface):
    def __init__(self, instance):
        global g_logger
        g_logger = self.log_message
        super(XoneK2_DJ, self).__init__(instance)
        self.tracks_with_listener = []
        self.slots_with_listener = []
        self.clips_with_listener = []
        self.slot_callbacks = []
        self.clip_callbacks = []

        with self.component_guard():
            self._set_suppress_rebuild_requests(True)
            self.shift_button = MultiShiftButton(BUTTON_LL, 4)

            self.init_session()
            self.init_mixer()

            self.remove_clip_listeners()
            self.add_clip_listeners()
            self.update_track_playing_status()

            self._set_suppress_rebuild_requests(False)

    def _tempo_changed(self):
        self.browser_repr.tempo(self.song().tempo)

    def init_session(self):
        self.transport = TransportComponent()
        self.browser_repr = BrowserRepresentation(self.application().browser, self.log_message)
        self.song().add_tempo_listener(self._tempo_changed)
        self._tempo_changed()
        self._browser_poll_task = self._tasks.add(Task.repeat(Task.run(self.browser_repr.poll)))

        self.bottom_left_encoder = MultiplexedEncoder(
            [
                TempoEncoder(self.transport),
                DynamicEncoder(None, self.song().master_track.mixer_device.cue_volume),
                BrowserScroller(self.browser_repr, BrowserScroller.HORIZONTAL),
                WaveformZoom(self.application(), self.song())
            ],
            self.shift_button, ENCODER_LL, PUSH_ENCODER_LL)

        self.bottom_right_encoder = MultiplexedEncoder(
            [
                SceneSelector(self.song()),
                DynamicEncoder(None, self.song().master_track.mixer_device.volume),
                BrowserScroller(self.browser_repr, BrowserScroller.VERTICAL),
                PositionScroller(self.application(), self.song())
            ],
            self.shift_button, ENCODER_LR, PUSH_ENCODER_LR)

        self.global_stop_button = GlobalStopButton(BUTTON_LR, self.song())

    def init_mixer(self):
        self.mixer = MixerWithDevices(
            num_tracks=NUM_TRACKS,
            device_select=[button(PUSH_ENCODERS[i]) for i in range(NUM_TRACKS)],
            device_encoders=ENCODERS
        )
        self.mixer.id = 'Mixer'

        self.song().view.selected_track = self.mixer.channel_strip(0)._track

        volume_limit = 0.85 # 0dB
        self.clip_start_buttons = []
        self.track_stop_buttons = []
        self.clip_view_buttons = []
        for i in range(NUM_TRACKS):
            self.mixer.channel_strip(i).set_volume_control(Fader(FADERS[i], volume_limit))
            self.mixer.channel_strip(i).set_solo_button(button(GRID[2][i]))
            self.mixer.set_eq_controls(i, (
                EqGainEncoder(KNOBS3[i]),
                EqGainEncoder(KNOBS2[i]),
                EqGainEncoder(KNOBS1[i]),
                None,
                button(BUTTONS3[i]),
                button(BUTTONS2[i]),
                button(BUTTONS1[i])))
            self.clip_start_buttons.append(ClipStartButton(i, GRID[0][i], self.song()))
            self.track_stop_buttons.append(TrackStopButton(i, GRID[1][i], self.mixer))
            if self.mixer.channel_strip(i)._track != None:
                # TODO support adding of tracks without the need to reload the script
                self.mixer.channel_strip(i)._track.add_clip_slots_listener(self.on_track_changed)
            self.clip_view_buttons.append(DetailViewButton(GRID[3][i], self, i))

        self.song().view.add_selected_scene_listener(self.on_scene_changed)
        self.mixer.update()

    def on_scene_changed(self):
        log("scene changed")
        self.update_track_playing_status()

    def on_track_changed(self):
        log("track changed")
        self.remove_clip_listeners()
        self.add_clip_listeners()
        self.update_track_playing_status()

    def on_slot_clip_changed(self, slot, track_idx, slot_idx):
        self.remove_clip_listeners()
        self.add_clip_listeners()
        self.update_track_playing_status()

    def on_clip_playing_changed(self, clip, track_idx, clip_idx):
        self.update_track_playing_status()

    def is_track_playing(self, track):
        for slot in track.clip_slots:
            if slot.has_clip and slot.clip.is_playing:
                return 1

        return 0

    def is_selected_slot_playing(self, track_idx):
        slot = self.song().view.selected_scene.clip_slots[track_idx]
        state = ClipState.STOPPED
        if slot.has_clip:
            if slot.clip.is_playing:
                state = ClipState.PLAYING
            elif slot.clip.is_triggered:
                state = ClipState.TRIGGERED
            elif slot.clip.is_audio_clip and not slot.clip.warping:
                # special state so we can emit warning when warping is not on
                state = ClipState.STOPPED_NO_WARP
        return slot.has_clip, state

    def update_track_playing_status(self):
        i = 0
        playing_tracks = []
        master_deck_index = -1
        max_play_time = 0
        for track in self.song().tracks:
            if i >= NUM_TRACKS:
                return

            is_selected, clip_state = self.is_selected_slot_playing(i)
            self.clip_start_buttons[i].set_clip_selected(is_selected, clip_state)
            self.track_stop_buttons[i].set_track_playing(self.is_track_playing(track))

            if track.playing_slot_index >= 0:
                slot = track.clip_slots[track.playing_slot_index]
                playing_tracks.append(slot.clip.file_path)

                # the master deck is the one that has been playing for the longest time
                if (slot.clip.playing_position > max_play_time):
                    max_play_time = slot.clip.playing_position
                    master_deck_index = i

            else:
                playing_tracks.append(None)

            i += 1
        self.browser_repr.set_decks(playing_tracks, master_deck_index)

    def clip_add_callback(self, clip, track_idx, clip_idx):
        callback = lambda : self.on_clip_playing_changed(clip, track_idx, clip_idx)
        clip.add_playing_status_listener(callback)
        self.clips_with_listener += [clip]
        self.clip_callbacks += [callback]

    def slot_add_callback(self, slot, track_idx, slot_idx):
        callback = lambda : self.on_slot_clip_changed(slot, track_idx, slot_idx)
        slot.add_has_clip_listener(callback)
        self.slots_with_listener += [slot]
        self.slot_callbacks += [callback]

    def add_clip_listeners(self):
        i = 0
        for track in self.song().tracks:
            if i >= NUM_TRACKS:
                return
            sloti = 0
            for slot in track.clip_slots:
                if slot.has_clip:
                    self.clip_add_callback(slot.clip, i, sloti)
                self.slot_add_callback(slot, i, sloti)
                sloti += 1

            i += 1

    def remove_slot_listeners(self):
        for i in range(0, len(self.slots_with_listener)):
            slot = self.slots_with_listener[i]
            callback = self.slot_callbacks[i]
            try:
                if slot.has_clip_has_listener(callback):
                    slot.remove_has_clip_listener(callback)
            except:
                continue

        self.slots_with_listener = []
        self.slot_callbacks = []

    def remove_clip_listeners(self):
        self.remove_slot_listeners()
        for i in range(0, len(self.clips_with_listener)):
            clip = self.clips_with_listener[i]
            callback = self.clip_callbacks[i]
            try:
                if clip.playing_status_has_listener(callback):
                    clip.remove_playing_status_listener(callback)
            except:
                continue

        self.clips_with_listener = []
        self.clip_callbacks = []

    def disconnect(self):
        super(XoneK2_DJ, self).disconnect()
        self.browser_repr.disconnect()