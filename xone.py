import time
import inspect
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


g_logger = None
DEBUG = True


def log(msg):
    global g_logger
    if DEBUG:
        if g_logger is not None:
            g_logger(msg)


EQ_DEVICES = {
    'Eq8': {
        'Gains': ['%i Gain A' % (index + 1) for index in range(8)]
    },
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


def button(notenr, name=None):
    rv = ButtonElement(True, MIDI_NOTE_TYPE, CHANNEL, notenr)
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
            self._mapped_param = self.mapped_parameter()
            self.release_parameter()

        if self._mapped_param != None:
            self._mapped_param.value = fval
            log("turn %d, mapped %f" % (value, self._mapped_param.value))

class Fader(SliderElement):
    def __init__(self, notenr, max=1.0):
        super(Fader,self).__init__(MIDI_CC_TYPE, CHANNEL, notenr)
        self.add_value_listener(self.handle_slider)
        self.max = max

    def handle_slider(self, value):
        if self.mapped_parameter() != None and self.mapped_parameter().value > self.max:
            self.mapped_parameter().value = self.max

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



class TempoEncoder(EncoderElement):
    def __init__(self, cc, button_cc, transport, growth=1.15, timeout=0.2, max_sensitivity=100):
        """
        target (DeviceParameter)
        growth (float): How much the paramter change accelerates with
            quick turns.
        timeout (float): Seconds. Acceleration will reset after this
            amount of time passes between encoder events.
        """
        self.growth = growth
        self.timeout = timeout
        self.encoder = encoder(cc)
        self.button = button(button_cc)
        self.encoder.add_value_listener(self.handle_encoder_turn)
        self.button.add_value_listener(self.handle_button)
        self.sensitivity = 1.0
        self.last_event_value = None
        self.last_event_time = 0
        self.transport = transport
        self.max_sensitivity = max_sensitivity
        self.button_pressed = True

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



class SceneSelector(EncoderElement):
    def __init__(self, cc, button_cc, stop_button_cc, song):
        self.encoder = encoder(cc)
        self.button = button(button_cc)
        self.stop_button = button(stop_button_cc)
        self.encoder.add_value_listener(self.handle_encoder_turn)
        self.button.add_value_listener(self.handle_button)
        self.stop_button.add_value_listener(self.handle_stop_button)
        self.song = song

    def handle_button(self, value):
        self.song.view.selected_scene.fire()

    def handle_stop_button(self, value):
        self.song.stop_all_clips()

    def handle_encoder_turn(self, value):
        scene_index = list(self.song.scenes).index(self.song.view.selected_scene)
        if value < 64:
            scene_index += 1
        else:
            scene_index -= 1

        if scene_index in range(len(self.song.scenes)):
            self.song.view.selected_scene = self.song.scenes[scene_index]
        

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

    def on_device_select_push(self, track, value):
        if value > 1:
            self.select_track(track)

    def select_track(self, track):
        self.active_track = track
        self.light_up(self.active_track)
        self.attach_encoders()
        self.song().view.selected_track = self.song().visible_tracks[track]

    def light_up(self, which_track):
        if self.device_select:
            for i, b in enumerate(self.device_select):
                velocity = 127 if i == which_track else 0
                b.send_midi((144 + CHANNEL, b._msg_identifier, velocity))

    def attach_encoders(self):
        for control, target in zip(self.encoders, self.devices[self.active_track]["params"]):
            log("c %s t %s" % (control, target))
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
                return self._on_eq_changed(i)
            dev["cb"] = dcb
            dev["track"] = track
            track.add_devices_listener(dcb)

            # force an update to attach to any existing device
            dcb()

    def _on_eq_changed(self, i):
        log("_on_eq_changed %d" % i)
        # the device chain on track i changed-- reassign device if needed
        track = self.eqs[i]["track"]
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


class XoneK2_DJ(ControlSurface):
    def __init__(self, instance):
        global g_logger
        g_logger = self.log_message
        super(XoneK2_DJ, self).__init__(instance, False)
        with self.component_guard():
            self._set_suppress_rebuild_requests(True)
            self.init_session()
            self.init_mixer()
            #self.init_matrix()
            self.init_tempo()

            # connect mixer to session
            #self.session.set_mixer(self.mixer)
            #self.session.update()
            #self.set_highlighting_session_component(self.session)
            self._set_suppress_rebuild_requests(False)

    def init_session(self):
        self.scene_selector = SceneSelector(ENCODER_LR, PUSH_ENCODER_LR, BUTTON_LR, self.song())


    def init_mixer(self):
        self.mixer = MixerWithDevices(
            num_tracks=NUM_TRACKS,
            device_select=[button(PUSH_ENCODERS[i]) for i in range(NUM_TRACKS)],
            device_encoders=ENCODERS
        )
        self.mixer.id = 'Mixer'

        self.song().view.selected_track = self.mixer.channel_strip(0)._track

        volume_limit = 0.85 # 0dB
        for i in range(NUM_TRACKS):
            self.mixer.channel_strip(i).set_volume_control(Fader(FADERS[i], volume_limit))
            #self.mixer.channel_strip(i).set_solo_button(button(BUTTONS3[i]))
            self.mixer.set_eq_controls(i, (
                EqGainEncoder(KNOBS3[i]),
                EqGainEncoder(KNOBS2[i]),
                EqGainEncoder(KNOBS1[i]),
                None,
                button(BUTTONS3[i]),
                button(BUTTONS2[i]),
                button(BUTTONS1[i])))
            #self.mixer.set_device_controls(i, button(BUTTONS1[i]))

        #self.master_encoder = DynamicEncoder(
        #    ENCODER_LR, self.song().master_track.mixer_device.volume)
        #self.cue_encoder = DynamicEncoder(
        #    ENCODER_LL, self.song().master_track.mixer_device.cue_volume)
        self.mixer.update()

    def init_matrix(self):
        self.matrix = ButtonMatrixElement()

        for scene_index in range(NUM_SCENES):
            scene = self.session.scene(scene_index) 
            scene.name = 'Scene ' + str(scene_index)
            button_row = []
            for track_index in range(NUM_TRACKS):
                note_nr = GRID[scene_index][track_index]
                b = button(note_nr, name='Clip %d, %d button' % (scene_index, track_index))
                button_row.append(b)
                clip_slot = scene.clip_slot(track_index)
                clip_slot.name = 'Clip slot %d, %d' % (scene_index, track_index)
                clip_slot.set_stopped_value(0)
                clip_slot.set_started_value(64)
                clip_slot.set_launch_button(b)
            self.matrix.add_row(tuple(button_row))
        #stop_buttons = [button(note_nr) for note_nr in BUTTONS2]
        #self.session.set_stop_track_clip_buttons(stop_buttons)

    def init_tempo(self):
        self.transport = TransportComponent()
        self.tempo = TempoEncoder(ENCODER_LL, PUSH_ENCODER_LL, self.transport)
