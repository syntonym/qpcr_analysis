"""Loading and saving data"""

import numpy as np
import pickle

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


def load_from_menqu_file(filename):
    with open(filename, mode="rb") as f:
        data = pickle.load(f)
    assert data["version"] == 1
    return data["data"]

def save_to_menqu_file(data, filename):
    with open(filename, mode="wb") as f:
        pickle.dump({"version":1, "data": data}, f)

