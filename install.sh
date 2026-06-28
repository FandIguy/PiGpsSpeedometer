#!/bin/bash
#
# Pi GPS Speedometer — installer
# Tested on Raspberry Pi OS (Bookworm, 64-bit Lite) on a Raspberry Pi 5.
#
# Run as your normal user (NOT root):  ./install.sh
#
set -e

USER_NAME="$(id -un)"
USER_UID="$(id -u)"
REPO_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "======================================="
echo " Pi GPS Speedometer Installer"
echo "======================================="
echo " User : $USER_NAME (uid $USER_UID)"
echo " Repo : $REPO_DIR"
echo "======================================="

if [ "$EUID" -eq 0 ]; then
    echo "ERROR: run this as your normal user, not root (no sudo)."
    exit 1
fi

# Copy a template file to a destination, substituting placeholders.
# Usage: install_template <src> <dest> [mode]
install_template() {
    local src="$1" dest="$2" mode="${3:-644}" tmp
    tmp="$(mktemp)"
    sed -e "s|USERNAME|${USER_NAME}|g" \
        -e "s|/run/user/1000|/run/user/${USER_UID}|g" \
        "$src" > "$tmp"
    sudo install -D -m "$mode" "$tmp" "$dest"
    rm -f "$tmp"
    echo "  installed: $dest"
}

echo ""
echo "[1/9] Updating system..."
sudo apt update
sudo apt upgrade -y

echo ""
echo "[2/9] Installing required packages..."
# The app talks to gpsd directly over its JSON socket (import socket),
# so no python-gps / python-serial library is needed.
sudo apt install -y \
    python3-pygame \
    gpsd \
    gpsd-clients \
    fonts-dejavu \
    curl \
    git

echo ""
echo "[3/9] Installing Orbitron font (optional, falls back to DejaVu)..."
mkdir -p "$HOME/.fonts"
if [ ! -f "$HOME/.fonts/Orbitron-Regular.ttf" ]; then
    curl -fsSL \
        "https://github.com/google/fonts/raw/main/ofl/orbitron/static/Orbitron-Regular.ttf" \
        -o "$HOME/.fonts/Orbitron-Regular.ttf" || \
        echo "  (font download failed — app will use DejaVu, no problem)"
fi
fc-cache -f

echo ""
echo "[4/9] Configuring user permissions..."
sudo usermod -aG video,render,input,dialout "$USER_NAME"

echo ""
echo "[5/9] Enabling lingering (creates /run/user/$USER_UID at boot)..."
# Ensures XDG_RUNTIME_DIR exists before the service starts (kmsdrm needs it).
sudo loginctl enable-linger "$USER_NAME"

echo ""
echo "[6/9] Installing the systemd service..."
install_template "$REPO_DIR/speedometer.service" \
    /etc/systemd/system/speedometer.service 644
sudo systemctl daemon-reload
sudo systemctl enable speedometer

echo ""
echo "[7/9] Installing configuration files..."
install_template "$REPO_DIR/config/gpsd" \
    /etc/default/gpsd 644
install_template "$REPO_DIR/config/autologin.conf" \
    /etc/systemd/system/getty@tty1.service.d/autologin.conf 644
install_template "$REPO_DIR/config/20-pi5-kms.conf" \
    /etc/X11/xorg.conf.d/20-pi5-kms.conf 644
install_template "$REPO_DIR/config/Xwrapper.config" \
    /etc/X11/Xwrapper.config 644

# sudoers needs validation + strict perms
SUDO_TMP="$(mktemp)"
sed "s|USERNAME|${USER_NAME}|g" "$REPO_DIR/config/speedometer-sudoers" > "$SUDO_TMP"
if sudo visudo -c -f "$SUDO_TMP" >/dev/null; then
    sudo install -D -m 440 "$SUDO_TMP" /etc/sudoers.d/speedometer
    echo "  installed: /etc/sudoers.d/speedometer"
else
    echo "  ERROR: sudoers failed validation, skipping (Ctrl+M / Ctrl+T may prompt for a password)"
fi
rm -f "$SUDO_TMP"

echo ""
echo "[8/9] Installing the app + helper scripts to \$HOME..."
install -m 755 "$REPO_DIR/speedometer.py" "$HOME/speedometer.py"
for s in launch_minetest.sh launch_terminal.sh minetest_x.sh; do
    if [ -f "$REPO_DIR/scripts/$s" ]; then
        sed "s|USERNAME|${USER_NAME}|g" "$REPO_DIR/scripts/$s" > "$HOME/$s"
        chmod +x "$HOME/$s"
        echo "  installed: $HOME/$s"
    fi
done

echo ""
echo "[9/9] Enabling gpsd..."
sudo systemctl enable gpsd
sudo systemctl restart gpsd

echo ""
echo "======================================="
echo " Installation complete."
echo "======================================="
echo ""
echo "Enable console autologin on tty1 (required for the display):"
echo "  sudo raspi-config -> System Options -> Boot / Auto Login"
echo "                    -> Console Autologin"
echo "Confirm after reboot that 'who' shows '$USER_NAME tty1'."
echo ""
echo "Then reboot:"
echo "  sudo reboot"
echo ""
echo "After reboot, verify GPS (needs sky view; first fix can take minutes):"
echo "  gpspipe -w -n 5      # look for \"mode\":3"
echo "  cgps                 # live view (terminal must be >= 80 cols)"
echo ""
echo "Check the cluster:"
echo "  systemctl status speedometer"
echo "  journalctl -u speedometer -n 30 --no-pager"
echo ""
