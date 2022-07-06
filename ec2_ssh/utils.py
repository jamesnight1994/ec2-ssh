import logging
import re
import shlex
import subprocess
import sys


__all__ = ['b', 'logger', 'run_command', 'shlex_quote']


# Configure logging
logging.basicConfig(level=logging.INFO)
logging.getLogger('botocore').setLevel(logging.WARNING)

PY2 = sys.version_info[0] == 2
PY3 = sys.version_info[0] == 3

if PY3:
    def b(s):
        return s.encode("latin-1")

    def shlex_quote(s):
        return shlex.quote(s)
else:
    def b(s):
        return s

    _find_unsafe = re.compile(r'[^\w@%+=:,./-]', re.I)

    # PY3 implementation of shlex.quote
    def shlex_quote(s):
        if not s:
            return "''"
        if _find_unsafe.search(s) is None:
            return s
        return "'" + s.replace("'", "'\"'\"'") + "'"


# Configure logger
class _LoggingHelper:
    __logger = None
    @classmethod
    def get_logger(cls):
        if not cls.__logger:
            cls.__logger = logging.getLogger('sote-ssh')
        return cls.__logger


logger = _LoggingHelper.get_logger()


def run_command(*args):
    """Execute a command

    Args:
        args(list|string) - The command to run
            * If args is a list, the command is run with shell=False
            * If args is a string, the command is run with shell=True
            * If args is of any other type, and exception is raised
    """
    shell = False
    if isinstance(args, (list, tuple)):
        args = [shlex_quote(x) for x in args]
    elif isinstance(args, (basestring)):
        args = shlex.split(args)
        shell = True
    else:
        raise Exception("Argument 'args' must be a list or string. Not %s", type(args))

    kwargs = dict(
        shell=shell,
        close_fds=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    cmd = subprocess.Popen(args, **kwargs)
    stdout, stderr = cmd.communicate()

    cmd.stdout.close()
    cmd.stderr.close()

    rc = cmd.returncode
    return (rc, stdout, stderr)
