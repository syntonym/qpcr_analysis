# Menqu

Mendjan Lab qPCR analysis script

# Install

Install the script

* `pip3 install https://github.com/syntonym/qpcr_analysis/releases/download/3.2.2/menqu-3.2.2-py3-none-any.whl`

* `echo PATH='$PATH':$HOME/Library/Python/3.9/bin >> ~/.bash_profile`
* `echo export PATH >> ~/.bash_profile`

Then restart your terminal.

You should now be able to execute the script via `menqu`.


For SVG export you also need to install [geckodriver](https://github.com/mozilla/geckodriver) and make sure firefox is available on your command line. One easy way to do that is to install [miniconda](https://docs.conda.io/en/latest/miniconda.html) and execute 

    conda install -c conda-forge firefox geckodriver
