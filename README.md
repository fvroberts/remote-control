# Remote desktop viewer and input mirroring

View the target's screen and control it from the host. Both computers need Python 3.10+ and an active graphical desktop; the Windows dependencies include prebuilt wheels for 64-bit Python 3.14.

## Fast Windows setup

Put the latest project files on both computers and connect them to the same trusted network.

1. **Install once:** double-click `install.bat` on each computer. No virtual environment, administrator install, or token is needed. If the current dependencies are already installed, skip this step.
2. **Target (computer being controlled):** double-click `start-target.bat`. Leave its terminal open. It listens automatically and displays target IP address suggestions.
3. **Host (computer you use):** double-click `start-host.bat`, enter the target's Wi-Fi/Ethernet IP, then click the viewer and press **F8** to enable control. Some laptops require **Fn+F8**.

If Windows Firewall asks, allow Python on **Private networks**. Device policy or Wi-Fi client isolation can still require administrator help; these cannot be bypassed by the scripts. The firewall must permit inbound TCP port **5050** on the target from the host.

**There is no authentication or encryption. Anyone who can reach the target's port can view and control it. Use only on a trusted private network, do not forward the port to the Internet, and stop the target when finished.**

Update both scripts together. The previous token-based version is incompatible; any old `REMOTE_CONTROL_TOKEN` setting is now ignored.

## Controls

- **F8:** enable/pause control. Input starts paused.
- **Switch away from the viewer:** control pauses and held keys/buttons release. Press F8 after returning to resume.
- **Close the viewer:** disconnect. The target remains available until you stop it.
- **Ctrl+C in the target terminal:** stop the target. Moving its mouse to a screen corner also triggers the PyAutoGUI emergency stop during input replay.

Clicking within the displayed image maps to the target's primary screen; black padding ignores clicks. Leaving the image during a drag releases held input. Shortcuts such as Ctrl+C work while the viewer has focus, but operating-system shortcuts like Alt+Tab and Ctrl+Alt+Delete may be intercepted locally. Use matching keyboard layouts. Unusual keys and non-ASCII text may not be supported.

## Command-line alternative

In the project folder (Command Prompt or PowerShell):

```sh
# Target: no IP argument required
python target.py

# Host: prompts for the target's IP
python host.py

# Or connect directly
python host.py 192.168.1.50
```

For a slower network, run `python target.py --fps 10 --quality 50 --max-width 1280`. Defaults are 15 FPS, JPEG quality 70, and a maximum width of 1600 pixels. Advanced options `--port` and `--bind` remain available. The default bind is `0.0.0.0` (all IPv4 interfaces); the host must connect to an actual target IP, not `0.0.0.0`.

## Troubleshooting

- **Missing packages:** run `install.bat`. It installs per-user packages and replaces legacy pygame with pygame-ce (both use `import pygame`). Package installation must be permitted by your device policy; TLS certificate verification remains enabled.
- **Connection timeout:** check the target is running, its IP is correct, both computers are reachable, and the firewall/network permits TCP 5050.
- **Wrong or missing IP suggestion:** run `ipconfig` on the target and use the active Wi-Fi/Ethernet IPv4 address.
- **Port already in use:** close the previous target process or use a different `--port` on both scripts.
- **No picture or input:** Linux requires X11; macOS requires Screen Recording and Accessibility permissions. Only the primary screen is supported, and its cursor is not captured.

For other platforms or an existing environment, install with `python -m pip install -r requirements.txt`. If legacy `pygame` is installed, uninstall it first and reinstall `pygame-ce` because their import files overlap.

## Development checks

Run `python -m unittest discover -s tests -v`. The tests exercise TCP connections, synthetic screen capture, JPEG decoding, viewer rendering, and simulated input. Real desktop capture, firewall prompts, Windows launchers, and OS shortcuts need verification on the devices.

## Feature ideas

- **Encrypted pairing:** TLS with a verified target certificate and one-time pairing codes, so sessions can safely cross less trusted networks.
- **Remote cursor overlay:** send cursor coordinates with frames for clearer clicking and dragging feedback.
- **Monitor selection:** pick a target monitor and map input to its desktop offset.
- **Connection stats and adaptive quality:** display FPS/latency/bandwidth and lower quality when the connection slows.
- **Dedicated shortcut buttons:** send supported combinations from a toolbar when the host OS intercepts them.
- **Clipboard and file transfer:** explicit, opt-in sharing with size limits and target approval.
- **Target session controls:** a visible connected-host indicator and a local disconnect button.
- **Reconnect and view-only permissions:** recover the feed after interruption while requiring deliberate input re-enablement.
