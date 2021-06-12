import threading
import asyncio
import os
import webview
import sys
import time

from menqu.plot import App

import zmq
from bokeh.server.server import Server

class BokehServer(threading.Thread):

    def __init__(self, port):
        self.port = port
        super().__init__()

    def run(self):
        # Setting num_procs here means we can't touch the IOLoop before now, we must
        # let Server handle that. If you need to explicitly handle IOLoops then you
        # will need to use the lower level BaseServer class.

        self.loop = loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        app = App()

        self.context = context = zmq.asyncio.Context()
        self.socket = socket = context.socket(zmq.REQ)
        socket.setsockopt(zmq.LINGER, 1)
        socket.connect(f"tcp://127.0.0.1:{self.port}")

        app.socket = socket

        self.server = server = Server({'/': app.transform}, num_procs=1)
        server.start()
        #server.io_loop.add_callback(server.show, "/")
        server.io_loop.start()

    def stop(self):
        self.loop.call_soon_threadsafe(self._stop)

    def _stop(self):

        self.loop.stop()
        self.context.destroy(linger=0)
        self.context.term()
        self.stop()

class WebViewThread(threading.Thread):

    def __init__(self, window, port):
        super().__init__()
        self.window = window
        self.port = port
        self._stopping = False

    def stop(self):
        self._stopping = True

    def run(self):
        window = self.window
        port = self.port

        context = zmq.Context()
        socket = context.socket(zmq.REP)
        socket.setsockopt(zmq.RCVTIMEO, 1000)
        socket.bind(f"tcp://127.0.0.1:{port}")

        while True:
            if self._stopping:
                break
            try:
                msg = socket.recv()
            except zmq.error.Again:
                continue
            if msg[:4] == b"SAVE":
                suggested_name = msg[4:].decode("utf-8")
                filename = window.create_file_dialog(webview.SAVE_DIALOG, directory=os.getcwd(), save_filename=suggested_name + ".menqu")
                if filename:
                    filename = "".join(filename)
                else:
                    filename = ""
                socket.send(filename.encode("utf-8"))
            elif msg == b"LOAD":
                filename = window.create_file_dialog(webview.OPEN_DIALOG, directory=os.getcwd(), save_filename='test.menqu')
                if filename:
                    filename = "".join(filename)
                else:
                    filename = ""
                socket.send(filename.encode("utf-8"))
            elif msg == b"EXPORT":
                filename = window.create_file_dialog(webview.SAVE_DIALOG, directory=os.getcwd(), save_filename='test.svg')
                if filename:
                    filename = "".join(filename)
                else:
                    filename = ""
                socket.send(filename.encode("utf-8"))
            elif msg == b"EXIT":
                socket.send(b"BYE")
                window.destroy()
                sys.exit(0)

def start_py_web_view(port, bokeh_server):
    window = webview.create_window('menqu', 'http://localhost:5006/')

    web_view_thread = WebViewThread(window, port)

    window.closing += bokeh_server.stop
    window.closing += web_view_thread.stop

    webview.start()

def start_all():
    PORT = 21934

    webview = BokehServer(PORT)
    webview.start()

    #webview.join()

    time.sleep(0.3)

    start_py_web_view(PORT, webview)
