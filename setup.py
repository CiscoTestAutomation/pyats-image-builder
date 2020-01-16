#! /usr/bin/env python

from setuptools import setup, find_packages

# launch setup
setup(
    name = 'pyatsdockerbuild',
    version = '20.1',

    # descriptions
    description = 'pyATS Docker image creation and execution',
    long_description = 'Cisco package intended to simplify and standardize the '
                       'creation and execution of pyATS jobs',

    # the project's main homepage.
    url = 'https://developer.cisco.com/docs/pyats/',

    # author details
    author = 'Cisco Systems Inc.',
    author_email = 'pyats-support-ext@cisco.com',

    # project licensing
    license = 'Cisco Systems, Inc. Cisco Confidential',

    # see https://pypi.python.org/pypi?%3Aaction=list_classifiers
    classifiers = [
        'Development Status :: 4 - Beta',
        'Environment :: Console',
        'Intended Audience :: Developers',
        'Intended Audience :: Telecommunications Industry'
        'License :: Other/Proprietary License',
        'Operating System :: POSIX :: Linux',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3 :: Only',
        'Topic :: Software Development :: Testing',
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
        '': ['Dockerfile', 'docker-entrypoint.sh']
    },

    # console entry point
    entry_points = {
        'console_scripts': ['pyats-docker-build = pyatsdockerbuild.build:main']
    },

    # package dependencies
    install_requires =  ['setuptools',
                         'pyyaml',
                         'requests',
                         'gitpython',
                         'docker'],

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
