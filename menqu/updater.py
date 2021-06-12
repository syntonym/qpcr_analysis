""" 
All function relating to updating menqu

Menqu checks by default every time it is called whether a new version is available.
This is performed by calling `needs_update(current_version)`, which checks github to see if a version with a bigger
version number is available and returns whether an update is available and the URL to the newest version.
The `update(url)` function can then download the newest version from that URL and restarts menqu.
"""

import requests
import os
import sys
import logging
import subprocess

def _get_latest_release():
    response = requests.get("https://api.github.com/repos/syntonym/qpcr_analysis/releases/latest").json()
    return response["tag_name"], response["assets"][0]["browser_download_url"]

def _parse_semver(ver: str) -> list[int]:
    return [int(x) for x in ver.split(".")]

def _semver_bigger_then(a: list[int], b: list[int]):
    for ai, bi in zip(a, b):
        if ai > bi:
            return True
        elif ai < bi:
            return False
    return False

def needs_update(current_version):
    """Checks whether a newer verison then the passed `current_version` is available.

    Return a tuple, the first item is a boolean indicating whether a newer version is available, 
    the second entry item is None or the URL at which the newer verison is available. 

    This function requires internet access, if case of any exceptions this function will default 
    to return that no update is necessary. Currently there is no way to know whether no update is
    neccessary or whether asking for updates failed.
    """
    try:
        latest, download_url = _get_latest_release()
        latest = _parse_semver(latest)
    except Exception as e:
        logging.exception(e)
        return (False, None)

    try:
        if _semver_bigger_then(latest, _parse_semver(current_version)):
            return (True, download_url)
    except Exception as e:
        logging.exception(e)
    return (False, None)

def update(url):
    """Download a new menqu version from `url` and relaunch menqu"""
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-U", url, "--user"])
    args = [arg for arg in sys.argv[:]]
    print('Re-spawning %s' % ' '.join(args))
    args.insert(0, sys.executable)
    if sys.platform == 'win32':
        args = ['"%s"' % arg for arg in args]

    os.execv(sys.executable, args)


