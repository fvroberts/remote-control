"""Mirror local input to target.py. F8 toggles forwarding; Ctrl+C exits."""
import argparse
import json
import os
import socket
import threading


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", help="Target IP address or hostname")
    parser.add_argument("--port", type=int, default=5050)
    args = parser.parse_args()
    token = os.environ.get("REMOTE_CONTROL_TOKEN")
    if not token:
        parser.error("Set REMOTE_CONTROL_TOKEN on both machines")
    from pynput import keyboard, mouse
    import pyautogui

    width, height = pyautogui.size()
    lock = threading.Lock()
    enabled = False
    stopped = threading.Event()
    aliases = {"alt_l": "alt", "alt_r": "altright", "ctrl_l": "ctrl",
               "ctrl_r": "ctrlright", "shift_l": "shift", "shift_r": "shiftright",
               "cmd": "win", "cmd_l": "winleft", "cmd_r": "winright",
               "caps_lock": "capslock", "page_up": "pageup", "page_down": "pagedown",
               "num_lock": "numlock", "scroll_lock": "scrolllock",
               "print_screen": "printscreen"}

    with socket.create_connection((args.target, args.port), timeout=10) as connection:
        connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        connection.sendall((json.dumps({"token": token}) + "\n").encode())
        reader = connection.makefile("rb")
        if reader.readline(1024) != b'{"ok":true}\n':
            raise RuntimeError("Target rejected authentication")
        connection.settimeout(5)

        def send(event):
            with lock:
                if stopped.is_set():
                    return
                try:
                    connection.sendall((json.dumps(event) + "\n").encode())
                except OSError:
                    stopped.set()

        def position(x, y):
            return {"x": max(0, min(1, x / max(1, width - 1))),
                    "y": max(0, min(1, y / max(1, height - 1)))}

        def move(x, y):
            if enabled:
                send({"type": "move", **position(x, y)})

        def click(x, y, button, pressed):
            if enabled and button.name in ("left", "right", "middle"):
                send({"type": "button", "button": button.name,
                      "pressed": pressed, **position(x, y)})

        def scroll(x, y, dx, dy):
            if enabled:
                send({"type": "scroll", "dx": dx, "dy": dy, **position(x, y)})

        def key_name(key):
            if isinstance(key, keyboard.Key):
                return aliases.get(key.name, key.name)
            # Normalize Ctrl+A..Z back to physical letter keys.
            char = key.char
            if char and len(char) == 1 and 1 <= ord(char) <= 26:
                return chr(ord(char) + 96)
            return char.lower() if char else None

        toggle_down = False

        def press(key):
            nonlocal enabled, toggle_down
            if key == keyboard.Key.f8:
                if not toggle_down:
                    toggle_down = True
                    enabled = not enabled
                    send({"type": "reset"})
                    print("Forwarding ON" if enabled else "Forwarding PAUSED", flush=True)
            elif enabled:
                name = key_name(key)
                if name:
                    send({"type": "key", "key": name, "pressed": True})

        def release(key):
            nonlocal toggle_down
            if key == keyboard.Key.f8:
                toggle_down = False
            elif enabled:
                name = key_name(key)
                if name:
                    send({"type": "key", "key": name, "pressed": False})

        print("Connected. Press F8 to start/pause forwarding. Ctrl+C exits.")
        with mouse.Listener(on_move=move, on_click=click, on_scroll=scroll) as ml, \
                keyboard.Listener(on_press=press, on_release=release) as kl:
            try:
                while not stopped.wait(0.25):
                    if not ml.running or not kl.running:
                        break
            except KeyboardInterrupt:
                pass
            finally:
                send({"type": "reset"})
                ml.stop()
                kl.stop()
        reader.close()


if __name__ == "__main__":
    main()
