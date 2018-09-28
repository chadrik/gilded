from __future__ import print_function

import pytest
import os
import subprocess


def filtertags(lines):
    return [l for l in lines if not l.startswith("Added tag ")]


class BaseRunner(object):
    name = None
    exe = None

    all = [
        'initial commit',
        'modify file-A',
        'modify file-A again',
        'add file-D',
        'modify file-B',
        'merge branch1',
        'modify file-C',
        'remove file-B'
    ]

    def __init__(self, datadir):
        self.repodir = os.path.join(datadir, self.name + 'test')

    def log(self, revset, template=None, filter=None):
        if template is None:
            template = "{desc}\n"
        output = subprocess.check_output(
            self.exe + ['log', '-r', revset, '--template', template,
                        '--traceback',
                        '-R', self.repodir])
        return output.splitlines()


class GitRunner(BaseRunner):
    name = 'git'
    exe = ['hg', '--config', 'extensions.gilded=']
    master = 'master'
    refs = {
        'branch1': 'ff2e4709adb23622f65f3a19c14bdcb40f988b55',
        'v1.0': '283c6a4ccb575c00ff463a7aa2a0f94744d3b6f7',
    }
    branch_commits = {
        'branch1': [
            'initial commit',
            'modify file-A',
            'modify file-A again',
            'add file-D',
        ],
        'branch2': [
            'initial commit',
            'modify file-A',
            'modify file-B',
            'modify file-A again',
            'add file-D',
            'merge branch1',
            'modify file-C',
        ],
        'master': [
            'initial commit',
            'modify file-A',
            'modify file-B',
            'modify file-A again',
            'add file-D',
            'merge branch1',
            'remove file-B',
        ]
    }


class HgRunner(BaseRunner):
    name = 'hg'
    exe = ['hg']
    master = 'default'
    refs = {
        'branch1': 'd3f9491a31d3912b11c4d4864bda16c380265a63',
        'v1.0': 'bac32f9c81edb48d558e80511708acc815e124ff',
    }
    branch_commits = {
        'branch1': [
            'modify file-A again',
            'add file-D',
        ]
    }

    def log(self, revset, template=None, filter=True):
        lines = super(HgRunner, self).log(revset, template)
        if filter:
            return filtertags(lines)
        else:
            return lines


@pytest.fixture(params=[GitRunner, HgRunner])
def repo(request):
    filename = request.module.__file__
    datadir = os.path.dirname(filename)
    runner = request.param(datadir)

    # tar = tarfile.open('.'.join((repo_path, 'tar')))
    # tar.extractall(self.temp_dir)
    # tar.close()

    yield runner


def test_predicate_all(repo):
    assert set(repo.log("all()")) == set(repo.all)


def test_predicate_ancestors(repo):
    assert repo.log("ancestors('branch1')") == [
        'initial commit',
        'modify file-A',
        'modify file-A again',
        'add file-D',
    ]


def test_predicate_branch(repo):
    assert repo.log("branch('branch1')") == repo.branch_commits['branch1']
    # in the case where we don't provide a branch name, we consider all
    # branches belonging to the incoming set
    if repo.name == 'git':
        result = set(repo.branch_commits['branch1'] +
                     repo.branch_commits['branch2'] +
                     repo.branch_commits['master'])
    else:
        result = set(repo.branch_commits['branch1'])
    assert set(repo.log("branch(%s)" % repo.refs['branch1'])) == result
    assert set(repo.log("branch(p1('branch1'))")) == result


@pytest.mark.skip("object of type 'gitchangelog' has no len()")
def test_predicate_branchpoint(repo):
    assert repo.log("branchpoint()") == [
        'merge branch1',
    ]


def test_predicate_children(repo):
    assert repo.log("children(branch1)") == [
        'merge branch1',
    ]


def test_predicate_desc(repo):
    assert set(repo.log("desc('modify ')")) == {
        'modify file-A',
        'modify file-A again',
        'modify file-B',
        'modify file-C',
    }


def test_predicate_head(repo):
    # default branch has a tag commit which gets filtered
    lines = repo.log("head()", filter=False)

    if repo.name == 'git':
        # FIXME: order is not stable between test environments, but it seems like it should be
        assert set(lines) == {
            'remove file-B',
            'add file-D',
            'modify file-C',
        }
    else:
        assert lines == [
            'add file-D',
            'modify file-C',
            'Added tag v1.1 for changeset 42ea125c5e0d',
        ]


def test_predicate_heads(repo):
    # default branch has a tag commit which gets filtered
    lines = repo.log("heads(all())", filter=False)

    if repo.name == 'git':
        assert lines == [
            'remove file-B',
            'modify file-C',
        ]
    else:
        assert lines == [
            'modify file-C',
            'Added tag v1.1 for changeset 42ea125c5e0d',
        ]


def test_predicate_merge(repo):
    assert repo.log("merge()") == [
        'merge branch1',
    ]


def test_predicate_limit(repo):
    assert repo.log("limit(sort(v1.0::v1.1, date))") == [
        'modify file-A',
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
    assert set(repo.log("tag('re:v\d.\d')")) == {
        'modify file-A',
        'remove file-B',
    }
    assert set(repo.log("tag()")) == {
        'modify file-A',
        'remove file-B',
    }


def test_predicate_user(repo):
    assert set(repo.log("user('Chad')")) == set(repo.all)


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


def test_revspecs(repo):
    assert repo.log(repo.refs['v1.0']) == [
        'modify file-A',
    ]
    assert repo.log(repo.refs['v1.0'][:12]) == [
        'modify file-A',
    ]


def test_template_node(repo):
    assert repo.log("tag('v1.0')", "{node}\n") == [
        repo.refs['v1.0'],
    ]
