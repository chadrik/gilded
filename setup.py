from __future__ import absolute_import, print_function

from setuptools import setup


setup(
    name="gilded",
    version="0.1.0",
    author="Chad Dombrova",
    description="A git command line interface based on mercurial.",
    license="MIT",
    keywords=["git", "mercurial"],
    url="https://github.com/chadrik/gilded",
    py_modules=['gilded'],
    install_requires=["mercurial>=4.6.0,<4.7.0", "pygit2"],
)
