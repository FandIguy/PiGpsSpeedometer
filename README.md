# Pi GPS Speedometer

A full-screen GPS digital instrument cluster for the **Raspberry Pi 5**, built to
run headless in a car — it boots straight to the gauge display with no desktop.
Originally built for a 1991 Dodge Stealth R/T.

![Dashboard Screenshot](docs/images/dashboard.png)

![Raspberry Pi 5](https://img.shields.io/badge/Raspberry%20Pi-5-C51A4A)
![Python](https://img.shields.io/badge/Python-3.11-blue)
![Bookworm](https://img.shields.io/badge/Tested%20on-Bookworm-success)
![GPSD](https://img.shields.io/badge/GPSD-Compatible-green)
![License](https://img.shields.io/badge/License-MIT-lightgrey)
---

## Features

- Full-screen digital speedometer (factory-orange VFD aesthetic)
- Real-time GPS speed, heading, altitude, and fix quality
- 0–60 mph timer with a persistent top-5 leaderboard
- 12-hour clock (US Central, DST-aware via zoneinfo)
- GPS signal-strength bars
- Boots directly to the cluster on power-up (systemd)
- Simulation mode when no GPS is present (no code changes needed)
- Optional Ctrl+M (Minetest) and Ctrl+T (terminal) launch hotkeys

---

## Hardware

| Part | Notes |
|------|-------|
| Raspberry Pi 5 (8GB) | Pi 4 also works — see compatibility note below |
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
The installer handles all of them; this section explains them for the curious /
for troubleshooting.

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

### Runtime dir

KMSDRM also needs `XDG_RUNTIME_DIR` (`/run/user/<uid>`). The installer enables
**lingering** (`loginctl enable-linger`) so that directory exists at boot before
the service starts, and the service sets the variable explicitly.

### GPS

The GPS is USB. The installer writes `/etc/default/gpsd` pointing at
`/dev/ttyUSB0` with `-n` (poll without a client connected) so a fix is ready as
soon as the cluster starts. The app reads gpsd's JSON socket directly — no
`python-gps`/`python-serial` library involved.

Verify a fix after reboot (needs a clear view of the sky; a cold start can take
a few minutes):

```bash
gpspipe -w -n 5      # raw JSON — look for "mode":3 and a lat/lon
cgps                 # live view (terminal must be >= 80 columns)
```

---

## Controls

| Key | Action |
|-----|--------|
| `ESC` | Quit |
| `UP` / `DOWN` | Adjust speed in simulation mode |
| `R` | Reset the 0–60 leaderboard |
| `Ctrl + M` | Launch Minetest (if the optional scripts are installed) |
| `Ctrl + T` | Drop to a terminal on tty2 (`exit` returns to the cluster) |

---

## Raspberry Pi compatibility

**Pi 5:** uses `card1` + KMSDRM with `SDL_KMSDRM_DEVICE_INDEX=1` (default in the
service).

**Pi 4:** exposes a single DRM device, so SDL selects it automatically. Remove
this line from `/etc/systemd/system/speedometer.service`:

```text
Environment=SDL_KMSDRM_DEVICE_INDEX=1
```

then `sudo systemctl daemon-reload && sudo systemctl restart speedometer`.

---

## Simulation mode

If no GPS receiver is connected (or gpsd has no fix), the app runs in simulation
mode automatically — useful for bench testing the UI. Use `UP`/`DOWN` to drive
the simulated speed. No code changes required.

---

## Service management

```bash
sudo systemctl status speedometer      # is it running?
sudo systemctl restart speedometer     # restart after editing the .py
sudo journalctl -u speedometer -f      # live logs / errors
```

---

## Troubleshooting

**Black screen, no error.** Almost always the display-ownership chain. Check, in
order: `who` shows `<user> tty1` (autologin working); the user is in the `video`
and `render` groups (`groups`); `/run/user/<uid>` exists (lingering enabled); and
the service has `SDL_KMSDRM_DEVICE_INDEX=1` on a Pi 5. The logs will often show
the driver falling back to `dummy` — that's this problem.

**`drmModePageFlip failed (-13)` (EACCES).** The process isn't DRM master. This
happens if you run the script directly over SSH (an SSH session has no console
seat). Test via the service, or with `openvt` on tty1 — not over SSH.

**GPS never locks.** Confirm a clear view of the sky, that `/dev/ttyUSB0` exists
(`ls -l /dev/ttyUSB*`), and that gpsd is running. A cold start can take several
minutes.

**Permission denied.** Make sure your user is in the required groups, then
reboot:

```bash
sudo usermod -aG video,render,input,dialout "$USER"
sudo reboot
```

---

## Roadmap

- Offline speed-limit lookup (OpenStreetMap `maxspeed` data)
- City / street display from GPS coordinates
- OBD-II integration (RPM, coolant, fuel)
- Twin analog gauge themes
- Touchscreen support

---

## Contributing

Issues and pull requests welcome.

---

## License

MIT
