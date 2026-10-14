import io
import json
import os
import socket
import struct
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

from PIL import Image
import host
import target


def jpeg():
    buffer = io.BytesIO()
    Image.new("RGB", (320, 180), (200, 50, 20)).save(buffer, "JPEG")
    return buffer.getvalue()


class ProtocolTests(unittest.TestCase):
    def test_fragmented_frame(self):
        frame = jpeg()
        class FragmentedSocket:
            data = struct.pack("!I", len(frame)) + frame
            def recv(self, size):
                chunk, self.data = self.data[:min(size, 3)], self.data[min(size, 3):]
                return chunk
        self.assertEqual(host.receive_frame(FragmentedSocket()), frame)

    def test_invalid_frame_size_and_truncated_frame(self):
        for packet, error in [(struct.pack("!I", 0), ValueError),
                              (struct.pack("!I", host.MAX_FRAME_BYTES + 1), ValueError),
                              (struct.pack("!I", 10) + b"abc", ConnectionError)]:
            sender, receiver = socket.socketpair()
            with sender, receiver:
                sender.sendall(packet)
                sender.shutdown(socket.SHUT_WR)
                with self.assertRaises(error):
                    host.receive_frame(receiver)

    def test_letterboxing_and_mouse_coordinates(self):
        rect = host.view_rect((1000, 700), (1920, 1080))
        self.assertEqual(rect, (0, 69, 1000, 562))
        self.assertIsNone(host.position((500, 10), rect))
        self.assertEqual(host.position((0, 69), rect), {"x": 0, "y": 0})
        self.assertEqual(host.position((999, 630), rect), {"x": 1, "y": 1})

    def test_modifier_and_unsupported_key_names(self):
        self.assertEqual(host.key_name("left ctrl"), "ctrlleft")
        self.assertEqual(host.key_name("left shift"), "shiftleft")
        self.assertEqual(host.key_name("[1]"), "1")
        self.assertIsNone(host.key_name("unknown key"))

    def test_capture_encode_transmit_decode(self):
        stopped = threading.Event()
        class Capture:
            monitors = [None, {"width": 320, "height": 180}]
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def grab(self, monitor):
                class Shot:
                    size = (320, 180)
                    rgb = Image.new("RGB", size, (200, 50, 20)).tobytes()
                return Shot()
        sender, receiver = socket.socketpair()
        with sender, receiver, patch("mss.mss", Capture):
            receiver.settimeout(3)
            thread = threading.Thread(target=target.stream_screen,
                                      args=(sender, stopped, 15, 70, 160))
            thread.start()
            try:
                with Image.open(io.BytesIO(host.receive_frame(receiver))) as image:
                    self.assertEqual(image.size, (160, 90))
                    self.assertEqual(image.format, "JPEG")
                    self.assertGreater(image.getpixel((0, 0))[0], 180)
            finally:
                stopped.set()
                thread.join(3)
            self.assertFalse(thread.is_alive())

    def test_hotkey_order_cleanup_and_ping(self):
        calls = []
        class GUI:
            FAILSAFE = True
            KEYBOARD_KEYS = ["ctrlleft", "shiftleft", "c"]
            def keyDown(self, key): calls.append(("down", key))
            def keyUp(self, key): calls.append(("up", key))
            def size(self): return (1920, 1080)
            def moveTo(self, x, y): pass
            def mouseDown(self, *, button): calls.append(("mouse_down", button))
            def mouseUp(self, *, button): calls.append(("mouse_up", button))
        gui = GUI()
        keys, buttons = set(), set()
        for key in ["ctrlleft", "shiftleft", "c"]:
            target.replay({"type": "key", "key": key, "pressed": True}, gui, keys, buttons)
        target.replay({"type": "button", "button": "left", "pressed": True, "x": .5, "y": .5},
                      gui, keys, buttons)
        target.replay({"type": "ping"}, gui, keys, buttons)
        target.replay({"type": "reset"}, gui, keys, buttons)
        self.assertEqual(calls[:3], [("down", "ctrlleft"), ("down", "shiftleft"), ("down", "c")])
        self.assertIn(("mouse_up", "left"), calls)
        self.assertFalse(keys or buttons)
        self.assertTrue(gui.FAILSAFE)

    def test_invalid_input(self):
        class GUI:
            KEYBOARD_KEYS = ["a"]
        for event in [{"type": "move", "x": float("nan"), "y": 0},
                      {"type": "key", "key": "bad", "pressed": True},
                      {"type": "key", "key": "a", "pressed": "yes"}]:
            with self.assertRaises(ValueError):
                target.replay(event, GUI(), set(), set())


class ViewerTests(unittest.TestCase):
    def test_target_authentication_stream_and_input_over_tcp(self):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        # Exercise the actual target server with only the desktop adapters replaced.
        program = '''
import sys, types
from unittest.mock import patch
from PIL import Image
import target
gui = types.ModuleType("pyautogui")
gui.FAILSAFE = True
gui.FailSafeException = type("FailSafeException", (Exception,), {})
gui.KEYBOARD_KEYS = ["ctrlleft", "c"]
gui.keyDown = lambda key: print("DOWN", key, flush=True)
gui.keyUp = lambda key: print("UP", key, flush=True)
class Capture:
    monitors = [None, {}]
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def grab(self, monitor):
        return types.SimpleNamespace(size=(320, 180), rgb=Image.new("RGB", (320, 180), "red").tobytes())
sys.modules["pyautogui"] = gui
with patch("mss.mss", Capture): target.main()
'''
        process = subprocess.Popen([sys.executable, "-c", program, "--port", str(port)],
                                   env={**os.environ, "REMOTE_CONTROL_TOKEN": "test-token"},
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        try:
            deadline = time.monotonic() + 5
            while True:
                try:
                    connection = socket.create_connection(("127.0.0.1", port), timeout=1)
                    break
                except OSError:
                    if time.monotonic() > deadline:
                        raise
                    time.sleep(.02)
            with connection:
                connection.sendall(b'{"token":"wrong"}\n')
                self.assertEqual(connection.recv(100), b"")
            with socket.create_connection(("127.0.0.1", port), timeout=3) as connection:
                connection.sendall(b'{"token":"test-token"}\n')
                with connection.makefile("rb", buffering=0) as reader:
                    self.assertEqual(reader.readline(), b'{"ok":true}\n')
                with Image.open(io.BytesIO(host.receive_frame(connection))) as frame:
                    self.assertEqual(frame.size, (320, 180))
                for key in ["ctrlleft", "c"]:
                    connection.sendall((json.dumps({"type": "key", "key": key, "pressed": True}) + "\n").encode())
                connection.sendall(b'{"type":"reset"}\n')
                connection.shutdown(socket.SHUT_WR)
                while connection.recv(4096):
                    pass
        finally:
            process.terminate()
            output, _ = process.communicate(timeout=5)
        for message in ["Rejected unauthenticated connection", "DOWN ctrlleft", "DOWN c", "UP ctrlleft", "UP c"]:
            self.assertIn(message, output)

    def test_real_viewer_render_input_and_focus_loss(self):
        import pygame
        received, errors = [], []
        finished = threading.Event()
        frame = jpeg()
        server = socket.socket()
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        server.settimeout(5)
        port = server.getsockname()[1]

        def serve():
            try:
                with server:
                    connection, _ = server.accept()
                    with connection:
                        connection.settimeout(5)
                        with connection.makefile("rb") as reader:
                            self.assertEqual(json.loads(reader.readline()), {"token": "test-token"})
                            # Auth and frame in a single send catches buffering mistakes.
                            connection.sendall(b'{"ok":true}\n' + struct.pack("!I", len(frame)) + frame)
                            for line in reader:
                                received.append(json.loads(line))
            except Exception as exc:
                errors.append(exc)
            finally:
                finished.set()

        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        loaded = False
        stage = 0
        original_load = pygame.image.load

        def load(*args):
            nonlocal loaded
            loaded = True
            return original_load(*args)

        def events():
            nonlocal stage
            if not loaded:
                return []
            stage += 1
            E = pygame.event.Event
            if stage == 1:
                return [E(pygame.KEYDOWN, key=pygame.K_F8),
                        E(pygame.KEYDOWN, key=pygame.K_LCTRL), E(pygame.KEYDOWN, key=pygame.K_c),
                        E(pygame.MOUSEBUTTONDOWN, button=1, pos=(500, 350))]
            if stage == 2:
                return [E(pygame.WINDOWFOCUSLOST)]
            return [E(pygame.KEYDOWN, key=pygame.K_x), E(pygame.QUIT)]

        with patch.dict(os.environ, {"REMOTE_CONTROL_TOKEN": "test-token"}), \
             patch.object(sys, "argv", ["host.py", "127.0.0.1", "--port", str(port)]), \
             patch.object(pygame.image, "load", side_effect=load), \
             patch.object(pygame.event, "get", side_effect=events), \
             patch.object(pygame.key, "get_focused", return_value=True):
            host.main()
        self.assertTrue(finished.wait(5))
        thread.join(1)
        self.assertFalse(errors, errors)
        self.assertTrue(loaded)
        self.assertIn({"type": "key", "key": "ctrlleft", "pressed": True}, received)
        self.assertIn({"type": "key", "key": "c", "pressed": True}, received)
        self.assertFalse(any(event.get("key") == "x" for event in received))
        self.assertEqual(sum(event["type"] == "reset" for event in received), 3)
        self.assertTrue(any(event["type"] == "button" for event in received))


if __name__ == "__main__":
    unittest.main()
