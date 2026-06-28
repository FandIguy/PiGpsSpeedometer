#!/bin/bash
# Stealth R/T Cyberdeck -- Terminal launcher
# Invoked via os.execvp from speedometer.py on Ctrl+T.
# This script IS the speedometer service process (execvp replaces, not forks).
# When we exit, systemd auto-restarts the cluster (Restart=always).

unset SDL_VIDEODRIVER
unset SDL_KMSDRM_DEVICE_INDEX
unset SDL_FBDEV
unset SDL_NOMOUSE

# Give kmsdrm a moment to release the display
sleep 0.5

# Open a login shell on tty2, switch the screen to it, and wait for exit.
# User types 'exit' to return to the cluster.
sudo openvt -c 2 -s -w -- /bin/bash --login

# Shell exited -- switch the screen back to tty1
sudo chvt 1

# Script exits -> systemd auto-restarts the speedometer
