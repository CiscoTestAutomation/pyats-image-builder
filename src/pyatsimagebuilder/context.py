import re
import shutil
import logging
import pathlib
import tempfile


class Context(object):
    def __init__(self,
                 keep=False,
                 logger=logging.getLogger(__name__),
                 prefix='pyats-image.'):
        '''
        a temp directory used as docker build context directory
        '''
        self._logger = logger

        self._prefix = prefix
        self.path = None
        self.keep = keep

    def mkdir(self, name):
        '''
        create a folder in this build context
        '''
        folder = self.path / name
        folder.mkdir()
        return folder.relative_to(self.path)

    def write_file(self, file, content):
        file = self.path / file
        file.write_text(content)

    def copy(self, src, dst):
        '''
        copy a file from to destination
        returns the relative path within this context
        '''
        # Copy either a single file or an entire directory
        src = pathlib.Path(src).expanduser()
        dst = self.path / dst

        if src.is_file():
            shutil.copy(src, dst)
        elif src.is_dir():
            shutil.copytree(src, dst, symlinks=True)
        else:
            raise OSError('Cannot copy %s' % src)

    def open(self, file, op):
        return open(self.path / file, op)

    def delete(self):
        if self.keep:
            self._logger.info('[WARNING] Keeping context directory %s' %
                              self.path)
        else:
            self._logger.info('Deleting context directory %s' % self.path)
            shutil.rmtree(str(self.path))
            self.path = None

    def create(self):
        if self.path and self.path.exists():
            raise ValueError('Already created at %s' % self._tempdir)

        # create tempdir
        self.path = pathlib.Path(tempfile.mkdtemp(prefix=self._prefix))

        self._logger.info('Setting up Docker context in %s' % self.path)

    def search_glob(self, pattern):
        return self.path.rglob(pattern)

    def __enter__(self):
        self.create()

    def __exit__(self, *args, **kwargs):
        self.delete()
