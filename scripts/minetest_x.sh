#!/bin/bash
# xinit client wrapper: starts a minimal WM for keyboard focus, then Minetest.
# Called by xinit so DISPLAY=:0 is already set.
setxkbmap us
matchbox-window-manager -use_titlebar no &
sleep 0.5
exec /usr/games/minetest
