from __future__ import print_function

import pytest
import os
import subprocess


class BaseRunner(object):
    name = None
    exe = None

    def __init__(self, datadir):
        self.repodir = os.path.join(datadir, self.name + 'test')

    def log(self, revset):
        output = subprocess.check_output(
            self.exe + ['log', '-r', revset, '--template', "{desc}\n",
                        '-R', self.repodir])
        return output.splitlines()


class GitRunner(BaseRunner):
    name = 'git'
    exe = ['hg', '--config', 'extensions.gilded=']


class HgRunner(BaseRunner):
    name = 'hg'
    exe = ['hg']

    def log(self, revset):
        lines = super(HgRunner, self).log(revset)
        return [l for l in lines if not l.startswith("Added tag ")]


@pytest.fixture(params=[GitRunner, HgRunner])
def repo(request):
    filename = request.module.__file__
    datadir = os.path.dirname(filename)
    runner = request.param(datadir)
    yield runner


def test_predicate_ancestors(repo):
    assert repo.log("ancestors('branch1')") == [
        'initial commit',
        'modify file-A',
        'modify file-A again',
        'add file-D',
    ]


def test_predicate_branch(repo):
    if repo.name == 'git':
        branch1 = [
            'initial commit',
            'modify file-A',
            'modify file-A again',
            'add file-D',
        ]
    else:
        branch1 = [
            'modify file-A again',
            'add file-D',
        ]

    assert repo.log("branch('branch1')") == branch1
    assert repo.log("branch(p1('branch1'))") == branch1


def test_predicate_branchpoint(repo):
    assert repo.log("branchpoint()") == [
        'merge branch1',
    ]


def test_predicate_children(repo):
    assert repo.log("children(branch1)") == [
        'merge branch1',
    ]


def test_predicate_desc(repo):
    assert repo.log("desc('modify ')") == [
        'modify file-A',
        'modify file-A again',
        'modify file-B',
        'modify file-C',
    ]


def test_predicate_merge(repo):
    assert repo.log("merge()") == [
        'merge branch1',
    ]


def test_predicate_parents(repo):
    assert repo.log("p1(branch1)") == [
        'modify file-A again',
    ]


def test_predicate_roots(repo):
    assert repo.log("roots(all())") == [
        'initial commit',
    ]


def test_predicate_sort(repo):
    # git and hg choose different parent order
    assert repo.log("sort(v1.0::v1.1, date)") == [
        'modify file-A',
        'modify file-A again',
        'add file-D',
        'modify file-B',
        'merge branch1',
        'remove file-B'
    ]


def test_predicate_tag(repo):
    assert repo.log("tag('v1.0')") == [
        'modify file-A',
    ]
    assert repo.log("tag('re:v\d.\d')") == [
        'modify file-A',
        'remove file-B',
    ]
    assert repo.log("tag()") == [
        'modify file-A',
        'remove file-B',
    ]


def test_booleans(repo):
    assert repo.log("v1.0 or v1.1") == [
        'modify file-A',
        'remove file-B',
    ]

    assert repo.log("branch1 or branch2") == [
        'add file-D',
        'modify file-C',
    ]


def test_revrange(repo):
    # git and hg choose different parent order
    assert set(repo.log("v1.0::v1.1")) == {
        'modify file-A',
        'modify file-A again',
        'add file-D',
        'modify file-B',
        'merge branch1',
        'remove file-B'
    }
