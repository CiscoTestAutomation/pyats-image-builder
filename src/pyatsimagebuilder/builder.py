import os
import re
import yaml
import json
import glob
import shutil
import docker
import logging
import pathlib
import requests
import tempfile
import configparser
import urllib.parse

from .utils import (scp, 
                    copy,
                    git_clone, 
                    ftp_retrieve, 
                    stringify_config_lists, 
                    is_pyats_job)

from .image import Image
from .schema import validate_builder_schema

HERE = pathlib.Path(os.path.dirname(__file__))
DEFAULT_PYTHON_VERSION = '3.7.9-slim'
WORKSPACE = 'pyats'
INSTALL_DIR = 'installation'
DEFAULT_JOB_REGEXES = [re.compile(r'.*job.*\.py'), ]

class ImageBuilder(object):
    def __init__(self, logger = logging.getLogger(__name__)):
        self.logger = logger

        self.context = None
        self.install_dir = None

    def setup_context(self):
        # context is always temporary
        context = tempfile.TemporaryDirectory(prefix='pyats-image.').name
        self.context = pathlib.Path(context).expanduser().resolve()

        if not self.context.exists():
            self.context.mkdir()
        
        self.logger.info('Setting up Docker context in %s' % self.context)

        # context is our /pyats workspace - keep it simple
        # no need to create more directories
        self.install_dir = self.context / INSTALL_DIR
        self.install_dir.mkdir()

    def handle_files(self, files):
        self.logger.info('Adding files to workspace')
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
                name = os.path.basename(url_parts.path.rstrip('/'))
            to_path = (self.workspace / name).resolve()
            # Ensure file is being copied to workspace
            to_path.relative_to(self.context)
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
                self.logger.info('Copying %s' % from_path)
                copy(from_path, to_path)
            elif url_parts.scheme in ['http', 'https']:
                # Download with GET request
                self.logger.info('Downloading %s' % from_path)
                r = requests.get(from_path)
                if r.status_code == 200:
                    to_path.write_bytes(r.content)
                else:
                    raise Exception('Could not download %s' % from_path)
            elif url_parts.scheme == 'scp':
                # scp file or dir. Must have passwordless ssh set up.
                self.logger.info('Copying with scp %s' % from_path)
                scp(host=host,
                    from_path=url_parts.path,
                    to_path=to_path,
                    port=port)
            elif url_parts.scheme in ['ftp', 'ftps']:
                # ftp file. Uses anonymous credentials.
                self.logger.info('Retreiving from ftp %s' % from_path)
                ftp_retrieve(host=host, from_path=url_parts.path,
                             to_path=to_path, port=port,
                             secure=url_parts.scheme == 'ftps')

    def handle_repositories(self, repositories):
        # Clone all git repositories and checkout a specific commit
        # if one is given
        self.logger.info('Cloning git repositories')
        for name, vals in repositories.items():
            self.logger.info('Cloning repo %s' % vals['url'])
            # Ensure dir is within workspace, and does not already exist
            repo_dir = (self.context / name).resolve()
            repo_dir.relative_to(self.context)
            assert not repo_dir.exists(), "%s already exists" % repo_dir
            # Clone and checkout the repo
            git_clone(vals['url'], repo_dir, vals.get('commit_id', None), True)

    def handle_packages(self, packages):
        # Generate python requirements file
        self.logger.info('Writing Python packages to requirements.txt')
        reqs = '\n'.join(packages) + '\n'
        requirements_file = self.install_dir / 'requirements.txt'
        requirements_file.write_text(reqs)

    def handle_pip_config(self, config):
        # pip config for setting things like pypi server.
        self.logger.info('Writing pip.conf file')
        pip_conf_file = self.context / 'pip.conf'
        confparse = configparser.ConfigParser()
        if isinstance(config, dict):
            # convert from dict
            stringify_config_lists(config)
            confparse.read_dict(config)
            with pip_conf_file.open('w') as f:
                confparse.write(f)
        elif isinstance(config, str):
            # ensure format is valid, but leave the contents to pip
            confparse.read_string(config)
            with pip_conf_file.open('w') as f:
                f.write(config)

    def handle_docker_files(self, python_version, env, pre_cmd, post_cmd):
        # Write formatted Dockerfile in context
        self.logger.info('Writing formatted Dockerfile')

        # read dockerfile template
        dockerfile = (HERE / 'Dockerfile').read_text()

        # substitute it
        dockerfile = dockerfile.format(python_version=python_version,
                                       workspace='/%s' % WORKSPACE,
                                       env=env,
                                       pre_cmd=pre_cmd,
                                       post_cmd=post_cmd)

        # write dockerfile to installation dir
        (self.install_dir/'Dockerfile').write_text(dockerfile)

        # copy entrypoint to the context
        self.logger.info('Copying entrypoint.sh to context')
        
        copy(HERE / 'docker-entrypoint.sh',
             self.install_dir / 'entrypoint.sh')

    def discover_jobs(self, jobfiles):
        self.logger.info('Discovering Jobfiles')

        # find all .py files in the workspace
        all_files = glob.glob("%s/**/*.py" % self.context, recursive=True)

        # discover all files that mach given regex patterns
        regexes = [re.compile(regex) for regex in jobfiles.get('match', [])]

        if not regexes:
            # apply default regex
            regexes = DEFAULT_JOB_REGEXES

        match_files = list(filter(lambda x: any(regex.match(x) \
                                    for regex in regexes), all_files))

        for index, file in enumerate(match_files):
            match_files[index] = file.replace('%s' % \
                                        self.context, WORKSPACE)

        # discover all files that are in given paths
        path_files = []
        paths = jobfiles.get('paths', [])

        # correct / translate user given paths
        for index, path in enumerate(paths):
            if path.startswith('${WORKSPACE}'):
                paths[index] = path.replace('${WORKSPACE}', WORKSPACE)
            elif path.startswith('$WORKSPACE'):
                paths[index] = path.replace('$WORKSPACE', WORKSPACE)
            else:
                paths[index] = '%s/%s' % (WORKSPACE, path)

            # verify if path is a valid file
            if os.path.isfile('%s%s' % (self.context, paths[index])):
                path_files.append(paths[index])


        # 3) discover all files that are pyats job
        pyats_files = list(filter(is_pyats_job, all_files))

        for index, file in enumerate(pyats_files):
            pyats_files[index] = file.replace('%s' % \
                                        self.context, WORKSPACE)

        # concat files paths
        all_files = list(set(match_files + path_files + pyats_files))

        # exclude all __init__.py files
        all_files = list(filter(lambda x: not x.endswith('__init__.py'), all_files))

        # write the files into a file as json
        jobfiles = self.install_dir / 'jobfiles.txt'
        with open('%s' % jobfiles, 'w') as file:
            content = json.dumps({'jobs': all_files})
            file.write(content)

        self.logger.info('Number of discovered job files: %s' % len(all_files))
        self.logger.info('List of job files written to: %s' % jobfiles)

    def docker_build(self,
                     tag=None,
                     build_args={},
                     no_cache=False):
        # Get docker client api
        api = docker.from_env().api
        build_error = []
        image_id = None

        # Trigger docker build
        for line in api.build(path=str(self.context),
                              dockerfile=str(self.install_dir/'Dockerfile'),
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
                    self.logger.debug(contents)

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

    def handle_requirements(self, config):
        if 'match' in requirements:
            # discover requirement files
            pass

        if 'paths' in requirements:
            # specific requirements.txt file by path
            pass

    def run(self,
            config={},
            tag=None,
            keep_context=False,
            no_cache=False,
            dry_run=False):
        """
        Arguments
        ---------
            config (dict): Build configuration
            tag (str): Tag for docker image once built
            keep_context (bool): Prevents deleting the docker build context
                                 directory after the image is built
                                 (only if context was created temporarily)
            no_cache (bool): Forces the rebuilding of intermediate docker image
                             layers
            dry_run (bool): Set up docker build context but do not run build

        Returns
        -------
            Image object when successful
        """
        image = None
        error = None

        # setup build context
        self.setup_context()

        try:
            # Verify schema
            self.logger.info('Verifying schema')
            validate_builder_schema(config)

            # Dump config to yaml file in context
            self.logger.info('Dumping config to file in context')
            (self.install_dir / 'build.yaml').write_text(yaml.safe_dump(config))

            proxy = {}
            if 'proxy' in config:
                self.logger.info('Setting proxy environment variables')
                # Proxy values must only belong to specifically defined keys
                proxy = config['proxy']
                # Update environment with proxy for git and file downloads
                os.environ.update(config['proxy'])

            # Write pip.conf
            if 'pip-config' in config:
                self.handle_pip_config(config['pip-config'])
            
            if 'python' in config:
                # user specified python version

                # Ensure python version is a valid format to use as the base
                # docker image. Appends '-slim' to the given version to acquire
                # the docker image tag.
                ver = str(config['python'])
                if not all([n.isdigit() for n in ver.split('.')]):
                    raise TypeError('Python version must be in format '
                                    '3[.X][.X]')
                python_version = ver + '-slim'
            else:
                # apply default python version
                python_version = DEFAULT_PYTHON_VERSION

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
                self.logger.info('Copying %s to context' % config['snapshot'])
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

            if 'requirements' in config:
                self.handle_requirements(config['requirements'])

            if 'files' in config:
                self.handle_files(config['files'])

            # job discovery
            jobfiles = {}
            if 'jobfiles' in config:
                jobfiles.update(config['jobfiles'])
            self.discover_jobs(jobfiles)

            # Tag for docker image   argument (cli) > config (yaml) > None
            tag = tag or config.get('tag', None)

            # Start docker build
            if not dry_run:
                self.logger.info('Building image')
                image = self.docker_build(tag=tag,
                                          build_args=proxy,
                                          no_cache=no_cache)

                self.logger.info("Built image '%s' successfully" 
                                 % tag if tag else image.id)

        except Exception as e:
            self.logger.exception('Failure while building docker image:')
            # Save error to raise later so we can clean up context first
            error = e

        if not keep_context:
            self.logger.info('Removing temporary build directory')
            shutil.rmtree(self.context)

        if error:
            # After cleaning context, raise error if there was one
            raise error

        return image



