import math
import sys
from collections import namedtuple
from colr import color as make_color
import click
import os
import tempfile
import pickle

from os.path import join as pjoin
from menqu.updater import needs_update, update
import menqu


Measurement = namedtuple("Measurement", ["data", "gene_name", "gene_type", "identifier"])
alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

@click.command()
@click.option("--update/--no-update", default=True)
def main(update):
    if update:
        _update()
    app, databook, analysisbook = prepare()
    excludes = input('Which data should be excluded due to funky melt curves? (Ex: 9A) ').split(",")
    excluded_wells = [parse_well(well.strip()) if well.strip() else None for well in excludes]

    _main(app, databook, analysisbook, excluded_wells)

def _update():
    update_needed, url = needs_update(menqu.__version__)
    if update_needed:
        update(url)

def save_as_pickle(obj, name):
    with open(name, mode="wb") as f:
        pickle.dump(obj, f)

def _main(app, databook, analysisbook, excluded_wells):
    color_mapping = read_gene_mapping(analysisbook)
    gene_order = read_gene_order(analysisbook)

    identifier_mapping = read_setup(analysisbook, color_mapping) 
    data = read_data(databook, color_mapping, identifier_mapping, excluded_wells)

    check_data_validity(data)
    data = sorted(data, key=lambda m: (str(m.gene_type) if m.gene_type else '', str(m.gene_name) if m.gene_name else '', str(m.identifier).zfill(4) if m.identifier else ''))

    data = [m for m in data if any(m.data)]

    name = pjoin(tempfile._get_default_tempdir(), "mendjan.pickle")
    print(name)
    save_as_pickle({"color_mapping": color_mapping, "identifier_mapping": identifier_mapping, "data": data}, name)

    write_to_sheet(data, analysisbook.sheets['Excluded'], color_mapping)

    housekeeping = calculate_housekeeping_normalisation(data)
    print(housekeeping)
    data = normalize_housekeeping(data, housekeeping)

    delta_data = data.copy()

    write_to_sheet(data, analysisbook.sheets['DeltaCT'], color_mapping)

    pluripotent = calculate_pluripotent_normalisation(data)
    data = normalize_pluripotent(data, pluripotent)

    deltadelta_data = data.copy()

    write_to_sheet(data, analysisbook.sheets['DDCT'], color_mapping)

    write_results(delta_data, deltadelta_data, analysisbook.sheets['Foldchange'])

    print('Finished working.')
    def get_sorting_key(measurement):
        return gene_order.index(measurement.gene_name)
    data = sorted(data, key=get_sorting_key)


    return data

def measurement_to_list(m, max_fields=0):
    return [m.gene_name, m.gene_type, m.identifier, *m.data, *[None for x in range(max_fields - 3 - len(m.data))]]

def write_to_sheet(data, sheet, color_mapping=None):
    max_fields = max([len(measurement_to_list(m)) for m in data])
    values = [["Name", "Type", "Sample", *["R" + str(i) for i in range(1, max_fields +1 - 3)]]]
    for m in data:
        values.append(measurement_to_list(m, max_fields))
    sheet.range((1,1), (max_fields, len(values))).value = values

    colors = []
    if color_mapping:
        inverse_color_mapping = {value[0]: key for key, value in color_mapping.items()}
        for m in data:
            color = inverse_color_mapping.get(m.gene_name, None)
            for _ in range(max_fields):
                colors.append(color)
        colors.append(color)

    if len(values) > 1:
        i = 0
        for color, cell in zip(colors, sheet.range((2,1), (len(values)-1, max_fields))):
            cell.color = color
            if i == 9:
                i = 0
                print('.', end='')
            i += 1 
        print()

def get_app():
    import xlwings
    if len(xlwings.apps) != 1:
        print('Too many excel applications open, i can only handle one, please close the other ones.')

    app = list(xlwings.apps)[0]

    return app

def get_databook(app):
    candidates = []
    for book in app.books:
     sheets = [sheet.name for sheet in book.sheets]
     if 'SYBR' in sheets:
      candidates.append(book)
      databook=book
      break
    else:
     print('Failed to identify databook. Aborting.')
     sys.exit(-1)
    if len(candidates) > 1:
        print('Found too many data books, aborting.')
        sys.exit(-1)
    print(f'Identified databook:        {book.name}')
    return databook

def get_analysisbook(app):
    candidates = []
    for book in app.books:
     sheets = [sheet.name.strip() for sheet in book.sheets]
     print(sheets)
     if "Set Up" in sheets:
      candidates.append(book)
      analysisbook=book
      break
    if len(candidates) > 1:
        print('Found too many analysis books, aborting.')
        sys.exit(-1)
    if len(candidates) == 0:
        print("Found no analysis book, aborting. Check if you opened the analysis book in excel. The analysis book should have a 'Set Up' sheet and a 'Genes' sheet.")
        sys.exit(-1)
    return analysisbook

def flatten_list_of_lists(l):
    return [x for ll in l for x in ll]

def read_setup(analysisbook, color_mapping):

    plate_setup_sheet = analysisbook.sheets['Set Up']
    plate_setup = plate_setup_sheet['B2:Y17']

    plate_setup_width = len(plate_setup.columns)

    identifier_mapping = {}

    cell_values = plate_setup.value

    for cell, value in zip(plate_setup, flatten_list_of_lists(cell_values)):
        color = cell.color
        identifier_mapping[(cell.row-2, cell.column-2)] = (str(value), color)
        if color not in color_mapping.keys():
            print(f'Unknown color in excel cell {cell.row}, {cell.column}: {make_color(color, color)} with value {value}')

    return identifier_mapping

def read_gene_order(analysisbook):
    gene_setup = analysisbook.sheets["Gene Order"]
    gene_template = gene_setup.range("A1:A20")
    gene_order = []

    for cell in gene_template:
        name = cell.value
        if name is None:
            break
        gene_order.append(name)


    return gene_order

def read_gene_mapping(analysisbook):
    gene_setup = analysisbook.sheets["Set Up"]
    gene_template = gene_setup.range("A21:C100")

    color_mapping = {}
    cells = iter(gene_template)
    while True:
        cell1 = next(cells)
        color = cell1.color
        cell2 = next(cells)
        name = cell2.value
        if name is None and color is None:
            break
        cell3 = next(cells)
        gene_type = str(cell3.value) if cell3.value is not None else None
        if name or gene_type:
            color_mapping[color] = (name, gene_type)
    print("Detected the following genes/colorcodes:")
    for color, (name, gene_type) in color_mapping.items():
        print(make_color(name + " " + (gene_type if gene_type else ""), fore=color))

    return color_mapping

def check_data_validity(data):
    invalid_data = False
    for measurement in data:
        if type(measurement.identifier) == float:
            if math.modf(measurement.identifier)[0] != 0.0:
                invalid_data = True
                print(f'Invalid measurement: {measurement}')
                print('If the identifier is messed up (i.e. a float) try restarting excel. Sometimes excel randomly returns invalid data.')
    if invalid_data:
        print('Detected invalid data. Aborting.')
        sys.exit(-1)
                
def read_data(databook, color_mapping, identifier_mapping, excluded_wells):


    well_to_gene = {}
    data_per_gene = {}
    data_matrix = []

    for row, number in enumerate(range(4, 65, 4)):
     datatransfer = databook.sheets['SYBR'].range(f'C{number}:Z{number}')

     for column, cell in enumerate(datatransfer):
      data = cell.value
      if data == None:
       data = 40
      if parse_well(excel_to_well(cell.row, cell.column)) in excluded_wells:
          data = None
      #filled_data.append(data)

      identifier, color = identifier_mapping.get((row, column), (None, None))
      if color is None:
          gene_type, gene_name = None, None
      else:
          try:
              gene_name, gene_type = color_mapping[color]
          except KeyError:
              gene_type, gene_name = None, None
      measurements_per_gene = data_per_gene.get((gene_name, gene_type), {}) 
      measurements = measurements_per_gene.get(identifier, [])
      measurements.append(data)
      data_per_gene[(gene_name, gene_type)] = measurements_per_gene
      measurements_per_gene[identifier] = measurements

    for gene, measurements_per_gene in data_per_gene.items():
         gene_name, gene_type = gene
         for identifier, measurements in measurements_per_gene.items():
             if gene_name is None and gene_type is None:
                 continue
             data_matrix.append(Measurement(measurements, gene_name,  gene_type , identifier))
    #data_matrix.append(Measurement(filled_data[0], filled_data[1], filled_data[2], gene_name, gene_type, identifier))
    filled_data = []

    return data_matrix

def parse_well(well):
    if len(well) == 2:
        if well[0].isalpha():
            row = well[0]
            column = int(well[1])
        else:
            column = int(well[0])
            row = well[1]
    elif len(well) == 3:
        if well[0].isalpha():
            row = well[0]
            column = int(well[1:3])
        else:
            column = int(well[0:2])
            row = well[2]
    else:
        raise Exception(f"Couldn't understand well {well}.")
    return row.upper(), column
    row = alphabet.index(row.upper())
    return row, column

def well_to_excel(row, column):
    row = alphabet.index(row.upper()) +1
    return row, column

def excel_to_well(cell_row, cell_column):
    character = alphabet[int((cell_row - 4) / 4)]
    number = cell_column - 2
    return (character, number)

def mean(l):
    ll = [x for x in l if x is not None]
    return sum(ll) / len(ll)

def calculate_housekeeping_normalisation(data):
    norms = {}
    for m in data:
        if m.gene_type == 'HK':
            norms[m.identifier] = mean(m.data)
    norms['water'] = 0
    return norms

def normalize_housekeeping(data, housekeeping):
    r = []
    for m in data:
        if m.identifier:
            r.append(Measurement([x - housekeeping[m.identifier] if x is not None else None for x in m.data ], m.gene_name, m.gene_type, m.identifier))
    return r

def calculate_pluripotent_normalisation(data):
    norms = {}
    for m in data:
        if m.identifier == 'pluri':
            print(f'Processing {m.gene_name} pluri')
            try:
                norms[m.gene_name] = mean(m.data)
            except ZeroDivisionError as e:
                print('Could not calculate pluri average, is every pluri excluded?')
                sys.exit(1)
    return norms

def normalize_pluripotent(data, pluripotent):
    r = []
    print(pluripotent)
    for m in data:
        if m.identifier:
            r.append(Measurement([x - pluripotent[m.gene_name] if x is not None else None for x in m.data ], m.gene_name, m.gene_type, m.identifier))
    return r

def get_sort_key(row):
    if row[0] == 'pluri':
        return ''
    else:
        return str(row[0]).zfill(5)

def write_results(deltadata, deltadeltadata, sheet):
    values = []

    max_fields = max([len(m.data)+1 for m in deltadata])

    values = [["Name", "Type", "Sample", *["DCT [Foldchange] R" + str(i) for i in range(1, max_fields +1 - 3)], "", *["DDCT [Foldchange] R" + str(i) for i in range(1, max_fields +1 - 3)]]]

    results = {}
    for m in deltadata:
        gene = results.get(m.gene_name, {})
        gene[m.identifier] = [m.gene_name, m.gene_type, m.identifier, *[2**-x if x is not None else None for x in m.data], *[None for x in range(max_fields-1-len(m.data))]]
        results[m.gene_name] = gene

    for m in deltadeltadata:
        results[m.gene_name][m.identifier].append("")
        for x in m.data:
            results[m.gene_name][m.identifier].append(2**-x if x is not None else None)
        for x in range(max_fields-1-len(m.data)):
            results[m.gene_name][m.identifier].append(None)

    values = [value for gene in results.values() for value in sorted(gene.values(), key=get_sort_key)]

    sheet.range("A1:G100").value = values

def prepare():
    import xlwings
    app = get_app()
    print('Connected to Excel.')
    print('We now try to find your data and your template')
    databook = get_databook(app)
    print()
    print(f"Detected data in   {databook.name}")
    print()
    analysisbook = get_analysisbook(app)
    print(f'Detected setup     {analysisbook.name}.')
    print()

    return app, databook, analysisbook

def parse_condition(v):
    if v:
        v = v.strip()
    return "True" if v == "+" else "False"

def get_sample_data(analysisbook):
    values = analysisbook.sheets["Identifying samples"].range("A1:Z100").value

    conditions = [str(x) for x in values[0] if x is not None]
    condition_data = {condition: [] for condition in conditions}
    for line in values[1:]:
        if line[0] == None:
            break
        for cond, v in zip(conditions, line):
            if cond != "Sample":
                if (v.strip() == '+') if type(v) == str else False:
                    v = 'True'
                else:
                    v = 'False'

            condition_data[cond].append(str(v))

    conditions = conditions[1:]

    return condition_data, conditions

if __name__ == "__main__":
    main()
