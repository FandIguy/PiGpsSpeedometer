#!/bin/bash
# Stealth R/T Cyberdeck -- Minetest launcher
# Invoked via os.execvp from speedometer.py on Ctrl+M.
# This script IS the speedometer service process (execvp replaces, not forks).
# When we exit, systemd auto-restarts the cluster (Restart=always).

unset SDL_VIDEODRIVER
unset SDL_KMSDRM_DEVICE_INDEX
unset SDL_FBDEV
unset SDL_NOMOUSE

# Give kmsdrm a moment to release the display
sleep 1

# Launch X on tty2 with Minetest.
# minetest_x.sh runs setxkbmap first so keyboard works in-game.
# Screen size and fullscreen come from ~/.minetest/minetest.conf.
xinit /home/USERNAME/minetest_x.sh -- :0 vt2 2>/dev/null

# Minetest exited -- clean up any lingering X process
pkill -f "X :0" 2>/dev/null
sleep 1

# Switch back to tty1 where the cluster will restart
sudo chvt 1

# Script exits -> systemd auto-restarts the speedometer
