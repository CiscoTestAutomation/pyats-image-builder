
# pyATS Image Builder

pyATS Image Builder is a stand-alone executable package for generating Docker
images that have all the necessary components to run a pyATS job. A single YAML
file must be created to define all of these components. Requires a local Docker
installation to build the image. For consistency, the entirety of an image name
including the registry, repository, name, and tag is referred to as a 'tag' in
this package. Docker tags (such as `:latest`) are not considered separately.

## General Information

- Website: https://developer.cisco.com/pyats/
- Documentation: https://developer.cisco.com/site/pyats/docs/


## Installation

To install this package, simply:

```bash

bash$ pip install pyats-image-builder
```

## Usage

This package does not require [pyATS](https://developer.cisco.com/pyats/) to be
installed in your environment. It features its own command line interface,
`pyats-image-build`. However, if you have `pyats` installed in this environment,
this functionality is also accessible as `pyats image` command.

```
usage: pyats-image-build [-h] [--tag TAG] [--path PATH] [--no-cache]
                         [--keep-context] [--dry-run] [--verbose]
                         file

Create Docker images for running pyATS jobs

positional arguments:
  file                  YAML file defining the image to be built.

optional arguments:
  -h, --help            show this help message and exit
  --tag TAG, -t TAG     Tag for Docker image. Overrides any tag defined in the
                        yaml.
  --path PATH, -p PATH  Specify a path to use as the context while building.
  --no-cache, -c        Do not use the cache when building the image.
  --keep-context, -k    Prevents the context dir from being deleted once the
                        image is built
  --dry-run, -n         Set up the context but do not build the image. Use
                        with --keep-context.
  --verbose, -v         Prints the output of docker build.
```


# Image

## Layout

Three main directories are created when building the image:
- `$WORKSPACE` is where all user specified files and repositories are stored. It
is also the working directory when running the Docker image.
- `$WORKSPACE/installation` is where files related to the building of the image
are stored. There is a copy of the yaml file used to create an image named
`build.yaml`, and the entrypoint script for starting a Docker container.
- `$VIRTUAL_ENV` which is where the python virtual env is created.

## Build Process

The image is built in two main stages. First, pyATS Image Builder sets up the
image context on the host machine, then it triggers a Docker build using this
context.

### Context Setup

Within the context, pyATS Image Builder creates an image directory, which will
have all of its contents copied to the root of the image. Inside this image
directory is a workspace directory and a virtual env directory that will become
`$WORKSPACE` and `$VIRTUAL_ENV`.

All file retrieval and git cloning is done in the workspace directory to make
use of user permissions not available within the docker image.

The `packages` list is used to generate a `requirements.txt` file inside the
installation directory, which is in the workspace directory. This file is used
later on in the Docker build stage. Additionally, the entrypoint script is also
copied to the installation directory.

A `pip.conf` file is generated in the virtual env directory if specified in the
yaml file. This can be used to specify a different pypi server, as well as many
other pip options.

### Docker Build

pyATS Image Builder uses a base image of `python:{version}-slim`. The default
version is `3.6.9` but can be specified by the user.

The entirety of the context image directory is copied to the image root, which
creates the `$WORKSPACE` and `$VIRTUAL_ENV` directories.

A Python virtual environment is created in `$VIRTUAL_ENV`, and all specified
Python packages are installed with pip from
`$WORKSPACE/installation/requirements.txt`. Some packages require non-python
dependencies (eg. gcc), which are unlikely to be included in the image since it
is so minimal. Advanced users familiar with Docker can use the `cmds` section of
the yaml to install these dependencies, however this will have a negative impact
on the final size of the image.

# YAML file

``` yaml
tag: "mypyatsimage:latest" # Docker tag for the image once it is built
python: 3.6.8 # Python version to use as base Docker image
env: # Mapping to set as environment variables in the image
  VAR1: VALUE1
  VAR2: VALUE2
files: # List of files/directories to copy to the image
    # A single file/dir on local host
  - /path/to/file1
    # A key can be given to provide a new name for the file
  - myfile_2: /path/to/file2
    # A key can also change the destination location
  - dirname/file3: /path/to/file3
    # Files can be downloaded from a web address
  - "https://webaddress.com/path/to/file4"
    # Keys work to rename files retrieved in any manner
  - myfile_5: "https://webaddress/path/to/file5"
    # Also supports scp
  - "scp://[user@]remotehost/path/to/file6"
    # Also supports ftp
  - "ftp://remotehost:2121/path/to/file7"
packages: # List of python packages to install
  - pyats[full]
  - otherpackage1==1.0 # Supports package version restrictions
  - otherpackage2==2.0
pip-config: # Values to be converted into a pip.conf file
  # [global]
  # disable-pip-version-check = 1
  global:
    disable-pip-version-check: 1
repositories: # Mapping of all git repositories to clone
  reponame: # Key is the name of the directory to clone to
    # Url to remote git repo
    url: "ssh://git@address/path/to/repo.git"
    # Optional commit ID to switch to after cloning
    commit_id: abcd1234
  dirname/repo2name: # Key supports cloning into a subdirectory
    url: "https://address/path/to/repo2.git"
snapshot: /path/to/snapshot/file.yaml # pyATS environment snapshot file
proxy: # Specific proxy arguments used by Docker during image building
  HTTP_PROXY: "http://127.0.0.1:1111"
  HTTPS_PROXY: "https://127.0.0.1:1111"
  FTP_PROXY: "ftp://127.0.0.1:1111"
  NO_PROXY: "*.test.example.com,.example2.com"
cmds: # Additional commands to be inserted into the Dockerfile
  # WARNING: This can have unintended consequences. Only use if you are
  # *absolutely* sure about what you are done.
  pre: "dockercommand" # Inserts a command before pip install
  post: "dockercommand" # Inserts a command after pip install
```

---

## Environment Variables

The environment variable `$WORKSPACE` is automatically set as the absolute path
to the image workspace. This is where all files and repositories are kept, and
is the working directory when starting a container. This variable can be used
in other variables since it is defined before. For example:

``` yaml
env:
  PYTHONPATH: ${WORKSPACE}/repo1dir/:${WORKSPACE}/repo2dir/
repositories:
  repo1:
    url: "ssh://git@address/path/to/a/repo.git"
  repo2:
    url: "ssh://git@address/path/to/another/repo.git"
```

This would clone two git repos into directories `repo1` and `repo2` in the
workspace. It would also add the locations of these repos to `$PYTHONPATH`,
which would allow Python to discover and import and scripts in those
repositories.

---

## Files

### scp

- pyATS Image Builder does not support any user interaction once building
  starts, so
  [passwordless ssh authentication](https://www.debian.org/devel/passwordlessssh)
  must be set up in advance in order to download files with scp.
- Requires an absolute path to be parsed correctly.
- Supports recursively copying entire directories.
- Specifying the user in the URI is optional.
- Port can be specified in the URI: `scp://user@remotehost:23/path/to/file`.

### ftp

- Only single files can be retrieved with ftp.
- pyATS Image Builder uses the anonymous login for ftp, so the file must be
  accesible to anonymous users.

---

## Pip Configuration

There are two ways to give a configuration for pip. The first is give all the values of the configuration in YAML format under `pip-config` which will be parsed into configuration format. The second is to give an already formatted configuration as a multi-line string under `pip-config`.

These two methods are equivalent:

``` yaml
pip-config:
  global:
    format: columns
    no-cache-dir: false
    trusted-host:
      - pypi.python.org
      - pyats-pypi.cisco.com
    index-url: "http://pyats-pypi.cisco.com/simple"
    disable-pip-version-check: 1
  search:
    index: "http://pyats-pypi.cisco.com"
```

``` yaml
pip-config: |
  [global]
  format = columns
  no-cache-dir = false
  trusted-host = pypi.python.org
          pyats-pypi.cisco.com
  index-url = http://pyats-pypi.cisco.com/simple
  disable-pip-version-check = 1

  [search]
  index = http://pyats-pypi.cisco.com
```

---

## Packages

The `packages` list also works with local wheel files, and can use the
`$WORKSPACE` environment variable to locate them. This example shows how a user
could download a wheel file from a remote host, and install that file with pip.

``` yaml
files:
  - "scp://[user@]remotehost/path/to/packagename.whl"
packages:
  - ${WORKSPACE}/packagename.whl
```

---

## Repositories

The user must have the ability to clone the listed git repositories without any
password input. The are instructions for
[GitHub](https://help.github.com/en/github/authenticating-to-github/generating-a-new-ssh-key-and-adding-it-to-the-ssh-agent)
and
[Bitbucket](https://confluence.atlassian.com/bitbucket/set-up-an-ssh-key-728138079.html)
on how to set up ssh for git.

---

## Snapshot

A snapshot created with `pyats environment snapshot` contains installed python
packages and git repositories cloned inside the virtual environment. A snapshot
file can be specified in the build yaml to extend the list of packages and
repositories already defined.

---

## Proxy

Proxy configuration can be set permanently using environment variables in the
env mapping, but in the case where a proxy is desired only for the duration of
building the image, the configuration can be set in the proxy mapping. This
configuration will not be set in containers run from the built image.

# Running the image

To run the newly generated image, do:
```bash
$ docker run [--rm] [-it] [-v LOCAL:CONTAINER] IMAGE [COMMAND]
```
Where `[IMAGE]` is the image tag or ID. `--rm` is an optional flag to remove the
container once finished. `-it` are optional flags that allow the container to
run interactively. `-v LOCAL:CONTAINER` is the optional argument that mounts a
file or directory `LOCAL` to the specified location `CONTAINER` in the
container. Both paths must be absolute. When no command is given, the container
will default to starting a bash session.

To run a pyATS job, the command would look like:
```bash
$ docker run --rm myimg:latest pyats run job myrepo/myjob.py
```
In this case, the job file in question is `$WORKSPACE/myrepo/myjob.py`. The
starting working directory of the image is `$WORKSPACE` which is why it does not
need to be specified in the command.

It may be beneficial to set an environment variable with the location of a job
file or any other information by defining it in the YAML file. These variables
cannot be used directly on the command line since the host will attempt to
interpolate variables before executing Docker. There are two methods to use
environment variables in the Docker container.

---

## Instructions File

Environment variables can be specified inside a small bash script without any
issues. This script can then be mounted and executed inside the container. This
has the additional benefit of allowing multiple commands to be passed without
running the container interactively

Create a small bash script that has all the commands and variables.

`run.sh`:
```bash
echo "\$JOBFILE is $JOBFILE"
echo "\TESTBEDFILE is $TESTBEDFILE"
pyats run job $JOBFILE --testbed-file $TESTBEDFILE
```
Then mount and run this file when running the container.
```bash
$ docker run --rm -v $(pwd)/run.sh:/mnt/run.sh myimg:latest bash /mnt/run.sh
```
This mounts the local file `run.sh` to the location `/mnt/run.sh` in the
container, and executes this file with bash.

A user created python file could also be mounted and run in the exact same
manner.
```bash
$ docker run --rm -v $(pwd)/run.py:/mnt/run.py myimg:latest python /mnt/run.py
```

---

## Bash Interpolation

Variables can be preserved when passed from the command line.
```bash
$ docker run --rm myimg:latest bash -c 'pyats run job $JOBFILE'
```
Bash does not interpolate anything within single quotes, so the entire command
is preserved as a string in this way when passed to Docker. Then the command
`bash -c` will interpolate and execute the string inside the Docker container,
which will resolve variables correctly.


# API

pyATS Image Builder can also be used directly from another Python script using
the `build()` function and `Image` class.

## `build()`

```python
build(config = {}, path = None, tag = None, keep_context = False,
      verbose = False, stream = None, no_cache = False, dry_run = False)
```

| Argument | Description |
| -------- | ----------- |
| config | The mapping typically loaded from the yaml file. Defines Python packages to install, files to copy, etc. Refer to the `YAML file` section for the schema. |
| path | An alternative path to use as the image context. If this location already exists, it will not be cleaned upon finishing the image build. If this location does not exist, pyATS Image Builder will attempt to create it. If not given, a temporary location will be used. |
| tag | A Docker tag for the completed image that takes precedence over any tag defined inside the config. |
| keep_context | When `True` prevents the context directory from being cleaned after the build is finished. |
| verbose | When `True` logs the entire Docker build process to the console. |
| stream | An IO Stream to write the logging output to. This will always include the Docker build logs. |
| no_cache | When `True` prevents Docker from using cached images when building, forcing intermediate images to be rebuilt. |
| dry_run | When `True` prevents the Docker build from happening after assembling the context. |

### Returns

On success, `build()` will return an Image object representing the Docker Image just built. This can be queried for information or used to push the image to a registry.

```python
from pyatsimagebuilder import build
config = {'tag':'mypyatsimage:latest', 'packages': ['pyats[full]']}
image = build(config=config)
```

---

## Image Class

The `Image` class can retrieve information about the newly created image, as
well as the push the image to a registry.

```python
Image(image_id, tag = None)
```

| Argument | Description |
| -------- | ----------- |
| image_id | The hash identifier for this image. |
| tag | The main tag to use for this image, since images can have multiple tags. If not provided here, must be given when pushing the image instead. |

### `inspect()`

An `Image` object can be queried with `inspect()` for a dict with detailed
information about the associated Docker image.

```python
image = build(config)
image.inspect()
# {
#   "Id": "sha256:...",
#   "RepoTags": ["myimg:latest"],
#   "Parent": "sha256:...",
#   "Created": "2020-01-01T20:00:00.0000000Z",
#   ...
# }
```

### `push()`

An `Image` object has a method for pushing the associate Docker image to a
registry. Can add a new tag to the image with the registry address for pushing
to a private registry.

```python
push(remote_tag = None, credentials = None)
```

| Argument | Description |
| -------- | ----------- |
| remote_tag | A tag to apply to the image before pushing in order to add the registry. |
| credentials | A dict of `username` and `password` to authenticate with instead of the credentials configured in Docker. |

```python
image = build(config)
image.push(remote_tag='myregistry.domain.com:5000/myrepo/custom:latest',
           credentials={'username':username, 'password':password})
```
