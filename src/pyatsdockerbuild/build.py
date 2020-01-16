import os
import sys
import yaml
import shutil
import docker
import logging
import pathlib
import datetime
import requests
import argparse
import collections
import configparser
import urllib.parse

from .utils import scp
from .utils import copy
from .utils import git_clone
from .utils import ftp_retrieve

PACKAGE_PATH = os.path.dirname(__file__)
PROXY_KEYS = ['HTTP_PROXY', 'HTTPS_PROXY', 'FTP_PROXY', 'NO_PROXY']
DEFAULT_PYTHON_VERSION = '3.6.9-slim'
WORKSPACE = '/workspace'
INSTALL_LOC = '/install'
VENV_LOC = '/venv'

logger = logging.getLogger(__name__)
stdout_handle = logging.StreamHandler(stream=sys.stdout)
logger.addHandler(stdout_handle)
logger.setLevel(logging.INFO)


class DockerBuilder(object):
    def __init__(self):
        # Paths to important context directories
        self.context_dir = None
        self.image_dir = None
        self.workspace_dir = None
        self.install_dir = None
        self.venv_dir = None


    def parser_config(self, argv=None):
        # Parse arguments for building a docker image
        parser = argparse.ArgumentParser(prog='pyats-docker-build',
                                     description='Create docker images for '
                                                 'running pyATS jobs')
        parser.add_argument('file')
        parser.add_argument('--keep-context', '-k', action='store_true')
        parser.add_argument('--dry-run', '-n', action='store_true')
        parser.add_argument('--verbose', '-v', action='store_true')
        return parser.parse_args()


    def setup_context(self, path='/tmp'):
        # Create directory structure for docker context
        parent_dir = pathlib.Path(path).resolve()
        now_str = datetime.datetime.utcnow().strftime('%Y%m%d%H%M%S%f')
        context_name = 'pyATSBuild' + now_str
        self.context_dir = parent_dir / context_name
        logger.info('Setting up Docker context in %s' % self.context_dir)
        self.context_dir.mkdir(parents=True)
        # The contents of context_dir/image are copied into the root / of
        # the image.
        self.image_dir = self.context_dir / 'image'
        self.image_dir.mkdir()

        # Create image directories. Must remove leading / since paths are not
        # absolute in builder host machine.
        self.workspace_dir = self.image_dir / WORKSPACE.lstrip('/')
        self.workspace_dir.mkdir()
        self.install_dir = self.image_dir / INSTALL_LOC.lstrip('/')
        self.install_dir.mkdir()
        self.venv_dir = self.image_dir / VENV_LOC.lstrip('/')
        self.venv_dir.mkdir()


    def handle_files(self, files):
        logger.info('Adding files to workspace')
        for from_path in files:
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
            to_path = self.workspace_dir / name
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
                scp(host=host,
                    from_path=url_parts.path,
                    to_path=to_path,
                    port=port)
            elif url_parts.scheme in ['ftp', 'ftps']:
                # ftp file. Uses anonymous credentials.
                logger.info('Retreiving from ftp %s' % from_path)
                ftp_retrieve(host=host, from_path=url_parts.path,
                             to_path=to_path, port=port,
                             secure=url_parts.scheme == 'ftps')


    def handle_repositories(self, repositories):
        # Clone all git repositories and checkout a specific commit
        # if one is given
        logger.info('Cloning git repositories')
        for name, vals in repositories.items():
            logger.info('Cloning repo %s' % vals['url'])
            # Ensure dir does not already exist
            repo_dir = self.workspace_dir / name
            assert not repo_dir.exists(), "%s already exists" % repo_dir
            # Clone and checkout the repo
            git_clone(vals['url'], repo_dir, vals.get('commit_id', None), True)


    def handle_packages(self, packages):
        # Generate python requirements file
        logger.info('Writing Python packages to requirements.txt')
        reqs = '\n'.join(packages) + '\n'
        requirements_file = self.install_dir / 'requirements.txt'
        requirements_file.write_text(reqs)


    def handle_pip_config(self, config):
        # pip config for setting things like pypi server.
        logger.info('Writing pip.conf file')
        confparse = configparser.ConfigParser()
        confparse.read_dict(config)
        pip_conf_file = self.venv_dir / 'pip.conf'
        with pip_conf_file.open('w') as f:
            confparse.write(f)


    def handle_docker_files(self, python_version, env):
        # Write formatted Dockerfile in context
        logger.info('Writing formatted Dockerfile')
        package_dir = pathlib.Path(PACKAGE_PATH)
        dockerfile = (package_dir / 'Dockerfile').read_text()
        dockerfile = dockerfile.format(python_version=python_version,
                                       workspace=WORKSPACE,
                                       install_loc=INSTALL_LOC,
                                       venv_loc=VENV_LOC,
                                       env=env)
        (self.context_dir / 'Dockerfile').write_text(dockerfile)

        # copy entrypoint to the context
        logger.info('Copying entrypoint.sh to context')
        copy(package_dir / 'docker-entrypoint.sh',
             self.install_dir / 'entrypoint.sh')


    def docker_build(self, tag=None, build_args={}, verbose=False):
        # Get docker client api
        api = docker.from_env().api
        build_error = None

        # Trigger docker build
        for line in api.build(path=str(self.context_dir),
                              tag=tag,
                              rm=True,
                              forcerm=True,
                              buildargs=build_args,
                              decode=True):

            # If verbose, print the build output
            if verbose:
                if 'stream' in line:
                    print(line['stream'], end='')

            # If we encounter an error, capture it
            if 'errorDetail' in line:
                build_error = line['errorDetail']['message']

        # Error encountered, raise exception with message
        if build_error:
            raise Exception('Build Error:\n%s' % build_error)


    def run(self, argv=None):
        # Parse args from command line
        args = self.parser_config(argv)

        # Set up build
        path = '/tmp'
        if args.keep_context or args.dry_run:
            path = '.'
        self.setup_context(path)

        try:
            # Read given yaml file
            yaml_content = yaml.safe_load(pathlib.Path(args.file).read_text())

            # Copy the build yaml to the image
            logger.info('Copying %s to context' % args.file)
            copy(args.file, self.install_dir / 'build.yaml')

            python_version = DEFAULT_PYTHON_VERSION
            if 'python' in yaml_content:
                # Ensure python version is a valid format to use as the base
                # docker image. Appends '-slim' to the given version to acquire
                # the docker image tag.
                ver = str(yaml_content['python'])
                if not all([n.isdigit() for n in ver.split('.')]):
                    raise TypeError('Python version must be in format '
                                    '3[.X][.X]')
                python_version = ver + '-slim'

            # Formatted environment variable to add to Dockerfile
            env = ''
            if 'env' in yaml_content:
                for key, val in yaml_content['env'].items():
                    env += 'ENV %s="%s"\n' % (key, val.replace('"','\\"'))

            # Generate Dockerfile and copy other files into image context
            self.handle_docker_files(python_version, env)

            snapshot = {}
            if 'snapshot' in yaml_content:
                # Extend given packages and repositories with any python
                # packages or repositories in the snapshot file
                with open(yaml_content['snapshot']) as f:
                    snapshot = yaml.safe_load(f.read())
                logger.info('Copying %s to context' % yaml_content['snapshot'])
                copy(yaml_content['snapshot'],
                     self.install_dir / 'snapshot.yaml')

            repositories = {}
            if 'repositories' in yaml_content:
                repositories.update(yaml_content['repositories'])
            if 'repositories' in snapshot:
                repositories.update(snapshot['repositories'])
            for key, val in repositories.items():
                assert isinstance(val, dict), \
                        "repository '%s' is not a mapping" % key
                assert 'url' in val, \
                        "repository '%s' is missing a url" % key
                assert isinstance(val['url'], str), \
                        "repository '%s' url is not a string" % key
            if repositories:
                self.handle_repositories(repositories)

            packages = []
            if 'packages' in yaml_content:
                packages.extend(yaml_content['packages'])
            if 'packages' in snapshot:
                packages.extend(snapshot['packages'])
            assert all([isinstance(i, str) for i in packages]), \
                    'not every listed package is a string'
            if packages:
                self.handle_packages(packages)

            if 'files' in yaml_content:
                # Ensure that files is a list
                files = yaml_content['files']
                assert isinstance(files, list), 'files is not a list'
                for f in files:
                    # Ensure every file is a list of dict of size 1
                    assert isinstance(f, (str, dict)), \
                            "file '%s' is neither a string nor a mapping" % f
                    if isinstance(f, dict):
                        assert len(f) == 1, "file '%s' has more than one value" % f
                        for k, v in f.items():
                            # Ensure no file destination starts with / since that
                            # will copy to root of host.
                            assert not str(k).startswith('/'), \
                                    "file '%s' cannot have an absolute " \
                                    "destination path" % f
                self.handle_files(files)

            if 'pip-config' in yaml_content:
                # pip options can only be simple key-value pairs of strings
                pip_config = yaml_content['pip-config']
                assert isinstance(pip_config, dict), \
                        'pip-config is not a mapping'
                self.handle_pip_config(pip_config)

            # Use docker build args to set proxy if there is one
            proxy = {}
            if 'proxy' in yaml_content:
                logger.info('Setting proxy args for docker')
                # Proxy values must only belong to specifically defined keys
                proxy = yaml_content['proxy']
                assert isinstance(proxy, dict), "proxy is not a mapping"
                for key, val in proxy.items():
                    assert key.upper() in PROXY_KEYS, \
                            "proxy key '%s' not one of %s" % (key, PROXY_KEYS)

            # Tag for docker image
            tag = None
            if 'tag' in yaml_content:
                tag = yaml_content['tag']

            if not args.dry_run:
                # Start docker build
                logger.info('Building image')
                self.docker_build(tag=tag,
                                  build_args=proxy,
                                  verbose=args.verbose)
                logger.info('Built image successfully')

        except Exception:
            logger.exception('Failure while building docker image:')

        if not (args.keep_context or args.dry_run):
            if self.context_dir:
                shutil.rmtree(self.context_dir)


def main():
    return DockerBuilder().run()

if __name__ == '__main__':
    main()
