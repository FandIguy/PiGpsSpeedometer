# PiGpsSpeedometer — Stealth R/T GPS Cluster

A factory-orange GPS digital speedometer cluster built on a Raspberry Pi 5, 
installed in a 1991 Dodge Stealth R/T. Features a twin analog gauge design, 
0-60 MPH timer with persistent leaderboard, offline speed limit lookup for 
Minnesota and Wisconsin, real-time city/street display, and a 12-hour 
Central Time clock.

## Hardware
- Raspberry Pi 5 8GB
- GlobalSat BU-353N5 USB GPS Receiver
- GeeekPi 7" 1024x600 HDMI IPS Display
- Argon NEO 5 Aluminum Case with Fan
- Powered via 12V cigarette socket → dual buck converters (5V each)

## Features
- Twin analog gauges (speed + 0-60 timer)
- Factory orange (#FF8C1A) VFD-style display
- Offline speed limit lookup (MN + WI OpenStreetMap data)
- City and street/highway display from GPS coordinates
- 0-60 MPH timer with persistent top-5 leaderboard (L key to view, R to reset)
- GPS signal bars, 12-hour Central Time clock
- Boots directly to cluster on startup via systemd
- Renders via SDL2 kmsdrm (no desktop required)

## Software
- Python 3 + Pygame (SDL2 kmsdrm)
- gpsd + gpsd-py3
- OpenStreetMap data via Geofabrik (osmium-tool, shapely, rtree)
- Systemd service with logind session for display ownership

## Setup
See the full build guide in the wiki or the setup comments in each file.

## Built by
[@FandIguy](https://github.com/FandIguy)
