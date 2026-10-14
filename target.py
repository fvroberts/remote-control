"""Stream the primary screen and replay input on a trusted network. No authentication."""
import argparse
import json
import io
import math
import socket
import struct
import threading
import time


def local_addresses():
    """Best-effort address hints without contacting an external service."""
    try:
        addresses = {entry[4][0] for entry in socket.getaddrinfo(
            socket.gethostname(), None, socket.AF_INET, socket.SOCK_STREAM)}
        return sorted(address for address in addresses if not address.startswith("127."))
    except OSError:
        return []


def stream_screen(connection, stopped, fps, quality, max_width):
    try:
        import mss
        from PIL import Image
        with mss.mss() as capture:
            monitor = capture.monitors[1]
            while not stopped.is_set():
                started = time.monotonic()
                shot = capture.grab(monitor)
                image = Image.frombytes("RGB", shot.size, shot.rgb)
                if image.width > max_width:
                    height = max(1, round(image.height * max_width / image.width))
                    image = image.resize((max_width, height), Image.Resampling.BILINEAR)
                with io.BytesIO() as buffer:
                    image.save(buffer, format="JPEG", quality=quality)
                    frame = buffer.getvalue()
                if len(frame) > 16 * 1024 * 1024:
                    raise ValueError("Screen frame too large")
                connection.sendall(struct.pack("!I", len(frame)) + frame)
                stopped.wait(max(0, 1 / fps - (time.monotonic() - started)))
    except Exception as error:
        if not stopped.is_set():
            print(f"Screen stream ended: {error}", flush=True)
    finally:
        stopped.set()
        try:
            connection.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass


def replay(event, gui, keys, buttons):
    kind = event.get("type")
    if kind == "ping":
        return
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
    for key in list(keys):
        gui.keyUp(key)
        keys.discard(key)
    for button in list(buttons):
        gui.mouseUp(button=button)
        buttons.discard(button)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bind", default="0.0.0.0", help="Listen address (default: all IPv4 interfaces)")
    parser.add_argument("--port", type=int, default=5050)
    parser.add_argument("--fps", type=int, default=15, help="Screen frames per second (1–60)")
    parser.add_argument("--quality", type=int, default=70, help="JPEG quality (1–95)")
    parser.add_argument("--max-width", type=int, default=1600, help="Maximum streamed image width")
    args = parser.parse_args()
    if not 1 <= args.fps <= 60 or not 1 <= args.quality <= 95 or not 64 <= args.max_width <= 7680:
        parser.error("Use fps 1–60, quality 1–95, and max-width 64–7680")
    import pyautogui as gui
    gui.PAUSE = 0
    gui.FAILSAFE = False
    keys, buttons = set(), set()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((args.bind, args.port))
        server.listen(1)
        addresses = local_addresses() if args.bind == "0.0.0.0" else [args.bind]
        if addresses:
            print("On the host, enter one of these target addresses: " + ", ".join(addresses), flush=True)
        else:
            print("Find this device's Wi-Fi/Ethernet IPv4 address with ipconfig and enter it on the host.", flush=True)
        print("No authentication. Use only on a trusted network; close this terminal when finished.", flush=True)
        print(f"Listening on {args.bind}:{args.port}. Press Ctrl+C in this terminal to stop.", flush=True)
        try:
            while True:
                connection, address = server.accept()
                with connection:
                    connection.settimeout(10)
                    connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    stopped = threading.Event()
                    streamer = None
                    try:
                        with connection.makefile("rb") as reader:
                            connection.sendall(b'{"ok":true}\n')
                            connection.settimeout(10)
                            print(f"Host connected: {address[0]}", flush=True)
                            streamer = threading.Thread(target=stream_screen,
                                args=(connection, stopped, args.fps, args.quality, args.max_width), daemon=True)
                            streamer.start()
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
                    except (OSError, ValueError, KeyError, TypeError) as error:
                        print(f"Connection ended: {error}", flush=True)
                    finally:
                        stopped.set()
                        try:
                            connection.shutdown(socket.SHUT_RDWR)
                        except OSError:
                            pass
                        if streamer:
                            streamer.join(timeout=2)
                        release_all(gui, keys, buttons)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    try:
        main()
    except ImportError as error:
        raise SystemExit(f"Missing dependency: {error}. Run python -m pip install --user -r requirements.txt.")
    except OSError as error:
        raise SystemExit(f"Target could not start: {error}. Close any previous target process and retry.")
