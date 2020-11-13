import sys
import yaml
import logging
import argparse

from .builder import ImageBuilder


def main(argv=None, prog='pyats-image-build'):
    """
    Command line entrypoint
    """

    # Parse args from command line
    parser = argparse.ArgumentParser(
        prog=prog, description='Create standard pyATS Docker '
        'images')
    parser.add_argument('file',
                        help='YAML file describing the image build details.')
    parser.add_argument('--tag',
                        '-t',
                        help='Tag for docker image. Overrides any tag defined '
                        'in the yaml.')
    parser.add_argument('--push',
                        '-P',
                        action='store_true',
                        help='Push image to Dockerhub after buiding')
    parser.add_argument('--no-cache',
                        '-c',
                        action='store_true',
                        help='Do not use any caching when building the image')
    parser.add_argument(
        '--keep-context',
        '-k',
        action='store_true',
        help='Prevents the Docker context directory from being '
        'deleted once the image is built')
    parser.add_argument(
        '--dry-run',
        '-n',
        action='store_true',
        help='Set up the context directory but do not build the'
        ' image. Use with --keep-context.')
    parser.add_argument('--verbose',
                        '-v',
                        action='store_true',
                        help='Prints the output of docker build')
    args = parser.parse_args(argv)

    # create our logger (thread safe using current thread
    logger = logging.getLogger(__name__)

    # setup logger
    loglevel = logging.DEBUG if args.verbose else logging.DEBUG
    logger.setLevel(loglevel)

    logger.addHandler(logging.StreamHandler(sys.stdout))

    # Load given yaml file
    logger.info('Reading provided yaml')
    with open(args.file, 'r') as file:
        config = yaml.safe_load(file.read())

    # Run builder
    image = ImageBuilder(config, logger).run()

    # Optionally push image after building
    if args.push:
        logger.info('Pushing image to registry')
        image.push()

    logger.info('Done')


if __name__ == '__main__':
    main()
