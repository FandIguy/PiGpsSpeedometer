# Pi GPS Speedometer

*A full-screen GPS speedometer and digital instrument cluster for the Raspberry Pi 5.*

![Dashboard Screenshot](docs/images/dashboard.png)

![Raspberry Pi 5](https://img.shields.io/badge/Raspberry%20Pi-5-C51A4A)
![Python](https://img.shields.io/badge/Python-3.11-blue)
![Bookworm](https://img.shields.io/badge/Tested%20on-Bookworm-success)
![GPSD](https://img.shields.io/badge/GPSD-Compatible-green)
![License](https://img.shields.io/badge/License-MIT-lightgrey)

---

## Features

* Full-screen digital speedometer
* Real-time GPS speed and heading
* Automatic GPS detection
* Simulation mode when GPS is unavailable
* Optimized for Raspberry Pi 5
* SDL2/KMSDRM rendering
* Automatic startup with systemd
* Lightweight and responsive

---

## Repository Layout

```text
PiGpsSpeedometer/
├── speedometer.py
├── speedometer.service
├── install.sh
├── config/
├── docs/
│   └── images/
├── fonts/
└── README.md
```

---

# Quick Install

Clone the repository.

```bash
git clone https://github.com/FandIguy/PiGpsSpeedometer.git
cd PiGpsSpeedometer
```

Install the required packages.

```bash
sudo apt update

sudo apt install \
python3-pygame \
python3-gps \
gpsd \
gpsd-clients \
python3-pip \
python3-serial \
fonts-dejavu \
curl
```

Run the installation script.

```bash
chmod +x install.sh
./install.sh
```

Reboot.

```bash
sudo reboot
```

That's it.

---

# Detailed Installation

This section explains what the installation script configures and why.

## Display Configuration

Explain why SDL uses card1 on the Raspberry Pi 5.

Explain the DRM/KMS configuration.

Include the environment variables.

---

## GPS Configuration

Enable UART.

Disable serial login.

Configure gpsd.

After reboot, verify GPS is working.

```bash
cgps -s
```

A successful fix will look similar to:

```text
Latitude: 44.xxxxxx
Longitude: -93.xxxxxx
Fix: 3D
Satellites: 10
Speed: 32 mph
```

**Note:** The first cold start may take several minutes while the receiver downloads satellite data. Future fixes are typically much faster.

---

## Service

Enable the application.

```bash
sudo systemctl enable speedometer
sudo systemctl start speedometer
```

Verify it is running.

```bash
systemctl status speedometer
```

Expected output:

```text
Active: active (running)
```

---

# Raspberry Pi Compatibility

## Raspberry Pi 5

Uses:

* card1
* KMSDRM
* SDL device index 1

## Raspberry Pi 4

Only one DRM device is exposed, so SDL automatically selects the correct display. Remove:

```text
SDL_KMSDRM_DEVICE_INDEX=1
```

from the service file.

---

# Simulation Mode

If no GPS receiver is connected, the application automatically enters simulation mode for testing. No code changes are required.

---

# Troubleshooting

## GPS never locks

* Confirm antenna has a clear view of the sky.
* Check `cgps -s`.
* Verify gpsd is running.
* Remember that the first cold start may take several minutes.

## Permission denied

Ensure the user belongs to the required groups.

```bash
sudo usermod -aG video,input,gpio,dialout $USER
```

Then reboot.

```bash
sudo reboot
```

## DRM pageflip errors

If you encounter:

```
drmModePageFlip failed (-13)
```

verify that no desktop environment is running and that SDL has DRM master.

## Keyboard input

If keyboard input does not work:

* Verify SDL has focus.
* Confirm no other application is capturing input.
* Ensure the input group permissions are correct.

---

# Roadmap

* OBD-II integration
* RPM gauge
* Coolant temperature
* Fuel level
* Trip computer
* Custom themes
* Touchscreen support
* CAN bus integration

---

# Contributing

Issues and pull requests are welcome.

---

# License

MIT License.
