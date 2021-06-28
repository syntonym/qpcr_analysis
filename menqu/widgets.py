"""
Bokeh is used to visualize data. It's building blocks are models, which are
syncronized with the client browser. As far as I found there is no support for
building more complex widgets from building blocks. This module contains classes
which generate bokeh models from data when calling `_draw()`. It populates a `_root_widget` 
container, which is added as a child to a passed container. When data changes `redraw()` 
has to be called, which mutates the `_root_widget`.
"""

from bokeh.plotting import figure
from bokeh.palettes import Viridis256
from bokeh.core.properties import value
from bokeh.transform import linear_cmap
from bokeh.models import Column, FactorRange, ColumnDataSource, BooleanFilter, CDSView, Row, ColorPicker, DataTable, TableColumn, TextInput, Div, Button, Tabs, Panel, Dropdown
from bokeh.models.widgets.tables import HTMLTemplateFormatter
from bokeh.models.callbacks import CustomJS

import menqu
from menqu.helpers import apply_theme, general_mapper, mutate_bokeh
from menqu.themes import CONDITIONS_THEME
from menqu.analysis import parse_well
from menqu.data_importers import ExcelImporter, CSVImporter
import asyncio

import numpy as np
from collections import defaultdict

MIN_BORDER_LEFT = 100

class Widget:

    def __init__(self, data):
        self._data = data
        self._links = defaultdict(list)

    def update(self, d):
        # update this widget
        for dataname, datavalue in d.items():
            self._data[dataname] = datavalue

        # update the child widget with all data it needs in one go
        for child_widget, data_names in self._links.items():
            child_widget.update({data_name: d[data_name] for data_name in data_names if data_name in d})

    def link(self, widget, dataname):
        self._links[widget].append(dataname)

class RootWidget(Widget):

    def __init__(self, app, data):
        super().__init__(data)
        self.app = app
        #self._data = {"gene_data": gene_data, "condition_data": condition_data, "samples": samples, "conditions": conditions, "colors":colors}

        self.tools_container = Row()
        self.plot_container = Column()
        self.wells_container = Column()
        self.bargraphs_container = Column()
        self.table_container = Column()
        self.importer_container = Column()
        self.importer_csv_container = Column()

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

        self.root = Column()
        self._button_bar = ButtonBar(self.root, app, self)
        self.root.children.append(self._main_column)

        self.colorpickers = ColorPickers(self.tools_container, {"conditions": data["conditions"], "colors": data["colors"]}, app=self)
        self.link(self.colorpickers, "conditions")
        self.link(self.colorpickers, "colors")

        self.heatmap = HeatmapGraphs(self.plot_container, data, color_pickers=self.colorpickers.color_pickers)

        self.bargraphs = BarGraphs(self.bargraphs_container, data, color_pickers=self.colorpickers.color_pickers)

        self.table = Table(self.table_container, data, color_pickers=self.colorpickers.color_pickers)

        self.excel_importer = ExcelImportWidget(self.importer_container, app, self)

        self.csv_importer = CSVImportWidget(self.importer_csv_container, app, self, {"genes": data["genes"]})

        for widget in [self.heatmap, self.bargraphs, self.table]:
            for data_name in data:
                self.link(widget, data_name)

        self.link(self.csv_importer, "genes")

    def show_excel_importer(self):
        self.root.children.remove(self._main_column)
        self.root.children.append(self.importer_container)

    def show_csv_importer(self):
        if self._main_column in self.root.children:
            self.root.children.remove(self._main_column)
        self.root.children.append(self.importer_csv_container)

    def show_main(self):
        if self.importer_container in self.root.children:
            self.root.children.remove(self.importer_container)
        if self.importer_csv_container in self.root.children:
            self.root.children.remove(self.importer_csv_container)
        self.root.children.append(self._main_column)

class ButtonBar(Widget):

    def __init__(self, root, app, root_widget):
        super().__init__({})
        self.app = app

        _buttons = []
        BUTTON_WIDTH = 100

        button_save = Button(label="Save", width=BUTTON_WIDTH)
        button_save.on_click(lambda: asyncio.ensure_future(self.app.save_file_dialog()))
        _buttons.append(button_save)

        button_load = Button(label="Load", width=BUTTON_WIDTH)
        button_load.on_click(lambda: asyncio.ensure_future(self.app.load_file_dialog()))
        _buttons.append(button_load)

        button_export = Button(label="Export", width=BUTTON_WIDTH)
        button_export.on_click(lambda: asyncio.ensure_future(self.app.export_file_dialog()))
        _buttons.append(button_export)

        button_exit = Button(label="Exit", width=BUTTON_WIDTH, name="ExitButton")
        button_exit.on_click(lambda: asyncio.ensure_future(self.app.exit()))
        _buttons.append(button_exit)

        button_import = Button(label="Import from Excel", width=200)
        button_import.on_click(root_widget.show_excel_importer)
        _buttons.append(button_import)

        button_import = Button(label="Import from CSV", width=200)
        button_import.on_click(root_widget.show_csv_importer)
        _buttons.append(button_import)

        button_ordering = Button(label="Reimport Graph Ordering", width=200)
        button_ordering.on_click(lambda: asyncio.ensure_future(self.app._import_graph_ordering()))
        _buttons.append(button_ordering)

        button_update = Button(label="Update", width=200)
        button_ordering.on_click(lambda: asyncio.ensure_future(self.app.update()))
        update_needed, self._update_url = self.app.update_needed()
        if update_needed:
            _buttons.append(button_update)

        self._root_widget = Row(children=_buttons)
        root.children.append(self._root_widget)

class WithConditions(Widget):

    def draw_conditions(self, xaxis, condition_data):
        p = figure(x_range=xaxis, frame_height=25*len(self._data["conditions"]), frame_width=self._width*len(self._data["samples"]), toolbar_location=None, y_range=self._data["conditions"])
        apply_theme(p, CONDITIONS_THEME)

        for condition in self._data["conditions"]:
            default_color = "black"
            if condition in self._color_pickers:
                cp = self._color_pickers[condition]
                default_color = cp.color

            fill_alpha = general_mapper(condition, [0, 1], ["False", "True"])
            r = p.rect(x="Sample", y=value(condition), fill_alpha=fill_alpha, line_alpha=fill_alpha, source=condition_data, width=0.8, height=0.8, color=default_color)

            if condition in self._color_pickers:
                cp.js_link("color", r.glyph, "fill_color")
                cp.js_link("color", r.glyph, "line_color")

        p.grid.visible = False
        p.min_border_left = MIN_BORDER_LEFT
        p.xaxis.major_label_orientation = "vertical"

        self._condition_plot = p

        return p

class BarGraphs(WithConditions):

    def __init__(self, root, data, color_pickers={}):
        super().__init__(data)

        self._color_pickers = color_pickers

        self._maxvalue = max(max(self._data["gene_data"]["R1"]), max(self._data["gene_data"]["R2"]), max(self._data["gene_data"]["R3"]))
        self._width = 25
        self._height = 25
        self._linear_color_mapper = None

        self._condition_height = 25

        self._root_widget = Column()
        self._draw()

        root.children.append(self._root_widget)

    def redraw(self):
        self._root_widget.children = []
        self._draw()

    def _draw(self):
        self._xrange = FactorRange(factors=self._data["samples"])
        for gene in self._data["genes"]:
            p = figure(frame_width=self._width*len(self._data["samples"]), frame_height = self._height*2, x_range=self._xrange, title=gene)
            p.xaxis.visible = False
            mask = np.array(self._data["gene_data"]["Gene"]) == gene
            x_values = np.array(self._data["gene_data"]["Sample"])[mask]
            rs =  [np.array(self._data["gene_data"][replicate], dtype=np.float)[mask] for replicate in [f"R{i}" for i in range(1, len(self._data["gene_data"])-2)]]
            p.vbar(x=x_values, top=np.array(self._data["gene_data"]["mean"])[mask], bottom=0, fill_color="black", line_color="black", fill_alpha=0.5, width=0.8)
            for r in rs:
                p.circle(x=x_values, y=r, color="black")

            stacked_data = np.stack(rs)
            mean = np.nanmean(stacked_data, axis=0)
            std = np.nanstd(stacked_data, axis=0)

            #whisker = Whisker(source=ColumnDataSource({"Sample": self._samples, "mean+var": mean+std, "mean-var": mean-std}), base="Sample", upper="mean+var", lower="mean-var")
            #p.add_layout(whisker)

            p.min_border_left = MIN_BORDER_LEFT

            self._root_widget.children.append(p)

        p = self.draw_conditions(self._xrange, self._data["condition_data"])
        self._root_widget.children.append(p)

class HeatmapGraphs(WithConditions):

    def __init__(self, root, data, color_pickers={}):
        super().__init__(data)

        self._color_pickers = color_pickers

        self._width = 25
        self._height = 25
        self._linear_color_mapper = None

        self._condition_height = 25

        self._root_widget = Column()
        self._draw_everything()

        root.children.append(self._root_widget)


    def redraw(self):
        self._root_widget.children = []
        self._draw_everything()

    def _calculate_maxvalues(self):
        maxvalues = {}
        for gene in self._data["genes"]:
            mask = np.array(self._data["gene_data"]["Gene"]) == gene
            data = np.array(self._data["gene_data"]["mean"])[mask]
            if len(data) > 0:
                m = np.max(data)
            else:
                m = 0
            maxvalues[gene] = m
        return maxvalues

    def _draw_everything(self):

        self._maxvalues = self._calculate_maxvalues()

        self._xrange = FactorRange(factors=self._data["samples"])

        p_heatmap = self.draw_heatmap(self._xrange, self._data["gene_data"], self._data["genes"])
        p_cond = self.draw_conditions(self._xrange, self._data["condition_data"])

        self._root_widget.children.append(p_heatmap)
        self._root_widget.children.append(p_cond)

    def draw_heatmap(self, xaxis, source, genes):
        cds = ColumnDataSource(source)

        TOOLTIPS = [
                ("Sample", "@Sample"),
                ("Gene", "@Gene"),
                ("Foldchange", "@mean"),
                ]
        p = figure(x_range=xaxis,
                y_range=FactorRange(factors=genes),
                frame_width=self._width*len(self._data["samples"]),
                frame_height=self._height*len(self._data["genes"]),
                tooltips=TOOLTIPS)

        self._heatmap_plot = p

        p.xaxis.visible = False
        p.min_border_left = MIN_BORDER_LEFT
        for gene in genes:
            view = CDSView(source=cds, filters=[BooleanFilter([x == gene for x in source["Gene"]])])
            color = linear_cmap('mean', Viridis256, low=0, high=self._maxvalues.get(gene, 1))
            self._linear_color_mapper = color["transform"]
            p.rect(x='Sample', y='Gene', width=1, height=1, color=color, source=cds, view=view)

        return p

class ColorPickers(Widget):

    def __init__(self, root, data, columns=8, app=None):
        super().__init__(data)
        self.app = app
        self._root_widget = Column()
        self._columns = columns
        self.color_pickers = {}
        root.children.append(self._root_widget)

        self._redraw_conditions()

    def _update_color(self, condition, attr, old, new):
        self._data["colors"][condition] = new
        self.app.save_colors()

    def _redraw_conditions(self):
        self._root_widget.children = []
        current_row = Row()
        cond_idx = 0
        for cond in self._data["conditions"]:
            cp = ColorPicker(color=self._data["colors"].get(cond, "blue"), title=cond, width=60)
            cp.on_change("color", lambda attr, old, new: self._update_color(cond, attr, old, new))
            self.color_pickers[cond] = cp
            if cond_idx == self._columns:
                self._root_widget.children.append(current_row)
                current_row = Row()
            current_row.children.append(cp)
        self._root_widget.children.append(current_row)

class Table(Widget):

    def __init__(self, root, data, color_pickers={}):
        super().__init__(data)
        self._color_pickers = color_pickers

        self._maxvalue = max(max(self._data["gene_data"]["R1"]), max(self._data["gene_data"]["R2"]), max(self._data["gene_data"]["R3"]))
        self._width = 25
        self._height = 25
        self._linear_color_mapper = None

        self._condition_height = 25

        self._root_widget = Column()
        self._draw()

        root.children.append(self._root_widget)

    def redraw(self):
        self._root_widget.children = []
        self._draw()

    def _draw(self):
        d = self._data["gene_data"]

        for condition in self._data["conditions"]:
            d[condition] = [self._data["condition_data"][condition][self._data["condition_data"]["Sample"].index(sample)] for sample in d["Sample"] if sample in self._data["condition_data"]["Sample"]]

        template_update_1 = '<% if (value === "True") {print(\'<div style="height: 20px; width: 20px; background-color:'
        template_update_2 = ';"></div>\')} %>'
        def make_template(color):
            return template_update_1 + str(color) + template_update_2

        template_update_1_esc = template_update_1.replace("'", "\\'")
        template_update_2_esc = template_update_2.replace("'", "\\'")

        formatters = [HTMLTemplateFormatter(template=make_template(color=self._color_pickers[cond].color)) for cond in self._data["conditions"]]



        condition_columns = [TableColumn(field=cond, title=cond, formatter=form, width=10) for cond, form in zip(self._data["conditions"], formatters)]
        columns = [
                TableColumn(field="Sample", title="Sample", width=200),
                TableColumn(field="Gene", title="Gene", width=10),
                TableColumn(field="R1", title="R1"),
                TableColumn(field="R2", title="R2"),
                TableColumn(field="R3", title="R3"),
                *condition_columns
                ]

        dt = DataTable(source=ColumnDataSource(d), columns=columns, width_policy="fit")

        code = f"form.template = '{template_update_1_esc}' + cp.color + '{template_update_2_esc}'; dt.change.emit();"

        for cp, formatter, col in zip(self._color_pickers.values(), formatters, condition_columns):
            cp.js_on_change("color", CustomJS(args={"cp": cp, "col":col, "form": formatter, "dt": dt}, code=code))

        self._root_widget.children.append(dt)

        dt.source.patch({})

class WellExcluder:

    def __init__(self, root):
        self._tp = TextInput()
        self._root_widget = Column(Div(text="Wells to Exclude"), self._tp)

        root.children.append(self._root_widget)

    def get_excluded_wells(self):
        return [parse_well(well.strip()) if well.strip() else None for well in self._tp.value.split(",")]

class ExcelImportWidget(Widget):

    def __init__(self, root, app, root_widget):
        super().__init__({})
        self.app = app

        BUTTON_WIDTH = 100
        self._title = Div(text="Excel Importer")
        self._button_back = Button(label="Back", width=BUTTON_WIDTH)
        self._button_back.on_click(root_widget.show_main)

        self._button = Button(label="Import", width=BUTTON_WIDTH)
        self._button.on_click(lambda: asyncio.ensure_future(self.import_))

        self._button_bar = Row(self._button_back, self._button)

        self._root_widget = Column(self._button_bar, self._title)

        self.well_excluder = WellExcluder(self._root_widget)
        root.children.append(self._root_widget)

        self._importer = ExcelImporter()

    async def import_(self):
        excluded_wells = self.well_excluder.get_excluded_wells()
        self._importer.prepare()
        data = self._importer.import_(excluded_wells)
        self.app.load_data(data)

class HKSelector(Widget):

    def __init__(self, root, app, data):
        super().__init__(data)
        self.app = app
        self.root_widget = Dropdown(label="Housekeeping Gene", menu=[("X", "X")])
        self.value = None
        root.children.append(self.root_widget)

        self.root_widget.on_click(self.on_click)

        self.update(data)

    def update(self, d):
        print("Updating HKSelector")
        super().update(d)
        self.root_widget.menu = [(x, x) for x in self._data["genes"]]
        if self.value not in self._data["genes"]:
            self.set_value(None)

    def set_value(self, value):
        self.value = value
        if value:
            self.root_widget.label = value
            self.root_widget.button_type = "success"
        else:
            self.root_widget.label = "Housekeeping Gene"
            self.root_widget.button_type = "warning"

    def on_click(self, event):
        self.set_value(event.item)

    def get_housekeeping(self):
        return self.value


class CSVImportWidget(Widget):

    def __init__(self, root, app, root_widget, data):
        super().__init__(data)
        self.app = app

        BUTTON_WIDTH = 100
        self._title = Div(text="CSV Importer")
        self._button_back = Button(label="Back", width=BUTTON_WIDTH)
        self._button_back.on_click(root_widget.show_main)

        self._button = Button(label="Import", width=BUTTON_WIDTH)
        self._button.on_click(lambda: asyncio.ensure_future(self.import_()))

        self._button_genes = Button(label="Import Genes", width=BUTTON_WIDTH)
        self._button_genes.on_click(lambda: asyncio.ensure_future(self.import_genes()))

        self._button_bar = Row(self._button_back, self._button_genes, self._button)



        self.hk_selector_container = Row()
        self.hk_selector = HKSelector(self.hk_selector_container, app, data)
        self.link(self.hk_selector, "genes")
        print(self._links)

        self._root_widget = Column(self._button_bar, self._title, self.hk_selector_container)
        self.well_excluder = WellExcluder(self._root_widget)
        root.children.append(self._root_widget)

        self._importer = CSVImporter()

    async def import_genes(self):
        path = await self.app._load_file_dialog()
        print(path)
        if path is not None and path != b"":
            meta = self._importer.read_meta(path.decode("utf-8"))
            self.app.update_data({"genes": self._importer.genes})

    async def import_(self):
        housekeeping = self.hk_selector.get_housekeeping()
        excluded_wells = self.well_excluder.get_excluded_wells()
        path = await self.app._load_file_dialog()
        self._importer.path_data = path.decode("utf8")
        data = self._importer.import_(excluded_wells, housekeeping)
        self.app.load_data(data)
