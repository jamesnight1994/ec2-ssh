# ec2 SSH
This package provides the `ec2-ssh` utility that enables SSH access to EC2 instances to be managed via Amazon IAM

## Setup
To use `ec2-ssh`:
1. [Upload public SSH keys](#upload-public-keys)
1. [Install `ec2-ssh`](#installation)
1. [Configure IAM permissions](#iam-permissions)

### Upload Public SSH Keys
Users will need to upload their public SSH keys on IAM. See the screenshots below for guidance.

[TODO: Add screenshots]

### Installation
To install `ec2-ssh`:

```shell
pip install git+https://github.com/jamesnight1994/ec2-ssh
```

Once the package is installed, the following command:

```shell
ec2-ssh install
```

The `install` command does two things:

* Configures SSH to use `ec2-ssh print-keys` to authenticate SSH connections
* Create a cron job to run `ec2-ssh sync --iam-group ssh-users --iam-sudo-group ssh-sudo-users` periodically - every 30 minutes by default - to sync user accounts in the IAM groups specified via the `--iam-group` and `iam-sudo-group` options

__IMPORTANT:__ After running the `install` command, `sshd` must be restarted in order for the changes to take effect

```shell
sudo service sshd reload
```


## IAM Permissions
The EC2 instance, where `ec2-ssh` is installed, needs a policy that allows the following IAM actions:

* iam:GetGroup
* iam:ListSSHPublicKeys
* iam:GetSSHPublicKey

## How it works
For information on the various commands in `ec2-ssh`, run `ec2-ssh --help`