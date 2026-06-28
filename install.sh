```bash
#!/bin/bash

set -e

echo "======================================="
echo " Pi GPS Speedometer Installer"
echo "======================================="

if [ "$EUID" -eq 0 ]; then
    echo "Please run this script as your normal user."
    exit 1
fi

echo ""
echo "[1/8] Updating system..."
sudo apt update
sudo apt upgrade -y

echo ""
echo "[2/8] Installing required packages..."

sudo apt install -y \
python3-pygame \
python3-gps \
python3-serial \
python3-pip \
gpsd \
gpsd-clients \
fonts-dejavu \
curl \
git

echo ""
echo "[3/8] Installing Orbitron font..."

mkdir -p ~/.fonts

if [ ! -f ~/.fonts/Orbitron-Regular.ttf ]; then
    curl -L \
https://github.com/google/fonts/raw/main/ofl/orbitron/Orbitron-Regular.ttf \
-o ~/.fonts/Orbitron-Regular.ttf
fi

fc-cache -fv

echo ""
echo "[4/8] Configuring permissions..."

sudo usermod -aG video,input,gpio,dialout "$USER"

echo ""
echo "[5/8] Installing systemd service..."

sudo cp speedometer.service /etc/systemd/system/

sudo systemctl daemon-reload
sudo systemctl enable speedometer

echo ""
echo "[6/8] Copying configuration files..."

if [ -d config ]; then
    sudo cp -r config/* /
fi

echo ""
echo "[7/8] Verifying GPSD..."

sudo systemctl enable gpsd
sudo systemctl restart gpsd

echo ""
echo "[8/8] Installation Complete!"

echo ""
echo "======================================="
echo "Next Steps"
echo "======================================="
echo ""
echo "1. Enable UART using raspi-config"
echo "2. Disable Serial Console"
echo "3. Reboot"
echo ""
echo "sudo reboot"
echo ""
echo "After reboot verify GPS:"
echo ""
echo "cgps -s"
echo ""
echo "Start the application:"
echo ""
echo "sudo systemctl start speedometer"
echo ""
echo "Done!"
```
