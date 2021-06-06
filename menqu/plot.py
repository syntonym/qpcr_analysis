import multiprocessing
import time
from bokeh.transform import linear_cmap, factor_cmap, transform
from bokeh.palettes import Viridis256
from bokeh.core.properties import value
from bokeh.models import Plot, Tabs, Panel, ColorPicker
from bokeh.plotting.figure import Figure
from bokeh.io.export import export_svg
import json
import webview
import threading
import asyncio
import pathlib
import zmq
import zmq.asyncio

import menqu
from menqu.helpers import apply_theme
from menqu.themes import CONDITIONS_THEME

from menqu.analysis import prepare, _main, parse_well, get_sample_data, _update
from menqu.widgets import BarGraphs, HeatmapGraphs, ColorPickers, Table
from menqu.updater import update, needs_update
import click
import sys
import os.path
import appdirs
import logging

NAME = 'AD20A7_D10.5'
EXCEL_AREA = 'A1:M1000'
CACHE_DIR = appdirs.user_cache_dir("menqu")
CACHE_FILE = os.path.join(CACHE_DIR, "cache")

from menqu.helpers import get_app, get_analysisbook, map_show, plot_data, export_as_svg, show
import numpy as np
import pickle
import pandas
import os.path
from functools import wraps

from bokeh.models import Row, Column,  TextInput, Div, Button, ColorPicker, CheckboxGroup, Grid, ColumnDataSource, CustomJSTransform
from bokeh.layouts import layout, grid
from bokeh.server.server import Server
from bokeh.plotting import figure
from bokeh.models import ColumnDataSource, Whisker, FactorRange, CDSView, BooleanFilter

def mutate_bokeh(f):
    def wrapped(self, *args, **kwargs):
        self._doc.add_next_tick_callback(lambda: f(self, *args, **kwargs))
    return wrapped





def get_fake_data():
    gene_data = {"R1": np.array([1, 2, 4, 4]),
            "R2": np.array([2, 1, 4, 4]),
            "R3":np.array([1, 2, 4, 4]),
            "Sample": ["1", "1", "2", "2"], "Gene":["HOXB", "SHO", "HOXB", "SHO"]}

    gene_data["mean"] = (gene_data["R1"] + gene_data["R2"] + gene_data["R3"]) / 3

    condition_data = {"Sample": ["1", "2"],
            "groß": ["True", "False"],
            "schnell": ["False", "True"],
            "rot": ["True", "True"]
            }

    conditions = ["groß", "schnell", "rot"]
    genes = ["HOXB", "SHO"]
    samples = ["1", "2"]

    colors = {"groß": "red", "schnell": "blue", "rot":"green"}

    gene_data["R1"] = gene_data["R1"].tolist()
    gene_data["R2"] = gene_data["R2"].tolist()
    gene_data["R3"] = gene_data["R3"].tolist()

    name = "TestData1"

    return {"gene_data": gene_data, "condition_data": condition_data, "conditions": conditions, "genes": genes, "samples":samples, "colors":colors, "name":name}

def get_fake_data2():
    gene_data = {"R1": np.array([1, 2, 4, 4, 5, 2]),
            "R2": np.array([2, 1, 4, 4, 5, 2]),
            "R3":np.array([1, 2, 4, 4, 5, 2]),
            "Sample": ["1", "1", "2", "2", "pluri", "pluri"], "Gene":["A", "B", "A", "B", "A", "B"]}

    gene_data["mean"] = (gene_data["R1"] + gene_data["R2"] + gene_data["R3"]) / 3

    condition_data = {"Sample": ["1", "2", "pluri"],
            "beating": ["True", "False", "True"],
            "3D": ["False", "True", "False"],
            }

    conditions = ["beating", "3D"]
    genes = ["A", "B"]
    samples = ["1", "2", "pluri"]

    colors = {"beating": "#AAAA00", "3D": "blue"}

    name = "TestData2"

    return {"gene_data": gene_data, "condition_data": condition_data, "conditions": conditions, "genes": genes, "samples":samples, "colors":colors, "name":name}

def load_from_menqu(data, filename):
    with open(filename, mode="rb") as f:
        data = pickle.load(f)
    assert data["version"] == 1
    return data["data"]

class WellExcluder:

    def __init__(self, root):
        self._root = root
        self._tp = TextInput()
        self._root_widget = Column(Div(text="Wells to Exclude"), self._tp)

        root.children.append(self._root_widget)

    def get_excluded_wells(self):
        return [parse_well(well.strip()) if well.strip() else None for well in self._tp.value.split(",")]

class App:

    def __init__(self):
        self.data = get_fake_data()
        colors = self._load_colors()
        gene_data = self.data["gene_data"]
        condition_data = self.data["condition_data"]
        conditions = self.data["conditions"]
        genes = self.data["genes"]
        samples = self.data["samples"]
        colors.update(self.data["colors"])
        
        self._importer_step = 0

        self.socket = None

        _buttons = []
        BUTTON_WIDTH = 100

        button_save = Button(label="Save", width=BUTTON_WIDTH)
        button_save.on_click(lambda: asyncio.ensure_future(self.save_file_dialog()))
        _buttons.append(button_save)

        button_load = Button(label="Load", width=BUTTON_WIDTH)
        button_load.on_click(lambda: asyncio.ensure_future(self.load_file_dialog()))
        _buttons.append(button_load)

        button_export = Button(label="Export", width=BUTTON_WIDTH)
        button_export.on_click(lambda: asyncio.ensure_future(self.export_file_dialog()))
        _buttons.append(button_export)

        button_exit = Button(label="Exit", width=BUTTON_WIDTH, name="ExitButton")
        button_exit.on_click(lambda: asyncio.ensure_future(self.exit()))
        _buttons.append(button_exit)

        button_import = Button(label="Import from Excel", width=200)
        button_import.on_click(lambda: asyncio.ensure_future(self._import()))
        _buttons.append(button_import)

        button_ordering = Button(label="Reimport Graph Ordering", width=200)
        button_ordering.on_click(lambda: asyncio.ensure_future(self._import_graph_ordering()))
        _buttons.append(button_ordering)

        button_update = Button(label="Update", width=200)
        button_ordering.on_click(lambda: asyncio.ensure_future(self.update()))
        update_needed, self._update_url = needs_update(menqu.__version__)
        if update_needed:
            _buttons.append(button_update)

        self.tools_container = Row()
        self.plot_container = Column()
        self.wells_container = Column()
        self.bargraphs_container = Column()
        self.table_container = Column()
        self._tabs = Tabs(tabs=[
                    Panel(child=self.plot_container, title="Heatmap"),
                    Panel(child=self.bargraphs_container, title="Bargraphs"),
                    Panel(child=self.table_container, title="Table")
                    ])
        self._main_column = Column(
                Div(text="", height=100), 
                Row(Div(text="", width=100), self.tools_container),
                Div(text="", height=100), 
                Row(Div(text="", width=100), 
                    self._tabs
                    )
                )

        self.root = Column(
                Row(*_buttons), 
                self._main_column)

        self.colorpickers = ColorPickers(self.tools_container, conditions=conditions, colors=colors, app=self)
        self.heatmap = HeatmapGraphs(self.plot_container, gene_data, condition_data, samples, genes, conditions, color_pickers=self.colorpickers.color_pickers)
        self.well_excluder = WellExcluder(self.wells_container)

        self.bargraphs = BarGraphs(self.bargraphs_container, gene_data, condition_data, samples, genes, conditions, color_pickers=self.colorpickers.color_pickers)

        self.table = Table(self.table_container, gene_data, condition_data, samples, genes, conditions, color_pickers=self.colorpickers.color_pickers)

        self._socket_in_use = False

        self._doc = None

    def _get_suggested_name(self):
        name = self.data["name"]
        if "-" in name:
            name = name.split("-")[0]
        name = name.replace("/", "_")
        return name 

    async def save_file_dialog(self):
        if self.socket and not self._socket_in_use:
            self._socket_in_use = True
            name = self._get_suggested_name().encode("utf-8")
            await self.socket.send(b"SAVE" + name)
            file = await self.socket.recv()
            self._socket_in_use = False

            if file != b"":
                self.save_to_menqu(file)

    async def load_file_dialog(self):
        if self.socket and not self._socket_in_use:
            self._socket_in_use = True
            await self.socket.send(b"LOAD")
            file = await self.socket.recv()
            self._socket_in_use = False

            if file != b"":
                self.load_from_menqu(file)

    async def export_file_dialog(self):
        if self.socket and not self._socket_in_use:
            self._socket_in_use = True
            await self.socket.send(b"EXPORT")
            file = await self.socket.recv()
            self._socket_in_use = False

            if file != b"":
                self.export_as_svg(file)

    async def exit(self):
        if self.socket and not self._socket_in_use:
            self._socket_in_use = True
            await self.socket.send(b"EXIT")
            file = await self.socket.recv()
            self._socket_in_use = False

            sys.exit(0)

    async def update(self):
        if self._update_url != None:
            update(self._update_url)

    def save_colors(self):
        pathlib.Path(CACHE_DIR).mkdir(parents=True, exist_ok=True)
        colors = self._load_colors()
        colors.update(self.colorpickers.colors)
        self._save_colors(colors)

    def load_colors(self):
        colors = self._load_colors()
        self.colorpickers.colors.update(colors)

    def _save_colors(self, colors):
        with open(CACHE_FILE, mode="wb") as f:
            pickle.dump(colors, f)

    def _load_colors(self):
        colors = {}
        try:
            with open(CACHE_FILE, mode="rb") as f:
                colors = pickle.load(f)
        except Exception:
            pass
        return colors

    def load_data(self, data):
        self.data = data
        self.load_data_to_plots()

    @mutate_bokeh
    def load_data_to_plots(self):
        gene_data = self.data["gene_data"]
        condition_data = self.data["condition_data"]
        conditions = self.data["conditions"]
        genes = self.data["genes"]
        samples = self.data["condition_data"]["Sample"]
        colors = self._load_colors()
        colors.update(self.data["colors"])

        self.colorpickers._conditions = conditions
        self.colorpickers.colors = colors
        self.colorpickers._redraw_conditions()
        self.heatmap._color_pickers = self.colorpickers.color_pickers

        self.heatmap._gene_data = gene_data
        self.heatmap._condition_data = condition_data
        self.heatmap._genes = genes
        self.heatmap._conditions = conditions
        self.heatmap._samples = samples

        self.heatmap.redraw()

        self.bargraphs._gene_data = gene_data
        self.bargraphs._condition_data = condition_data
        self.bargraphs._genes = genes
        self.bargraphs._conditions = conditions
        self.bargraphs._samples = samples

        self.bargraphs.redraw()

        self.table._gene_data = gene_data
        self.table._condition_data = condition_data
        self.table._genes = genes
        self.table._conditions = conditions
        self.table._samples = samples

        self.table.redraw()

    def save_to_menqu(self, filename):
        self._get_color_data()
        with open(filename, mode="wb") as f:
            pickle.dump({"version":1, "data": self.data}, f)

    def _get_color_data(self):
        for name, cp in self.colorpickers.color_pickers.items():
            self.data["colors"][name] = cp.color

    def load_from_menqu(self, name):
        with open(name, mode='rb') as f:
            data = pickle.load(f)
        self.load_data(data["data"])

    @mutate_bokeh
    def export_as_svg(self, filename):
        p = self._tabs.tabs[self._tabs.active].child
        self._change_backend_to_svg(p)
        export_svg(p, filename=filename)

    def _change_backend_to_svg(self, p):
        if hasattr(p, "children"):
            for child in p.children:
                self._change_backend_to_svg(child)
        if type(p) == Figure:
            p.output_backend = "svg"

    async def _import(self):
        if self._importer_step == 0:
            self._import_step1()
            self._importer_step = 1
        elif self._importer_step == 1:
            self._import_step2()
            self._importer_step = 0

    @mutate_bokeh
    def _import_step1(self):
        self.root.children.remove(self._main_column)
        self.root.children.append(self.wells_container)

        self._app, self._databook, self._analysisbook = prepare()

    @mutate_bokeh
    def _import_step2(self):
        self.root.children.append(self._main_column)
        self.root.children.remove(self.wells_container)

        excluded_wells = self.well_excluder.get_excluded_wells()

        data = _main(self._app, self._databook, self._analysisbook, excluded_wells)

        means = []
        samples = []
        genes = []
        max_repititions = max(len(x.data) for x in data)
        repitions = [[] for x in range(max_repititions)]
        for m in data:
            mean = np.sum(2**-x for x in m.data if x is not None) / np.sum(1 for x in m.data if x is not None)
            for i, x in enumerate(m.data):
                repitions[i].append(2**-x if x is not None else None)
            for i in range(len(m.data), max_repititions):
                repitions[i].append(None)

            means.append(mean)
            samples.append(str(m.identifier))
            genes.append(m.gene_name)

        gene_data = {"mean":means, "Sample":samples, "Gene": genes, **{"R"+str(i+1) : d for i, d in enumerate(repitions)}}

        samples_found = set()
        samples = []
        for x in gene_data["Sample"]:
            if x in samples_found:
                continue
            samples.append(x)
            samples_found.add(x)

        colors = {}
        genes = list(set(gene_data["Gene"]))
        name = ".".join(self._databook.fullname.split(".")[:-1])

        condition_data, conditions = get_sample_data(self._analysisbook)

        data =  {"gene_data": gene_data, "condition_data": condition_data, "conditions": conditions, "genes": genes, "samples":samples, "colors":colors, "name":name}
        self.load_data(data)

    async def _import_graph_ordering(self):
        condition_data, conditions = get_sample_data(self._analysisbook)
        self.data["condition_data"] = condition_data
        self.data["conditions"] = conditions

        self.load_data(self.data)
    
    def transform(self, doc):
        doc.add_root(self.root)
        self._doc = doc

    def load_fake_data_1(self):
        data = get_fake_data()
        self.load_data(data)

    def load_fake_data_2(self):
        data = get_fake_data2()
        self.load_data(data)

def start_py_web_view(port, bokeh_server):
    window = webview.create_window('menqu', 'http://localhost:5006/')

    web_view_thread = WebViewThread(window, port)

    window.closing += bokeh_server.stop
    window.closing += web_view_thread.stop

    webview.start()

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

def _main_pywebview():
    PORT = 21934

    webview = BokehServer(PORT)
    webview.start()

    #webview.join()

    time.sleep(0.3)

    start_py_web_view(PORT, webview)

@click.command()
@click.option("--update/--no-update", default=True)
def main(update):
    try:
        if update:
            _update()
    except:
        logging.exception()
    _main_pywebview()

if __name__ == "__main__":
    main()
