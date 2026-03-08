#!/usr/bin/env python

from setuptools import find_packages, setup

install_requires = ['py-trees',
                    'pyyaml']

setup(
    name="py_branches",
    version="1.0.0",
    packages=find_packages(exclude=["tests*", "configs*"]),
    install_requires=install_requires,
)

