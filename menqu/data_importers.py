from menqu.analysis import prepare, _main, parse_well, get_sample_data, _update, metadata_from_pandas, data_matrix_from_pandas, _main_csv
import numpy as np
import pandas

def calculate_data(data, name):
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

    condition_data, conditions = get_sample_data(self._analysisbook)

    data =  {"gene_data": gene_data, "condition_data": None, "conditions": None, "genes": genes, "samples":samples, "colors":colors, "name":name}

class ExcelImporter:

    async def prepare(self):
        self._app, self._databook, self._analysisbook = prepare()

    async def get_sample_data(self):
        if self._analysisbook is not None:
            self.condition_data, self.conditions = get_sample_data(self._analysisbook)

    #name = ".".join(self._databook.fullname.split(".")[:-1])
    def import_(self, excluded_wells):
        self.data = data = _main(self._app, self._databook, self._analysisbook, excluded_wells)
        return data

class CSVImporter:

    def read_meta(self, path):
        self.path_meta = path
        df_meta = pandas.read_csv(self.path_meta)
        self.well_to_identifier, self.well_to_gene = metadata_from_pandas(df_meta)

        list_of_genes = list(self.well_to_gene.values())
        self.genes = list(set(list_of_genes))
        self.genes.sort(key=list_of_genes.index)

        print(self.genes)

    def import_(self, excluded_wells, housekeeping):
        df = pandas.read_csv(self.path_data)
        data_matrix = data_matrix_from_pandas(df, self.well_to_gene, self.well_to_identifier, {housekeeping: "HK"}, excluded_wells)
        data = _main_csv(data_matrix)
