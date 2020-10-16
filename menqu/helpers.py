from bokeh.plotting import figure
from bokeh.layouts import layout
import sys
from bokeh.models import Whisker, ColumnDataSource, Slope, Span, Row, Column
from bokeh.io import show, output_notebook, export_svgs
from bokeh.core.properties import value
#import xlwings
import pandas
import numpy as np
import numpy as np
import pandas as pd
from bokeh.models import LabelSet, ColumnDataSource
from bokeh.palettes import Category10_10
from bokeh.io import export_svgs
from bokeh.io import export_png

def save(obj, filename):

    backend = obj.output_backend
    obj.output_backend = "svg"
    export_png(obj, filename + ".png", width=2000, height=2000)
    obj.output_backend = backend

def export_as_svg(figure, name):
    if isinstance(figure, Row) or isinstance(figure, Column):
        for i, p in enumerate(figure.children):
            export_as_svg(p, name+'.'+str(i))
        return
    backend = figure.output_backend
    figure.output_backend = 'svg'
    figure.toolbar_location=None
    export_svgs(figure, filename=name+'.svg')
    figure.output_backend = backend


def get_app():
    if len(xlwings.apps) > 1:
        print('Too many excel applications open, i can only handle one, please close the other ones.')
    elif len(xlwings.apps) < 1:
        print('No excel open, please open the excel sheet.')

    app = list(xlwings.apps)[0]

    return app

def get_analysisbook(app):
    candidates = []
    for book in app.books:
        sheets = [sheet.name for sheet in book.sheets]
        if "Set Up" in sheets and "Genes" in sheets:
            candidates.append(book)
            analysisbook=book
    if len(candidates) > 1:
        print('Found too many analysis books, aborting.')
        sys.exit(-1)
    if len(candidates) == 0:
        print('Found no analysis book, aborting.')
        sys.exit(-1)
    return analysisbook

def map_show(s):
    try:
        float(s)
        return ''
    except:
        return s

def plot_data(data, conditions, xaxis=None, title=None, colors={}, text_conditions=["Cell Line",'Density','Collection']):
    #this is where we define the colors for each condition google color picker (hex codes)

    
    # Prepare Data for plotting
    # Put all repetitions together
    x = np.stack((data['R1'], data['R2'], data['R3']))#identifies the replicates 
    data.loc[:, "mean"] = np.nanmean(x, axis=0)#takes the mean ignoring empty values 

    data.loc[:,"var"] = np.nanstd(x, axis=0) #standard deviation ignoring empty values (to change look up numpy library for your calvulations)
    data.loc[:,"mean-var"] = data["mean"] - data["var"]#calculate the bottom of the error bar
    data.loc[:,"mean+var"] = data["mean"] + data["var"]#calcualte the top of the error bar
    
    if xaxis is None:
        xaxis= data["Sample"]#takes all of the samples


    WIDTH = 900
    source = ColumnDataSource(data)#puts data so the library works
    p = figure(  #makes the figure,
        x_range=xaxis, #generates the xaxis
        width=WIDTH, #width of overall plot where you change it 
        height=200, #height of over all greaph where you change it
        title=title,)#this you change when calling the function
   
    #puts in the individual data points  
    p.circle(source=source, x="Sample", y="R1",fill_color="black",line_color="black")
    p.circle(source=source, x="Sample", y="R2",fill_color="black",line_color="black")
    p.circle(source=source, x="Sample", y="R3",fill_color="black",line_color="black")
    
    
    #this makese the verticle bars of the graph
    p.vbar(x="Sample", #defines what to take at x-coordinate
           top="mean",#determines where the top of the the bar is 
           bottom=0, #defines where the bottom of the bar is
           width=0.6, #defines the width of the bar
           source=source, #defines the source of the bars for samples and mean and all the things
           fill_alpha=0.5, #fill of the bar, opaqueness in percent 0-1
           fill_color="black", #color of the fill of the bar
           line_color="black")#color of the outline of the box
    p.add_layout(
    Whisker(source=source, base="Sample", upper="mean+var", lower="mean-var")#this adds the error bars
)
    p.min_border_left = 100
    p.yaxis.major_label_text_font_size='18pt'
    p.yaxis.major_label_text_font_style='bold'
    p.yaxis.major_label_text_color='black'
    p.yaxis.ticker.desired_num_ticks = 3
    
    pp = figure(x_range=p.x_range, #the xrange of the second plot is equal to the x range of the first
                width=WIDTH, #width of the second plot is the same as the width of the first plot
                height=25*len(conditions), #height of the figure is 25* the number of the conditons
                toolbar_location=None, #disabel tool bar
                y_range=conditions)#on the y axis put the conditions in the default position google how to change if you want
    
    for cond in conditions:#this mathches conditions to a color
        if cond in text_conditions:#this is where we add conditions that text should be written
            labels = LabelSet(x='Sample', y=value(cond), text=cond, source=ColumnDataSource(
                data[data[cond].notnull()]
                 ), text_font_size='6pt', text_align='center')
            pp.add_layout(labels)
        else:#this for plus minus conditions
            pp.rect(x="Sample", #makesthe x coordinates the sample
                    y=value(cond), #defines y coordinates
                    width=0.8, #defines the width oght the box 0-1 is the % of the sample area the box takes up (centered)
                    height=0.8, #defines the height same as the width
                    color=colors[cond], #defines the color based on above 
                    source=data[(data[cond] == '+') | (data[cond] == ' +')] )#if the there is the + in the data make box

    #this makes it so none of the axis lines and grids exist on the second plot
    pp.xaxis.axis_label=None
    pp.xaxis.visible=False
    pp.yaxis.axis_line_alpha = 0
    pp.grid.grid_line_color = None
    pp.outline_line_color = None
    pp.min_border_left = 100
    pp.yaxis.major_label_text_font_size='18pt'
    pp.yaxis.major_label_text_font_style='bold'
    pp.yaxis.major_label_text_color='black'
    return layout([p, pp])



