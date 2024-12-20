#!/usr/bin/env python

from setuptools import find_packages, setup

install_requires = ['py_trees==0.7.6',
                    'numpy',
                    'pyyaml']

setup(
    name="py_branches",
    version="0.0.1",
    packages=find_packages(exclude=["tests*", "configs*"]),
    install_requires=install_requires,
)

