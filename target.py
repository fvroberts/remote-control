"""Replay input from an authenticated host on a trusted network."""
import argparse
import hmac
import json
import math
import os
import socket


def replay(event, gui, keys, buttons):
    kind = event.get("type")
    if kind == "reset":
        release_all(gui, keys, buttons)
        return
    if kind in ("move", "button", "scroll"):
        x, y = event["x"], event["y"]
        if any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1
               for v in (x, y)):
            raise ValueError("Invalid coordinates")
        width, height = gui.size()
        gui.moveTo(round(x * (width - 1)), round(y * (height - 1)))
    if kind == "move":
        return
    if kind in ("key", "button"):
        value = event["key" if kind == "key" else "button"]
        allowed = gui.KEYBOARD_KEYS if kind == "key" else ("left", "right", "middle")
        if not isinstance(value, str) or value not in allowed or type(event["pressed"]) is not bool:
            raise ValueError("Invalid input")
        held = keys if kind == "key" else buttons
        down = gui.keyDown if kind == "key" else gui.mouseDown
        up = gui.keyUp if kind == "key" else gui.mouseUp
        if event["pressed"]:
            down(value) if kind == "key" else down(button=value)
            held.add(value)
        else:
            up(value) if kind == "key" else up(button=value)
            held.discard(value)
    elif kind == "scroll":
        dx, dy = event["dx"], event["dy"]
        if any(type(v) is not int or abs(v) > 100 for v in (dx, dy)):
            raise ValueError("Invalid scroll")
        if dx:
            gui.hscroll(dx)
        if dy:
            gui.scroll(dy)
    else:
        raise ValueError("Unknown event")


def release_all(gui, keys, buttons):
    # Cleanup must still release held input after the corner emergency stop.
    previous = gui.FAILSAFE
    try:
        gui.FAILSAFE = False
        for key in list(keys):
            gui.keyUp(key)
            keys.discard(key)
        for button in list(buttons):
            gui.mouseUp(button=button)
            buttons.discard(button)
    finally:
        gui.FAILSAFE = previous


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bind", default="127.0.0.1", help="Listen address; use your LAN IP for remote hosts")
    parser.add_argument("--port", type=int, default=5050)
    args = parser.parse_args()
    token = os.environ.get("REMOTE_CONTROL_TOKEN")
    if not token:
        parser.error("Set REMOTE_CONTROL_TOKEN on both machines")
    import pyautogui as gui
    gui.PAUSE = 0
    gui.FAILSAFE = True
    keys, buttons = set(), set()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((args.bind, args.port))
        server.listen(1)
        print(f"Listening on {args.bind}:{args.port}. Move mouse to a screen corner to stop.", flush=True)
        try:
            while True:
                connection, address = server.accept()
                with connection:
                    connection.settimeout(10)
                    connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    try:
                        with connection.makefile("rb") as reader:
                            auth = json.loads(reader.readline(4097))
                            supplied = auth.get("token") if isinstance(auth, dict) else None
                            if not isinstance(supplied, str) or not hmac.compare_digest(supplied.encode(), token.encode()):
                                print("Rejected unauthenticated connection", flush=True)
                                continue
                            connection.sendall(b'{"ok":true}\n')
                            connection.settimeout(None)
                            print(f"Host connected: {address[0]}", flush=True)
                            while True:
                                line = reader.readline(4097)
                                if not line:
                                    break
                                if len(line) > 4096 or not line.endswith(b"\n"):
                                    raise ValueError("Event too large")
                                event = json.loads(line)
                                if not isinstance(event, dict):
                                    raise ValueError("Expected an event object")
                                replay(event, gui, keys, buttons)
                    except gui.FailSafeException:
                        print("Emergency stop triggered. Target exiting.", flush=True)
                        return
                    except (OSError, ValueError, KeyError, TypeError) as error:
                        print(f"Connection ended: {error}", flush=True)
                    finally:
                        release_all(gui, keys, buttons)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
