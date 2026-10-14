"""View and control target.py. F8 toggles input; close the window to exit."""
import argparse
import io
import json
import socket
import struct
import threading
import time

MAX_FRAME_BYTES = 16 * 1024 * 1024
KEY_ALIASES = {
    "left ctrl": "ctrlleft", "right ctrl": "ctrlright",
    "left shift": "shiftleft", "right shift": "shiftright",
    "left alt": "altleft", "right alt": "altright",
    "left gui": "winleft", "right gui": "winright",
    "left meta": "winleft", "right meta": "winright",
    "return": "enter", "escape": "esc", "caps lock": "capslock",
    "page up": "pageup", "page down": "pagedown", "numlock": "numlock",
    "scroll lock": "scrolllock", "print screen": "printscreen",
    "menu": "apps", "[enter]": "enter", "[+]": "add", "[-]": "subtract",
    "[*]": "multiply", "[/]": "divide", "[.]": "decimal",
}


def key_name(name):
    name = KEY_ALIASES.get(name, name)
    if len(name) == 3 and name[0] == "[" and name[2] == "]" and name[1].isdigit():
        return name[1]
    if len(name) == 1 and " " <= name <= "~":
        return name
    if name in set(KEY_ALIASES.values()) | {
        "backspace", "space", "tab", "delete", "insert", "home", "end",
        "up", "down", "left", "right", "pause", "clear",
    } or name in {f"f{i}" for i in range(1, 25)}:
        return name
    return None


def recv_exact(connection, size):
    data = bytearray()
    while len(data) < size:
        chunk = connection.recv(size - len(data))
        if not chunk:
            raise ConnectionError("Target disconnected")
        data.extend(chunk)
    return bytes(data)


def receive_frame(connection):
    size, = struct.unpack("!I", recv_exact(connection, 4))
    if not 0 < size <= MAX_FRAME_BYTES:
        raise ValueError("Invalid screen frame size")
    return recv_exact(connection, size)


def view_rect(window_size, screen_size):
    scale = min(window_size[0] / screen_size[0], window_size[1] / screen_size[1])
    width, height = max(1, int(screen_size[0] * scale)), max(1, int(screen_size[1] * scale))
    return ((window_size[0] - width) // 2, (window_size[1] - height) // 2, width, height)


def position(point, rect):
    left, top, width, height = rect
    x, y = point
    if not (left <= x < left + width and top <= y < top + height):
        return None
    return {"x": (x - left) / max(1, width - 1), "y": (y - top) / max(1, height - 1)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="?", help="Target IP address or hostname (prompts if omitted)")
    parser.add_argument("--port", type=int, default=5050)
    args = parser.parse_args()
    if not args.target:
        args.target = input("Target IP address: ").strip()
    if not args.target:
        parser.error("Enter the IP address shown by the target")
    import pygame

    with socket.create_connection((args.target, args.port), timeout=10) as connection:
        connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        # An unbuffered read leaves the first binary frame in the socket.
        with connection.makefile("rb", buffering=0) as reader:
            if reader.readline(1024) != b'{"ok":true}\n':
                raise RuntimeError("Unexpected server response. Update both devices to the latest scripts.")
        connection.settimeout(10)
        stopped = threading.Event()
        frame_lock = threading.Lock()
        latest = None
        error = None

        def receive():
            nonlocal latest, error
            try:
                while not stopped.is_set():
                    data = receive_frame(connection)
                    with frame_lock:
                        latest = data  # Drop old frames to bound latency and memory.
            except (OSError, ValueError) as exc:
                if not stopped.is_set():
                    error = str(exc)
                stopped.set()

        def send(event):
            connection.sendall((json.dumps(event) + "\n").encode())

        receiver = threading.Thread(target=receive, daemon=True)
        pygame.init()
        window = pygame.display.set_mode((1000, 700), pygame.RESIZABLE)
        clock = pygame.time.Clock()
        image = None
        enabled = False
        rect = (0, 0, 1, 1)
        buttons = {1: "left", 2: "middle", 3: "right"}
        held_buttons = set()
        last_ping = time.monotonic()
        receiver.start()
        print("Connected. F8 enables/pauses input while the viewer has focus. Close to exit.")
        try:
            while not stopped.is_set():
                if time.monotonic() - last_ping >= 2:
                    send({"type": "ping"})
                    last_ping = time.monotonic()
                with frame_lock:
                    data, latest = latest, None
                if data is not None:
                    image = pygame.image.load(io.BytesIO(data), "frame.jpg").convert()
                if image is not None:
                    rect = view_rect(window.get_size(), image.get_size())
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        stopped.set()
                    elif event.type == pygame.WINDOWFOCUSLOST:
                        send({"type": "reset"})
                        held_buttons.clear()
                        enabled = False
                    elif event.type == pygame.KEYDOWN and event.key == pygame.K_F8:
                        if not getattr(event, "repeat", False):
                            enabled = not enabled
                            send({"type": "reset"})
                            held_buttons.clear()
                    elif enabled and image is not None and pygame.key.get_focused():
                        if event.type in (pygame.KEYDOWN, pygame.KEYUP):
                            if event.key != pygame.K_F8:
                                name = pygame.key.name(event.key)
                                name = key_name(name)
                                if name:
                                    send({"type": "key", "key": name,
                                          "pressed": event.type == pygame.KEYDOWN})
                        elif event.type == pygame.MOUSEMOTION:
                            coords = position(event.pos, rect)
                            if coords:
                                send({"type": "move", **coords})
                            elif held_buttons:
                                send({"type": "reset"})
                                held_buttons.clear()
                        elif event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
                            coords = position(event.pos, rect)
                            if event.button in buttons and coords:
                                pressed = event.type == pygame.MOUSEBUTTONDOWN
                                send({"type": "button", "button": buttons[event.button],
                                      "pressed": pressed, **coords})
                                if pressed:
                                    held_buttons.add(event.button)
                                else:
                                    held_buttons.discard(event.button)
                            elif event.type == pygame.MOUSEBUTTONUP and event.button in held_buttons:
                                send({"type": "reset"})
                                held_buttons.clear()
                        elif event.type == pygame.MOUSEWHEEL:
                            coords = position(pygame.mouse.get_pos(), rect)
                            if coords:
                                send({"type": "scroll", "dx": max(-100, min(100, event.x)),
                                      "dy": max(-100, min(100, event.y)), **coords})
                window.fill((20, 20, 20))
                if image is not None:
                    window.blit(pygame.transform.smoothscale(image, rect[2:]), rect[:2])
                status = "CONTROL ON" if enabled else "PAUSED / VIEW ONLY"
                if image is None:
                    status = "Waiting for screen"
                pygame.display.set_caption(f"Remote control — {status} — F8 toggles input")
                pygame.display.flip()
                clock.tick(60)
        except (KeyboardInterrupt, OSError):
            pass
        finally:
            try:
                send({"type": "reset"})
            except OSError:
                pass
            stopped.set()
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            receiver.join(timeout=2)
            pygame.quit()
        if error:
            raise ConnectionError(error)


if __name__ == "__main__":
    try:
        main()
    except ImportError as error:
        raise SystemExit(f"Missing dependency: {error}. Run python -m pip install --user -r requirements.txt.")
    except OSError as error:
        raise SystemExit(f"Connection failed: {error}. Check the target is running, its IP, and TCP port 5050 access.")
    except KeyboardInterrupt:
        pass
