from collections import OrderedDict

from pyats.cli.base import Command
from pyats.cli.base import CommandWithSubcommands
from pyats.cli.base import Subcommand

from . import main as builder_main


class ImageBuild(Command):

    name = 'build'
    help = 'Build a Docker image from a YAML file'

    def main(self, argv):
        return builder_main.main(argv, self.prog)


class ImageCommand(Command):

    name = 'image'
    help = 'Docker image related features'
    description = '''
Docker image related subcommands for pyATS.
    '''
    standard_logging = False

    # this command contains entrypoints
    SUBCMDS_ENTRYPOINT = 'pyats.cli.commands.image'
    SUBCMDS_BASECLS = Command
    SUBCOMMANDS = [ImageBuild]

    def __init__(self, prog):
        super().__init__(prog)

        # create main subparser section
        self.subparser = self.parser.add_subparsers(title='Subcommands',
                                                    dest='subcmd',
                                                    metavar='')

        # load all subcommands
        self.subcmds = self.load_subcmds()

        # populate subcommands
        for subcmd in self.subcmds.values():
            self.subparser.add_parser(name=subcmd.name,
                                      help=subcmd.help,
                                      add_help=False)

    def load_subcmds(self):
        subcmds = super().load_subcmds(subcommands=self.SUBCOMMANDS,
                                       entrypoint=self.SUBCMDS_ENTRYPOINT,
                                       base_cls=self.SUBCMDS_BASECLS)

        # sort alphabetically
        return OrderedDict((n, c(self.prog)) for n, c in subcmds.items())

    def parse_args(self, argv):
        # inject general group options
        self.add_general_opts(self.parser)

        # do the parsing
        return self.parser.parse_known_args(argv)

    def main(self, argv):
        # parse for subcommand and/or top-level help
        args, subcmd_argv = self.parse_args(argv)

        if args.subcmd:
            subcmd = self.subcmds[args.subcmd]
        else:
            # no command given, print help and exit
            self.parser.print_help()
            self.parser.exit()

        # do dirty work - pass in the subcommand arguments
        return subcmd.main(subcmd_argv)
