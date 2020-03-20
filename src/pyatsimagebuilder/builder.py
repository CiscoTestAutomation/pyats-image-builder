import os
import re
import sys
import yaml
import shutil
import docker
import logging
import pathlib
import requests
import argparse
import tempfile
import configparser
import urllib.parse

from .utils import scp
from .utils import copy
from .image import Image
from .utils import git_clone
from .utils import ftp_retrieve
from .schema import validate_builder_schema

PACKAGE_PATH = os.path.dirname(__file__)
DEFAULT_PYTHON_VERSION = '3.6.9-slim'
WORKSPACE = '/workspace'
INSTALL_DIR = '/workspace/installation'
VIRTUAL_ENV = '/venv'

logger = logging.getLogger(__name__)
stdout_handler = logging.StreamHandler(stream=sys.stdout)
stdout_handler.setLevel('INFO')
logger.addHandler(stdout_handler)
logger.setLevel('DEBUG')
logger.propagate = False


class ImageBuilder(object):
    def __init__(self):
        # Paths to important context directories
        self.context_dir = None
        self.image_dir = None
        self.workspace_dir = None
        self.install_dir = None
        self.virtual_env = None
        # Remove context dir when finished?
        self.remove_context = True

    def setup_context(self, path=None):
        # Path is given and already exists, do not remove when done
        if path and pathlib.Path(path).exists():
            self.remove_context = False
        # No path given, use a temporary dir and remove at the end unless
        # specified.
        if not path:
            path = tempfile.mkdtemp()
        self.context_dir = pathlib.Path(path).expanduser().resolve()
        logger.info('Setting up Docker context in %s' % self.context_dir)
        if not self.context_dir.exists():
            self.context_dir.mkdir(parents=True)
        # The contents of context_dir/image are copied into the root / of
        # the image.
        self.image_dir = self.context_dir / 'image'
        self.image_dir.mkdir()

        # Create image directories. Must remove leading / since paths are not
        # absolute in builder host machine.
        self.workspace_dir = self.image_dir / WORKSPACE.lstrip('/')
        self.workspace_dir.mkdir()
        self.install_dir = self.image_dir / INSTALL_DIR.lstrip('/')
        self.install_dir.mkdir()
        self.virtual_env = self.image_dir / VIRTUAL_ENV.lstrip('/')
        self.virtual_env.mkdir()

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
            to_path = (self.workspace_dir / name).resolve()
            # Ensure file is being copied to workspace
            to_path.relative_to(self.workspace_dir)
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
            # Ensure dir is within workspace, and does not already exist
            repo_dir = (self.workspace_dir / name).resolve()
            repo_dir.relative_to(self.workspace_dir)
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
        pip_conf_file = self.virtual_env / 'pip.conf'
        with pip_conf_file.open('w') as f:
            confparse.write(f)

    def handle_docker_files(self, python_version, env, pre_cmd, post_cmd):
        # Write formatted Dockerfile in context
        logger.info('Writing formatted Dockerfile')
        package_dir = pathlib.Path(PACKAGE_PATH)
        dockerfile = (package_dir / 'Dockerfile').read_text()
        dockerfile = dockerfile.format(python_version=python_version,
                                       workspace=WORKSPACE,
                                       install_dir=INSTALL_DIR,
                                       virtual_env=VIRTUAL_ENV,
                                       env=env,
                                       pre_cmd=pre_cmd,
                                       post_cmd=post_cmd)
        (self.context_dir / 'Dockerfile').write_text(dockerfile)

        # copy entrypoint to the context
        logger.info('Copying entrypoint.sh to context')
        copy(package_dir / 'docker-entrypoint.sh',
             self.install_dir / 'entrypoint.sh')

    def docker_build(self,
                     tag=None,
                     build_args={},
                     verbose=False,
                     no_cache=False):
        # Get docker client api
        api = docker.from_env().api
        build_error = []
        image_id = None

        # Trigger docker build
        for line in api.build(path=str(self.context_dir),
                              tag=tag,
                              rm=True,
                              forcerm=True,
                              buildargs=build_args,
                              decode=True,
                              nocache=no_cache):

            # Log stream from build
            if 'stream' in line:
                contents = line['stream'].rstrip()
                if contents:
                    logger.debug(contents)

            # If we encounter an error, capture it
            if 'errorDetail' in line:
                build_error.append(line['errorDetail']['message'])

            # Attempt to retrieve image ID
            if 'stream' in line:
                m = re.search('^Successfully built (\w+)$', line['stream'])
                if m:
                    image_id = m.group(1)
        api.close()

        # Error encountered, raise exception with message
        if build_error:
            raise Exception('Build Error:\n%s' % '\n'.join(build_error))

        if image_id:
            # After a successful build, return an image object
            return Image(image_id, tag)
        else:
            # If no "Successfully built..." message is found, we do not have the
            # ID to create an Image object.
            raise Exception('No confirmation of successful build.')

    def run(self,
            config={},
            path=None,
            tag=None,
            keep_context=False,
            verbose=False,
            stream=None,
            no_cache=False,
            dry_run=False):
        """
        Arguments
        ---------
            config (dict): Build configuration
            path (str): Path to build context
            tag (str): Tag for docker image once built
            keep_context (bool): Prevents deleting the docker build context
                                 directory after the image is built
            verbose (bool): Enables more logging to stdout when building
            stream (IOStream): Stream to write logs to
            no_cache (bool): Forces the rebuilding of intermediate docker image
                             layers
            dry_run (bool): Set up docker build context but do not run build

        Returns
        -------
            Image object when successful
        """
        image = None
        error = None

        # Set up logger to use given stream
        if stream:
            stream_handler = logging.StreamHandler(stream=stream)
            stream_handler.setLevel('DEBUG')
            logger.addHandler(stream_handler)

        # If verbose, log build output to console
        if verbose:
            stdout_handler.setLevel('DEBUG')

        # Do not delete context at the end if --keep-context is set
        if keep_context:
            self.remove_context = False

        # Set up build
        self.setup_context(path)

        try:
            # Verify schema
            logger.info('Verifying schema')
            validate_builder_schema(config)

            proxy = {}
            if 'proxy' in config:
                logger.info('Setting proxy environment variables')
                # Proxy values must only belong to specifically defined keys
                proxy = config['proxy']
                # Update environment with proxy for git and file downloads
                os.environ.update(config['proxy'])

            # Dump config to yaml file in context
            logger.info('Dumping config to file in context')
            (self.install_dir / 'build.yaml').write_text(yaml.safe_dump(config))

            python_version = DEFAULT_PYTHON_VERSION
            if 'python' in config:
                # Ensure python version is a valid format to use as the base
                # docker image. Appends '-slim' to the given version to acquire
                # the docker image tag.
                ver = str(config['python'])
                if not all([n.isdigit() for n in ver.split('.')]):
                    raise TypeError('Python version must be in format '
                                    '3[.X][.X]')
                python_version = ver + '-slim'

            # Formatted environment variable to add to Dockerfile
            env = ''
            if 'env' in config:
                for key, val in config['env'].items():
                    env += 'ENV %s="%s"\n' % (key, val.replace('"', '\\"'))

            # Docker commands to insert into the Dockerfile. Very risky.
            pre_cmd = post_cmd = ''
            if 'cmds' in config:
                pre_cmd = str(config['cmds'].get('pre', ''))
                post_cmd = str(config['cmds'].get('post', ''))

            # Generate Dockerfile and copy other files into image context
            self.handle_docker_files(python_version, env, pre_cmd, post_cmd)

            snapshot = {}
            if 'snapshot' in config:
                # Extend given packages and repositories with any python
                # packages or repositories in the snapshot file
                with open(config['snapshot']) as f:
                    snapshot = yaml.safe_load(f.read())
                logger.info('Copying %s to context' % config['snapshot'])
                copy(config['snapshot'],
                     self.install_dir / 'snapshot.yaml')

            repositories = {}
            if 'repositories' in config:
                repositories.update(config['repositories'])
            if 'repositories' in snapshot:
                repositories.update(snapshot['repositories'])
            if repositories:
                self.handle_repositories(repositories)

            packages = []
            if 'packages' in config:
                packages.extend(config['packages'])
            if 'packages' in snapshot:
                packages.extend(snapshot['packages'])
            self.handle_packages(packages)

            if 'files' in config:
                self.handle_files(config['files'])

            if 'pip-config' in config:
                self.handle_pip_config(config['pip-config'])

            # Tag for docker image   argument (cli) > config (yaml) > None
            tag = tag or config.get('tag', None)

            # Start docker build
            if not dry_run:
                logger.info('Building image')
                image = self.docker_build(tag=tag,
                                          build_args=proxy,
                                          verbose=verbose,
                                          no_cache=no_cache)

                logger.info("Built image '%s' successfully"
                            % tag if tag else image.id)

        except Exception as e:
            logger.exception('Failure while building docker image:')
            # Save error to raise later so we can clean up context first
            error = e

        if self.remove_context:
            logger.info('Removing context directory')
            shutil.rmtree(self.context_dir)

        if error:
            # After cleaning context, raise error if there was one
            raise error

        return image


def main(argv=None, prog='pyats-image-build'):
    """
    Command line entrypoint
    """
    # Parse args from command line
    parser = argparse.ArgumentParser(prog=prog,
                                     description='Create Docker images for '
                                                 'running pyATS jobs')
    parser.add_argument('file',
                        help='YAML file defining the image to be built.')
    parser.add_argument('--tag', '-t',
                        help='Tag for docker image. Overrides any tag defined '
                             'in the yaml.')
    parser.add_argument('--path', '-p',
                        help='Specify a path to use as the context while '
                             'building.')
    parser.add_argument('--push', '-P', action='store_true',
                        help='Push image to once built.')
    parser.add_argument('--no-cache', '-c', action='store_true',
                        help='Do not use the cache when building the image.')
    parser.add_argument('--keep-context', '-k', action='store_true',
                        help='Prevents the context dir from being deleted '
                             'once the image is built')
    parser.add_argument('--dry-run', '-n', action='store_true',
                        help='Set up the context but do not build the '
                             'image. Use with --keep-context.')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Prints the output of docker build.')
    args = parser.parse_args(argv)

    # Load given yaml file
    logger.info('Reading provided yaml')
    config = yaml.safe_load(pathlib.Path(args.file).read_text())

    # Run builder
    image = ImageBuilder().run(config=config,
                               path=args.path,
                               tag=args.tag,
                               keep_context=args.keep_context,
                               verbose=args.verbose,
                               no_cache=args.no_cache,
                               dry_run=args.dry_run)

    # Optionally push image after building
    if args.push:
        logger.info('Pushing image to registry')
        image.push()

    logger.info('Done')


def build(config, **kwargs):
    """
    API for building images from another Python script

    Arguments
    ---------
        config (dict): Build configuration
        path (str): Path to build context
        tag (str): Tag for docker image once built
        keep_context (bool): Prevents deleting the docker build context
                             directory after the image is built
        verbose (bool): Enables more logging to stdout when building
        stream (IOStream): Stream to write logs to
        no_cache (bool): Forces the rebuilding of intermediate docker image
                         layers
        dry_run (bool): Set up docker build context but do not run build

    Returns
    -------
        Image object when successful
    """
    # Run builder and return image
    return ImageBuilder().run(config=config, **kwargs)


if __name__ == '__main__':
    main()
