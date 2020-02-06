
import jsonschema

BUILD_SCHEMA = {
    # Nothing is required
    'type': 'object',
    # Only defined keys can be used
    'additionalProperties': False,
    'properties': {
        # tag is just a string
        'tag': {'type': 'string'},
        'python': {
            # Python version can be a string or a number (3.6.8 vs 3.6)
            'oneOf': [
                {'type': 'string'},
                {'type': 'number'}
            ]
        },
        'env': {
            'type': 'object',
            'additionalProperties': {
                # Environment variables can be strings numbers or bools.
                'oneOf': [
                    {'type': 'string'},
                    {'type': 'number'},
                    {'type': 'boolean'}
                ]
            }
        },
        'files': {
            'type': 'array',
            'items': {
                # File can be a string or a specific dict
                'oneOf': [
                    {'type': 'object',
                     # Exactly one property
                     'minProperties': 1,
                     'maxProperties': 1,
                     # Force matching of pattern
                     'additionalProperties': False,
                     'patternProperties': {
                         # Cannot have absolute path for destination
                         '^[^/]': {'type': 'string'}
                     }
                    },
                    {'type': 'string'}
                ]
            }
        },
        'packages': {
            'type': 'array',
            'items': {'type': 'string'}
        },
        # pip-config takes any dict to give to configparser
        'pip-config': {'type': 'object'},
        'repositories': {
            'type': 'object',
            # Force property to match pattern
            'additionalProperties': False,
            'patternProperties': {
                # Cannot have absolute path for destination
                '^[^/]': {
                    'type': 'object',
                    # Must have a url
                    'required': ['url'],
                    'additionalProperties': False,
                    'properties': {
                        'url': {'type': 'string'},
                        'commit_id': {'type': 'string'}
                    }
                }
            }
        },
        'snapshot': {'type': 'string'},
        'proxy': {
            'type': 'object',
            # proxy can only accept the defined properties
            'additionalProperties': False,
            'properties': {
                'HTTP_PROXY': {'type': 'string'},
                'http_proxy': {'type': 'string'},
                'HTTPS_PROXY': {'type': 'string'},
                'https_proxy': {'type': 'string'},
                'FTP_PROXY': {'type': 'string'},
                'ftp_proxy': {'type': 'string'},
                'NO_PROXY': {'type': 'string'},
                'no_proxy': {'type': 'string'}
            },
        },
        'cmds': {
            'type': 'object',
            'additionalProperties': False,
            'properties': {
                'pre': {'type': 'string'},
                'post': {'type': 'string'}
            }
        },
    }
}


def validate_builder_schema(data):
    jsonschema.validate(data, BUILD_SCHEMA)
