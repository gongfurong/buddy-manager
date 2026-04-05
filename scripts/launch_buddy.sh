#!/bin/bash
# Launch or focus Buddy Manager TUI window (Mac/Linux)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PY="$SCRIPT_DIR/buddy.py"
TITLE="Buddy Manager"

if [[ "$OSTYPE" == "darwin"* ]]; then
    # ── macOS ────────────────────────────────────────────────────────────
    # Check if a Terminal window titled "Buddy Manager" already exists
    HAS_WIN=$(osascript 2>/dev/null <<'EOF'
        tell application "Terminal"
            set found to false
            repeat with w in windows
                if name of w contains "Buddy Manager" then
                    set found to true
                    exit repeat
                end if
            end repeat
            return found
        end tell
EOF
)
    if [ "$HAS_WIN" = "true" ]; then
        # Focus existing window
        osascript 2>/dev/null <<'EOF'
            tell application "Terminal"
                set frontmost of (first window whose name contains "Buddy Manager") to true
                activate
            end tell
EOF
    else
        # Open new Terminal window running buddy.py
        osascript 2>/dev/null <<APPLESCRIPT
            tell application "Terminal"
                do script "python3 '$PY'; exit"
                set w to front window
                set custom title of (selected tab of w) to "$TITLE"
                activate
            end tell
APPLESCRIPT
    fi

else
    # ── Linux ─────────────────────────────────────────────────────────────
    # Try wmctrl to focus existing window
    if command -v wmctrl &>/dev/null; then
        if wmctrl -l 2>/dev/null | grep -q "$TITLE"; then
            wmctrl -a "$TITLE"
            exit 0
        fi
    fi

    # Open new terminal window
    if command -v gnome-terminal &>/dev/null; then
        gnome-terminal --title="$TITLE" -- python3 "$PY"
    elif command -v konsole &>/dev/null; then
        konsole --title "$TITLE" -e python3 "$PY" &
    elif command -v xfce4-terminal &>/dev/null; then
        xfce4-terminal --title="$TITLE" -e "python3 '$PY'" &
    elif command -v xterm &>/dev/null; then
        xterm -title "$TITLE" -e python3 "$PY" &
    else
        # Last resort: run in current terminal (no new window)
        python3 "$PY"
    fi
fi
