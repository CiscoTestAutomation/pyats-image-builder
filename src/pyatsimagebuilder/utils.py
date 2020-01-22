import os
import sys
import ssl
import git
import shutil
import ftplib
import pathlib
import subprocess


def copy(fro, to):
    # Copy either a single file or an entire directory
    fro = pathlib.Path(fro).expanduser()
    to = pathlib.Path(to).expanduser()
    if fro.is_file():
        shutil.copy(fro, to)
    elif fro.is_dir():
        shutil.copytree(fro, to)
    else:
        raise OSError('Cannot copy %s' % fro)


def scp(host, from_path, to_path, port=None):
    # scp file or dir. Must have passwordless ssh set up.
    scp_cmd = 'scp -B -r '
    if port:
        scp_cmd += '-P %s ' % port
    scp_cmd += '%s:%s %s' % (host, from_path, to_path)
    p = subprocess.Popen(scp_cmd,
                         stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT,
                         shell=True)
    return_code = p.wait()
    if return_code != 0:
        raise Exception('Could not scp %s' % from_path)
    return return_code


def ftp_retrieve(host, from_path, to_path, port=None, secure=False):
    if secure:
        ftp = ftplib.FTP_TLS(
                context=ssl.create_default_context())
    else:
        ftp = ftplib.FTP()
    host = (host, port) if port else (host,)
    ftp.connect(*host)
    ftp.login()
    with open(to_path, 'wb') as f:
        ftp.retrbinary('RETR ' + from_path, f.write, 1024)
    ftp.close()


def git_clone(url, path, commit_id=None, rm_git=False):
    # Clone the repo
    repo = git.Repo.clone_from(url, path)

    if commit_id:
        # If given a commit_id, switch to that commit
        commit = repo.commit(commit_id)
        repo.head.reference = commit
        repo.head.reset(index=True, working_tree=True)

    # Get the hexsha of the current commit
    hexsha = repo.head.commit.hexsha

    if rm_git:
        # Delete the .git dir to save space after checking out
        shutil.rmtree(repo.git_dir)

    return hexsha
