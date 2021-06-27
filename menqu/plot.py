import multiprocessing
import time
from bokeh.transform import linear_cmap, factor_cmap, transform
from bokeh.palettes import Viridis256
from bokeh.core.properties import value
from bokeh.models import Plot, Tabs, Panel, ColorPicker
from bokeh.plotting.figure import Figure
from bokeh.io.export import export_svg
import json
import threading
import asyncio
import pathlib
import zmq
import zmq.asyncio

import menqu
from menqu.helpers import apply_theme
from menqu.themes import CONDITIONS_THEME

from menqu.analysis import prepare, _main, parse_well, get_sample_data, _update
from menqu.widgets import BarGraphs, HeatmapGraphs, ColorPickers, Table, WellExcluder, ButtonBar
from menqu.updater import update, needs_update
from menqu.datasources import get_fake_data, get_fake_data2, load_from_menqu_file, save_to_menqu_file
import sys
import os.path
import appdirs
import logging

NAME = 'AD20A7_D10.5'
EXCEL_AREA = 'A1:M1000'
CACHE_DIR = appdirs.user_cache_dir("menqu")
CACHE_FILE = os.path.join(CACHE_DIR, "cache")

from menqu.helpers import get_app, get_analysisbook, map_show, plot_data, export_as_svg, show
from menqu.widgets import RootWidget
import numpy as np
import pickle
import pandas
import os.path
from functools import wraps

from bokeh.models import Row, Column,  TextInput, Div, Button, ColorPicker, CheckboxGroup, Grid, ColumnDataSource, CustomJSTransform
from bokeh.layouts import layout, grid
from bokeh.plotting import figure
from bokeh.models import ColumnDataSource, Whisker, FactorRange, CDSView, BooleanFilter

def mutate_bokeh(f):
    def wrapped(self, *args, **kwargs):
        self._doc.add_next_tick_callback(lambda: f(self, *args, **kwargs))
    return wrapped


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

        data = {"gene_data": gene_data, "condition_data": condition_data, "samples": samples,
                "genes": genes, "conditions": conditions, "colors": colors}
        self.root_widget = RootWidget(self, data)
        self.root = self.root_widget.root


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
                self.load_from_menqu_file(file)

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

    def update_needed(self):
        return needs_update(menqu.__version__)

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
        save_to_menqu_file(self.data, filename)

    def load_from_menqu(self, name):
        data = load_from_menqu_file(name)
        self.load_data(data)

    def _get_color_data(self):
        for name, cp in self.colorpickers.color_pickers.items():
            self.data["colors"][name] = cp.color

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
        self.root_widget.show_wells()

        self._app, self._databook, self._analysisbook = prepare()

    @mutate_bokeh
    def _import_step2(self):
        self.root_widget.show_main()

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

