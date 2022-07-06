import grp
import os
import pwd
import re
import shutil
import stat
import tempfile

import boto3
from .utils import b, run_command, logger


__all__ = ['configure_ssh_authorized_keys_command', 'OsGroup', 'OsUser']

# Constants
SSHD_CONFIG = '/etc/ssh/sshd_config'
AUTHORIZED_KEYS_COMMAND_PERMISSIONS = 0o751 # rwx-rx-x
AUTHORIZED_KEYS_COMMAND_SCRIPT_PATH = '/opt/ec2-ssh/ec2-ssh-print-keys'
AUTHORIZED_KEYS_COMMAND_REGEX = r'^AuthorizedKeysCommand .*$'
AUTHORIZED_KEYS_COMMAND_USER_REGEX = r'^AuthorizedKeysCommandUser .*$'

# Template for the AuthorizedKeysCommand
AUTHORIZED_KEYS_COMMAND_SCRIPT_TEMPLATE = """
#!/bin/bash
# A script used to look up the public keys of the connecting user using ec2-ssh

# Run print-keys so that stdout contains the valid public keys and stderr is redirected to syslog
{cmd_path} print-keys "$@" 2> >(logger)
"""


def create_authorized_keys_command_script():
    """Creates the script for the AuthorizedKeysCommand SSH directive
    and assigns ownership to the root user.

    Both the script and the directory that houses it must be owned by
    the root user (or the user that will be used to run the
    AuthorizedKeysCommand script)
    """
    script_dir = os.path.dirname(AUTHORIZED_KEYS_COMMAND_SCRIPT_PATH)
    if not os.path.exists(script_dir):
        os.makedirs(script_dir, AUTHORIZED_KEYS_COMMAND_PERMISSIONS)
    os.chown(script_dir, 0, 0)
    os.chmod(script_dir, AUTHORIZED_KEYS_COMMAND_PERMISSIONS)

    if os.path.exists(AUTHORIZED_KEYS_COMMAND_SCRIPT_PATH):
        return

    script = AUTHORIZED_KEYS_COMMAND_SCRIPT_TEMPLATE.format(
        cmd_path='/usr/local/bin/ec2-ssh')

    with open(AUTHORIZED_KEYS_COMMAND_SCRIPT_PATH, 'wb') as f:
        f.write(script.strip())
    os.chown(AUTHORIZED_KEYS_COMMAND_SCRIPT_PATH, 0, 0)
    os.chmod(AUTHORIZED_KEYS_COMMAND_SCRIPT_PATH,
             AUTHORIZED_KEYS_COMMAND_PERMISSIONS)


def append_or_replace_ssh_config(regexp, line):
    matcher = re.compile(regexp)
    with open(SSHD_CONFIG, 'rb') as f:
        lines = f.readlines()

    index = -1
    for lineno, cur_line in enumerate(lines):
        match = matcher.search(cur_line)
        if match:
            index = lineno
            break

    line_sep = os.linesep
    if index == -1:
        if lines[-1][-1] not in (b('\r'), b('\n')):
            lines.append(line_sep)
        lines.append(line + line_sep)
    else:
        if lines[index].rstrip(b('\r\n')) != line:
            line = line + line_sep
        lines[index] = line

    tmpfile = tempfile.mktemp()
    with open(tmpfile, 'wb') as f:
        f.writelines(lines)

    shutil.copyfile(tmpfile, SSHD_CONFIG)
    os.remove(tmpfile)


def configure_ssh_authorized_keys_command():
    """Adds an AuthorizedKeysCommand entry to /etc/ssh/sshd_config
    if it does not already exist
    """
    create_authorized_keys_command_script()

    authorized_keys_command = 'AuthorizedKeysCommand %s' % AUTHORIZED_KEYS_COMMAND_SCRIPT_PATH
    authorized_keys_command_user = 'AuthorizedKeysCommandUser root'

    append_or_replace_ssh_config(AUTHORIZED_KEYS_COMMAND_REGEX,
                                 authorized_keys_command)
    append_or_replace_ssh_config(AUTHORIZED_KEYS_COMMAND_USER_REGEX,
                                 authorized_keys_command_user)

    logger.info('Successfully added AuthorizedKeysCommand to %s', SSHD_CONFIG)


def create_os_user(username, os_group):
    """Creates an OS user, adds them to the specified OS group and grants
    them sudo access if `os_group` is a sudoers group

    Params:
        username(str) - The OS username
        os_group(auth.OsGroup) - The OsGroup object
    """
    user = OsUser(username)
    if not user.exists:
        user.create()
    os_group.add_user(username)
    if os_group.is_sudo_group:
        user.grant_sudo_access()


class OsGroup:
    """Class to represent an operating system group"""
    def __init__(self, name, is_sudo_group=False):
        self.name = name
        self.is_sudo_group = is_sudo_group

    @property
    def exists(self):
        exists = True
        try:
            grp.getgrnam(self.name)
        except KeyError:
            exists = False
        return exists

    def create(self):
        run_command('/usr/sbin/groupadd', self.name)

    def delete(self):
        run_command('/usr/sbin/groupdel', self.name)

    def add_user(self, username):
        """Adds a user in `username` to an OS group"""
        run_command('/usr/sbin/usermod', '--append', '--groups', self.name, username)

    def remove_user(self, username):
        """Removes the user in `username` from the OS group"""
        run_command('/usr/sbin/usermod', '-G', "", username)

    @property
    def members(self):
        """Gets and returns all the members of the group"""
        users = []
        for entry in grp.getgrall():
            if entry.gr_name == self.name:
                users += entry.gr_mem
                break
        return users

    def sync(self, iam_users):
        """Removes users from the current group if they are no longer members
        and adds new members; creating a new OS user where non exists
        """
        os_users = self.members

        # Remove group members that are not in list of IAM users
        for username in os_users:
            if username not in iam_users:
                self.remove_user(username)

        # Create non-existent users
        for username in iam_users:
            if username not in os_users:
                create_os_user(username, self)


class OsUser:
    """This class is a generic represention of an OS user"""

    DEFAULT_SHELL = '/bin/bash'
    SUDOERS_BASE_PATH = '/etc/sudoers.d'

    def __init__(self, username):
        self._username = re.sub(r'@.*', '', username, re.I)
        self._public_key_ids = None
        self._ssh_public_keys = None
        self._client = boto3.client('iam')

    def create(self):
        run_command('/usr/sbin/useradd',
                    '--shell',
                    self.DEFAULT_SHELL,
                    '--create-home',
                    self._username)

    @property
    def ssh_public_keys(self):
        if not self._ssh_public_keys:
            self._ssh_public_keys = self._get_ssh_public_keys()
        return self._ssh_public_keys

    def _get_ssh_public_keys(self):
        public_keys = []
        key_ids = self._get_ssh_public_key_ids()
        for entry in key_ids:
            response = self._client.get_ssh_public_key(
                UserName=self._username,
                SSHPublicKeyId=entry,
                Encoding='SSH')
            pubkey = response['SSHPublicKey']['SSHPublicKeyBody']
            public_keys.append(pubkey)

        return public_keys

    def _get_ssh_public_key_ids(self):
        key_ids = []

        paginator = self._client.get_paginator('list_ssh_public_keys')
        iterator = paginator.paginate(UserName=self._username)
        for item in iterator:
            for key in item['SSHPublicKeys']:
                if key.get('Status') == 'Active':
                    key_ids.append(key['SSHPublicKeyId'])

        return key_ids

    def delete(self):
        run_command('/usr/sbin/userdel', self._username)
        self.revoke_sudo_access()

    @property
    def exists(self):
        try:
            pwd.getpwnam(self._username)
        except KeyError:
            return False
        return True

    def grant_sudo_access(self):
        """Grants sudo access to the user by creating a sudoers
        file in /etc/sudoers.d and setting the permissions to 440
        """
        sudoers_file = '%s/%s' % (self.SUDOERS_BASE_PATH, self._username)
        if os.path.exists(sudoers_file):
            logger.info('User %s already has sudo access (sudoers file already exists). Skipping',
                self._username)
            return

        logger.info('Creating sudoers file for user %s', self._username)
        contents = '%s ALL=(ALL) NOPASSWD:ALL' % self._username
        with open(sudoers_file, 'w') as sudo:
            sudo.write(contents)
        os.chmod(sudoers_file, stat.S_IRUSR | stat.S_IRGRP | 0)

    def revoke_sudo_access(self):
        sudoers_file = '%s/%s' % (self.SUDOERS_BASE_PATH, self._username)
        if not os.path.exists(sudoers_file):
            logger.info('User %s does not have sudo access (sudoers file does not exist)',
                self._username)
            return

        logger.info('Revoking sudo access for user %s', self._username)
        os.remove(sudoers_file)
