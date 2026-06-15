#!/usr/bin/env python3
"""
Chorded Keyboard Daemon for Steam Deck — v2 (F-key approach)

Steam Input (desktop config) maps the physical controls to NUMPAD keys,
which Steam emits through its virtual keyboard device. We grab that
device exclusively (so the numpad keys never leak to apps), do chord
logic, and emit real characters via uinput.

Mapping expected from Steam desktop configuration:
  L4 grip -> Keypad 1     L5 grip -> Keypad 2
  R4 grip -> Keypad 3     R5 grip -> Keypad 4
  Dpad Up -> Keypad 5     Dpad Down -> Keypad 6
  Dpad Left -> Keypad 7   Dpad Right -> Keypad 8
  A -> Keypad 9   B -> Keypad 0   X -> Keypad .   Y -> Keypad +

Touchpads/triggers keep their native Steam mouse behavior — we never
touch the gamepad device at all.
"""

import threading
import os
import sys
import signal
import logging
import time
from pathlib import Path
from evdev import InputDevice, UInput, ecodes as e, list_devices
from evdev.ecodes import (
    KEY_KP0, KEY_KP1, KEY_KP2, KEY_KP3, KEY_KP4, KEY_KP5,
    KEY_KP6, KEY_KP7, KEY_KP8, KEY_KP9, KEY_KPDOT, KEY_KPPLUS,
    KEY_A, KEY_B, KEY_C, KEY_D, KEY_E, KEY_F, KEY_G, KEY_H,
    KEY_I, KEY_J, KEY_K, KEY_L, KEY_M, KEY_N, KEY_O, KEY_P,
    KEY_Q, KEY_R, KEY_S, KEY_T, KEY_U, KEY_V, KEY_W, KEY_X,
    KEY_Y, KEY_Z,
    KEY_0, KEY_1, KEY_2, KEY_3, KEY_4, KEY_5, KEY_6, KEY_7, KEY_8, KEY_9,
    KEY_SPACE, KEY_ENTER, KEY_BACKSPACE, KEY_COMMA, KEY_DOT,
    KEY_APOSTROPHE, KEY_MINUS, KEY_EQUAL, KEY_SLASH, KEY_BACKSLASH,
    KEY_SEMICOLON, KEY_GRAVE, KEY_LEFTBRACE, KEY_RIGHTBRACE,
    KEY_LEFTSHIFT,
    EV_KEY,
)

LOG_DIR = Path.home() / ".local/share/chorded-keyboard"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "chorded.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

# ─── Input key groups ────────────────────────────────────────────────────────
GRIP_KEYS = {KEY_KP1: "L4", KEY_KP2: "L5", KEY_KP3: "R4", KEY_KP4: "R5"}
# KEY_KP5 (Dpad Up) is intentionally left unmapped — free for future use.
LAYER_KEYS = {KEY_KP6: "shift", KEY_KP7: "numbers", KEY_KP8: "symbols"}
FACE_KEYS = {KEY_KP9: "A", KEY_KP0: "B", KEY_KPDOT: "X", KEY_KPPLUS: "Y"}
ALL_KEYS = set(GRIP_KEYS) | set(LAYER_KEYS) | set(FACE_KEYS)

GRIP_STATES = {
    frozenset(["L4"]): "L1",
    frozenset(["L5"]): "L2",
    frozenset(["L4", "L5"]): "L1+L2",
    frozenset(["R4"]): "R1",
    frozenset(["R5"]): "R2",
    frozenset(["R4", "R5"]): "R1+R2",
}

FACE_STATES = {
    frozenset(["A"]): "A",
    frozenset(["B"]): "B",
    frozenset(["X"]): "X",
    frozenset(["Y"]): "Y",
    frozenset(["A", "B"]): "A+B",
    frozenset(["X", "Y"]): "X+Y",
}

# ─── Chord map (unchanged layout) ────────────────────────────────────────────
CHORD_MAP = {
    "base": {
        "L1":    {"A": "e",  "B": "t",  "Y": "r",  "X": "h",  "A+B": "er", "X+Y": "q"},
        "L2":    {"A": "a",  "B": "n",  "Y": "d",  "X": " ",  "A+B": "BKSP", "X+Y": "ENT"},
        "L1+L2": {"A": "i",  "B": "x",  "Y": "o",  "X": "g",  "A+B": ",",  "X+Y": "."},
        "R1":    {"A": "s",  "B": "c",  "Y": "f",  "X": "w",  "A+B": "'",  "X+Y": "-"},
        "R2":    {"A": "l",  "B": "u",  "Y": "p",  "X": "b",  "A+B": "!",  "X+Y": "?"},
        "R1+R2": {"A": "m",  "B": "y",  "Y": "k",  "X": "v",  "A+B": "j",  "X+Y": "z"},
    },
    "shift": {
        "L1":    {"A": "E",  "B": "T",  "Y": "R",  "X": "H",  "A+B": None, "X+Y": "Q"},
        "L2":    {"A": "A",  "B": "N",  "Y": "D",  "X": " ",  "A+B": "BKSP", "X+Y": "ENT"},
        "L1+L2": {"A": "I",  "B": "X",  "Y": "O",  "X": "G",  "A+B": ";",  "X+Y": ":"},
        "R1":    {"A": "S",  "B": "C",  "Y": "F",  "X": "W",  "A+B": '"',  "X+Y": None},
        "R2":    {"A": "L",  "B": "U",  "Y": "P",  "X": "B",  "A+B": "(",  "X+Y": ")"},
        "R1+R2": {"A": "M",  "B": "Y",  "Y": "K",  "X": "V",  "A+B": "J",  "X+Y": "Z"},
    },
    "numbers": {
        "L1":    {"A": "1",  "B": "2",  "Y": "3",  "X": "4",  "A+B": None, "X+Y": None},
        "L2":    {"A": "5",  "B": "6",  "Y": "7",  "X": "8",  "A+B": None, "X+Y": None},
        "L1+L2": {"A": "9",  "B": "0",  "Y": ".",  "X": ",",  "A+B": None, "X+Y": None},
        "R1":    {"A": "+",  "B": "-",  "Y": "*",  "X": "/",  "A+B": "=",  "X+Y": None},
        "R2":    {"A": "%",  "B": "^",  "Y": "<",  "X": ">",  "A+B": None, "X+Y": None},
        "R1+R2": {"A": "(",  "B": ")",  "Y": "[",  "X": "]",  "A+B": "{",  "X+Y": "}"},
    },
    "symbols": {
        "L1":    {"A": "!",  "B": "@",  "Y": "#",  "X": "$",  "A+B": None, "X+Y": None},
        "L2":    {"A": "%",  "B": "^",  "Y": "&",  "X": "*",  "A+B": None, "X+Y": None},
        "L1+L2": {"A": "~",  "B": "`",  "Y": "\\", "X": "|",  "A+B": None, "X+Y": None},
        "R1":    {"A": "_",  "B": "=",  "Y": "+",  "X": None, "A+B": None, "X+Y": None},
        "R2":    {"A": "[",  "B": "]",  "Y": "{",  "X": "}",  "A+B": None, "X+Y": None},
        "R1+R2": {"A": "<",  "B": ">",  "Y": "/",  "X": "?",  "A+B": ";",  "X+Y": ":"},
    },
}

# ─── Character → keycode mapping ─────────────────────────────────────────────
CHAR_TO_KEY = {}
for _c, _k in zip("abcdefghijklmnopqrstuvwxyz",
                  [KEY_A, KEY_B, KEY_C, KEY_D, KEY_E, KEY_F, KEY_G, KEY_H,
                   KEY_I, KEY_J, KEY_K, KEY_L, KEY_M, KEY_N, KEY_O, KEY_P,
                   KEY_Q, KEY_R, KEY_S, KEY_T, KEY_U, KEY_V, KEY_W, KEY_X,
                   KEY_Y, KEY_Z]):
    CHAR_TO_KEY[_c] = (_k, False)
    CHAR_TO_KEY[_c.upper()] = (_k, True)
for _c, _k in zip("0123456789",
                  [KEY_0, KEY_1, KEY_2, KEY_3, KEY_4, KEY_5, KEY_6, KEY_7,
                   KEY_8, KEY_9]):
    CHAR_TO_KEY[_c] = (_k, False)
CHAR_TO_KEY.update({
    ' ':  (KEY_SPACE, False),      ',':  (KEY_COMMA, False),
    '.':  (KEY_DOT, False),        "'":  (KEY_APOSTROPHE, False),
    '-':  (KEY_MINUS, False),      '=':  (KEY_EQUAL, False),
    '/':  (KEY_SLASH, False),      '\\': (KEY_BACKSLASH, False),
    ';':  (KEY_SEMICOLON, False),  '`':  (KEY_GRAVE, False),
    '[':  (KEY_LEFTBRACE, False),  ']':  (KEY_RIGHTBRACE, False),
    '!':  (KEY_1, True),  '@': (KEY_2, True),  '#': (KEY_3, True),
    '$':  (KEY_4, True),  '%': (KEY_5, True),  '^': (KEY_6, True),
    '&':  (KEY_7, True),  '*': (KEY_8, True),  '(': (KEY_9, True),
    ')':  (KEY_0, True),  '_': (KEY_MINUS, True), '+': (KEY_EQUAL, True),
    '?':  (KEY_SLASH, True), '|': (KEY_BACKSLASH, True),
    ':':  (KEY_SEMICOLON, True), '"': (KEY_APOSTROPHE, True),
    '~':  (KEY_GRAVE, True), '{': (KEY_LEFTBRACE, True),
    '}':  (KEY_RIGHTBRACE, True), '<': (KEY_COMMA, True),
    '>':  (KEY_DOT, True),
})

# ─── Keyboard emitter ────────────────────────────────────────────────────────
class KeyboardEmitter:
    def __init__(self):
        cap = {EV_KEY: sorted(set(
            [k for k, _ in CHAR_TO_KEY.values()]
            + [KEY_BACKSPACE, KEY_ENTER, KEY_LEFTSHIFT]
        ))}
        self.ui = UInput(cap, name="chorded-keyboard", version=0x2)
        log.info("uinput keyboard device created")

    def emit(self, token):
        if token == "BKSP":
            self._press(KEY_BACKSPACE, False)
        elif token == "ENT":
            self._press(KEY_ENTER, False)
        else:
            for ch in token:
                mapping = CHAR_TO_KEY.get(ch)
                if mapping:
                    self._press(*mapping)
                else:
                    log.warning(f"No keycode mapping for: {ch!r}")

    def _press(self, keycode, shift):
        if shift:
            self.ui.write(EV_KEY, KEY_LEFTSHIFT, 1)
        self.ui.write(EV_KEY, keycode, 1)
        self.ui.syn()
        self.ui.write(EV_KEY, keycode, 0)
        if shift:
            self.ui.write(EV_KEY, KEY_LEFTSHIFT, 0)
        self.ui.syn()

    def close(self):
        try:
            self.ui.close()
        except Exception:
            pass

# ─── Chord engine (release-based) ────────────────────────────────────────────
class ChordEngine:
    """
    Face keys accumulate while held; the chord fires on the FIRST face-key
    release, using the peak face set and the grip/layer state at that moment.
    Further releases in the same press-cycle are ignored until all face keys
    are up. This makes rolling (hold grip, A down, A up, B down, B up) emit
    'A' then 'B', while a deliberate A+B (both down, then release) emits one
    A+B chord.
    """
    def __init__(self, emitter, enabled_flag):
        self.emitter = emitter
        self.enabled = enabled_flag
        self.grips_held = set()
        self.layers_held = set()
        self.faces_held = set()
        self.face_peak = set()
        self.fired = False

    def handle(self, code, value):
        # value: 1 press, 0 release, 2 autorepeat (ignore)
        if value == 2:
            return
        pressed = value == 1

        if code in GRIP_KEYS:
            name = GRIP_KEYS[code]
            (self.grips_held.add if pressed else self.grips_held.discard)(name)
        elif code in LAYER_KEYS:
            name = LAYER_KEYS[code]
            (self.layers_held.add if pressed else self.layers_held.discard)(name)
        elif code in FACE_KEYS:
            name = FACE_KEYS[code]
            if pressed:
                self.faces_held.add(name)
                self.face_peak.add(name)
            else:
                self.faces_held.discard(name)
                if not self.fired and self.face_peak:
                    self._fire()
                    self.fired = True
                if not self.faces_held:
                    self.face_peak = set()
                    self.fired = False

    def _fire(self):
        if not self.enabled[0]:
            return
        grip = GRIP_STATES.get(frozenset(self.grips_held))
        face = FACE_STATES.get(frozenset(self.face_peak))
        layer = "base"
        if "shift" in self.layers_held:
            layer = "shift"
        elif "numbers" in self.layers_held:
            layer = "numbers"
        elif "symbols" in self.layers_held:
            layer = "symbols"
        if not grip or not face:
            log.info(f"Unmapped chord: grips={self.grips_held} faces={self.face_peak}")
            return
        token = CHORD_MAP.get(layer, {}).get(grip, {}).get(face)
        if token:
            log.info(f"Chord: {layer}/{grip}/{face} -> {token!r}")
            self.emitter.emit(token)

# ─── Device discovery ────────────────────────────────────────────────────────
def find_steam_kbd_devices():
    """Valve/Steam-named devices with keyboard capability. These carry the
    numpad keys Steam Input emits for our mapped buttons. We grab them
    EXCLUSIVELY so the raw numpad presses never reach other apps. Real
    (non-Valve) keyboards are never touched."""
    found = []
    for path in list_devices():
        try:
            dev = InputDevice(path)
            name = dev.name.lower()
            keys = dev.capabilities().get(EV_KEY, [])
            if ("valve" in name or "steam" in name) and KEY_KP1 in keys:
                try:
                    dev.grab()
                    log.info(f"Grabbed Steam kbd device: {dev.name!r} at {path}")
                    found.append(dev)
                except OSError as ex:
                    log.warning(f"Could not grab {path}: {ex}")
                    dev.close()
            else:
                dev.close()
        except Exception:
            continue
    return found

class Reader:
    def __init__(self, engine):
        self.engine = engine
        self.running = True

    def run(self):
        import selectors
        while self.running:
            devices = find_steam_kbd_devices()
            if not devices:
                log.warning("No Steam keyboard devices found, retrying in 3s...")
                time.sleep(3)
                continue
            sel = selectors.DefaultSelector()
            for dev in devices:
                sel.register(dev, selectors.EVENT_READ)
            log.info(f"Listening on {len(devices)} device(s)")
            try:
                while self.running:
                    for key, _ in sel.select(timeout=1.0):
                        dev = key.fileobj
                        for event in dev.read():
                            if event.type == EV_KEY and event.code in ALL_KEYS:
                                self.engine.handle(event.code, event.value)
            except OSError as ex:
                log.warning(f"Device went away ({ex}); rescanning...")
            finally:
                for dev in devices:
                    try:
                        sel.unregister(dev)
                        dev.ungrab()
                    except Exception:
                        pass
                    try:
                        dev.close()
                    except Exception:
                        pass
            time.sleep(1)

    def stop(self):
        self.running = False

# ─── System tray ─────────────────────────────────────────────────────────────
def make_icon(active):
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    color = (74, 222, 128) if active else (100, 100, 100)
    draw.ellipse([8, 8, 56, 56], fill=color)
    draw.text((20, 18), "KB", fill=(0, 0, 0))
    return img

def run_tray(enabled_flag, stop_event):
    import pystray
    from pystray import MenuItem, Menu

    def toggle(icon, item=None):
        enabled_flag[0] = not enabled_flag[0]
        icon.icon = make_icon(enabled_flag[0])
        icon.title = f"Chorded Keyboard - {'ON' if enabled_flag[0] else 'OFF'}"
        log.info(f"Chorded keyboard {'enabled' if enabled_flag[0] else 'disabled'}")

    def quit_app(icon, item):
        stop_event.set()
        icon.stop()

    icon = pystray.Icon(
        "chorded-keyboard",
        make_icon(enabled_flag[0]),
        f"Chorded Keyboard - {'ON' if enabled_flag[0] else 'OFF'}",
        menu=Menu(
            MenuItem("Toggle On/Off", toggle, default=True),
            MenuItem("Quit", quit_app),
        ),
    )
    icon.run()

# ─── Main ────────────────────────────────────────────────────────────────────
def main():
    enabled_flag = [True]
    stop_event = threading.Event()

    emitter = KeyboardEmitter()
    engine = ChordEngine(emitter, enabled_flag)
    reader = Reader(engine)

    ctrl_thread = threading.Thread(target=reader.run, daemon=True)
    ctrl_thread.start()

    def on_signal(sig, frame):
        log.info("Shutting down...")
        stop_event.set()
        reader.stop()
        emitter.close()
        sys.exit(0)

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)

    # The tray only works in Desktop Mode (it needs an X11/AppIndicator tray).
    # In Gaming Mode there's no tray, so fall back to a headless loop that keeps
    # the reader thread alive and typing. CHORDED_NO_TRAY=1 forces headless.
    no_tray = os.environ.get("CHORDED_NO_TRAY") == "1"
    try:
        if no_tray:
            log.info("CHORDED_NO_TRAY set; running headless (no tray icon)")
            stop_event.wait()
        else:
            run_tray(enabled_flag, stop_event)
    except Exception as ex:
        log.warning(f"Tray unavailable ({ex}); running headless. Typing stays active.")
        stop_event.wait()
    finally:
        reader.stop()
        emitter.close()

if __name__ == "__main__":
    main()
