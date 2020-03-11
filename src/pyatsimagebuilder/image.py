import docker


class Image(object):
    def __init__(self, image_id, tag=None):
        """Image

        Arguments
        ---------
            image_id (str): Identification hash for image
            tag (str): The main tag to use for this image
        """
        self.id = image_id
        # Main tag for image - there can be many more
        self._tag = tag
        # Get docker client api
        self._api = docker.from_env().api
        # Check that id is valid (while getting tags)
        tags = self.inspect()['RepoTags']
        # Ensure tag is valid
        if tag:
            if tag not in tags:
                if tag + ':latest' in tags:
                    self._tag += ':latest'
                else:
                    raise KeyError("No tag '%s' associated with image" % tag)

    @property
    def tag(self):
        """
        Retrieve main docker tag for image
        """
        return self._tag

    @tag.setter
    def tag(self, val):
        """
        Set image tag in docker
        """
        # Set tag
        if not self._api.tag(self.id, val):
            raise KeyError("Cannot tag image with '%s'" % val)
        # Look for tag in image inspect
        tags = self.inspect()['RepoTags']
        if val in tags:
            self._tag = val
        elif val + ':latest' in tags:
            self._tag = val + ':latest'
        else:
            raise KeyError("Tag '%s' not found associated with image" % val)

    def inspect(self):
        """
        Retrieve docker inspect for information about the image
        """
        return self._api.inspect_image(self.id)

    def push(self, url=None, tag=None, credentials=None):
        """
        Push image to a registry

        Arguments
        ---------
            url (str): Registry location to prepend to image tag before pushing.
                       Can be omitted if tag already includes the registry.
            tag (str): Specify an alternative repository/tag to upload with.
            credentials (dict): optional override for username and password when
                                pushing image.
        """
        # Get the tag to use
        remote_tag = None
        if tag:
            remote_tag = tag.strip(' /')
        elif self.tag:
            remote_tag = self.tag.strip(' /')
        else:
            # Image must have a tag
            raise KeyError("Image '%s' has no tag" % self.id)

        # Prepend registry if necessary
        if url:
            url = url.strip(' /')
            if not remote_tag.startswith(url):
                remote_tag = '%s/%s' % (url, remote_tag)

        # Apply tag to image and push with new tag
        push_error = []
        if self._api.tag(self.id, remote_tag):
            for line in self._api.push(remote_tag, auth_config=credentials,
                                       stream=True, decode=True):
                if 'errorDetail' in line:
                    push_error.append(line['errorDetail']['message'])
        else:
            raise AttributeError("Cannot tag image with '%s'" % remote_tag)

        # Encountered error when pushing
        if push_error:
            raise Exception("Error pushing image '%s':\n%s"
                            % (remote_tag, '\n'.join(push_error)))

