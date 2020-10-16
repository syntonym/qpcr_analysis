
NAME = 'AD20A7_D10.5'
EXCEL_AREA = 'A1:M1000'

from .helpers import get_app, get_analysisbook, map_show, plot_data, export_as_svg, show
import numpy as np
import pickle
import pandas
import os.path

from bokeh.models import Row, Column,  TextInput, Div, Button
from bokeh.layouts import layout
from bokeh.server.server import Server

def bkapp(doc):

    data_name = NAME + '.pickle'
    if os.path.exists(data_name):
        with open(data_name, mode='rb') as f:
            data = pickle.load(f)
    else:
        app = get_app()
        analysisbook = get_analysisbook(app)
        data = analysisbook.sheets['GraphOrdering'].range(EXCEL_AREA).value
        data = pandas.DataFrame(data[1:], columns=data[0])
        data['Sample'] = np.array([str(x) for x in data['Sample']])
        data['Sample_show'] = np.array([map_show(x) for x in data['Sample']])
        with open(data_name, mode='wb') as f:
            pickle.dump(data, f)


    genes = [x for x in data["Gene"].unique() if x is not None]#takes each unique gene and put in a list
    samples = [str(x) for x in data['Sample'].unique() if x is not None and x is not 'None']#take each unique sample sample #
    conditions = data['Sample'].unique()#this is calling the codndions for the y axis on the legend plot
    conditions = list(data.columns)#make the list the right way
    conditions.remove('Sample')
    conditions.remove('R1')
    conditions.remove('R2')
    conditions.remove('R3')
    conditions.remove('Gene')
    conditions.remove('Sample_show')
    samples.remove('None')



    colors = {'Cell Line':'Black',
              'SHF':'#124be6',
              'FHF':'#e69c12',
              'CHSBRA':'#800000',
              'XAVSBRA':'#48a10d',
              'CH4':'#1a83b8',
             'CH6':'#BCC2C2',
             'CH8':'#757575',
             'Density':'Black',
             'Collection':'Black',
             'D1.5-D3.5':'Black',
             'A50':'#beaec2',
             'FGF':'#ff7700',
             'Insulin':'#00f587',
             'CH1.5 D5':'#1a83b8'}

    root = Column()
    doc.add_root(root)

    color_children = []

    def get_colors():
        button = Button(label="Continue")
        button.on_click(from_colors_to_text_conditions)
        color_children.append(button)
        for condition in conditions:
            default_color = colors.get(condition, "")
            color_children.append(Div(text=condition), TextInput(text=default_color))

        root.children.append(layout(children=color_children))

    text_conditions = [
        "Cell Line",
        'Density',
        'Collection',
        'D1.5-D3.5']

    def from_colors_to_text_conditions():
        global colors
        colors = {div.text: textinput.text for div, textinput in color_children}
        while len(root.chlidren) > 0:
            root.children.pop()
        cont()


    def cont():

        #makes a plot for each gene
        for gene in genes:
            plots = plot_data(data.loc[data["Gene"] == gene], conditions, title=gene, xaxis=samples, colors=colors, text_conditions=text_conditions)
            root.children.append(plots)
            #show(plots)

    if False:
        #makes a plot for each gene
        for gene in genes:
            plots = plot_data(data.loc[data["Gene"] == gene], conditions, title=gene, xaxis=samples, colors=colors)
            export_as_svg(plots, NAME+gene)



def main():


    # Setting num_procs here means we can't touch the IOLoop before now, we must
    # let Server handle that. If you need to explicitly handle IOLoops then you
    # will need to use the lower level BaseServer class.
    server = Server({'/': bkapp}, num_procs=4)
    server.start()
    print('Opening Bokeh application on http://localhost:5006/')

    server.io_loop.add_callback(server.show, "/")
    server.io_loop.start()
