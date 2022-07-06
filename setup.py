import io
import re
from setuptools import setup, find_packages

with io.open('ec2_ssh/__init__.py', 'rt', encoding='utf-8') as f:
    version = re.search(r"__version__ = \'(.*?)\'", f.read()).group(1)

setup(
    name='ec2_ssh',
    version=version,
    description='Manage SSH access to EC2 instances via IAM',
    author='James Nganga',
    author_email='jamesnight1995@gmail.com',
    url='https://github.com/jamesnight1994/ec2-ssh',
    packages=find_packages(),
    install_requires=[
        'boto3>=1.9',
        'click>=7.0'
    ],
    python_requires='>=2.7, !=3.0.*, !=3.1.*, !=3.2.*, !=3.3.*',
    classifiers=[
        'Development Status :: Beta',
        'Environment :: Console',
        'Intended Audience :: System Administrators',
        'Intended Audience :: DevOps Engineers',
        'Natural Language :: English',
        'Operating System :: POSIX',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3.6',
        'Topic :: System :: Systems Administration',
        'Topic :: Utilities'
    ],
    scripts=['bin/sote-ssh'])