# Copyright 2017-2019 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"). You
# may not use this file except in compliance with the License. A copy of
# the License is located at
#
#     http://aws.amazon.com/apache2.0/
#
# or in the "license" file accompanying this file. This file is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF
# ANY KIND, either express or implied. See the License for the specific
# language governing permissions and limitations under the License.
"""Placeholder docstring"""
from __future__ import absolute_import

import os
from glob import glob
import sys

from setuptools import setup, find_packages


def read(fname):
    """
    Args:
        fname:
    """
    return open(os.path.join(os.path.dirname(__file__), fname)).read()


def read_version():
    return read("VERSION").strip()


# Declare minimal set for installation
required_packages = [
    "boto3>=1.10.32",
    "numpy>=1.9.0",
    "protobuf>=3.1",
    "scipy>=0.19.0",
    "protobuf3-to-dict>=0.1.5",
    "requests>=2.20.0, <2.21",
    "smdebug-rulesconfig==0.1.2",
]

# Specific use case dependencies
extras = {
    "analytics": ["pandas"],
    "local": [
        "urllib3>=1.21, <1.25",
        "docker-compose>=1.23.0",
        "PyYAML>=3.10, <5",  # PyYAML version has to match docker-compose requirements
    ],
    "tensorflow": ["tensorflow>=1.3.0"],
}
# Meta dependency groups
extras["all"] = [item for group in extras.values() for item in group]
# Tests specific dependencies (do not need to be included in 'all')
extras["test"] = (
    [
        extras["all"],
        "tox==3.13.1",
        "flake8",
        "pytest==4.4.1",
        "pytest-cov",
        "pytest-rerunfailures",
        "pytest-xdist",
        "mock",
        "contextlib2",
        "awslogs",
        "black==19.3b0 ; python_version >= '3.6'",
        "stopit==1.1.2",
        "apache-airflow==1.10.5",
        "fabric>=2.0",
    ],
)

# enum is introduced in Python 3.4. Installing enum back port
if sys.version_info < (3, 4):
    required_packages.append("enum34>=1.1.6")

setup(
    name="sagemaker",
    version=read_version(),
    description="Open source library for training and deploying models on Amazon SageMaker.",
    packages=find_packages("src"),
    package_dir={"": "src"},
    py_modules=[os.path.splitext(os.path.basename(path))[0] for path in glob("src/*.py")],
    long_description=read("README.rst"),
    author="Amazon Web Services",
    url="https://github.com/aws/sagemaker-python-sdk/",
    license="Apache License 2.0",
    keywords="ML Amazon AWS AI Tensorflow MXNet",
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "Natural Language :: English",
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python",
        "Programming Language :: Python :: 2.7",
        "Programming Language :: Python :: 3.6",
    ],
    install_requires=required_packages,
    extras_require=extras,
    entry_points={"console_scripts": ["sagemaker=sagemaker.cli.main:main"]},
    include_package_data=True,  # TODO-reinvent-2019 [knakad]: Remove after rule_configs is in PyPI
)
