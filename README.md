
# pyATS Image Builder

pyATS image builder is a utility package aiming to standardize the building of
pyATS test scripts and their corresponding environment dependencies into Docker
images.

It does so by abstracting away the need to directly write Dockerfiles, and
instead presents the common, boilerplate dependency handling paradigms into
a simple to use YAML file.

In addition, this package helps conventional users make their scripts portable
by leveraging the power of Docker, without requiring them to understand how
the Docker image building process works.

> No Docker expertise necessary - though, basic familiarity would help.

## General Information

- Website: https://developer.cisco.com/pyats/
- Documentation: https://developer.cisco.com/site/pyats/docs/
- Docker Build: https://docs.docker.com/engine/reference/commandline/build/

## Requirements

- Linux Environment
- Docker Engine installed in your machine/server (https://docs.docker.com/engine/)
- Python 3.5+ Environment

## Installation

To install this package, simply `pip install` it onto your server's Python
environment.

```bash

bash$ pip install pyats-image-builder
```

## Usage

This package does not require [pyATS](https://developer.cisco.com/pyats/) to be
installed. It features its own command line interface, `pyats-image-build`.

However, if you do install this package into an existing pyATS virtual
environment the primary `pyats` command will be automatically updated to include
this package's functionality under `pyats image build` sub-command.

```
usage: pyats-image-build [-h] [--tag TAG] [--path PATH] [--no-cache]
                         [--keep-context] [--dry-run] [--verbose]
                         file

       pyats image build [-h] [--tag TAG] [--path PATH] [--push] [--no-cache]
                         [--keep-context] [--dry-run] [--verbose]
                         file

Create standard pyATS Docker images

positional arguments:
  file                  YAML build file describing the image build details.

optional arguments:
  -h, --help            show this help message and exit
  --tag TAG, -t TAG     Tag for docker image. Overrides any tag defined in the
                        yaml.
  --path PATH, -p PATH  Specify a path to use as the context directory used
                        for building Docekr image
  --push, -P            Push image to Dockerhub after buiding
  --no-cache, -c        Do not use any caching when building the image
  --keep-context, -k    Prevents the Docker context directory from being
                        deleted once the image is built
  --dry-run, -n         Set up the context directory but do not build the
                        image. Use with --keep-context.
  --verbose, -v         Prints the output of docker build
```

# Basic Concepts

<dl>
  <dt>YAML Build File</dt>
  <dd>The input file containing the build instructions and dependencies, in YAML format. See section below on syntax and feature support.</dd>
  <dt>Image Name, Tag</dt>
  <dd>See <a href="https://docs.docker.com/engine/reference/commandline/tag/#extended-description">official documentation</a> for details.</dd>
  <dt>Build Context Directory</dt>
  <dd>Folder that includes all the files necessary for the build process. See <a href="https://docs.docker.com/engine/reference/commandline/build/#extended-description">official documentation</a> for further details.</dd>
</dl>

# YAML Build File

The package abstract away the need to write your own Dockerfile (and having to
deal with [dockerfile syntax](https://docs.docker.com/engine/reference/builder/)).
Instead, it uses a human-readable YAML syntax as input, performs the necessary
actions such as:

- copying files
- cloning repositories
- installing Python packages

in a standardized fashion, and ensures all built-images looks & feels similar.

## Build File Syntax

``` yaml
tag: "mypyatsimage:latest"      # Docker name/tag for the image

python: 3.6.8                   # Your desired Python version

env:                            # environment variables to be set within the image
  "<name>": "<value>"           # <- format
  MY_VARIABLE: "my-value"       # <- example

files:                          # list of files from various sources to be copied into the image
                                # supports syntax for copying files from:
                                #   - localhost (this server)
                                #   - remote URL
                                # [Optional]

  - /path/to/file1              # copy a localhost file to /pyats/

  - myfile_2: /path/to/file2    # copy a localhost file to /pyats/ and renaming it

  - dirname/file3: /path/to/file3               # copy a localhost file to /pyats/ directory

  - "https://webaddress.com/path/to/file4"      # download remote file to /pyats/

  - myfile_5: "https://webaddress/path/to/file5"   # download remote file to /pyats/, and rename it

packages:                       # List of python packages to be installed into the virtual environment
  - pyats[full]
  - otherpackage1==1.0
  - otherpackage2==2.0

repositories:                   # Git repositories to clone and include in the image
                                # [Optional]

  "<name_of_repo>":             # name of the folder to clone to
    url: "ssh://git@address/path/to/repo.git"       # clone source URL
    commit_id: abcd1234                             # [Optional] Commit-id/branch to checkout after cloning
    ssh_key: "<private_ssh_key>"                    # [Optional] Private ssh key for private repositories

  dirname/repo2name:            # alternatively, you can also specify a sub-folder to clone to
    url: "https://address/path/to/repo2.git"
    credentials:                                    # [Optional] Git credentials for private repositories
        username: "<git_username>"
        password: "<git_password>"

jobfiles:                       # Additional criteria to consider in job discovery in the image
                                # [Optional]

  paths:                        # list of paths to the jobfiles
    - relative/path/to/job.py                       # relative path from /pyats
    - /pyats/absolute/path/to/job.py                # absolute path to job in image
  match:                        # list of regex expressions to match python jobfiles
    - .*job.py

proxy:                          # proxy variables - use this if your host server is behind a proxy
                                # (needed for pip installations using public PyPI servers)
  HTTP_PROXY: "http://127.0.0.1:1111"
  HTTPS_PROXY: "https://127.0.0.1:1111"
  FTP_PROXY: "ftp://127.0.0.1:1111"
  NO_PROXY: "*.test.example.com,.example2.com"

cmds:                           # Additional commands to be inserted into the Dockerfile
                                # To be executed before and after the pip install process
                                # WARNING: This can have unintended consequences.
                                # Only use if you are *absolutely* sure about what you are done.
                                # [Optional]
  pre: "dockercommand"          # Docker command(s) in string format, executed before pip installation
  post: "dockercommand"         # Docker command(s) in string format, executed after pip installation

pip-config:                     # Custom pip configuration values
  global:
    disable-pip-version-check: 1
```

#### `tag`
Docker name/tag to assign to this image after build finishes. This name must
obey the [official docker image naming convention](https://docs.docker.com/engine/reference/commandline/tag/#extended-description).

You can override the provided name/tag using the `--tag` argument from the
command line

#### `python`
Your desired Python version. The pyATS Image Builder builds from a base image of
`python:{version}-slim`. The default version is `3.6.9`.

> Make sure your specified version exists at https://hub.docker.com/_/python

#### `env`
Environment variables to be defined in the image. These environment variables
will persist in the built image - and visible in your pyATS job runs.

In addition to your custom ones, the builder automatically sets environment
variable `$WORKSPACE`, typically referring `/pyats` directory. This can be
used to dynamically reference files:

``` yaml
# cloning two repositories to workspace, and adding them to your PYTHONPATH
env:
  PYTHONPATH: ${WORKSPACE}/repo1dir/:${WORKSPACE}/repo2dir/
repositories:
  repo1:
    url: "ssh://git@address/path/to/a/repo.git"
  repo2:
    url: "ssh://git@address/path/to/another/repo.git"
```

#### `files`

Section to specify the list of files or folders to copy to `/pyats`. This
section allows you to specify both localhost files and remote files to include
in your build image, and as well give you a place to rename them on copy.

```yaml
# Format
files:
    - <list of files>
    - <in yaml format>
    - <to copy>
```

List entires under `files` block supports a few different input formats:

- `/path/to/file`: copies a this particular file from your host system to
  `/pyats/file`

- `new_name: /path/to/file`: copies + rename file, to `/pyats/new_name`

- `new_dir/new_name: /path/to/file`: copies + rename file to `/pyats/new_dir/new_name`

In addition, in addition to localhost files, you can also specify remote files
by URL scheme:

- `scp://[user@]remotehost/path/to/file`: SCP this file to `/pyats/file`
- `ftp://remotehost:2121/path/to/file`: same as above, but this time using FTP
- `https://webaddress/path/to/file`: same as above, using HTTPS (file-get)

You can also rename remote files, and move them into sub-directories:

```yaml

files:
    - subdir/new_name: https://webaddress/path/to/file
    - new_ftp_file_name: ftp://remotehost:2121/path/to/file
```

**SCP Limitations**
- pyATS Image Builder does not support any user interaction once building
  starts, so
  [passwordless ssh authentication](https://www.debian.org/devel/passwordlessssh)
  must be set up in advance in order to download files with scp.
- Requires an absolute path to be parsed correctly.
- Supports recursively copying entire directories.
- Specifying the user in the URI is optional.
- Port can be specified in the URI: `scp://user@remotehost:23/path/to/file`.

**FTP Limitations**
- Only single files can be retrieved with ftp.
- pyATS Image Builder uses the anonymous login for ftp, so the file must be
  accessible to anonymous users.


#### `packages`
List of packages and their corresponding versions to install. Similar to a
`pip freeze` output, but on a line-by-line basis.

```yaml
# Format
packages:
    - <name>
    - <name>==<version>

# Example
packages:
    - pyats[full]>=20.3
    - netmiko
    - ansible==2.9.7
```

This list also works with local wheel files, and supports the use of
`$WORKSPACE` environment variable to reference them.

``` yaml
# Example:
# download a wheel file from a remote host, and install it using pip.
files:
  - "scp://[user@]remotehost/path/to/packagename.whl"
packages:
  - ${WORKSPACE}/packagename.whl
```


#### `repositories`

Git repositories to clone to this docker image. By default, each repo will be
cloned to the provided name under `/pyats`. However, you may also specify a
new subdirectory to home it in.

If your repository is private you may provide the credentials or ssh_key to gain
access. You may also avoid including these private details in the yaml by
passing them through host environment variable. Check the ```Yaml loader``` section for
more details. Once the image is built, it will remove the login information.

```yaml
# Format

repositories:
    <name>:
        url: <repository url>
        commit_id: <name of branch or commit-id to checkout after clone>

# Example:
repositories:
    #   equivalent to: git clone https://github.com/CiscoTestAutomation/examples /pyats/examples
    examples:
        url: https://github.com/CiscoTestAutomation/examples
        ssh_key: <id_rsa file contents>

    #   equivalent to: mkdir -p /pyats/solutions; git clone https://github.com/CiscoTestAutomation/examples /pyats/solutions/examples
    solutions/examples:
        url: https://github.com/CiscoTestAutomation/solution_examples
        credentials:
            username: <git username>
            password: <git password>

```

#### `yaml loader`

Host environment variables to be loaded into the build yaml. This provides a way
to dynamically substitute variables into the yaml.

For example, a substitution of ssh key to a repository:

```text
export example_ssh_key=<private_ssh_key>
```

```yaml

# Example:
repositories:
    examples:
        url: https://github.com/CiscoTestAutomation/examples
        ssh_key: '%ENV{ example_ssh_key }'


```


#### `jobfiles`

pyATS Image Builder will attempt to discover all pyATS jobfiles within the
image. Only files with a `.py` extension will be considered as potential
jobfiles for discovery. To enable automatic discovery of your jobfile, include
the keyword `<PYATS_JOBFILE>` as part of the module docstring within the first
10 lines of the file.

By default, all file names containing `*job*.py` will be included as a job file.
This behavior is overwritten when you provide any `match` regex pattern.

For example, a jobfile should look similar to the following:

```python
"""
my_jobfile.py
<PYATS_JOBFILE>

Description of this job.
"""
from pyats.easypy import run

...
```

You can also define your jobfiles within the build YAML file.

```yaml
# Format
jobfiles:
  paths:
    - <path-to-jobfile>
    - <another-path-to-jobfile>
  match:
    - <regex-to-match>
    - <another-regex-to-match>

# Example
jobfiles:
  paths:
    - relative/path/to/job.py
    - /pyats/path/to/job.py
  match:
    - .*job.py
    - .*example_job.py
```

The list of paths also supports the use of the `$WORKSPACE` environment
variable to define paths.

#### `proxy`
Proxy variables. Useful if your host server is sitting behind a network
proxy, and you need to pull data/packages from public internet.

Supported keys:

- `HTTP_PROXY`
- `HTTPS_PROXY`
- `FTP_PROXY`
- `NO_PROXY`

#### `cmds`

Any additional docker command(s) in raw text format, to be inserted before/after
the pip installation command in the build process. See [Dockerfile template](./Dockerfile)
for where the `pre_cmd` and `post_cmd` are inserted.

Use cases example for `cmds` block: some packages require non-python
dependencies (eg. gcc), which are unlikely to be included in the image since it
is minimal. Use the `cmds` section to invoke `apt-get` command to install these
dependencies.

#### `pip-config`

Pip configuration file. The content of this section gets converted to a
`pip.conf` file used to customize your pip installation behavior.

For example, use this section to define your own PyPI server to download
packages from.

This section is read as a dictionary, and parsed directly into
[pip.conf](https://pip.pypa.io/en/stable/user_guide/#config-file)
INI format without translation.

```yaml
# Example
pip-config:
  global:
    trusted-host:
        - pypi.python.org

    index-url: https://pypi.org/simple
    no-cache-dir: True
```

Alternatively, you can also specify your `pip-config` block directly in
string format - this will be taken directly and stored as the content of
`pip.conf`:

``` yaml
pip-config: |
  [global]
  format = columns
  no-cache-dir = false
  trusted-host = pypi.python.org
  index-url = https://pypi.org/simple
  disable-pip-version-check = 1

  [search]
  index = https://pypi.org/simple
```

# Image Layout

pyATS Docker images created using this package features the following directory
structure:

```text
/pyats
    Directory where the Python virtual environment is created. All Python
    packages (including pyATS) specified in the build YAML file are installed
    into here. Additionally acts as the workspace, where all files and
    repositories specified in the YAML build file gets copied to. Set as the
    Docker working directory.

/pyats/installation
    Files related to the building of this docker image is stored under here.
    (for bookkeeping and debugging)

/pyats/installation/build.yaml
    Copy of the input build YAML file.

/pyats/installation/requirements.txt
    Pip packages installed in the virtual environment in pip freeze format.

/pyats/installation/repos.json
    A mapping of all git repos in the image with the current checked out commit
    or branch.

/pyats/installation/jobfiles.txt
    List of all discovered pyATS jobfiles in the image.

/pyats/installation/manifest.json
    A mapping of all discovered manifest files with the contents of that file.
```

See more about [manifest files](https://pubhub.devnetcloud.com/media/pyats/docs/manifest/index.html).

# Image Build

The image is built in two main stages.

1. the builder parsers the input YAML file and sets up the build context on the
   local build machine in what's called a *build context directory*.

2. Generates a Dockerfile, and launches `docker build` the directory.

## Build Context Directory

When the builder starts up, it creates a temporary directory in your file
system (eg, `/tmp`), used for storing artifacts necessary for your pyATS
docker image build process:

- file and git repositories defined in the build YAML file are copied/clones
  here

- the pip package dependency list in the build YAML file is converted into
  a `requirements.txt` file here

- if custom pip configuration is provided, a `pip.conf` file is generated here,
  customizing the pip installation behavior

---

# Running Built Images

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

In this case, the jobfile in question is `$WORKSPACE/myrepo/myjob.py`. The
starting working directory of the image is `$WORKSPACE` which is why it does not
need to be specified in the command.

It may be beneficial to set an environment variable with the location of a job
file or any other information by defining it in the YAML file. These variables
cannot be used directly on the command line since the host will attempt to
interpolate variables before executing Docker. There are two methods to use
environment variables in the Docker container.

---

# Advaned Use Cases

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
