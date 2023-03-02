import os
import re
import yaml
import json
import docker
import logging
import pathlib
import requests
import configparser
import urllib.parse

from .utils import (scp, git_clone, ftp_retrieve, stringify_config_lists,
                    discover_jobs, discover_manifests, to_image_path,
                    search_regex)

from .image import Image
from .schema import validate_builder_schema
from .context import Context

HERE = pathlib.Path(os.path.dirname(__file__))

PIP_CONF_FILE = 'pip.conf'
INSTALLATION = pathlib.Path('installation')
REQUIREMENTS = pathlib.Path('requirements')
REQUIREMENTS_FILE = 'requirements.txt'
ENV_PATTERN = re.compile(r'(%ENV{ *([0-9a-zA-Z\_]+) *})')
IMAGE_BUILD_SUCCESSUL = \
    re.compile(r' *Successfully built (?P<image_id>[a-z0-9]{12}) *$')


class ImageBuilder(object):
    def __init__(self, config, logger=logging.getLogger(__name__)):
        """
        Arguments
        ---------
            config (dict): Build configuration
            logger (logging.Logger): python logger to use for this build
        """

        self._logger = logger
        self._req_counter = 0

        # init defaults
        self.context = None
        self._docker_build_args = {}

        # Verify schema
        self._logger.info('Verifying schema')
        validate_builder_schema(config)

        self.config = config
        self.image = Image()

    def run(self, keep_context=False, tag=None, no_cache=True, dry_run=False):
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
        # create context obj
        self.context = Context(keep=keep_context, logger=self._logger)

        with self.context:

            # create our installation directory
            self.context.mkdir(INSTALLATION)
            self.context.mkdir(INSTALLATION / REQUIREMENTS)

            self._populate_context()

            # Tag for docker image   argument (cli) > config (yaml) > None
            self.image.tag = tag or self.config.get('tag', None)

            # Get Arch for image
            self.image.platform = self.config.get('platform', None)

            # Start docker build
            if not dry_run:
                self._logger.info('Building image')
                self._build_image(no_cache=no_cache)
                self._logger.info("Built image '%s' successfully" %
                                  tag if tag else self.image.id)

        return self.image

    def _populate_context(self):

        # replace config with environment variables
        self._replace_environment_variables()

        if 'python' in self.config:
            # user specified python version/label

            # Ensure python version is a valid format to use as the base
            # docker image. Appends '-slim' to the given version to acquire
            # the docker image tag.
            label = str(self.config['python'])
            if not all([n.isdigit() for n in label.split('.')]):
                raise TypeError('Python version must be in format '
                                '3[.X][.X]')

            self.image.base_image_label = label + '-slim'

        # Formatted environment variable to add to Dockerfile
        if 'env' in self.config:
            self.image.env.update(self.config['env'])

        # Docker commands to insert into the Dockerfile. Very risky.
        if 'cmds' in self.config:
            self.image.pre_pip_cmds = self.config['cmds'].get('pre', '')
            self.image.post_pip_cmds = self.config['cmds'].get('post', '')

        # handle proxy
        if 'proxy' in self.config:
            self._process_proxy(self.config['proxy'])

        # generate pip.conf in context
        if 'pip-config' in self.config:
            self._process_pip_config(self.config['pip-config'])

        repo_list = []
        if 'snapshot' in self.config:
            repo_list.extend(
                self._process_snapshot(self.config['snapshot']))

        if 'repositories' in self.config:
            repo_list.extend(
                self._process_repositories(self.config['repositories']))

        if 'files' in self.config:
            self._process_files(self.config['files'])

        if 'requirements' in self.config:
            self._discover_requirements_txt(self.config['requirements'])

        # write config/packages last
        # this ensures these "high-level" packages are installed last
        # pip install hierarchy = snapshot, then git repo discovered, then
        # from config
        if 'packages' in self.config:
            self._write_requirements_file(self.config['packages'])

        # job discovery
        job_paths = discover_jobs(jobfiles=self.config.get('jobfiles', {}),
                                  search_path=self.context.path,
                                  ignore_folders=[INSTALLATION],
                                  relative_path=self.image.workspace_dir)

        if job_paths:
            # write the files into a file as json
            self.context.write_file(INSTALLATION / 'jobfiles.txt',
                                    json.dumps({'jobs': job_paths}))

            self._logger.info('List of job files written to: %s' %
                              (INSTALLATION / 'jobfiles.txt'))

        # Convert list of repos into a dict with corrected image paths
        # This is the format that will be written to a json file
        repo_data = {}
        if repo_list:
            for repo in repo_list:
                repo['path'] = to_image_path(repo['path'],
                                             self.context.path,
                                             self.image.workspace_dir)
                repo_data[repo['path']] = repo

        # manifest/repo discovery
        super_manifest = discover_manifests(search_path=self.context.path,
                                            ignore_folders=[INSTALLATION],
                                            relative_path=self.image.workspace_dir,
                                            repo_data=repo_data)

        if super_manifest:
            # write the files into a file as json
            self.context.write_file(INSTALLATION / 'manifest.json',
                                    json.dumps(super_manifest))

            self._logger.info('List of manifest files written to: %s' %
                              (INSTALLATION / 'manifest.json'))

        if repo_data:
            # write dict of repos into a json file
            self.context.write_file(INSTALLATION / 'repos.json',
                                    json.dumps(repo_data))

            self._logger.info('List of git repos written to: %s' %
                              (INSTALLATION / 'repos.json'))

        # Write formatted Dockerfile in context
        self._logger.info('Writing formatted Dockerfile')
        self.context.write_file(INSTALLATION / 'Dockerfile',
                                self.image.manifest())

        # Dump config to yaml file in context
        self._logger.info('Saving config to context folder')
        self.context.write_file(
            INSTALLATION / 'build.yaml',
            yaml.safe_dump(self.config, default_flow_style=False))

    def _process_snapshot(self, snapshot_file):
        # Extend given packages and repositories with any python
        # packages or repositories in the snapshot file
        with open(snapshot_file) as f:
            snapshot = yaml.safe_load(f.read())

        self._logger.info('Copying %s to context' % snapshot_file)

        # keep a copy of it in context
        self.context.copy(snapshot_file, INSTALLATION / 'snapshot.yaml')

        # process the snapshot content
        repo_list = []
        if 'repositories' in snapshot:
            repo_list = self._process_repositories(snapshot['repositories'])

        if 'packages' in snapshot:
            self._write_requirements_file(snapshot['packages'])

        return repo_list

    def _process_proxy(self, proxy_config):
        self._logger.info('Setting proxy environment variables')
        # Proxy values must only belong to specifically defined keys

        # Update environment with proxy for git and file downloads
        os.environ.update(proxy_config)

        # if proxy is set, it's required for docker build
        self._docker_build_args.update(proxy_config)

    def _process_files(self, files):
        self._logger.info('Adding files to workspace')
        for from_path in files:
            name = None
            # If a file/dir is given as a dict, the key is the desired name for
            # that file/dir in the docker image
            # files:
            #   - /path/to/a_file
            #   - new_name: /path/to/original_name
            if isinstance(from_path, dict):
                name, from_path = next(iter(from_path.items()))

            # Files can be given as urls to be downloaded
            url_parts = urllib.parse.urlsplit(from_path)

            # Use original file name if a new one is not provided
            if not name:
                name = os.path.basename(url_parts.path.rstrip('/'))

            # compute where it goes to
            to_path = self.context.path / name

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
                self._logger.info('Copying %s' % from_path)
                self.context.copy(from_path, to_path)

            elif url_parts.scheme in ['http', 'https']:
                # Download with GET request
                self._logger.info('Downloading %s' % from_path)
                r = requests.get(from_path)
                if r.status_code == 200:
                    to_path.write_bytes(r.content)
                else:
                    raise Exception('Could not download %s' % from_path)
            elif url_parts.scheme == 'scp':
                # scp file or dir. Must have passwordless ssh set up.
                self._logger.info('Copying with scp %s' % from_path)
                scp(host=host,
                    from_path=url_parts.path,
                    to_path=to_path,
                    port=port)
            elif url_parts.scheme in ['ftp', 'ftps']:
                # ftp file. Uses anonymous credentials.
                self._logger.info('Retreiving from ftp %s' % from_path)
                ftp_retrieve(host=host,
                             from_path=url_parts.path,
                             to_path=to_path,
                             port=port,
                             secure=url_parts.scheme == 'ftps')

    def _process_repositories(self, repositories):
        # Clone all git repositories and checkout a specific commit
        # if one is given
        self._logger.info('Cloning git repositories')

        repo_list = []
        for name, vals in repositories.items():
            self._logger.info('Cloning repo %s' % vals['url'])

            # Ensure dir is within workspace, and does not already exist
            target = self.context.path / name

            assert not target.exists(), "%s already exists" % name

            credentials = vals.pop('credentials', None)
            if credentials:
                vals['credentials'] = {
                    'username': '*' * 8,
                    'password': '*' * 8
                }

            ssh_key = vals.pop('ssh_key', None)
            if ssh_key:
                vals['ssh_key'] = '*' * 8

            GIT_SSL_NO_VERIFY = vals.get('GIT_SSL_NO_VERIFY', False)

            # Clone and checkout the repo
            git_info = git_clone(vals['url'], target,
                                 vals.get('commit_id', None), True,
                                 credentials, ssh_key, GIT_SSL_NO_VERIFY)

            # Save repo info here since .git was deleted
            repo_list.append(git_info)

            # clone repo's requirements-txt file
            if vals.get('requirements_file', False) is True:
                if (target / REQUIREMENTS_FILE).exists():
                    self._register_requirements_file(target /
                                                     REQUIREMENTS_FILE)

        return repo_list

    def _write_requirements_file(self, packages):
        # Generate python requirements file
        self._req_counter += 1
        filename = '%s-%s' % (self._req_counter, REQUIREMENTS_FILE)

        self._logger.info('Writing %s' % filename)

        # support for rel path and $WORKSPACE files
        package_content = '\n'.join(to_image_path(
            i, self.context, self.image.workspace_dir) for i in packages)

        self.context.write_file(INSTALLATION / REQUIREMENTS / filename,
                                package_content)

    def _register_requirements_file(self, file):
        self._req_counter += 1
        filename = '%s-%s' % (self._req_counter, REQUIREMENTS_FILE)
        self.context.copy(file, INSTALLATION / REQUIREMENTS / filename)

    def _discover_requirements_txt(self, config):
        # 1. find all the requirement files in context by regex pattern
        requirement_files = search_regex(config['match'], [INSTALLATION,])

        # 2. find all requirement files by glob
        for pattern in config.get('glob', []):
            requirement_files.extend(self.context.search_glob(pattern))

        # 3. find all requirement files by specificy paths
        for path in config.get('paths', []):
            path = self.context.path / path

            if path.exists() and path.is_file():
                requirement_files.append(path)

        # register them
        for file in requirement_files:
            self._register_requirements_file(file)

    def _process_pip_config(self, config):
        # pip config for setting things like pypi server.
        self._logger.info('Writing %s file' % PIP_CONF_FILE)

        confparse = configparser.ConfigParser()

        if isinstance(config, dict):
            # convert from dict
            stringify_config_lists(config)
            confparse.read_dict(config)

            with self.context.open(PIP_CONF_FILE, 'w') as f:
                confparse.write(f)

        elif isinstance(config, str):
            # ensure format is valid, but leave the contents to pip
            confparse.read_string(config)
            self.context.write_file(PIP_CONF_FILE, config)

    def _build_image(self, no_cache=False):

        # copy entrypoint to the context
        self._logger.info('Copying entrypoint to context')
        self.context.copy(HERE / 'docker-entrypoint.sh',
                          INSTALLATION / 'entrypoint.sh')

        # Get docker client api
        api = docker.from_env().api
        build_error = []

        # Trigger docker build
        for line in api.build(path=str(self.context.path),
                              dockerfile=str(INSTALLATION / 'Dockerfile'),
                              tag=self.image.tag,
                              platform=self.image.platform,
                              rm=True,
                              forcerm=True,
                              buildargs=self._docker_build_args,
                              decode=True,
                              nocache=no_cache):

            # If we encounter an error, capture it
            if 'errorDetail' in line:
                build_error.append(line['errorDetail']['message'])

            # retrieve image ID
            if 'aux' in line and 'ID' in line['aux']:
                self.image.id = line['aux']['ID']

            # Log stream from build
            if 'stream' in line:
                contents = line['stream'].rstrip()
                if contents:
                    self._logger.debug(contents)

                # retrive image ID in steam log
                match = IMAGE_BUILD_SUCCESSUL.search(contents)
                if match:
                    self.image.id = match.group('image_id')

        api.close()

        # Error encountered, raise exception with message
        if build_error:
            raise Exception('Build Error:\n%s' % '\n'.join(build_error))

        if not self.image.id:
            # we've failed to set the image id - something is wrong!
            raise Exception('No confirmation of successful build.')

    def _replace_environment_variables(self):

        _recursive_handle_leaf(self.config, _replace_environment_variable)


def _replace_environment_variable(data):
    replace_list = re.findall(ENV_PATTERN, data)
    for replace_item in replace_list:
        data = data.replace(replace_item[0], os.environ[replace_item[1]])
    return data


def _recursive_handle_leaf(data, handle):
    if isinstance(data, dict):
        for key in data:
            if isinstance(data[key], str):
                data[key] = handle(data[key])

            elif isinstance(data[key], list):
                for i in range(len(data[key])):
                    if isinstance(data[key][i], str):
                        data[key][i] = handle(data[key][i])
                    else:
                        pass

            elif isinstance(data[key], dict):
                _recursive_handle_leaf(data[key], handle)
            else:
                pass
    else:
        raise TypeError("Need dict, type={}".format(type(data)))
