# Steam Deck Chorded Keyboard

A chorded-keyboard daemon for the Steam Deck. You type by holding a **grip**
(one of the four back paddles, or a left/right pair) and **tapping a face
button** (A / B / X / Y). The dpad selects a layer (shift, numbers, symbols).
With a little practice you can type real text without a touchscreen keyboard.

## How it works

The Steam Deck doesn't let normal apps read its buttons directly, so this
project rides on top of Steam Input:

1. A **Steam Input desktop configuration** maps the physical controls (back
   paddles, dpad, ABXY) to **numpad keys**. Steam emits those keys through its
   own virtual keyboard device.
2. The daemon **exclusively grabs** that virtual keyboard device, so the raw
   numpad presses never leak into your apps.
3. It runs the **chord logic** and emits the resulting real characters through
   a `uinput` virtual keyboard.

Touchpads, triggers, and sticks keep their normal Steam behavior — the daemon
never touches the gamepad device.

## Prerequisite: Steam Input mapping

This is the key manual step. In Steam (Desktop Mode), create a desktop
controller configuration that maps the controls to these numpad keys:

| Physical control | Numpad key |
| ---------------- | ---------- |
| L4 grip          | Keypad 1   |
| L5 grip          | Keypad 2   |
| R4 grip          | Keypad 3   |
| R5 grip          | Keypad 4   |
| Dpad Up          | Keypad 5   |
| Dpad Down        | Keypad 6   |
| Dpad Left        | Keypad 7   |
| Dpad Right       | Keypad 8   |
| A                | Keypad 9   |
| B                | Keypad 0   |
| X                | Keypad .   |
| Y                | Keypad +   |

The daemon won't see any input until this mapping is in place.

## Install

From the directory containing the scripts:

```bash
./install.sh
```

The installer sets up a Python venv, installs a systemd **user** service, and
configures device permissions. It needs **sudo** (for the `input` group, the
`uinput` module, and a udev rule) and, on SteamOS, temporarily disables the
read-only rootfs.

After installing, **log out and back in (or reboot)** so your new `input`
group membership takes effect. If a SteamOS update later breaks the keyboard,
just re-run `./install.sh` — system updates can revert the `/etc` changes.

## Using it

- **Grips** choose the row:
  - `L1` = hold L4 · `L2` = hold L5 · `L1+L2` = hold both left paddles
  - `R1` = hold R4 · `R2` = hold R5 · `R1+R2` = hold both right paddles
- **Face buttons** choose the column: `A`, `B`, `X`, `Y`, plus the combos
  `A+B` (press A and B together) and `X+Y`.
- **Dpad** chooses the layer: nothing = base, **Down** = shift, **Left** =
  numbers, **Right** = symbols. (Dpad **Up** is currently unused.)
- Rolling works: hold a grip, then tap A, tap B → emits `a`-row then `b`-row
  letters. Press A and B together and release → emits the `A+B` chord.

A chord fires on the **first face-button release**.

### Base layer (lowercase)

| Grip   | A | B | Y | X | A+B  | X+Y  |
| ------ | - | - | - | - | ---- | ---- |
| L1     | e | t | r | h | er   | q    |
| L2     | a | n | d | ␣ | BKSP | ENT  |
| L1+L2  | i | x | o | g | ,    | .    |
| R1     | s | c | f | w | '    | -    |
| R2     | l | u | p | b | !    | ?    |
| R1+R2  | m | y | k | v | j    | z    |

### Shift layer (Dpad Down — uppercase)

| Grip   | A | B | Y | X | A+B  | X+Y  |
| ------ | - | - | - | - | ---- | ---- |
| L1     | E | T | R | H | —    | Q    |
| L2     | A | N | D | ␣ | BKSP | ENT  |
| L1+L2  | I | X | O | G | ;    | :    |
| R1     | S | C | F | W | "    | —    |
| R2     | L | U | P | B | (    | )    |
| R1+R2  | M | Y | K | V | J    | Z    |

### Numbers layer (Dpad Left)

| Grip   | A | B | Y | X | A+B | X+Y |
| ------ | - | - | - | - | --- | --- |
| L1     | 1 | 2 | 3 | 4 | —   | —   |
| L2     | 5 | 6 | 7 | 8 | —   | —   |
| L1+L2  | 9 | 0 | . | , | —   | —   |
| R1     | + | - | * | / | =   | —   |
| R2     | % | ^ | < | > | —   | —   |
| R1+R2  | ( | ) | [ | ] | {   | }   |

### Symbols layer (Dpad Right)

| Grip   | A | B | Y | X  | A+B | X+Y |
| ------ | - | - | - | -- | --- | --- |
| L1     | ! | @ | # | $  | —   | —   |
| L2     | % | ^ | & | *  | —   | —   |
| L1+L2  | ~ | ` | \ | \| | —   | —   |
| R1     | _ | = | + | —  | —   | —   |
| R2     | [ | ] | { | }  | —   | —   |
| R1+R2  | < | > | / | ?  | ;   | :   |

## Desktop vs Gaming Mode

The toggle **tray icon only appears in Desktop Mode** (it needs an X11/
AppIndicator tray). The daemon still types in **Gaming Mode** — it runs
headless there. You can force headless mode with `CHORDED_NO_TRAY=1`.

## Troubleshooting

```bash
systemctl --user status chorded-keyboard      # is it running?
journalctl --user -u chorded-keyboard -f       # live logs
```

The daemon also writes to `~/.local/share/chorded-keyboard/chorded.log`.

- **Nothing types:** confirm the Steam Input numpad mapping is active, and that
  you logged out/in after install (for `input` group membership).
- **Wrong symbols:** the character map assumes a **US-QWERTY** layout. Non-US
  layouts will produce different shifted symbols.
