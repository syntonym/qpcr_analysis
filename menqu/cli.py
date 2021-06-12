import logging

from menqu.analysis import _update
from menqu.services import start_all

import click

@click.command()
@click.option("--update/--no-update", default=True)
def main(update):
    try:
        if update:
            _update()
    except:
        logging.exception()
    start_all()

if __name__ == "__main__":
    main()
