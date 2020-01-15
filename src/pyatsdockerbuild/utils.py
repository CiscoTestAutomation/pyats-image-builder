import os
import sys
import shutil
import pathlib
import subprocess


def run_cmd(*args, **kwargs):
    p = subprocess.Popen(*args,
                         shell=True,
                         **kwargs)
    return_code = p.wait()
    return return_code

def copy(fro, to):
    fro = pathlib.Path(fro)
    to = pathlib.Path(to)
    if fro.is_file():
        shutil.copy(fro, to)
    elif fro.is_dir():
        shutil.copytree(fro, to)
    else:
        raise FileNotFoundError('Cannot copy %s' % fro)
