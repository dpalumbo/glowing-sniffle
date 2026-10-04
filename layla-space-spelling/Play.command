#!/bin/bash
# Double-click to play. Serves the game on localhost so the YouTube reward video can play.
cd "$(dirname "$0")"
PORT=8765
(sleep 1 && open "http://localhost:$PORT/") &
echo "Space Typing Adventure is running at http://localhost:$PORT — close this window to stop."
exec python3 -m http.server "$PORT" --bind 127.0.0.1
