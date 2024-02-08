import requests
import os
import sys
import logging
import subprocess

def _get_latest_release():
    response = requests.get("https://api.github.com/repos/syntonym/qpcr_analysis/releases/latest").json()
    return response["tag_name"], response["assets"][0]["browser_download_url"]

def _parse_semver(ver):
    return [int(x) for x in ver.split(".")]

def _semver_bigger_then(a, b):
    if a[0] > b[0]:
        return True
    elif a[0] < b[0]:
        return False
    elif a[1] > b[1]:
        return True
    elif a[1] < b[1]:
        return False
    elif a[2] > b[2]:
        return True
    else:
        return False

def needs_update(current_version):
    try:
        latest, download_url = _get_latest_release()
        try:
            latest = _parse_semver(latest)
        except Exception:
            logging.exception()
            return (False, None)
    except requests.exceptions.BaseHTTPError:
        return (False, None)

    try:
        if _semver_bigger_then(latest, _parse_semver(current_version)):
            return (True, download_url)
    except Exception:
        logging.exception()
    return (False, None)

def update(url):
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-U", url, "--user"])
    args = [arg for arg in sys.argv[:]]
    print('Re-spawning %s' % ' '.join(args))
    args.insert(0, sys.executable)
    if sys.platform == 'win32':
        args = ['"%s"' % arg for arg in args]

    os.execv(sys.executable, args)


