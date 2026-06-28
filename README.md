<<<<<<< HEAD
# Stealth R/T GPS Cluster

A fullscreen amber VFD-style GPS speedometer kiosk built for a **1991 Dodge Stealth R/T**, running on a Raspberry Pi 5. Renders directly to the framebuffer via SDL2 kmsdrm — no desktop environment, no compositor, boots straight into the cluster display.

> Bonus: press **Ctrl+M** to launch Minetest, **Ctrl+T** for a terminal. Press Esc in Minetest to return to the cluster automatically.

---

## Features

- Analog sunrise-arc speedometer with segmented LED bar
- Speed in MPH with configurable smoothing
- Compass heading (16-point cardinal with degree readout)
- Altitude in feet and vertical speed (ft/min)
- GPS quality indicators: satellite count, HDOP, fix type (2D/3D), signal bars
- Local clock (US Central, 12-hour, blinking colon) + UTC date
- Trip odometer and elapsed session timer
- **0–60 MPH timer** with persistent top-5 leaderboard (power-loss safe atomic writes)
- Speed limit display + street name from OpenStreetMap data (optional)
- City name lookup (optional)
- VFD-style amber color palette with CRT scanline overlay
- Animated boot splash sequence
- **Simulation mode** — runs with no GPS connected; arrow keys adjust simulated speed
- Hotkey launcher: **Ctrl+M** → Minetest, **Ctrl+T** → bash terminal

---

## Hardware

| Component | Detail | Notes |
|-----------|--------|-------|
| SBC | Raspberry Pi 5 8GB | Pi 4 also works — see Pi 4 notes |
| Display | GeeekPi 7" 1024×600 HDMI | Connected to HDMI1 port |
| GPS | GlobalSat BU-353N5 | USB dongle, Prolific PL2303 chip → `/dev/ttyUSB0` |
| Input | 2.4GHz wireless USB keyboard | Any standard USB HID keyboard |
| Power | 12V cigarette → USB-C buck converter | One for Pi, one for screen |
| Vehicle | 1991 Dodge Stealth R/T | Any car will do |

**Pi 4 users:** Remove the `SDL_KMSDRM_DEVICE_INDEX=1` line from `speedometer.service` and skip the `20-pi5-kms.conf` step — Pi 4 uses a single DRM device index.

---

## Software Dependencies

### System packages

```bash
sudo apt update
sudo apt install -y \
    gpsd gpsd-clients \
    python3-pygame \
    xinit \
    xserver-xorg-core \
    xserver-xorg-input-libinput \
    matchbox-window-manager \
    minetest \
    git
```

### Python packages

`pygame` is the only external Python dependency. If `python3-pygame` from apt is outdated:

```bash
pip3 install pygame --break-system-packages
```

### Optional: tzdata (for local time zone)

```bash
sudo apt install -y python3-tzdata
```

Without this, the clock falls back to UTC display.

---

## Installation Guide

### Step 1 — Flash Raspberry Pi OS

Use **Raspberry Pi Imager** to flash **Raspberry Pi OS Lite (64-bit)** to your SD card. In the imager's settings:

- Set hostname: `stealth` (or whatever you prefer)
- Enable SSH
- Set username: `stealth` (see note below)
- Set your WiFi credentials if needed

> **Username note:** The service and launch scripts use `/home/stealth/` paths. If you choose a different username, edit lines 821 and 829 of `speedometer.py` to match, or use the portable version that auto-detects its own path (recommended — see Customization).

### Step 2 — Initial system setup

SSH into the Pi and run:

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y gpsd gpsd-clients python3-pygame xinit \
    xserver-xorg-core xserver-xorg-input-libinput \
    matchbox-window-manager minetest git
```

Add your user to the required groups:

```bash
sudo usermod -aG video,render,input stealth
```

Log out and back in (or reboot) for group changes to take effect.

### Step 3 — Clone the repo

```bash
cd /home/stealth
git clone https://github.com/YOUR_USERNAME/stealth-rt-gps-cluster.git temp-cluster
cp temp-cluster/speedometer.py .
cp temp-cluster/speedometer.service .
cp temp-cluster/scripts/launch_minetest.sh .
cp temp-cluster/scripts/launch_terminal.sh .
cp temp-cluster/scripts/minetest_x.sh .
chmod +x launch_minetest.sh launch_terminal.sh minetest_x.sh
rm -rf temp-cluster
```

### Step 4 — Install the Orbitron font

The cluster uses the Orbitron typeface (free, Google Fonts). Download and install it:

```bash
mkdir -p ~/.fonts
cd ~/.fonts
curl -L "https://github.com/google/fonts/raw/main/ofl/orbitron/Orbitron%5Bwght%5D.ttf" \
     -o Orbitron.ttf
fc-cache -fv
```

If `curl` fails or you'd rather do it manually:
1. Go to fonts.google.com and search "Orbitron"
2. Download the font zip, extract `Orbitron[wght].ttf`
3. Copy it to `~/.fonts/` and run `fc-cache -fv`

The cluster falls back to DejaVu Sans Mono → Liberation Mono → system monospace if Orbitron isn't found.

### Step 5 — Configure GPS

Edit `/etc/default/gpsd`:

```bash
sudo nano /etc/default/gpsd
```

Replace the contents with (or copy from `config/gpsd`):

```ini
DEVICES="/dev/ttyUSB0"
GPSD_OPTIONS="-n -b"
START_DAEMON="true"
USBAUTO="true"
```

Enable and start gpsd:

```bash
sudo systemctl enable gpsd
sudo systemctl start gpsd
```

Confirm the GPS is talking:

```bash
cgps -s
# or
gpsmon
```

You should see satellite data within about 60 seconds outdoors (cold start). The `-n` flag makes gpsd poll before any client connects, so a fix is ready the moment the cluster starts.

### Step 6 — Configure tty1 autologin (required for kmsdrm)

The cluster needs a real login session on tty1 to acquire DRM master. Without this you get a silent black screen.

```bash
sudo mkdir -p /etc/systemd/system/getty@tty1.service.d
sudo nano /etc/systemd/system/getty@tty1.service.d/autologin.conf
```

Paste (or copy from `config/autologin.conf`):

```ini
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin stealth --noclear %I $TERM
```

### Step 7 — Pi 5 display configuration (skip for Pi 4)

The Pi 5 splits DRM across two devices: `card0` is the V3D GPU (no displays), `card1` is the RP1 display controller (HDMI). SDL defaults to index 0 and finds no displays, silently falling back to the `dummy` driver — you'd get a running process with a black screen.

Fix 1: force SDL to card1 (done in the service file already).

Fix 2: force X to card1 for Minetest:

```bash
sudo mkdir -p /etc/X11/xorg.conf.d
sudo cp config/20-pi5-kms.conf /etc/X11/xorg.conf.d/
```

Contents of `config/20-pi5-kms.conf`:

```
Section "Device"
    Identifier "Pi5 RP1 Display"
    Driver     "modesetting"
    Option     "kmsdev" "/dev/dri/card1"
EndSection
```

### Step 8 — X server permissions (required for Minetest hotkey)

The speedometer service has no console stdin (`StandardInput=` is not set, defaulting to `/dev/null`). Xorg's default `allowed_users=console` check fails for this process. Fix:

```bash
sudo cp config/Xwrapper.config /etc/X11/Xwrapper.config
```

Or manually set `/etc/X11/Xwrapper.config` to:

```
allowed_users=anybody
```

### Step 9 — Sudoers entry (for VT switching)

The launch scripts need to switch virtual terminals and open VTs without a password prompt:

```bash
sudo cp config/speedometer-sudoers /etc/sudoers.d/speedometer
sudo chmod 440 /etc/sudoers.d/speedometer
```

Verify it's correct before applying:

```bash
sudo visudo -c -f config/speedometer-sudoers
```

### Step 10 — Install the systemd service

```bash
sudo cp speedometer.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable speedometer
sudo systemctl start speedometer
```

Check it's running:

```bash
sudo systemctl status speedometer
sudo journalctl -u speedometer -f
```

Look for the line:

```
[display] using SDL video driver: kmsdrm
```

If you see `dummy` instead, the DRM session setup failed — see Troubleshooting.

### Step 11 — Minetest configuration (optional)

```bash
mkdir -p ~/.minetest
nano ~/.minetest/minetest.conf
```

```ini
screenW = 1024
screenH = 600
fullscreen = true
vsync = true
fps_max = 30
viewing_range = 50
smooth_lighting = false
```

---

## Hotkeys

| Key | Action |
|-----|--------|
| `Esc` | Quit the cluster (for testing; service auto-restarts) |
| `Arrow Up` | Increase simulated speed by 5 mph (sim mode only) |
| `Arrow Down` | Decrease simulated speed by 5 mph (sim mode only) |
| `R` | Arm leaderboard reset (LED flashes prompt) |
| `R` (again within 3s) | Confirm leaderboard clear |
| `Ctrl+M` | Exit cluster → launch Minetest |
| `Ctrl+T` | Exit cluster → open bash terminal on tty2 |

**Returning from Minetest:** Press `Esc` inside the game → `Exit to OS`. The cluster restarts automatically within 2 seconds via systemd.

**Returning from terminal:** Type `exit` at the shell prompt. The cluster restarts automatically.

---

## Simulation Mode

The cluster enters simulation mode automatically if gpsd is unreachable or not installed. No code changes needed — it just works.

In sim mode:
- `Arrow Up` / `Arrow Down` adjusts speed in 5 mph increments
- Heading drifts realistically based on speed
- Altitude oscillates around a fixed value
- The display shows `SIM MODE` instead of `3D FIX`

This lets you test the full UI, 0-60 timer, and all features on a laptop or desktop with no GPS hardware.

To run in simulation on a desktop with X:

```bash
python3 speedometer.py
```

---

## Troubleshooting

### Black screen / process runs but nothing on display

1. Check what driver SDL used:
   ```bash
   journalctl -u speedometer -n 50 | grep "video driver"
   ```
   Must show `kmsdrm`. If it shows `dummy`, kmsdrm failed.

2. Verify the logind session exists:
   ```bash
   loginctl list-sessions
   ```
   Must show `Seat=seat0`, `TTY=tty1`, `Active=yes`.

3. Check the autologin config is in place:
   ```bash
   cat /etc/systemd/system/getty@tty1.service.d/autologin.conf
   ```

4. Pi 5: confirm `SDL_KMSDRM_DEVICE_INDEX=1` is in the service file.

### GPS not connecting

```bash
systemctl status gpsd
gpsd -N -D3 /dev/ttyUSB0   # test manually
ls /dev/ttyUSB*             # confirm device enumerated
```

The BU-353N5 shows up as `/dev/ttyUSB0` via the Prolific PL2303 driver. If absent, check `dmesg | grep PL2303`.

### Keyboard not working in Minetest

This was the trickiest part of the build. Three things must all be in place:

1. `matchbox-window-manager` installed — without a WM, X uses pointer focus and Minetest's window starts without keyboard focus.
2. `/etc/X11/Xwrapper.config` contains `allowed_users=anybody` — without this, `xinit` fails entirely when called from the service (no console stdin).
3. `20-pi5-kms.conf` pointing X at `card1` — without this, X finds no display connectors on `card0`.

### Pageflip error -13 (EACCES)

This is expected when running `python3 speedometer.py` directly over a plain SSH session. SSH has no logind seat and can't acquire DRM master. Test via the service or with:

```bash
sudo openvt -c 1 -s -- sudo -u stealth env SDL_VIDEODRIVER=kmsdrm SDL_KMSDRM_DEVICE_INDEX=1 python3 /home/stealth/speedometer.py
```

---

## Optional: Speed Limit + City Name

The cluster can display the posted speed limit and current city/street name using pre-built OpenStreetMap indexes. These data files are large (~150MB total) and not included in this repo.

If the `osm/` directory is absent, the cluster runs perfectly — speed limit and city panels just show `--`. Everything else works normally.

To build the OSM indexes: [documentation TBD — the build pipeline processes OSM PBF extracts into spatial indexes for fast lat/lon lookups].

---

## Customization

All display constants are at the top of `speedometer.py` (~line 44):

```python
WIDTH, HEIGHT = 1024, 600    # change for your display
FPS = 30                     # render rate
MAX_SPEED = 120              # top of the analog gauge (mph)
FULLSCREEN = True

LEADERBOARD_SIZE = 5         # top-N 0-60 times to keep

# Color palette — all RGB tuples
AMBER     = (255, 128, 22)   # primary display color
AMBER_HI  = (255, 178, 50)   # highlights
RED       = (255, 70, 25)    # alerts and overspeed
```

**Portable launch script paths:** If you change the username from `stealth`, update the `os.execvp` calls in `main()` around lines 821 and 829, or replace the hardcoded paths with:

```python
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.execvp(os.path.join(_SCRIPT_DIR, 'launch_minetest.sh'),
          [os.path.join(_SCRIPT_DIR, 'launch_minetest.sh')])
```

---

## Service Management

```bash
# View live logs
sudo journalctl -u speedometer -f

# Restart after editing speedometer.py
sudo systemctl restart speedometer

# After editing speedometer.service
sudo systemctl daemon-reload && sudo systemctl restart speedometer

# Syntax-check before deploying
python3 -m py_compile speedometer.py
```

---

## License

MIT License — do whatever you want with it. If you build one for your car, post a photo.
=======
# PiGpsSpeedometer
Raspberry Pi GPS Speedometer/Carputer. Use a Raspberry Pi as a speedometer for a classic car or if you are looking for a Cyberdeck type build you can install and run in your own car! 
>>>>>>> da6adb71272172c710c864b5ec8d7d964e45c728
