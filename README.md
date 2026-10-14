# Remote input mirroring

`host.py` captures the host's keyboard and mouse with pynput and sends newline-delimited JSON over TCP. `target.py` replays it with PyAutoGUI. This mirrors input only; it does not stream the target's screen.

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

Forwarding starts paused. Press **F8** to toggle it. Pausing or disconnecting releases held keys and mouse buttons. Press **Ctrl+C** to exit. Moving the target's mouse to a screen corner triggers PyAutoGUI's emergency stop and exits the target process. Host coordinates scale to the target's primary screen; avoid screen corners during normal forwarding.

Input still acts locally on the host. Keyboard layouts should match; unusual keys and non-ASCII text may not be supported by PyAutoGUI. Only the primary screen is supported. Linux requires an X11 desktop (Wayland is generally unsupported), and macOS requires Accessibility/Input Monitoring permissions. A headless cloud machine cannot capture or replay real desktop input.
