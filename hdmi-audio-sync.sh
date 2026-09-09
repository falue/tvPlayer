#!/bin/bash
# hdmi-audio-sync.sh
# Re-probe the Pi's HDMI sound cards so the connected port gets its sink.
# Only WirePlumber is restarted; PipeWire, combined-output and mpv stay up.
set -u
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"

connected=""
for name in HDMI-A-2 HDMI-A-1; do
  f=$(ls /sys/class/drm/card*-"$name"/status 2>/dev/null | head -n1)
  [ -n "$f" ] && [ "$(cat "$f")" = "connected" ] && { connected=$name; break; }
done
echo "hdmi-audio-sync: connected HDMI = ${connected:-none}"

systemctl --user restart wireplumber

# Wait for the analog sink (always) and an HDMI sink (if a display is present)
for _ in $(seq 1 40); do
  sinks=$(pactl list short sinks 2>/dev/null)
  if echo "$sinks" | grep -q 'mailbox' && { [ -z "$connected" ] || echo "$sinks" | grep -q 'hdmi'; }; then
    echo "hdmi-audio-sync: sinks ready"
    exit 0
  fi
  sleep 0.25
done
echo "hdmi-audio-sync: WARNING expected sinks did not appear" >&2
exit 0