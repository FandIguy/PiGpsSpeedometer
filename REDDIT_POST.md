# Reddit Post — copy and paste into your chosen subreddit

---

## Suggested subreddits

- **r/raspberry_pi** — technical audience, loves Pi projects
- **r/DIY** — general maker audience
- **r/MoparNation** — Mopar/Dodge car community
- **r/CarAV** — car audio/video/electronics
- **r/selfhosted** — people who run their own embedded systems

---

## Post title (r/raspberry_pi)

```
Built an amber VFD-style GPS cluster for my 1991 Dodge Stealth R/T — Raspberry Pi 5, pygame, bare-metal kmsdrm with no desktop
```

## Post title (r/MoparNation / r/cars)

```
Replaced the factory gauges in my 1991 Dodge Stealth R/T with a Raspberry Pi 5 GPS cluster [OC]
```

---

## Post body

---

I spent the last few months replacing the aging gauge cluster in my 1991 Dodge Stealth R/T with a fullscreen amber VFD-style GPS display running on a Raspberry Pi 5. Thought I'd share the build since there wasn't a good single resource for getting kmsdrm + GPS + car power working together on Pi 5.

**The display shows:**
- Analog arc speedometer (mph, smoothed) with segmented LED bar
- Compass heading with 16-point cardinal
- Altitude (ft) and vertical speed (ft/min)
- GPS signal bars, satellite count, HDOP, fix type (2D/3D)
- Local clock (US Central, 12-hour blinking colon) + UTC date
- Trip odometer and elapsed session time
- **0–60 MPH timer** with a persistent top-5 leaderboard that survives power cuts (atomic file writes)
- Posted speed limit and street/city name from OpenStreetMap data
- CRT scanline overlay and corner bracket accents for that 90s terminal aesthetic

---

**Hardware:**

- Raspberry Pi 5 8GB
- GeeekPi 7" 1024×600 HDMI display
- GlobalSat BU-353N5 GPS USB dongle
- 2.4GHz wireless USB keyboard
- Cigarette socket → buck converters (separate rails for Pi and screen)

---

**The interesting Pi 5 gotchas I had to solve:**

1. **Pi 5 splits DRM across two devices.** `card0` is the V3D GPU (no display connectors), `card1` is the RP1 display controller (HDMI). SDL defaults to index 0, finds no displays, and silently falls back to the `dummy` driver — process runs fine, screen stays black. Fix: `SDL_KMSDRM_DEVICE_INDEX=1` in the service and a one-line xorg.conf for X sessions.

2. **kmsdrm needs a real logind session.** The service needs `PAMName=login` + `TTYPath=/dev/tty1` in the systemd unit AND the user must be autologin'd on tty1. Without the logind session, kmsdrm can't acquire DRM master (error -13). No logind = black screen, no error messages.

3. **Minetest is X11-only on Linux.** The game links libX11/libGLX — no SDL, no kmsdrm path. So Ctrl+M kills the cluster, spawns an X server on tty2 with `xinit`, and uses `matchbox-window-manager` to handle keyboard focus. When you exit Minetest, the script switches back to tty1 and systemd auto-restarts the cluster in ~2 seconds.

4. **VT switching from kmsdrm is a one-way door.** SDL kmsdrm holds DRM master and doesn't implement the SIGUSR1/SIGUSR2 VT cooperation protocol, so you can't Ctrl+Alt+F2 away from the cluster. The only way out is through the hotkeys that cleanly exit pygame first.

---

**Full step-by-step build guide + all code:**

[GitHub link here — replace with your repo URL]

Includes: `speedometer.py`, systemd service, launch scripts, all config file templates, and a troubleshooting section for the common failure modes.

Runs in **simulation mode** automatically if there's no GPS connected — arrow keys adjust speed, so you can test the full UI on any desktop.

Happy to answer questions about the kmsdrm setup, Pi 5 display config, or anything else.

---

*Cross-posted to r/MoparNation and r/CarAV*

---

## Photo caption suggestions (if you have photos)

- `The cluster at speed on I-94 — 0-60 timer just tripped`
- `Boot splash — "ACQUIRING SATELLITES... SEARCHING"`
- `Side by side: factory gauge cluster vs. the new display`
- `Raspberry Pi 5 tucked behind the dash`
- `GPS dongle mounted on the dash near the windshield`
