import multiprocessing
from bokeh.transform import linear_cmap, factor_cmap, transform
from bokeh.palettes import Viridis256
from bokeh.core.properties import value
from bokeh.models import Plot
from bokeh.plotting.figure import Figure
from bokeh.io.export import export_svg
import json
import webview
import threading
import asyncio
import zmq
import zmq.asyncio

from .analysis import prepare, _main, parse_well, get_sample_data

NAME = 'AD20A7_D10.5'
EXCEL_AREA = 'A1:M1000'

from .helpers import get_app, get_analysisbook, map_show, plot_data, export_as_svg, show
import numpy as np
import pickle
import pandas
import os.path
from functools import wraps

from bokeh.models import Row, Column,  TextInput, Div, Button, ColorPicker, CheckboxGroup, Grid, ColumnDataSource, CustomJSTransform
from bokeh.layouts import layout, grid
from bokeh.server.server import Server
from bokeh.plotting import figure
from bokeh.models import ColumnDataSource, Whisker, FactorRange

def mutate_bokeh(f):
    def wrapped(self, *args, **kwargs):
        self._doc.add_next_tick_callback(lambda: f(self, *args, **kwargs))
    return wrapped


def general_mapper(column, mapped_to, to_map):
    m = dict(zip(to_map, mapped_to))
    v_func = """
    const first = xs[0]
    const norm = new Float64Array(xs.length)
    for (let i = 0; i < xs.length; i++) {
        norm[i] = m[xs[i]];
    }
    return norm
    """
    t = CustomJSTransform(args={"m": m}, v_func=v_func)

    return transform(column, t)

def apply_theme(p, theme):
    if "Figure" in theme:
        p.apply_theme(theme["Figure"])
    if "Axis" in theme:
        for axis in p.axis:
            axis.apply_theme(theme["Axis"])
    if "Grid" in theme:
        for grid in p.grid:
            grid.apply_theme(theme["Grid"])

CONDITIONS_THEME = {
    "Axis": {
        "major_label_text_font_size": "18pt",
        "major_label_text_font_style": "bold",
        "major_label_text_color": "black" },
    "Grid": {
        "grid_line_color": None},
}

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
        return [parse_well(well.strip()) if well.strip() else None for well in self._tp.value]


class ColorPickers:

    def __init__(self, root, columns=8, conditions=tuple(), colors={}):
        self._conditions = conditions.copy()
        self._default_colors = colors
        self._root_widget = Column()
        self._columns = columns
        self.color_pickers = {}
        root.children.append(self._root_widget)

        self._redraw_conditions()

    def _redraw_conditions(self):
        self._root_widget.children = []
        current_row = Row()
        cond_idx = 0
        for cond in self._conditions:
            cp = ColorPicker(color=self._default_colors.get(cond, "blue"), title=cond, width=60)
            self.color_pickers[cond] = cp
            if cond_idx == self._columns:
                self._root_widget.children.append(current_row)
                current_row = Row()
            current_row.children.append(cp)
        self._root_widget.children.append(current_row)

class HeatmapGraphs:

    def __init__(self, root, gene_data, condition_data, samples, genes, conditions, color_pickers={}):
        self._gene_data = ColumnDataSource(gene_data)
        self._condition_data = condition_data
        self._genes = genes
        self._conditions = conditions
        self._samples = samples

        self._color_pickers = color_pickers

        self._maxvalue = max(max(gene_data["R1"]), max(gene_data["R2"]), max(gene_data["R3"]))
        self._width = 25
        self._height = 25
        self._linear_color_mapper = None

        self._condition_height = 25

        self._root = Column()
        self._draw_everything()

        root.children.append(self._root)


    def redraw(self):
        self._root.children = []
        self._draw_everything()

    def _draw_everything(self):

        self._xrange = FactorRange(factors=self._samples)

        p_heatmap = self.draw_heatmap(self._xrange, self._gene_data, self._genes)
        p_cond = self.draw_conditions(self._xrange, self._condition_data)

        self._root.children.append(p_heatmap)
        self._root.children.append(p_cond)

    def draw_heatmap(self, xaxis, source, genes):
        p = figure(x_range=xaxis,
                y_range=FactorRange(factors=genes),
                frame_width=self._width*len(self._samples),
                frame_height=self._height*len(self._genes))

        self._heatmap_plot = p

        color = linear_cmap('mean', Viridis256, low=0, high=self._maxvalue)
        self._linear_color_mapper = color["transform"]
        p.xaxis.visible = False
        p.min_border_left = 70

        p.rect(x='Sample', y='Gene', width=1, height=1, color=color, source=source)

        return p

    def draw_conditions(self, xaxis, condition_data):
        p = figure(x_range=xaxis, frame_height=25*len(self._conditions), frame_width=self._width*len(self._samples), toolbar_location=None, y_range=self._conditions)
        print(self._conditions)
        apply_theme(p, CONDITIONS_THEME)

        for condition in self._conditions:
            default_color = "black"
            if condition in self._color_pickers:
                cp = self._color_pickers[condition]
                default_color = cp.color

            fill_alpha = general_mapper(condition, [0, 1], ["True", "False"])
            r = p.rect(x="Sample", y=value(condition), fill_alpha=fill_alpha, line_alpha=fill_alpha, source=condition_data, width=0.8, height=0.8, color=default_color)

            if condition in self._color_pickers:
                cp.js_link("color", r.glyph, "fill_color")
                cp.js_link("color", r.glyph, "line_color")

        p.grid.visible = False
        p.min_border_left = 70

        self._condition_plot = p

        return p

class App:

    def __init__(self):
        self.data = get_fake_data2()
        gene_data = self.data["gene_data"]
        condition_data = self.data["condition_data"]
        conditions = self.data["conditions"]
        genes = self.data["genes"]
        samples = self.data["samples"]
        colors = self.data["colors"]
        
        self._importer_step = 0

        self.socket = None

        button_save = Button(label="Save")
        button_save.on_click(lambda: asyncio.ensure_future(self.save_file_dialog()))

        button_load = Button(label="Load")
        button_load.on_click(lambda: asyncio.ensure_future(self.load_file_dialog()))

        button_export = Button(label="Export")
        button_export.on_click(lambda: asyncio.ensure_future(self.export_file_dialog()))

        button_import = Button(label="Import from Excel")
        button_import.on_click(lambda: asyncio.ensure_future(self._import()))

        button_ordering = Button(label="Reimport Graph Ordering")
        button_ordering.on_click(lambda: asyncio.ensure_future(self._import_graph_ordering()))

        self.tools_container = Row()
        self.plot_container = Column()
        self.wells_container = Column()
        self._main_column = Column(
                Div(text="", height=100), 
                Row(Div(text="", width=100), self.tools_container),
                Div(text="", height=100), 
                Row(Div(text="", width=100), self.plot_container))
        self.root = Column(
                Row(button_load, button_save, button_export, button_import, button_ordering), 
                self._main_column)

        self.colorpickers = ColorPickers(self.tools_container, conditions=conditions, colors=colors)
        self.heatmap = HeatmapGraphs(self.plot_container, gene_data, condition_data, samples, genes, conditions, color_pickers=self.colorpickers.color_pickers)
        self.well_excluder = WellExcluder(self.wells_container)

        self._socket_in_use = False

        self._doc = None

    async def save_file_dialog(self):
        if self.socket and not self._socket_in_use:
            self._socket_in_use = True
            await self.socket.send(b"SAVE")
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

    @mutate_bokeh
    def load_data(self, data):
        self.data = data
        gene_data = self.data["gene_data"]
        condition_data = self.data["condition_data"]
        conditions = self.data["conditions"]
        genes = self.data["genes"]
        samples = self.data["samples"]
        colors = self.data["colors"]

        self.colorpickers._conditions = conditions
        self.colorpickers._default_colors = colors
        self.colorpickers._redraw_conditions()
        self.heatmap._color_pickers = self.colorpickers.color_pickers

        self.heatmap._gene_data = gene_data
        self.heatmap._condition_data = condition_data
        self.heatmap._genes = genes
        self.heatmap._conditions = conditions
        self.heatmap._samples = samples

        self.heatmap.redraw()

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
        p = self.plot_container
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

        excluded_wells = self.wells_container.get_excluded_wells()

        data = _main(self._app, self._databook, self._analysisbook, excluded_wells)

        means = []
        samples = []
        genes = []
        repitions = [[] for x in data[0].data]
        for m in data:
            mean = np.sum(2**-x for x in m.data if x is not None) / np.sum(1 for x in m.data if x is not None)
            for i, x in enumerate(m.data):
                repitions[i].append(2**-x if x is not None else None)

            means.append(mean)
            samples.append(m.identifier)
            genes.append(m.gene_name)

        gene_data = {"mean":means, "Sample":samples, "Gene": genes}
        samples = list(set(gene_data["Sample"]))
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

def start_py_web_view(port):
    window = webview.create_window('menqu', 'http://localhost:5006/')

    webview.start(func=start_zmq_window_server, args=(window, port))

def start_zmq_window_server(window, port):
    context = zmq.Context()
    socket = context.socket(zmq.REP)
    socket.bind(f"tcp://127.0.0.1:{port}")

    while True:
        msg = socket.recv()
        if msg == b"SAVE":
            filename = window.create_file_dialog(webview.SAVE_DIALOG, directory=os.getcwd(), save_filename='test.menqu')
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


def start_server(port):
    # Setting num_procs here means we can't touch the IOLoop before now, we must
    # let Server handle that. If you need to explicitly handle IOLoops then you
    # will need to use the lower level BaseServer class.

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    app = App()

    context = zmq.asyncio.Context()
    socket = context.socket(zmq.REQ)
    socket.connect(f"tcp://127.0.0.1:{port}")

    app.socket = socket

    server = Server({'/': app.transform}, num_procs=1)
    server.start()
    #server.io_loop.add_callback(server.show, "/")
    server.io_loop.start()

def main():
    PORT = 21934

    webview = threading.Thread(target=start_server, args=(PORT,), daemon=True)
    webview.start()

    #webview.join()

    start_py_web_view(PORT)



if __name__ == "__main__":
    main()
