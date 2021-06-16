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
from bokeh.models import Column, FactorRange, ColumnDataSource, BooleanFilter, CDSView, Row, ColorPicker, DataTable, TableColumn, TextInput, Div, Button
from bokeh.models.widgets.tables import HTMLTemplateFormatter
from bokeh.models.callbacks import CustomJS

import menqu
from menqu.helpers import apply_theme, general_mapper
from menqu.themes import CONDITIONS_THEME
from menqu.analysis import parse_well
import asyncio

import numpy as np

MIN_BORDER_LEFT = 100

class ButtonBar:

    def __init__(self, root, app):
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
        button_import.on_click(lambda: asyncio.ensure_future(self.app._import()))
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

class WithConditions:

    def draw_conditions(self, xaxis, condition_data):
        p = figure(x_range=xaxis, frame_height=25*len(self._conditions), frame_width=self._width*len(self._samples), toolbar_location=None, y_range=self._conditions)
        apply_theme(p, CONDITIONS_THEME)

        for condition in self._conditions:
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

    def __init__(self, root, gene_data, condition_data, samples, genes, conditions, color_pickers={}):
        self._gene_data = gene_data
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

        self._root_widget = Column()
        self._draw()

        root.children.append(self._root_widget)

    def redraw(self):
        self._root_widget.children = []
        self._draw()

    def _draw(self):
        self._xrange = FactorRange(factors=self._samples)
        for gene in self._genes:
            p = figure(frame_width=self._width*len(self._samples), frame_height = self._height*2, x_range=self._xrange, title=gene)
            p.xaxis.visible = False
            mask = np.array(self._gene_data["Gene"]) == gene
            x_values = np.array(self._gene_data["Sample"])[mask]
            rs =  [np.array(self._gene_data[replicate], dtype=np.float)[mask] for replicate in [f"R{i}" for i in range(1, len(self._gene_data)-2)]]
            p.vbar(x=x_values, top=np.array(self._gene_data["mean"])[mask], bottom=0, fill_color="black", line_color="black", fill_alpha=0.5, width=0.8)
            for r in rs:
                p.circle(x=x_values, y=r, color="black")

            stacked_data = np.stack(rs)
            mean = np.nanmean(stacked_data, axis=0)
            std = np.nanstd(stacked_data, axis=0)

            #whisker = Whisker(source=ColumnDataSource({"Sample": self._samples, "mean+var": mean+std, "mean-var": mean-std}), base="Sample", upper="mean+var", lower="mean-var")
            #p.add_layout(whisker)

            p.min_border_left = MIN_BORDER_LEFT

            self._root_widget.children.append(p)

        p = self.draw_conditions(self._xrange, self._condition_data)
        self._root_widget.children.append(p)

class HeatmapGraphs(WithConditions):

    def __init__(self, root, gene_data, condition_data, samples, genes, conditions, color_pickers={}):
        self._gene_data = gene_data
        self._condition_data = condition_data
        self._genes = genes
        self._conditions = conditions
        self._samples = samples

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
        for gene in self._genes:
            mask = np.array(self._gene_data["Gene"]) == gene
            data = np.array(self._gene_data["mean"])[mask]
            if len(data) > 0:
                m = np.max(data)
            else:
                m = 0
            maxvalues[gene] = m
        return maxvalues

    def _draw_everything(self):

        self._maxvalues = self._calculate_maxvalues()

        self._xrange = FactorRange(factors=self._samples)

        p_heatmap = self.draw_heatmap(self._xrange, self._gene_data, self._genes)
        p_cond = self.draw_conditions(self._xrange, self._condition_data)

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
                frame_width=self._width*len(self._samples),
                frame_height=self._height*len(self._genes),
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

class ColorPickers:

    def __init__(self, root, columns=8, conditions=tuple(), colors={}, app=None):
        self.app = app
        self._conditions = conditions.copy()
        self.colors = colors
        self._root_widget = Column()
        self._columns = columns
        self.color_pickers = {}
        root.children.append(self._root_widget)

        self._redraw_conditions()

    def _update_color(self, condition, attr, old, new):
        self.colors[condition] = new
        self.app.save_colors()

    def _redraw_conditions(self):
        self._root_widget.children = []
        current_row = Row()
        cond_idx = 0
        for cond in self._conditions:
            cp = ColorPicker(color=self.colors.get(cond, "blue"), title=cond, width=60)
            cp.on_change("color", lambda attr, old, new: self._update_color(cond, attr, old, new))
            self.color_pickers[cond] = cp
            if cond_idx == self._columns:
                self._root_widget.children.append(current_row)
                current_row = Row()
            current_row.children.append(cp)
        self._root_widget.children.append(current_row)

class Table:

    def __init__(self, root, gene_data, condition_data, samples, genes, conditions, color_pickers={}):
        self._gene_data = gene_data
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

        self._root_widget = Column()
        self._draw()

        root.children.append(self._root_widget)

    def redraw(self):
        self._root_widget.children = []
        self._draw()

    def _draw(self):
        d = self._gene_data

        for condition in self._conditions:
            d[condition] = [self._condition_data[condition][self._condition_data["Sample"].index(sample)] for sample in d["Sample"] if sample in self._condition_data["Sample"]]

        template_update_1 = '<% if (value === "True") {print(\'<div style="height: 20px; width: 20px; background-color:'
        template_update_2 = ';"></div>\')} %>'
        def make_template(color):
            return template_update_1 + str(color) + template_update_2

        template_update_1_esc = template_update_1.replace("'", "\\'")
        template_update_2_esc = template_update_2.replace("'", "\\'")

        formatters = [HTMLTemplateFormatter(template=make_template(color=self._color_pickers[cond].color)) for cond in self._conditions]



        condition_columns = [TableColumn(field=cond, title=cond, formatter=form, width=10) for cond, form in zip(self._conditions, formatters)]
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
