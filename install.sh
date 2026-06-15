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
echo "[1/5] Creating install directory..."
mkdir -p "$INSTALL_DIR"
mkdir -p "$SERVICE_DIR"

# 2. Copy script
echo "[2/5] Copying script..."
cp chorded_keyboard.py "$INSTALL_DIR/chorded_keyboard.py"
chmod +x "$INSTALL_DIR/chorded_keyboard.py"

# 3. Create venv and install dependencies
echo "[3/5] Setting up Python venv and installing dependencies..."
# Remove broken venv if it exists
rm -rf "$VENV_DIR"
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --upgrade pip --quiet
"$VENV_DIR/bin/pip" install evdev-binary pystray Pillow --quiet
echo "    Dependencies installed."

# 4. Capture display environment for systemd
echo "[4/6] Capturing display environment..."
mkdir -p "$HOME/.config"
echo "DISPLAY=${DISPLAY:-:0}" > "$HOME/.config/chorded-keyboard-env"
echo "DBUS_SESSION_BUS_ADDRESS=${DBUS_SESSION_BUS_ADDRESS}" >> "$HOME/.config/chorded-keyboard-env"
echo "XAUTHORITY=${XAUTHORITY:-$HOME/.Xauthority}" >> "$HOME/.config/chorded-keyboard-env"

# 5. Write systemd user service
echo "[5/6] Writing systemd service..."
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

# 6. Enable and start service
echo "[6/6] Enabling and starting service..."
systemctl --user daemon-reload
systemctl --user enable chorded-keyboard.service
systemctl --user start chorded-keyboard.service

echo ""
echo "=== Done! ==="
echo ""
echo "The chorded keyboard is now running."
echo "A tray icon should appear in your system tray."
echo "Left-click or select 'Toggle On/Off' to enable/disable."
echo ""
echo "Useful commands:"
echo "  Check status:  systemctl --user status chorded-keyboard"
echo "  View logs:     journalctl --user -u chorded-keyboard -f"
echo "  Stop:          systemctl --user stop chorded-keyboard"
echo "  Disable auto:  systemctl --user disable chorded-keyboard"
