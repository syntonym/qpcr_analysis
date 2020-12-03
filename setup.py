from setuptools import setup, find_packages
from os import path
from os.path import splitext
from glob import glob

here = path.abspath(path.dirname(__file__))

with open("menqu/__init__.py", "r") as f:
    for line in f:
        if line.startswith("__version__"):
            version = line.strip().split("=")[1].strip(" '\"")
            break
    else:
        version = "0.0.1"

# Get the long description from the README file
with open(path.join(here, "README.md"), encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="menqu",
    version=version,
    description="qPCR analysis",
    long_description=long_description,
    author="Simon Haendeler",
    author_email="simon@haend.de",
    packages=find_packages(exclude=["examples", "contrib", "docs", "tests"]),
    include_package_data=True,
    entry_points="""
    [console_scripts]
    menqu-analysis=menqu.analysis:main
    menqu=menqu.plot:main
    """,
    # This are the versions I tested with, but if you know what you do you can also change these for compatibility reasons
    install_requires=["xlwings", "colr", "click", "pandas", "zmq", "bokeh", "pywebview", "selenium", "wheel"],
    extras_require={"SVG export": []},
)
