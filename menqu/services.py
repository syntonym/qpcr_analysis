"""
Services that need to be run in seperate threads

We have two main components: The bokeh server (generating plots) and the pywebview (showing the GUI).

Pywebview uses system libraries (qt or gtk on linux) to show a browser window withouth decorations.
It provides functions to interact with the OS like (1) close the window, (2) popup a file saving diolog, 
(3) popup a file loading dialog. The file dialog functions are blocking until the user chooses a file. 

The Bokeh server generates plots which are syncronized via a websocket to the client. Actions on the client side
can trigger callbacks which are processed by the server.

So that the bokeh server and handling the pywebview functions does not interfer with each other, they're running in seperate threads. 
There are three threads: The pywebview GUI thread, the pywebview function handling thread (OSThread) and the Bokeh Server thread (BokehThread). OSThread and BokehThread communicate via a ZMQ socket when necessary (e.g. when exiting and closing).
"""

import threading
import asyncio
import os
import webview
import sys
import time

from menqu.plot import App

import zmq
from bokeh.server.server import Server

class BokehThread(threading.Thread):

    def __init__(self, port):
        self.port = port
        super().__init__()

    def run(self):

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
        """Schedule stopping"""
        self.loop.call_soon_threadsafe(self._stop)

    def _stop(self):
        """Stop the server"""
        self.loop.stop()
        self.context.destroy(linger=0)
        self.context.term()
        self.stop()

class OSThread(threading.Thread):

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

def start_all():
    PORT = 21934

    bokeh_thread = BokehThread(PORT)
    bokeh_thread.start()

    # make sure bokeh started up and bound to port 5006
    time.sleep(0.3)

    window = webview.create_window('menqu', 'http://localhost:5006/')

    web_view_thread = OSThread(window, PORT)
    web_view_thread.start()

    window.closing += bokeh_thread.stop
    window.closing += web_view_thread.stop

    webview.start()
