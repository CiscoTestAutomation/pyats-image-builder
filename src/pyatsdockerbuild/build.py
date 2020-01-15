import os
import sys
import ssl
import git
import yaml
import shutil
import pprint
import ftplib
import logging
import pathlib
import datetime
import requests
import argparse
import collections
import configparser
import urllib.parse

from .utils import copy
from .utils import run_cmd

DEFAULT_PYTHON_VERSION = '3.6.9-slim'
WORKSPACE = '/workspace'
INSTALL_LOC = '/install'
VENV_LOC = '/venv'

logger = logging.getLogger(__name__)
stdout_handle = logging.StreamHandler(stream=sys.stdout)
logger.addHandler(stdout_handle)
logger.setLevel(logging.INFO)

def check_schema(yaml_content):
    '''
    Prepare and validate yaml_content before processing to generate docker
    context and image.
    '''

    if 'python' in yaml_content:
        # Ensure python version is a valid format to use as the base docker
        # image. Appends '-slim' to the given version to acquire the docker
        # image tag.
        ver = str(yaml_content['python'])
        if not all([n.isdigit() for n in ver.split('.')]):
            raise TypeError('Python version must be in format 3[.X][.X]')
        yaml_content['python'] = ver + '-slim'

    if 'env' in yaml_content:
        # env must be a dict
        assert isinstance(yaml_content['env'], dict), 'env is not a mapping'

    if 'files' in yaml_content:
        # Ensure that files is a list
        assert isinstance(yaml_content['files'], list), 'files is not a list'
        for f in yaml_content['files']:
            # Ensure every file is a list of dict of size 1
            assert isinstance(f, (str, dict)), \
                    "file '%s' is neither a string nor a mapping" % f
            if isinstance(f, dict):
                assert len(f) == 1, "file '%s' has more than one value" % f
                for k, v in f.items():
                    # Ensure no file destination starts with / since that will
                    # copy to root of host.
                    assert not str(k).startswith('/'), \
                            "file '%s' cannot have an absolute destination" % f

    if 'packages' in yaml_content:
        # Ensure packages is a list of strings
        assert isinstance(yaml_content['packages'], list), \
                'packages is not a list'
        assert all([isinstance(i, str) for i in yaml_content['packages']]), \
                'not every listed package is a string'

    if 'repositories' in yaml_content:
        # Ensure that each repo is a dict with a URL The key is the name of
        # directory to clone into
        assert isinstance(yaml_content['repositories'], dict), \
                'repositories is not a mapping'
        for key, val in yaml_content['repositories'].items():
            assert isinstance(val, dict), \
                    "repository '%s' is not a mapping" % key
            assert 'url' in val, "repository '%s' is missing a url" % key
            assert isinstance(val['url'], str), \
                    "repository '%s' url is not a string" % key

    if 'snapshot' in yaml_content:
        # Extend the given yaml with any python packages or repositories in
        # the snapshot file
        assert isinstance(yaml_content['snapshot'], str), \
                'snapshot is not a string'
        with open(yaml_content['snapshot']) as f:
            snapshot = yaml.safe_load(f.read())
        if 'packages' in snapshot:
            yaml_content.setdefault('packages', [])\
                    .extend(snapshot['packages'])
        if 'repositories' in snapshot:
            yaml_content.setdefault('repositories', {})\
                    .update(snapshot['repositories'])

    if 'pip-config' in yaml_content:
        # pip options can only be simple key-value pairs of strings
        assert isinstance(yaml_content['pip-config'], dict), \
                'pip-config is not a mapping'

    if 'proxy' in yaml_content:
        # Proxy values must only belong to specifically defined keys
        proxy_keys = ['HTTP_PROXY', 'HTTPS_PROXY', 'FTP_PROXY', 'NO_PROXY']
        assert isinstance(yaml_content['proxy'], dict), "proxy is not a mapping"
        for key, val in yaml_content['proxy'].items():
            assert isinstance(key, str), "proxy key '%s' is not a string" % key
            assert isinstance(val, str), \
                    "proxy value '%s' is not a string" % val
            assert key.upper() in proxy_keys, \
                    "proxy key '%s' not recognized" % key


def build(args):
    # Status code to return
    status = 0

    # Read given yaml file
    try:
        yaml_content = yaml.safe_load(pathlib.Path(args.file).read_text())
    except FileNotFoundError:
        logger.error('File not found: %s' % args.file)
        return 1

    # Prep yaml content
    check_schema(yaml_content)
    logger.info('Configuration:')
    logger.info(pprint.pformat(yaml_content))

    # Install location of this package which includes docker files to be copied
    # over
    docker_files_path = pathlib.Path(__file__).parent

    # Prep docker context as a temp directory
    parent_path = pathlib.Path('/tmp')
    if args.keep_context or args.dry_run:
        parent_path = pathlib.Path('.').resolve()
    now_str = datetime.datetime.utcnow().strftime('%Y%m%d%H%M%S%f')
    context_name = 'pyATSImage' + now_str
    context_path = parent_path / context_name
    logger.info('Setting up context in %s' % context_path)
    context_path.mkdir()
    # The contents of {context}/image are copied into / in the image.
    image_path = context_path / 'image'
    image_path.mkdir()

    # Create image directories. Must remove leading / since paths are not
    # absolute in builder host machine.
    workspace_path = image_path / WORKSPACE.lstrip('/')
    workspace_path.mkdir()
    install_path = image_path / INSTALL_LOC.lstrip('/')
    install_path.mkdir()
    venv_path = image_path / VENV_LOC.lstrip('/')
    venv_path.mkdir()

    try:

        # Set up docker build command and environment to be built upon depending
        # on yaml contents
        build_cmd = 'docker build .'

        if 'tag' in yaml_content:
            logger.info('Setting docker image tag: %s' % yaml_content['tag'])
            # Set the tag of the newly built image
            build_cmd += ' -t %s' % yaml_content['tag']

        python_version = DEFAULT_PYTHON_VERSION
        if 'python' in yaml_content:
            # Sets the tag of the python docker image from build from.
            python_version = yaml_content['python']
        logger.info('Using Python base image: %s' % python_version)

        # Format environment variables for Dockerfile
        dockerfile_env = ''
        if 'env' in yaml_content:
            logger.info('Formatting image environment variables')
            for key, val in yaml_content['env'].items():
                dockerfile_env += 'ENV %s="%s"\n' \
                                  % (key, val.replace('"','\\"'))

        # Write formatted Dockerfile in context
        logger.info('Writing formatted Dockerfile')
        dockerfile = (docker_files_path / 'Dockerfile').read_text()
        dockerfile = dockerfile.format(python_version=python_version,
                                       workspace=WORKSPACE,
                                       install_loc=INSTALL_LOC,
                                       venv_loc=VENV_LOC,
                                       env=dockerfile_env)
        (context_path / 'Dockerfile').write_text(dockerfile)

        if 'files' in yaml_content:
            logger.info('Adding files to workspace')
            for from_path in yaml_content['files']:
                name = None
                # If a file/dir is given as a dict, the key is the desired name for
                # that file/dir in the docker image
                # files:
                #   - /path/to/a_file
                #   - new_name: /path/to/original_name
                if isinstance(from_path, dict):
                    for n, f in from_path.items():
                        name = n
                        from_path = f
                # Files can be given as urls to be downloaded
                url_parts = urllib.parse.urlsplit(from_path)
                # Use original file name if a new one is not provided
                if not name:
                    name = os.path.basename(url_parts.path)
                to_path = workspace_path / name
                # Prevent overwriting existing files
                assert not to_path.exists(), "%s already exists" % to_path
                # Make sure parent dir exists
                if not to_path.parent.exists():
                    to_path.parent.mkdir(parents=True)

                # Separate host and port, if given
                host = port = None
                if url_parts.netloc:
                    host = url_parts.netloc
                    if ':' in host:
                        host, port = host.split(':')
                        port = int(port) if port else None

                # Perform action dictated by scheme, or lack of one.
                if not url_parts.scheme:
                    # Copy file or dir directly
                    logger.info('Copying %s' % from_path)
                    copy(from_path, to_path)
                elif url_parts.scheme in ['http', 'https']:
                    # Download with GET request
                    logger.info('Downloading %s' % from_path)
                    r = requests.get(from_path)
                    if r.status_code == 200:
                        to_path.write_bytes(r.content)
                    else:
                        raise Exception('Could not download %s' % from_path)
                elif url_parts.scheme == 'scp':
                    # scp file or dir. Must have passwordless ssh set up.
                    logger.info('Copying with scp %s' % from_path)
                    scp_cmd = 'scp -B -r '
                    if port:
                        scp_cmd += '-P %s ' % port
                    scp_cmd += '%s:%s %s' % (host,
                                             url_parts.path,
                                             to_path.absolute())
                    return_code = run_cmd(scp_cmd, cwd=context_path)
                    if return_code != 0:
                        raise Exception('Could not scp %s' % from_path)
                elif url_parts.scheme in ['ftp', 'ftps']:
                    # ftp file. Uses anonymous credentials.
                    logger.info('Retreiving from ftp %s' % from_path)
                    host = (host, port) if port else (host)
                    if url_parts.scheme == 'ftps':
                        ftp = ftplib.FTP_TLS(
                                context=ssl.create_default_context())
                    else:
                        ftp = ftplib.FTP()
                    ftp.connect(*host)
                    ftp.login()
                    with open(to_path, 'wb') as f:
                        ftp.retrbinary('RETR ' + url_parts.path, f.write, 1024)
                    ftp.close()

        if 'repositories' in yaml_content:
            # Clone all git repositories and checkout a specific commit
            # if one is given
            logger.info('Cloning git repositories')
            for name, vals in yaml_content['repositories'].items():
                logger.info('Cloning repo %s' % vals['url'])

                # Ensure dir does not already exist
                repo_dir = workspace_path / name
                assert not repo_dir.exists(), "%s already exists" % repo_dir

                # Clone the repo
                repo = git.Repo.clone_from(vals['url'], repo_dir)

                commit_id = vals.get('commit_id', None)
                if commit_id:
                    # If given a commit_id, switch to that commit
                    commit = repo.commit(commit_id)
                    repo.head.reference = commit
                    repo.head.reset(index=True, working_tree=True)
                else:
                    # No commit_id, find the commit_id of head
                    vals['commit_id'] = repo.head.commit.hexsha

                shutil.rmtree(repo.git_dir)

        # Generate python requirements file
        logger.info('Writing Python packages to requirements.txt')
        reqs = '\n'.join(yaml_content.get('packages', [])) + '\n'
        requirements_path = install_path / 'requirements.txt'
        requirements_path.write_text(reqs)

        # pip config for setting things like pypi server.
        if 'pip-config' in yaml_content:
            logger.info('Writing pip.conf file')
            confparse = configparser.ConfigParser()
            confparse.read_dict(yaml_content['pip-config'])
            pip_conf_path = venv_path / 'pip.conf'
            pip_conf_file = pip_conf_path.open('w')
            confparse.write(pip_conf_file)
            pip_conf_file.close()

        # Proxy args are predefined in docker, and can be set for building the
        # image. Does not affect the image after it is built.
        if 'proxy' in yaml_content:
            logger.info('Setting proxy args for docker')
            for key, val in yaml_content['proxy'].items():
                build_cmd += ' --build-arg %s="%s"' % (key, val)

        # copy entrypoint to the context
        logger.info('Copying entrypoint.sh to context')
        copy(docker_files_path / 'docker-entrypoint.sh',
            install_path / 'entrypoint.sh')

        # Also copy the build yaml and snapshot if available so that they are
        # bundled with the image
        logger.info('Copying %s to context' % args.file)
        copy(args.file, install_path / 'oldbuild.yaml')
        if 'snapshot' in yaml_content:
            logger.info('Copying %s to context' % yaml_content['snapshot'])
            copy(yaml_content['snapshot'], install_path / 'snapshot.yaml')

        # Write new yaml containing processed and retrieved data
        (install_path / 'build.yaml').write_text(yaml.safe_dump(yaml_content))

        if not args.dry_run:
            # Run build command
            logger.info('Building image')
            return_code = run_cmd(build_cmd, cwd=context_path)
            if return_code == 0:
                logger.info('Built image successfully')
            else:
                logger.error('Failure while building image')

    except Exception:
        # Catch exception so we can attempt to clean up directories
        status = 1
        logger.exception('Encountered error while attempting build:')

    if not args.keep_context and not args.dry_run:
        # Remove context directory after build
        logger.info('Cleaning up context directory')
        shutil.rmtree(context_path)

    return status


def main():
    parser = argparse.ArgumentParser(prog='pyats-docker-build',
                                     description='Create docker images for '
                                                 'running pyATS jobs')
    parser.add_argument('file')
    parser.add_argument('--keep-context', '-k', action='store_true')
    parser.add_argument('--dry-run', '-n', action='store_true')
    args = parser.parse_args(sys.argv[1:])

    return build(args)

if __name__ == '__main__':
    main()
