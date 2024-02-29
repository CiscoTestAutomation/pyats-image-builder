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
MANIFEST_REGEX = r'.*\.tem$'
MANIFEST_VERSION = 1

GIT_REGEX = r'.*\.git$'

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


def git_info(path, repo=None):
    # Get information about the given repo
    if repo is None:
        repo = git.Repo(path)

    # Get the hexsha of the current commit
    hexsha = repo.head.commit.hexsha

    # Get remotes
    remotes = {r.name: r.url for r in repo.remotes}

    # Get tags and heads of HEAD
    cmd = 'git tag --points-at HEAD'
    out = subprocess.check_output(cmd, shell=True, cwd=path,
                                  universal_newlines=True)
    tags = out.split()

    cmd = 'git branch --points-at HEAD'
    out = subprocess.check_output(cmd, shell=True, cwd=path,
                                  universal_newlines=True)

    heads = out.split()
    # Remove marker of current branch
    if '*' in heads:
        heads.remove('*')

    return {'commit': hexsha,
            'heads': heads,
            'tags': tags,
            'remotes': remotes,
            'path': str(path)}


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

    info = git_info(path, repo)

    if rm_git:
        # Delete the .git dir to save space after checking out
        shutil.rmtree(repo.git_dir)

    return info


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
        path = path.replace('${WORKSPACE}', workspace_dir, 1)
    elif path.startswith('$WORKSPACE'):
        path = path.replace('$WORKSPACE', workspace_dir, 1)
    elif path.startswith(search_path):
        path = path.replace(search_path, workspace_dir, 1)

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

    return job_paths


def discover_manifests(search_path, ignore_folders=None, relative_path=None,
                       repo_data=None):
    """ Discover manifest files and write manifest.json file

    Arguments:
        search_path (Path): pathlib Path object with the directory to start discovery from
        ignore_folders (list): list of strings with directories being excluded from searching
        relative_path (str): String with the directory search results will be relative to
        repo_list (dict): dict of repositories to link to each manifest file.
                          Additional repos are discovered and appended to
                          this list.
    """
    logger.info('Discovering Manifests')

    if not ignore_folders:
        ignore_folders = []

    # Combine search for manifests and git repos in one recursive glob search
    discovered_manifests = search_regex([MANIFEST_REGEX, GIT_REGEX],
                                        search_path,
                                        ignore_folders=ignore_folders)

    # Separate git repos and manifests
    git_regex = re.compile(GIT_REGEX)
    discovered_repos = []
    i = 0
    while i < len(discovered_manifests):
        if git_regex.match(str(discovered_manifests[i])):
            discovered_repos.append(discovered_manifests.pop(i))
        else:
            i += 1

    if repo_data is None:
        repo_data = {}

    for repo in discovered_repos:
        # remove /.git from path and convert from Path to str
        repo = os.path.dirname(str(repo))
        if relative_path:
            image_repo = to_image_path(repo, search_path, relative_path)
        else:
            image_repo = repo
        # only add undiscovered repos
        if image_repo not in repo_data:
            try:
                r = git_info(repo)
                # use corrected image path
                r['path'] = image_repo
                repo_data[image_repo] = r
            except Exception:
                # problem getting git information - probably not an actual repo
                logger.exception('Error getting git info about {}'.format(repo))

    # Generate single manifest structure linking the files to the data
    jobs = []
    for manifest in discovered_manifests:
        try:
            with open(manifest) as f:
                manifest_data = yaml.safe_load(f.read())
        except yaml.error.YAMLError as e:
            logger.error('Error loading manifest file {} from yaml\n{}'.format(
                manifest, str(e)))
            continue

        if manifest_data is None:
            logger.warning(f'No manifest data from file {manifest}')
            continue

        try:
            if relative_path:
                manifest_data['file'] = to_image_path(str(manifest),
                                                      search_path,
                                                      relative_path)
            else:
                manifest_data['file'] = str(manifest)

            # Find any repo containing this manifest file
            for repo in repo_data:
                if manifest_data['file'].startswith(repo):
                    manifest_data['repo_path'] = repo
                    break

            manifest_data['run_type'] = 'manifest'
            manifest_data['job_type'] = manifest_data.pop('type', None)
            if not manifest_data['job_type']:
                logger.warning(f'No job type specified in {manifest}')
                continue

            # Pop runtimes and profiles to add them back later as lists
            runtimes = manifest_data.pop('runtimes', {})
            profiles = manifest_data.pop('profiles', {})

            # Create default profile from top level arguments and system environment
            default_arguments = manifest_data.pop('arguments', {})
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

        except Exception as e:
            logger.exception('Error processing manifest file {}'.format(
                manifest))
            continue

    logger.info('Number of discovered manifest files: %s' % \
                len(discovered_manifests))



    if jobs:
        discover_yamls(jobs, search_path=search_path, relative_path=relative_path)
        return {'version': MANIFEST_VERSION, 'jobs': jobs}
    else:
        return {}


def _process_testbed_file(profile, yaml_contents):
    # Extract specific device information from each device
    # in the testbed and attach to the profile
    if yaml_contents.get('devices'):
        testbed_info = profile.setdefault('testbed_info', {})
        for dev_name, dev in yaml_contents['devices'].items():
            if isinstance(dev, dict):
                testbed_info[dev_name] = {}
                for key in ('os', 'platform', 'model', 'pid', 'type', 'logical'):
                    if key in dev:
                        testbed_info[dev_name][key] = dev[key]

def _process_clean_file(profile, yaml_contents):
    # Extract bringup information from the clean file and
    # attach to the profile
    bringup_module = yaml_contents.get('bringup', {}).get('BringUpWorker', {}).get('module')
    if bringup_module:
        clean_info = profile.setdefault('clean_info', {})
        clean_info['bringup_module'] = bringup_module

yaml_processors = {
    'testbed-file': _process_testbed_file,
    'logical-testbed-file': _process_testbed_file,
    'clean-file': _process_clean_file
}

def discover_yamls(manifests, search_path, relative_path=None):
    """ Discover yaml files referenced in manifest files and extract key
        information

    Arguments:
        manifests (list): list of contents of discovered manifests
        search_path (Path): pathlib Path object with the directory to start discovery from
        relative_path (str): String with the directory search results will be relative to
    """
    logger.info('Discovering YAML files from manifests')
    for manifest in manifests:
        manifest_dir = os.path.dirname(manifest['file'])
        for profile in manifest['profiles']:
            profile['yaml_files'] = []
            if not isinstance(profile.get('arguments'), dict):
                continue
            for argument, value in profile['arguments'].items():
                if argument not in yaml_processors:
                    # Filter for only testbed and clean files. No need to
                    # load other yaml files
                    continue
                if not (isinstance(value, str) and value.lower().endswith('.yaml')):
                    continue

                # Do not process any files that start with a variable
                # or some inaccessible absolute path. If the yaml file
                # starts with the relative path, it should be
                # accessible in the image, and still valid
                if value.startswith('$'):
                    continue
                elif value.startswith('/'):
                    if not relative_path or not value.startswith(relative_path):
                        continue

                # Construct an absolute path using the dir of the manifest
                # This will be the relative path to the image root once
                # built, not the actual path of the file in the build
                # environment
                yaml_file = os.path.abspath(os.path.join(manifest_dir, value))
                # Convert to a real path so we can find the file in our
                # build environment
                if relative_path:
                    yaml_file = to_image_path(yaml_file, relative_path, search_path)
                if os.path.isfile(yaml_file):
                    try:
                        with open(yaml_file) as f:
                            # load yaml contents with handling for an
                            # empty file
                            yaml_contents = yaml.safe_load(f.read()) or {}
                    except Exception as e:
                        msg = f'Error loading YAML file {value} from ' \
                                f'manifest {manifest["file"]}'
                        logger.exception(msg)
                        continue
                else:
                    # YAML file relative path from manifest does not
                    # exist.
                    msg = f'Could not find YAML file {value} from ' \
                            f'manifest {manifest["file"]}'
                    logger.warning(msg)

                processor = yaml_processors.get(argument)
                if processor:
                    try:
                        processor(profile, yaml_contents)
                    except Exception as e:
                        # Problem processing the specific type of YAML file
                        msg = f'Error processing {argument} {value} from ' \
                                f'manifest {manifest["file"]}'
                        logger.exception(msg)

    return manifests