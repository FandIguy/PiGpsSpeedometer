# Pi GPS Speedometer

A full-screen GPS digital instrument cluster for the **Raspberry Pi 5**, built to
run headless in a car — it boots straight to the gauge display with no desktop with the option to switch to terminal or play Minetest(Minecraft) when you are parked! 

![Dashboard](docs/images/dashboard.jpg)

![Raspberry Pi 5](https://img.shields.io/badge/Raspberry%20Pi-5-C51A4A)
![Python](https://img.shields.io/badge/Python-3.11%2B-blue)
![Bookworm](https://img.shields.io/badge/Tested%20on-Bookworm-success)
![GPSD](https://img.shields.io/badge/GPSD-Compatible-green)
![License](https://img.shields.io/badge/License-MIT-lightgrey)

---

## Features

- Full-screen digital speedometer (factory-orange VFD aesthetic)
- analog gauge layout — speed and 0–60 timer
- Real-time GPS speed, heading, altitude, and fix quality
- 0–60 mph timer with a persistent top-5 leaderboard
- Offline speed limit display (OpenStreetMap `maxspeed` data)
- City and street / highway name from GPS coordinates
- 12-hour clock (US Central, DST-aware via zoneinfo)
- GPS signal-strength bars
- Boots directly to the cluster on power-up (systemd)
- Simulation mode when no GPS is connected (no code changes needed)
- Optional Ctrl+M (Minetest) and Ctrl+T (terminal) launch hotkeys

---

## Hardware

| Part | Notes |
|------|-------|
| Raspberry Pi 5 (8 GB) | Pi 4 also works — see compatibility note below |
| GlobalSat BU-353N5 USB GPS | Enumerates as `/dev/ttyUSB0` (Prolific serial) |
| 7" 1024×600 HDMI IPS display | Driver-free over HDMI |
| Power | 5V to the Pi; the display has its own 5V feed |

> This build uses a **USB** GPS receiver read through gpsd. There is **no UART
> wiring** and no serial-console setup required.

---

## Quick Install

```bash
git clone https://github.com/FandIguy/PiGpsSpeedometer.git
cd PiGpsSpeedometer
chmod +x install.sh
./install.sh
```

The script installs packages, the font, the systemd service, all config files
(with your username substituted automatically), and the app. When it finishes:

1. Enable console autologin (required — see below):
   `sudo raspi-config` → **System Options** → **Boot / Auto Login** → **Console Autologin**
2. Reboot: `sudo reboot`

After reboot the cluster appears on the display automatically.

---

## What the installer configures (and why)

These are the non-obvious pieces that make a headless KMSDRM app work on a Pi 5.
The installer handles all of them; this section explains them for the curious
and for troubleshooting.

### Display: forcing the correct DRM card (Pi 5)

The Pi 5 exposes **two** DRM devices:

- `card0` = the V3D GPU — render only, **no display connectors**
- `card1` = the RP1 display controller — this is where HDMI lives

SDL's KMSDRM backend defaults to device index 0, opens `card0`, finds no
displays, and **silently falls back to the dummy driver** (black screen, no
error). The service sets `SDL_KMSDRM_DEVICE_INDEX=1` to target the right card.
**On a Pi 4 there is only one DRM device — remove that line** (see compatibility).

### Display ownership: autologin + logind session

KMSDRM has to become **DRM master**, which requires a real **logind session** on
the console. The service uses `PAMName=login` + `TTYPath=/dev/tty1`, and the
installed `autologin.conf` auto-logs-in your user on tty1 at boot so that session
exists. Without it: a silent black screen on cold boot (no crash, no error).

### Runtime directory

KMSDRM also needs `XDG_RUNTIME_DIR` (`/run/user/<uid>`). The installer enables
**lingering** (`loginctl enable-linger`) so that directory exists at boot before
the service starts, and the service sets the variable explicitly.

### GPS

The GPS is USB. The installer writes `/etc/default/gpsd` pointing at
`/dev/ttyUSB0` with `-n` (poll without a client connected) so a fix is ready as
soon as the cluster starts. The app reads gpsd's JSON socket directly — no
`python-gps` or `python-serial` library involved.

Verify a fix after reboot (needs a clear view of the sky; a cold start can take
a few minutes):

```bash
gpspipe -w -n 5      # raw JSON — look for "mode":3 and a lat/lon
cgps                 # live view (terminal must be >= 80 columns wide)
```

---

## Controls

| Key | Action |
|-----|--------|
| `ESC` | Quit |
| `UP` / `DOWN` | Adjust speed in simulation mode |
| `R` | Reset the 0–60 leaderboard (double-press to confirm) |
| `Ctrl + M` | Launch Minetest (requires optional setup — see below) |
| `Ctrl + T` | Drop to a terminal on tty2 (type `exit` to return) |

---

## Optional: Offline Speed Limit and Location Data

The speedometer can display the **posted speed limit** for the road you are on
and the **city and street name** — all offline with no internet connection needed
while driving. This uses OpenStreetMap data downloaded once to the Pi.

### Where the data comes from

[Geofabrik](https://download.geofabrik.de) provides free daily extracts of
OpenStreetMap data, pre-cut by region. No account is required.

### Download data for your state

Navigate to:

```
https://download.geofabrik.de/north-america/us/
```

Find your state and download the `.osm.pbf` file. Example for Minnesota:

```bash
mkdir -p ~/osm && cd ~/osm
wget https://download.geofabrik.de/north-america/us/minnesota-latest.osm.pbf
```

For multiple states (for example a border commute):

```bash
wget https://download.geofabrik.de/north-america/us/minnesota-latest.osm.pbf
wget https://download.geofabrik.de/north-america/us/wisconsin-latest.osm.pbf
```

For the entire US (large — several GB):

```bash
wget https://download.geofabrik.de/north-america/us-latest.osm.pbf
```

### Process the data

Install the required tools:

```bash
sudo apt install -y osmium-tool
pip install shapely rtree --break-system-packages
sudo apt install -y libspatialindex-dev   # install this first if rtree fails
```

Filter to roads with speed limits and export to GeoJSON:

```bash
cd ~/osm

# Single state
osmium tags-filter minnesota-latest.osm.pbf w/highway w/maxspeed -o mn-roads.osm.pbf
osmium export mn-roads.osm.pbf -o maxspeed-roads.geojson

# Multiple states — filter each then merge
osmium tags-filter minnesota-latest.osm.pbf w/highway w/maxspeed -o mn-roads.osm.pbf
osmium tags-filter wisconsin-latest.osm.pbf w/highway w/maxspeed -o wi-roads.osm.pbf
osmium merge mn-roads.osm.pbf wi-roads.osm.pbf -o roads.osm.pbf
osmium export roads.osm.pbf -o maxspeed-roads.geojson
```

Build the fast lookup index (one-time, takes a few minutes):

```bash
cd ~/osm
python3 speed_limit.py --build
```

This creates cached index files (`speedlimit_idx.*`, `speedlimit_segs.pkl`) so
the cluster loads the data in under a second on every boot instead of rebuilding
from scratch each time.

Test it with a known coordinate:

```bash
python3 speed_limit.py <lat> <lon>
```

A match distance under ~10 m means a confident result. You should see the speed
limit, road name, and match distance for that point.

### Storage requirements

| Coverage | Raw extract | Processed index |
|----------|-------------|-----------------|
| One state (e.g. Minnesota) | ~300 MB | ~130 MB |
| Two states | ~600 MB | ~200 MB |
| Full US | ~8 GB | ~2–3 GB |

A 32 GB SD card has plenty of room for one or two states alongside the OS and
the application.

### Check coverage before downloading

Before processing a large download, confirm your roads are tagged with speed
limits in OSM. Go to [openstreetmap.org](https://www.openstreetmap.org), click
on a road you drive regularly, and look for a `maxspeed` tag in the details
panel. Highways and main roads are almost always tagged. Residential streets vary
by area.

If a road you drive is not tagged, you can add the data yourself — OSM is
community-edited and contributions are welcome at
[openstreetmap.org](https://www.openstreetmap.org).

---

## Raspberry Pi Compatibility

**Pi 5:** uses `card1` + KMSDRM with `SDL_KMSDRM_DEVICE_INDEX=1` (default in the
service file).

**Pi 4:** exposes a single DRM device, so SDL selects it automatically. Remove
this line from `/etc/systemd/system/speedometer.service`:

```
Environment=SDL_KMSDRM_DEVICE_INDEX=1
```

Then reload and restart:

```bash
sudo systemctl daemon-reload
sudo systemctl restart speedometer
```

---

## Simulation Mode

If no GPS receiver is connected (or gpsd has no fix), the app runs in simulation
mode automatically — useful for bench testing the UI. Use `UP` / `DOWN` to drive
the simulated speed. No code changes are required.

---

## Service Management

```bash
sudo systemctl status speedometer      # is it running?
sudo systemctl restart speedometer     # restart after editing speedometer.py
sudo journalctl -u speedometer -f      # live logs and errors
```

---

## Troubleshooting

**Black screen, no error.** Almost always the display-ownership chain. Check in
order:

1. `who` shows `<your-user> tty1` — autologin is working
2. User is in the `video` and `render` groups — run `groups`
3. `/run/user/<uid>` exists — lingering is enabled
4. Service has `SDL_KMSDRM_DEVICE_INDEX=1` on a Pi 5

The logs will often show the driver falling back to `dummy` — that is this
problem.

```bash
journalctl -u speedometer -n 30 --no-pager | grep -i "driver\|dummy\|error"
```

**`drmModePageFlip failed (-13)` (EACCES).** The process is not DRM master. This
happens when you run the script directly over SSH — an SSH session has no console
seat. Always test via the service, or use `openvt` on tty1, not SSH.

**GPS never locks.** Confirm a clear view of the sky, that `/dev/ttyUSB0` exists,
and that gpsd is running:

```bash
ls -l /dev/ttyUSB*
sudo systemctl status gpsd
gpspipe -w -n 5
```

A cold start on the BU-353N5 can take several minutes outdoors.

**Permission denied on DRM or input devices.** Make sure your user is in the
required groups, then reboot:

```bash
sudo usermod -aG video,render,input,dialout "$USER"
sudo reboot
```

**Speed stuck at zero.** Confirm gpsd is receiving data with `gpspipe -w -n 10`
and check that the `TPV` sentences contain a non-zero `speed` field. The app
falls back to simulation mode automatically if gpsd is unreachable — arrow keys
will move the simulated speed if that is happening.

---

## Contributing

Issues and pull requests are welcome.

---

## License

MIT
