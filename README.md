# Remote desktop viewer and input mirroring

`target.py` captures its primary screen with MSS, encodes JPEG frames with Pillow, and streams them over TCP. `host.py` displays the live feed in a resizable Pygame window and forwards keyboard and mouse events from that window. The target replays input with PyAutoGUI. Screen and input share one authenticated connection.

Both machines need Python 3.10+ and an active graphical desktop. Install dependencies:

```sh
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
```

Generate a random token with `python -c "import secrets; print(secrets.token_urlsafe(32))"`, then set the same `REMOTE_CONTROL_TOKEN` environment variable in both terminals. Bash: `export REMOTE_CONTROL_TOKEN='your-token'`. PowerShell: `$env:REMOTE_CONTROL_TOKEN='your-token'`.

On the target, explicitly listen on its LAN address:

```sh
python target.py --bind 192.168.1.50
```

On the host:

```sh
python host.py 192.168.1.50
```

Allow TCP port 5050 through the target's firewall only from the host. The default target bind is loopback. This protocol is unencrypted, including its token: use only on a trusted private network or through an authenticated encrypted tunnel; do not expose it to the Internet.

The screen streams immediately after authentication. Input starts paused. Click the viewer and press **F8** to enable/pause input. Losing window focus pauses input and releases held keys/buttons; press F8 again after returning. The window title shows the mode. Close the viewer to disconnect, or press **Ctrl+C** in either script's terminal. Moving the target's mouse to a screen corner triggers PyAutoGUI's emergency stop and exits the target process. Avoid screen corners during normal forwarding.

Mouse coordinates map from the displayed image to the target's primary screen; black padding around the image ignores clicks. Leaving the image during a drag releases held input. Modifier shortcuts such as Ctrl+C are forwarded while control is enabled. F8 is reserved. Operating-system shortcuts such as Alt+Tab, Windows shortcuts, and Ctrl+Alt+Delete may be intercepted locally and cannot be guaranteed remotely. Keyboard layouts should match; unusual keys and non-ASCII text may not be supported by PyAutoGUI.

Streaming defaults to 15 FPS, JPEG quality 70, and a maximum width of 1600 pixels (preserving aspect ratio). Lower these for slower networks:

```sh
python target.py --bind 192.168.1.50 --fps 10 --quality 50 --max-width 1280
```

Only the primary screen is supported; the target cursor is not included in the capture. Linux requires an X11 desktop (Wayland is generally unsupported), and macOS requires Screen Recording permissions for the target as well as Accessibility permissions for input replay. Both scripts must be updated together; the streaming protocol is incompatible with the earlier input-only host. A headless cloud machine cannot capture or replay real desktop input.

Run automated checks with `python -m unittest discover -s tests -v`. These use synthetic screen captures and simulated input; test actual desktop capture, permissions, and shortcuts on your machines.

## Feature ideas

- **Encrypted pairing:** TLS with a verified target certificate and one-time pairing codes, so sessions can safely cross less trusted networks.
- **Remote cursor overlay:** send cursor coordinates with frames for clearer clicking and dragging feedback.
- **Monitor selection:** pick a target monitor and map input to its desktop offset.
- **Connection stats and adaptive quality:** display FPS/latency/bandwidth and lower quality when the connection slows.
- **Dedicated shortcut buttons:** send supported combinations from a toolbar when the host OS intercepts them.
- **Clipboard and file transfer:** explicit, opt-in sharing with size limits and target approval.
- **Target session controls:** a visible connected-host indicator and a local disconnect button.
- **Reconnect and view-only permissions:** recover the feed after interruption while requiring deliberate input re-enablement.
