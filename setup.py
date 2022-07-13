#! /usr/bin/env python
import os
import re


from setuptools import setup, find_packages


def read(*paths):
    '''read and return txt content of file'''
    with open(os.path.join(*paths)) as fp:
        return fp.read()


def find_version(*paths):
    '''reads a file and returns the defined __version__ value'''
    version_match = re.search(r"^__version__ ?= ?['\"]([^'\"]*)['\"]",
                              read(*paths), re.M)
    if version_match:
        return version_match.group(1)
    raise RuntimeError("Unable to find version string.")


def build_version_range(version):
    '''
    for any given version, return the major.minor version requirement range
    eg: for version '3.4.7', return '>=3.4.0, <3.5.0'
    '''
    req_ver = version.split('.')
    version_range = '>= %s.%s.0, < %s.%s.0' % \
                    (req_ver[0], req_ver[1], req_ver[0], int(req_ver[1]) + 1)

    return version_range


def version_info(*paths):
    '''returns the result of find_version() and build_version_range() tuple'''

    version = find_version(*paths)
    return version, build_version_range(version)


version = find_version('src', 'pyatsimagebuilder', '__init__.py')

# launch setup
setup(
    name='pyats-image-builder',
    version=version,

    # descriptions
    description='pyATS Docker image creation',
    long_description='Cisco package intended to simplify and standardize the '
                     'creation of Python virtual environments for pyATS jobs',

    # the project's main homepage.
    url='https://developer.cisco.com/docs/pyats/',

    # author details
    author='Cisco Systems Inc.',
    author_email='pyats-support-ext@cisco.com',

    # project licensing
    license='Cisco Systems, Inc. Cisco Confidential',

    # see https://pypi.python.org/pypi?%3Aaction=list_classifiers
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Environment :: Console',
        'Intended Audience :: Developers',
        'Intended Audience :: Telecommunications Industry',
        'Intended Audience :: Information Technology',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved :: Apache Software License',
        'Operating System :: MacOS',
        'Operating System :: POSIX :: Linux',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3 :: Only',
        'Programming Language :: Python :: Implementation :: CPython',
        'Topic :: Software Development :: Testing',
        'Topic :: Software Development :: Build Tools',
        'Topic :: Software Development :: Libraries',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ],

    # project keywords
    keywords='pyats cisco development packaging docker',

    # project packages
    packages=find_packages(where='src'),

    # project directory
    package_dir={
        '': 'src',
    },

    # additional package data files that goes into the package itself
    package_data={
        # '': ['Dockerfile', 'docker-entrypoint.sh']
        '': ['Dockerfile', 'docker-entrypoint.sh', '*.template']
    },

    # console entry point
    entry_points={
        'console_scripts': [
            'pyats-image-build = pyatsimagebuilder.main:main',
            'pyats-image-build-askpass = pyatsimagebuilder.askpass:main'],
        'pyats.cli.commands': [
            'image = pyatsimagebuilder.commands:ImageCommand'],
    },

    # package dependencies
    install_requires=['setuptools',
                      'pyyaml',
                      'requests',
                      'gitpython',
                      'docker',
                      'jsonschema',
                      'jinja2'],

    # any additional groups of dependencies.
    # install using: $ pip install -e .[dev]
    extras_require={},

    # any data files placed outside this package.
    # See: http://docs.python.org/3.4/distutils/setupscript.html
    # format:
    #   [('target', ['list', 'of', 'files'])]
    # where target is sys.prefix/<target>
    data_files=[],

    # custom commands for setup.py
    cmdclass={},

    # non zip-safe (never tested it)
    zip_safe=False,
)
