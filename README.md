
# pyATS Docker Build

pyATS Docker Build is a stand-alone executible package for generating Docker
images that have all the necessary components to run a pyATS job. A single YAML
file must be created to define all of these components. Requires a local Docker
installation to build the image.

To start building an image, run:

`$ pyats-docker-build build.yaml`

# Image

## Layout

Three main directories are created when building the image:
- `$WORKSPACE` is where all user specified files and repositories are stored. It
is also the working directory when running the docker image.
- `$INSTALL_DIR` is where files related to the building of the image are stored.
There is a copy of the yaml file used to create an image at
`$INSTALL_DIR/build.yaml`.
- `$VENV_DIR` which is where the python virtual env is created.

## Build Process

The image is built in two main stages. First, pyATS Docker Build sets up the
image context on the host machine, then it triggers a Docker build using this
context.

### Context Setup

Within the context, pyATS Docker Build creates an image directory, which will
have all of its contents copied to the root of the image. Inside this image
directory is a workspace directory, an install directory, and a venv directory
that will become `$WORKSPACE`, `$INSTALL_DIR`, and `$VENV_DIR`.

All file retrieval and git cloning is done in the workspace directory to make
use of user permissions not available within the docker image.

The `packages` list is used to generate a `requirements.txt` file inside the
install directory, to be used later on in the image. Additionally, the
entrypoint script is also copied to the install directory.

A `pip.conf` file is generated in the venv directory if specified in the yaml
file. This can be used to specify a different pypi server, as well as many
other pip options.

### Docker Build

pyATS Docker Build uses a base image of `python:{version}-slim`. The default
version is `3.6.9` but can be specified by the user.

The entirety of the context image directory is copied to the image root, which
creates the `$WORKSPACE`, `$INSTALL_DIR`, and `$VENV_DIR` directories.

A Python virtual environment is created in `$VENV_DIR`, and all specified Python
packages are installed with pip from `$INSTALL_DIR/requirements.txt`. Some
packages require non-python dependencies (eg. gcc), which are unlikely to be
included in the image since it is so minimal. Advanced users familiar with
docker can use the `cmds` section of the yaml to install these dependencies,
however this will have a negative impact on the final size of the image.

# YAML file

``` yaml
tag: "mypyatsimage:latest" # Docker tag for the image once it is built
python: 3.6.8 # Python version to use as base docker image
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
  - pyats[full]>=20.1,<20.2 # Supports package version restrictions
  - otherpackage1==1.0
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

- pyATS Docker Build does not support any user interaction once building starts,
  so [passwordless ssh authentication](https://www.debian.org/devel/passwordlessssh)
  must be set up in advance in order to download files with scp.
- Requires an absolute path to be parsed correctly.
- Supports recursively copying entire directories.
- Specifying the user in the URI is optional.
- Port can be specified in the URI: `scp://user@remotehost:23/path/to/file`.

### ftp

- Only single files can be retrieved with ftp.
- pyATS Docker Build uses the anonymous login for ftp, so the file must be
  accesible to anonymous users.

---

## Pip Configuration

pyATS Docker Build uses the values from `pip-config` to build a `pip.conf` file
in *.ini* format.

This YAML:

``` yaml
pip-config:
  global:
    format: columns
    no-cache-dir: false
    trusted-host: |
      pypi.python.org
      pyats-pypi.cisco.com
    index-url: "http://pyats-pypi.cisco.com/simple"
    disable-pip-version-check: 1
  search:
    index: "http://pyats-pypi.cisco.com"
```

Produces this pip.conf:

``` ini
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
