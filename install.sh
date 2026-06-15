#!/bin/bash
# Chorded Keyboard Installer for SteamOS
# Run this from the directory containing chorded_keyboard.py

set -e

INSTALL_DIR="$HOME/.local/share/chorded-keyboard"
VENV_DIR="$INSTALL_DIR/venv"
SERVICE_DIR="$HOME/.config/systemd/user"
SERVICE_FILE="$SERVICE_DIR/chorded-keyboard.service"

echo "=== Chorded Keyboard Installer ==="
echo ""

# 1. Create install directory
echo "[1/7] Creating install directory..."
mkdir -p "$INSTALL_DIR"
mkdir -p "$SERVICE_DIR"

# 2. Copy script
echo "[2/7] Copying script..."
cp chorded_keyboard.py "$INSTALL_DIR/chorded_keyboard.py"
chmod +x "$INSTALL_DIR/chorded_keyboard.py"

# 3. Create venv and install dependencies
echo "[3/7] Setting up Python venv and installing dependencies..."
# Remove broken venv if it exists
rm -rf "$VENV_DIR"
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --upgrade pip --quiet
"$VENV_DIR/bin/pip" install evdev-binary pystray Pillow --quiet
echo "    Dependencies installed."

# 4. Set up device permissions (needs sudo)
# The daemon runs as your unprivileged user but must open /dev/uinput and grab
# /dev/input/event* devices. That requires membership in the 'input' group plus
# a udev rule giving the group access to uinput. SteamOS has a read-only rootfs,
# so we toggle it off around the /etc writes and back on afterward.
echo "[4/7] Setting up device permissions (you may be prompted for your sudo password)..."
HAVE_STEAMOS_RO=0
if command -v steamos-readonly >/dev/null 2>&1; then
    HAVE_STEAMOS_RO=1
    sudo steamos-readonly disable
fi

# Add the current user to the 'input' group (no-op if already a member).
sudo usermod -aG input "$USER"

# Ensure the uinput module is loaded now and on every boot.
sudo modprobe uinput || true
echo "uinput" | sudo tee /etc/modules-load.d/uinput.conf >/dev/null

# udev rule: give the 'input' group read/write access to /dev/uinput.
echo 'KERNEL=="uinput", GROUP="input", MODE="0660", OPTIONS+="static_node=uinput"' \
    | sudo tee /etc/udev/rules.d/99-uinput.rules >/dev/null
sudo udevadm control --reload-rules
sudo udevadm trigger

if [ "$HAVE_STEAMOS_RO" -eq 1 ]; then
    sudo steamos-readonly enable
fi
echo "    Permissions configured."

# 5. Capture display environment for systemd
echo "[5/7] Capturing display environment..."
mkdir -p "$HOME/.config"
echo "DISPLAY=${DISPLAY:-:0}" > "$HOME/.config/chorded-keyboard-env"
echo "DBUS_SESSION_BUS_ADDRESS=${DBUS_SESSION_BUS_ADDRESS}" >> "$HOME/.config/chorded-keyboard-env"
echo "XAUTHORITY=${XAUTHORITY:-$HOME/.Xauthority}" >> "$HOME/.config/chorded-keyboard-env"

# 6. Write systemd user service
echo "[6/7] Writing systemd service..."
cat > "$SERVICE_FILE" << EOF
[Unit]
Description=Chorded Keyboard Daemon
After=graphical-session.target
PartOf=graphical-session.target

[Service]
Type=simple
ExecStart=$VENV_DIR/bin/python $INSTALL_DIR/chorded_keyboard.py
Restart=on-failure
RestartSec=3
Environment=DISPLAY=:0
EnvironmentFile=-%h/.config/chorded-keyboard-env

[Install]
WantedBy=graphical-session.target
EOF

# 7. Enable and start service
echo "[7/7] Enabling and starting service..."
systemctl --user daemon-reload
systemctl --user enable chorded-keyboard.service
systemctl --user start chorded-keyboard.service

echo ""
echo "=== Done! ==="
echo ""
echo "The chorded keyboard is now running."
echo "A tray icon should appear in your system tray (Desktop Mode only)."
echo "Left-click or select 'Toggle On/Off' to enable/disable."
echo ""
echo "IMPORTANT:"
echo "  - 'input' group membership only takes effect after you log out and back"
echo "    in (or reboot). If typing doesn't work yet, reboot and try again."
echo "  - A SteamOS system update may revert the /etc changes above. If the"
echo "    keyboard stops working after an update, just re-run this installer."
echo ""
echo "Useful commands:"
echo "  Check status:  systemctl --user status chorded-keyboard"
echo "  View logs:     journalctl --user -u chorded-keyboard -f"
echo "  Stop:          systemctl --user stop chorded-keyboard"
echo "  Disable auto:  systemctl --user disable chorded-keyboard"
