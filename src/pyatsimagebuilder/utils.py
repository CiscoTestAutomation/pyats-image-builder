import re
import ssl
import git
import shutil
import ftplib
import pathlib
import subprocess
import os
import tempfile
import logging
import json
import yaml
import sys

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.StreamHandler(sys.stdout))


PYATS_ANCHOR = 'PYATS_JOBFILE'

DEFAULT_JOB_REGEXES = [
    r'.*job.*\.py$',
]
MANIFEST_REGEX = [r'.*\.tem$']
MANIFEST_VERSION = 1


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


def search_regex(regexes, path, ignore_folders=[]):
        regexes = [re.compile(regex) for regex in regexes]
        ignore_folders = [path / i for i in ignore_folders]

        match = []

        for file in path.rglob('*'):
            if any(i in file.parents for i in ignore_folders):
                continue
            if any(regex.match(file.name) for regex in regexes):
                match.append(file)

        return match


def to_image_path(path, search_path, workspace_dir):
    '''
    returns the path within image workspace

    Arguments:
        path (Path): Path to convert
        search_path (Path): pathlib Path object with the directory to start discovery from
        workspace_dir (str): workspace directory
    '''

    search_path = str(search_path)
    path = str(path)
    workspace_dir = str(workspace_dir)

    if path.startswith('${WORKSPACE}'):
        path = path.replace('${WORKSPACE}', workspace_dir)
    elif path.startswith('$WORKSPACE'):
        path = path.replace('$WORKSPACE', workspace_dir)
    elif path.startswith(search_path):
        path = path.replace(search_path, workspace_dir)

    return path


def discover_jobs(jobfiles, 
                  search_path, 
                  ignore_folders=None, 
                  relative_path=None):
    """ Discover job files based on regex

    Arguments:
        jobfiles (dict): Dict of jobfiles config
        search_path (Path): pathlib Path object with the directory to start discovery from
        ignore_folders (list): list of strings with directories being excluded from searching
        relative_path (str): String with the directory search results will be relative to
    """
    logger.info('Discovering Jobfiles')
    
    if not ignore_folders:
        ignore_folders = []

    jobfiles.setdefault('match', DEFAULT_JOB_REGEXES)

    # 1. find all the job files in context by regex pattern
    discovered_jobs = search_regex(jobfiles['match'], 
                                   search_path, 
                                   ignore_folders=ignore_folders)

    # 2. find all job files by glob
    for pattern in jobfiles.get('glob', []):
        discovered_jobs.extend(search_path.rglob(pattern))

    # 3. find all job files by specificy paths
    for path in jobfiles.get('paths', []):
        path = search_path / path

        if path.exists() and path.is_file():
            discovered_jobs.append(path)

    # 4. discover all files that are pyats job by marker
    discovered_jobs.extend(
        filter(is_pyats_job, search_path.rglob('*.py')))

    # sort and remove duplicates
    discovered_jobs = sorted(set(discovered_jobs))

    if relative_path:
        # compute path from context to image path
        job_paths = [to_image_path(i, 
                                   search_path, 
                                   relative_path) for i in discovered_jobs]
    else:
        job_paths = [str(i) for i in discovered_jobs]

    logger.info('Number of discovered job files: %s' % len(job_paths))
    logger.info('List of job files written to: %s' % jobfiles)

    return job_paths


def discover_manifests(search_path, ignore_folders=None, relative_path=None):
    """ Discover manifest files and write manifest.json file

    Arguments:
        search_path (Path): pathlib Path object with the directory to start discovery from
        ignore_folders (list): list of strings with directories being excluded from searching
        relative_path (str): String with the directory search results will be relative to
    """
    logger.info('Discovering Manifests')
    
    if not ignore_folders:
        ignore_folders = []

    discovered_manifests = search_regex(MANIFEST_REGEX, 
                                        search_path, 
                                        ignore_folders=ignore_folders)

    # Generate single manifest structure linking the files to the data
    jobs = []
    for manifest in discovered_manifests:
        with open(manifest) as f:
            manifest_data = yaml.safe_load(f.read())

        if relative_path:
            manifest_data['file'] = to_image_path(str(manifest), 
                                                  search_path, 
                                                  relative_path)
        else:
            manifest_data['file'] = str(manifest)

        manifest_data['run_type'] = 'manifest'
        manifest_data['job_type'] = manifest_data.pop('type')

        # Pop runtimes and profiles to add them back later as lists
        runtimes = manifest_data.pop('runtimes', {})
        profiles = manifest_data.pop('profiles', {})

        # Create default profile from top level arguments and system environment
        default_arguments = manifest_data.pop('arguments')
        default_runtime = runtimes.get('system', {})
        default_environment = default_runtime.get('environment', {})
        profiles['DEFAULT'] = {}
        profiles['DEFAULT']['runtime'] = 'system'
        profiles['DEFAULT']['arguments'] = default_arguments
        profiles['DEFAULT']['environment'] = default_environment

        # Update profiles with environment from runtimes
        for profile_name in profiles:
            runtime = profiles[profile_name].get('runtime', 'system')
            if runtime in runtimes:
                environment = runtimes[runtime].get('environment', {})
                if environment:
                    profiles[profile_name]['environment'] = environment

        # Convert profiles from hierarchical dict to list of dict
        manifest_data['profiles'] = []
        for profile_name in profiles:
            manifest_data['profiles'].append(profiles[profile_name])
            manifest_data['profiles'][-1]['name'] = profile_name

        # Convert runtimes from hierarchical dict to list of dict
        manifest_data['runtimes'] = []
        for profile_name in runtimes:
            manifest_data['runtimes'].append(runtimes[profile_name])
            manifest_data['runtimes'][-1]['name'] = profile_name

        jobs.append(manifest_data)

    logger.info('Number of discovered manifest files: %s' % \
        len(discovered_manifests))

    if jobs:
        return {'version': MANIFEST_VERSION, 'jobs': jobs}
    else:
        return {}
