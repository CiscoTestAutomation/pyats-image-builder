import os
import docker

from jinja2 import Environment, FileSystemLoader

JINJA2_ENV = Environment(loader=FileSystemLoader(os.path.dirname(__file__)),
                         trim_blocks=True,
                         lstrip_blocks=True)
DEFAULT_BASE_IMAGE = 'python'
DEFAULT_BASE_IMAGE_LABEL = '3.7.9-slim'
DEFAULT_TINI_VERSION = '0.18.0'
DEFAULT_WORKSPACE_NAME = 'pyats'

DOCKERIMAGE_TEMPLATE = 'Dockerfile.template'


class Image(object):
    def __init__(self,
                 *,
                 env=None,
                 pre_pip_cmds=None,
                 post_pip_cmds=None,
                 base_image=DEFAULT_BASE_IMAGE,
                 base_image_label=DEFAULT_BASE_IMAGE_LABEL,
                 tini_version=DEFAULT_TINI_VERSION,
                 workspace_name=DEFAULT_WORKSPACE_NAME):

        self._template = JINJA2_ENV.get_template(DOCKERIMAGE_TEMPLATE)

        self.base_image = base_image
        self.base_image_label = base_image_label
        self.tini_version = tini_version
        self.workspace_dir = os.path.join('/', workspace_name)

        # docker id and tag
        self.id = None
        self.tag = None
        self.platform = None

        # environment variables
        self.env = env or {}

        # commands to run before/after pip installation
        self.pre_pip_cmds = pre_pip_cmds
        self.post_pip_cmds = post_pip_cmds


    def manifest(self):
        return self._template.render(image=self)

    def push(self, remote_tag=None, credentials=None):
        """
        Push image to a registry

        Arguments
        ---------
            remote_tag (str): Full name to tag image with before pushing to
                              include a private registry host.
                              ie. registry-host:5000/repo/image:latest
            credentials (dict): optional override for username and password when
                                pushing image.
        """
        # Get the tag to use
        if not remote_tag:
            remote_tag = self.tag

        if not remote_tag:
            # Image must have a tag
            raise KeyError("Image '%s' has no tag" % self.id)

        # Apply tag to image and push with new tag
        push_error = []
        api = docker.from_env().api

        if api.tag(self.id, remote_tag):
            for line in api.push(remote_tag,
                                 auth_config=credentials,
                                 stream=True,
                                 decode=True):
                if 'errorDetail' in line:
                    push_error.append(line['errorDetail']['message'])
        else:
            raise AttributeError("Cannot tag image with '%s'" % remote_tag)

        # Encountered error when pushing
        if push_error:
            raise Exception("Error pushing image '%s':\n%s" %
                            (remote_tag, '\n'.join(push_error)))
