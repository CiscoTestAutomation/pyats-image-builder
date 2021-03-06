import re
import ssl
import git
import glob
import shutil
import ftplib
import pathlib
import subprocess
import os
import tempfile

PYATS_ANCHOR = 'PYATS_JOBFILE'


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
        ftp = ftplib.FTP_TLS(context=ssl.create_default_context())
    else:
        ftp = ftplib.FTP()
    host = (host, port) if port else (host, )
    ftp.connect(*host)
    ftp.login()
    with open(to_path, 'wb') as f:
        ftp.retrbinary('RETR ' + from_path, f.write, 1024)
    ftp.close()


def git_clone(url,
              path,
              commit_id=None,
              rm_git=False,
              credentials=None,
              ssh_key=None,
              GIT_SSL_NO_VERIFY=False):
    # Clone the repo

    GIT_SSL_NO_VERIFY_old = os.environ.get('GIT_SSL_NO_VERIFY', None)

    if GIT_SSL_NO_VERIFY:
        os.environ['GIT_SSL_NO_VERIFY'] = 'true'

    if credentials:
        # https git credentials provided
        repo = clone_with_credentials(url, path, credentials)
    elif ssh_key:
        # ssh key provided
        repo = clone_with_ssh(url, path, ssh_key)
    else:
        # repo is public
        repo = git.Repo.clone_from(url, path)

    if commit_id:
        # If given a commit_id (could be a branch), switch to it
        repo.git.checkout(commit_id)

    if GIT_SSL_NO_VERIFY_old:
        os.environ['GIT_SSL_NO_VERIFY'] = GIT_SSL_NO_VERIFY_old
    elif GIT_SSL_NO_VERIFY:
        del os.environ['GIT_SSL_NO_VERIFY']

    # Get the hexsha of the current commit
    hexsha = repo.head.commit.hexsha

    if rm_git:
        # Delete the .git dir to save space after checking out
        shutil.rmtree(repo.git_dir)

    return hexsha


def clone_with_credentials(url, path, credentials):

    GIT_ASKPASS_old = os.environ.get('GIT_ASKPASS', None)
    GIT_USERNAME_old = os.environ.get('GIT_USERNAME', None)
    GIT_PASSWORD_old = os.environ.get('GIT_PASSWORD', None)

    os.environ['GIT_ASKPASS'] = "pyats-image-build-askpass"
    os.environ['GIT_USERNAME'] = credentials['username']
    os.environ['GIT_PASSWORD'] = credentials['password']

    repo = git.Repo.clone_from(url, path)

    if GIT_ASKPASS_old:
        os.environ['GIT_ASKPASS'] = GIT_ASKPASS_old
    else:
        del os.environ['GIT_ASKPASS']

    if GIT_USERNAME_old:
        os.environ['GIT_USERNAME'] = GIT_USERNAME_old
    else:
        del os.environ['GIT_USERNAME']

    if GIT_PASSWORD_old:
        os.environ['GIT_PASSWORD'] = GIT_PASSWORD_old
    else:
        del os.environ['GIT_PASSWORD']

    return repo


def clone_with_ssh(url, path, ssh_key):

    # make temp file for ssh_key
    temp = tempfile.NamedTemporaryFile(mode="w")

    # remove all line breaks in ssh_key
    ssh_key = ssh_key.replace('\n', '')
    ssh_key = ssh_key.strip()

    # add needed line breaks to ssh_key

    if "-----BEGIN OPENSSH PRIVATE KEY-----" in ssh_key:
        ssh_key = ssh_key.replace("-----BEGIN OPENSSH PRIVATE KEY-----",
                                  "-----BEGIN OPENSSH PRIVATE KEY-----\n", 1)
    else:
        ssh_key = "-----BEGIN OPENSSH PRIVATE KEY-----\n" + ssh_key

    if "-----END OPENSSH PRIVATE KEY-----" in ssh_key:
        ssh_key = ssh_key.replace("-----END OPENSSH PRIVATE KEY-----",
                                  "\n-----END OPENSSH PRIVATE KEY-----\n", 1)
    else:
        ssh_key = ssh_key + "\n-----END OPENSSH PRIVATE KEY-----\n"

    temp.write(ssh_key)
    temp.seek(0)

    GIT_SSH_COMMAND_old = os.environ.get('GIT_SSH_COMMAND', None)

    if os.environ.get('socks_proxy', None):
        os.environ[
            'GIT_SSH_COMMAND'] = 'ssh -o "StrictHostKeyChecking no" -o "UserKnownHostsFile /dev/null" -o "ProxyCommand nc -x $socks_proxy %h %p" -i {}'.format(
                temp.name)
    else:
        os.environ[
            'GIT_SSH_COMMAND'] = 'ssh -o "StrictHostKeyChecking no" -o "UserKnownHostsFile /dev/null" -i {}'.format(
                temp.name)

    repo = git.Repo.clone_from(url, path)

    if GIT_SSH_COMMAND_old:
        os.environ['GIT_SSH_COMMAND'] = GIT_SSH_COMMAND_old
    else:
        del os.environ['GIT_SSH_COMMAND']

    temp.close()
    return repo


def stringify_config_lists(config):
    """
    In place convert lists into multi-line strings for pip configuration options
    """
    items = list(config.items())
    for key, val in items:
        if isinstance(val, list):
            if all([isinstance(s, str) for s in val]):
                config[key] = '\n'.join(val)
        elif isinstance(val, dict):
            stringify_config_lists(val)


def is_pyats_job(job_file):
    """ Check whether a (job) file is a pyats jobfile
    read the first 15 lines of the file
    """
    try:
        count = 0
        with open(job_file, 'r') as file:
            while count < 10:
                count += 1
                line = file.readline()
                if not line:
                    continue
                if PYATS_ANCHOR in line:
                    return True
    except:
        return False
    return False
