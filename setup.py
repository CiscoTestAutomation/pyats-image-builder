#! /usr/bin/env python

from setuptools import setup, find_packages

# launch setup
setup(
    name = 'pyats-image-builder',
    version = '22.2',

    # descriptions
    description = 'pyATS Docker image creation',
    long_description = 'Cisco package intended to simplify and standardize the '
                       'creation of Python virtual environments for pyATS jobs',

    # the project's main homepage.
    url = 'https://developer.cisco.com/docs/pyats/',

    # author details
    author = 'Cisco Systems Inc.',
    author_email = 'pyats-support-ext@cisco.com',

    # project licensing
    license = 'Cisco Systems, Inc. Cisco Confidential',

    # see https://pypi.python.org/pypi?%3Aaction=list_classifiers
    classifiers = [
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
    keywords = 'pyats cisco development packaging docker',

    # project packages
    packages = find_packages(where = 'src'),

    # project directory
    package_dir = {
        '': 'src',
    },

    # additional package data files that goes into the package itself
    package_data = {
        # '': ['Dockerfile', 'docker-entrypoint.sh']
        '': ['Dockerfile', 'docker-entrypoint.sh', '*.template']
    },

    # console entry point
    entry_points = {
        'console_scripts': [
                'pyats-image-build = pyatsimagebuilder.main:main',
                'pyats-image-build-askpass = pyatsimagebuilder.askpass:main'],
        'pyats.cli.commands': [
                'image = pyatsimagebuilder.commands:ImageCommand'],
    },

    # package dependencies
    install_requires =  ['setuptools',
                         'pyyaml',
                         'requests',
                         'gitpython',
                         'docker',
                         'jsonschema',
                         'jinja2'],

    # any additional groups of dependencies.
    # install using: $ pip install -e .[dev]
    extras_require = {},

    # any data files placed outside this package.
    # See: http://docs.python.org/3.4/distutils/setupscript.html
    # format:
    #   [('target', ['list', 'of', 'files'])]
    # where target is sys.prefix/<target>
    data_files = [],

    # custom commands for setup.py
    cmdclass = {},

    # non zip-safe (never tested it)
    zip_safe = False,
)
