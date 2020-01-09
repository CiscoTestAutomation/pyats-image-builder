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

def get_git_repo(name, url, cwd, checkout=None):
    commitid = None
    cwd = pathlib.Path(cwd)
    repo_dir = cwd / name
    git_dir = repo_dir / '.git'
    env = os.environ.copy()
    print(env)
    # Prevent input prompt on connection to http
    env['GIT_TERMINAL_PROMPT'] = '0'
    # Prevent input prompt on connection to ssh
    env['GIT_SSH_COMMAND'] = 'ssh -oBatchMode=yes'
    return_code = run_cmd('git clone %s %s' % (url, name), cwd=cwd, env=env)
    if return_code == 0 and checkout:
        return_code = run_cmd('git checkout %s' % checkout,
                              cwd=repo_dir, env=env)
    if return_code == 0:
        commitid = subprocess.check_output('git rev-parse --verify HEAD',
                                           shell=True,
                                           cwd=repo_dir).decode().strip()
        shutil.rmtree(git_dir)
    return commitid

def make_ini(data):
    ini = ''
    for key, val in data.items():
        ini += '[%s]\n' % key
        for key, val in val.items():
            ini += '%s =' % key
            if isinstance(val, list):
                ini += '\n'
                ini += '\n'.join(['    %s' % i for i in val])
            else:
                ini += ' %s' % val
            ini += '\n'
        ini += '\n'
    return ini