from __future__ import absolute_import, print_function

import collections
import contextlib
import sys

import pygit2

from mercurial.i18n import _

from mercurial import (
    changelog,
    color,
    context,
    dirstate as dirstatemod,
    dagop,
    encoding,
    error,
    match as matchmod,
    namespaces,
    node,
    pathutil,
    pycompat,
    revset,
    revsetlang,
    scmutil,
    smartset,
    templatekw,
    util,
    vfs as vfsmod,
)

from mercurial.node import (
    nullid,
    nullrev,
)

from mercurial.utils import (
    stringutil,
)

if False:
    from typing import *
    from mercurial import (
        ui as uimod,
    )

propertycache = util.propertycache
namespace = namespaces.namespace
tolist = namespaces.tolist

# -- General pygit2 utilities

class OidProxy(object):
    """
    Make a pygit2.Oid behave more like an int
    """
    __slots__ = ('id', 'sortid')
    def __init__(self, oid, sortid=0):
        self.id = oid
        self.sortid = sortid

    def __repr__(self):
        return '%s(%r, %d)' % (self.__class__.__name__, self.id, self.sortid)

    def __str__(self):
        return str(self.id)

    def __eq__(self, other):
        try:
            return self.id == other.id
        except AttributeError:
            return self.id == other

    def __lt__(self, other):
        return self.sortid < int(other)

    def __le__(self, other):
        return self.sortid <= int(other)

    def __gt__(self, other):
        return self.sortid > int(other)

    def __ge__(self, other):
        return self.sortid >= int(other)

    def __hash__(self):
        return hash(self.id)

    def __hex__(self):
        return hex(self.id)

    def __int__(self):
        # the real impetus for this method is to pass %d string operators
        # without failure, so while line below is more accurate, it's too
        # verbose
        # return int(self.hex, base=16)
        return self.sortid

def oid(rev):
    return getattr(rev, 'id', rev)

def branches_with(repo, commit):
    result = []
    for branch_name in repo.branches:
        branch = repo.branches[branch_name]
        target = branch.peel().id
        if target == commit.id or repo.descendant_of(target, commit.id):
            result.append(target)
    return result

# --

class gitchangelog(object):
    def __init__(self, repo):
        self._repo = repo
        self._gitrepo = repo._repo

    def parentrevs(self, rev):
        rev = oid(rev)
        commit = self._gitrepo[rev]
        nparents = len(commit.parents)
        if nparents == 0:
            p1 = p2 = node.nullrev
        else:
            assert nparents <= 2
            p1 = OidProxy(commit.parents[0].id)
            if nparents == 2:
                p2 = OidProxy(commit.parents[1].id)
            else:
                p2 = node.nullrev
        return p1, p2

    def changelogrevision(self, rev):
        if hasattr(rev, 'id'):
            rev = rev.id
        commit = self._gitrepo[rev]
        return changelog._changelogrevision(
            extra=changelog._defaultextra,
            user="%s <%s>" % (commit.author.name, commit.author.email),
            date=(commit.commit_time, commit.commit_time_offset),
            description=commit.message)

    def _partialmatch(self, id):
        try:
            return self._gitrepo.revparse_single(id).id
        except (KeyError, ValueError):
            return None

    def rev(self, node):
        if isinstance(node, bytes):
            return OidProxy(pygit2.Oid(raw=node))
        elif isinstance(node, pygit2.Oid):
            return OidProxy(node)
        else:
            raise TypeError(node)

    def commonancestorsheads(self, a, b):
        # ancestor = self._repo._repo.merge_base(a, b)
        # parents = set(p.rev() for p in self._repo[x].parents())
        # heads = revset.heads(self._repo, [], ["symbol", ancestor])
        heads = self._repo.revs("heads(::%s and ::%s)" % (a, b))
        return list(heads)

    def findmissing(self, *args, **kwargs):
        # FIXME: short-circuit this for now to get summary working
        return []

class gitchangectx(context.basectx):
    def __init__(self, repo, changeid='.'):
        # type: (gitrepository, Union[int, bytes]) -> None
        """changeid is a revision number, node, or tag"""
        super(gitchangectx, self).__init__(repo)

        try:
            if isinstance(changeid, pygit2.Oid):
                self._node = changeid
                self._rev = OidProxy(self._node)
                return
            if changeid in ['null', nullrev]:
                self._node = nullid
                self._rev = nullrev
                return
            if isinstance(changeid, OidProxy):
                self._node = changeid.id
                self._rev = changeid
                return
            # if hasattr(changeid, 'id'):
            #     self._node = changeid.id
            #     self._rev = self._node
            #     return
            # if changeid == 'tip':
            #     self._node = repo.changelog.tip()
            #     self._rev = repo.changelog.rev(self._node)
            #     return
            if (changeid == '.'
                or repo.local() and changeid == repo.dirstate.p1()):
                # this is a hack to delay/avoid loading obsmarkers
                # when we know that '.' won't be hidden
                self._node = repo.dirstate.p1()
                self._rev = OidProxy(self._node)
                return
            # if len(changeid) == 20:
            #     try:
            #         self._node = changeid
            #         self._rev = repo.changelog.rev(changeid)
            #         return
            #     except error.FilteredLookupError:
            #         raise
            #     except LookupError:
            #         pass
        #
        #     try:
        #         r = int(changeid)
        #         if '%d' % r != changeid:
        #             raise ValueError
        #         l = len(repo.changelog)
        #         if r < 0:
        #             r += l
        #         if r < 0 or r >= l and r != wdirrev:
        #             raise ValueError
        #         self._rev = r
        #         self._node = repo.changelog.node(r)
        #         changectxdeprecwarn(repo)
        #         return
        #     except error.FilteredIndexError:
        #         raise
        #     except (ValueError, OverflowError, IndexError):
        #         pass
        #
        #     if len(changeid) == 40:
        #         try:
        #             self._node = bin(changeid)
        #             self._rev = repo.changelog.rev(self._node)
        #             return
        #         except error.FilteredLookupError:
        #             raise
        #         except (TypeError, LookupError):
        #             pass
        #
        #     # lookup bookmarks through the name interface
        #     try:
        #         self._node = repo.names.singlenode(repo, changeid)
        #         self._rev = repo.changelog.rev(self._node)
        #         changectxdeprecwarn(repo)
        #         return
        #     except KeyError:
        #         pass
        #
        #     self._node = scmutil.resolvehexnodeidprefix(repo, changeid)
        #     if self._node is not None:
        #         self._rev = repo.changelog.rev(self._node)
        #         changectxdeprecwarn(repo)
        #         return
        #
        #     # lookup failed
        #     # check if it might have come from damaged dirstate
        #     #
        #     # XXX we could avoid the unfiltered if we had a recognizable
        #     # exception for filtered changeset access
        #     if (repo.local()
        #         and changeid in repo.unfiltered().dirstate.parents()):
        #         msg = _("working directory has unknown parent '%s'!")
        #         raise error.Abort(msg % short(changeid))
        #     try:
        #         if len(changeid) == 20 and nonascii(changeid):
        #             changeid = hex(changeid)
        #     except TypeError:
        #         pass
        except (error.FilteredIndexError, error.FilteredLookupError):
            raise error.FilteredRepoLookupError(_("filtered revision '%s'")
                                                % changeid)
        except error.FilteredRepoLookupError:
            raise
        except IndexError:
            pass
        raise error.RepoLookupError(
            _("unknown revision '%s'") % changeid)

    @classmethod
    def __subclasshook__(cls, other):
        # make gitchangectx appear to inherit from changectx
        if cls is gitchangectx:
            return cls in other.__mro__ or context.changectx in other.__mro__
        return NotImplemented

    def __hash__(self):
        try:
            return hash(self._rev)
        except AttributeError:
            return id(self)

    def __nonzero__(self):
        return self._rev != nullrev

    __bool__ = __nonzero__

    @propertycache
    def _changeset(self):
        # type: () -> changelog.changelogrevision
        return self._repo.changelog.changelogrevision(self.rev())


    def _buildstatus(self, other, s, match, listignored, listclean,
                     listunknown):
        # type: (basectx, scmutil.status, Callable, bool, bool, bool) -> scmutil.status

        modified, added = [], []
        removed = []
        clean = []
        deleted, unknown, ignored = s.deleted, s.unknown, s.ignored

        d = self._repo._repo[self._node]

        return scmutil.status(modified, added, removed, deleted, unknown,
                              ignored, clean)

    # @propertycache
    # def _manifest(self):
    #     return self._manifestctx.read()
    #
    # @property
    # def _manifestctx(self):
    #     return self._repo.manifestlog[self._changeset.manifest]
    #
    # @propertycache
    # def _manifestdelta(self):
    #     return self._manifestctx.readdelta()

    @propertycache
    def _parents(self):
        repo = self._repo
        p1, p2 = repo.changelog.parentrevs(self._rev)
        if p2 == nullrev:
            return [gitchangectx(repo, p1)]
        return [gitchangectx(repo, p1), gitchangectx(repo, p2)]

    def changeset(self):
        c = self._changeset
        return (
            c.manifest,
            c.user,
            c.date,
            c.files,
            c.description,
            c.extra,
        )
    def manifestnode(self):
        return self._changeset.manifest

    def user(self):
        # type: () -> str
        return self._changeset.user
    def date(self):
        return self._changeset.date
    def files(self):
        # type: () -> List[str]
        return self._changeset.files
    def description(self):
        # type: () -> str
        return self._changeset.description
    def branch(self):
        return encoding.tolocal(self._changeset.extra.get("branch"))
    def closesbranch(self):
        return 'close' in self._changeset.extra
    def extra(self):
        """Return a dict of extra information."""
        return self._changeset.extra
    def tags(self):
        # type: () -> List[bytes]
        """Return a list of byte tag names"""
        return self._repo.nodetags(self._node)
    def bookmarks(self):
        """Return a list of byte bookmark names."""
        return self._repo.nodebookmarks(self._node)
    def phase(self):
        return 0
        #return self._repo._phasecache.phase(self._repo, self._rev)

    def hidden(self):
        return False

    def isinmemory(self):
        return False

    def children(self):
        # type: () -> List[gitchangectx]
        """return list of changectx contexts for each child changeset.

        This returns only the immediate child changesets. Use descendants() to
        recursively walk children.
        """
        c = self._repo.changelog.children(self._node)
        return [gitchangectx(self._repo, x) for x in c]

    def ancestors(self):
        # type: () -> Iterator[gitchangectx]
        for a in self._repo.changelog.ancestors([self._rev]):
            yield gitchangectx(self._repo, a)

    def descendants(self):
        # type: () -> Iterator[gitchangectx]
        """Recursively yield all children of the changeset.

        For just the immediate children, use children()
        """
        for d in self._repo.changelog.descendants([self._rev]):
            yield gitchangectx(self._repo, d)

    def filectx(self, path, fileid=None, filelog=None):
        # type: (str, Any, Any) -> Any
        """get a file context from this changeset"""
        if fileid is None:
            fileid = self.filenode(path)
        return filectx(self._repo, path, fileid=fileid,
                       changectx=self, filelog=filelog)

    def ancestor(self, c2, warn=False):
        # type: (gitchangectx, bool) -> gitchangectx
        """return the "best" ancestor context of self and c2

        If there are multiple candidates, it will show a message and check
        merge.preferancestor configuration before falling back to the
        revlog ancestor."""
        # deal with workingctxs
        n2 = c2._node
        if n2 is None:
            n2 = c2._parents[0]._node
        cahs = self._repo.changelog.commonancestorsheads(self._node, n2)
        if not cahs:
            anc = nullid
        elif len(cahs) == 1:
            anc = cahs[0]
        else:
            # experimental config: merge.preferancestor
            for r in self._repo.ui.configlist('merge', 'preferancestor'):
                try:
                    ctx = scmutil.revsymbol(self._repo, r)
                except error.RepoLookupError:
                    continue
                anc = ctx.node()
                if anc in cahs:
                    break
            else:
                anc = self._repo.changelog.ancestor(self._node, n2)
            if warn:
                self._repo.ui.status(
                    (_("note: using %s as ancestor of %s and %s\n") %
                     (short(anc), short(self._node), short(n2))) +
                    ''.join(_("      alternatively, use --config "
                              "merge.preferancestor=%s\n") %
                            short(n) for n in sorted(cahs) if n != anc))
        return gitchangectx(self._repo, anc)

    def descendant(self, other):
        """True if other is descendant of this changeset"""
        return self._repo.changelog.descendant(self._rev, other._rev)

    def walk(self, match):
        '''Generates matching file names.'''

        # Wrap match.bad method to have message with nodeid
        def bad(fn, msg):
            # The manifest doesn't know about subrepos, so don't complain about
            # paths into valid subrepos.
            if any(fn == s or fn.startswith(s + '/')
                   for s in self.substate):
                return
            match.bad(fn, _('no such file in rev %s') % self)

        m = matchmod.badmatch(match, bad)
        # print(self.rev())
        # print(self._changeset)
        # print(self._changeset.manifest)
        return self._manifest.walk(m)

    def matches(self, match):
        return self.walk(match)

class gitworkingctx(context.workingctx):
    def __init__(self, repo):
        # type: (gitrepository) -> None
        super(gitworkingctx, self).__init__(repo)

    # @property
    # def _parents(self):
    #     return [gitchangectx(self._repo, self._repo._repo.head.target)]

    def _checklookup(self, files):
        # because we don't save and track modification times, and therefore
        # don't return them in gitindexmap.__getitem__, we end up with files
        # in the "unsure" category.
        print(files)
        return [], [], []

    @propertycache
    def _parents(self):
        # type: () -> List[gitchangectx]
        p = self._repo.dirstate.parents()
        if p[1] == nullid:
            p = p[:-1]
        return [gitchangectx(self._repo, x) for x in p]

class gitindexmap(collections.MutableMapping):
    """
    Wrap a pygit2 index in a mutable mapping where the values correspond to
    Mercurial's notion of file status.
    """
    def __init__(self, repo):
        self._repo = repo
        self._index = repo.index

    def __getitem__(self, key):
        '''Return the current state of key (a filename) in the dirstate.

        States are:
          n  normal
          m  needs merging
          r  marked for removal
          a  marked for addition
        '''
        item = self._index[key]
        status = self._repo.status_file(key)

        if status == pygit2.GIT_STATUS_WT_NEW:
            # means untracked
            raise KeyError(key)

        map = [
            (pygit2.GIT_STATUS_INDEX_NEW, 'a'),
            (pygit2.GIT_STATUS_INDEX_DELETED, 'r'),
            (pygit2.GIT_STATUS_WT_DELETED, 'n'),
            # # FIXME: need to differentiate staged vs unstaged modified
            (pygit2.GIT_STATUS_WT_MODIFIED, 'm'),
            (pygit2.GIT_STATUS_INDEX_MODIFIED, 'm'),
        ]

        if status == pygit2.GIT_STATUS_CURRENT:
            # special-case bitmask 0
            return ('n', item.mode, 0, 0)

        for gstat, hstat in map:
            if status & gstat:
                return (hstat, item.mode, 0, 0)

        raise RuntimeError(key, status)

    def __setitem__(self, key, value):
        self._index.add(key)

    def __delitem__(self, key):
        self._index.remove(key)

    def __len__(self):
        return len(self._index)

    def __iter__(self):
        for key in self._index:
            yield key.path


class gitdirstatemap(dirstatemod.dirstatemap):
    """
    manages a git index via a gitindexmap
    """
    def __init__(self, ui, repo, root):
        super(gitdirstatemap, self).__init__(ui, None, root)
        self._repo = repo

    def clear(self):
        raise RuntimeError("Not supported. Need to investigate further")
        self._map.clear()
        self.copymap.clear()
        self.setparents(nullid, nullid)
        util.clearcachedproperty(self, "_dirs")
        util.clearcachedproperty(self, "_alldirs")
        util.clearcachedproperty(self, "filefoldmap")
        util.clearcachedproperty(self, "dirfoldmap")
        util.clearcachedproperty(self, "nonnormalset")
        util.clearcachedproperty(self, "otherparentset")

    def preload(self):
        """Loads the underlying data, if it's not already loaded"""
        pass

    @propertycache
    def _map(self):
        self._map = gitindexmap(self._repo)
        # self.read()
        return self._map

    def parents(self):
        # type: () -> Tuple[bytes, bytes]
        if not self._parents:
            # FIXME: p2
            try:
                self._parents = self._repo.head.target, node.nullid
            except pygit2.GitError:
                self._parents = node.nullid, node.nullid

        return self._parents

    def read(self):
        pass

    def write(self, st, now):
        self._map._index.write()


class gitdirstate(dirstatemod.dirstate):
    def __init__(self, repo, ui, root):
        super(gitdirstate, self).__init__(None, ui, root, lambda x: x, None)
        self._repo = repo
        self._map = gitdirstatemap(ui, repo._repo, root)

        # FIXME: hardwire these for now
        self._checkcase = False  # false means fs is case sensitive

    @propertycache
    def nonnormalset(self):
        # fixes issue with remove/forget
        return set()

    def branch(self):
        try:
            refname = self._repo._repo.head.name
        except pygit2.GitError:
            # this can happen before files have been added
            return 'master'
        else:
            return refname.split('/', 2)[-1]

    # FIXME: this is probably a bit too simplistic
    def write(self, rt):
        self._map.write(None, None)

    def add(self, f):
        '''Mark a file added.'''
        self._addpath(f, 'a', 0, -1, -1)
        # self._map.copymap.pop(f, None)

    def normalize(self, path, *args, **kwargs):
        # FIXME: not sure whether we need to handle normalization, or if that is handled by pygit2
        return path

    def status(self, match, subrepos, ignored, clean, unknown):
        # type: (matchmod.basematcher, List[str], List[str], List[str], List[str]) -> Tuple[List[str], scmutil.status]
        '''Determine the status of the working copy relative to the
        dirstate and return a pair of (unsure, status), where status is of type
        scmutil.status and:

          unsure:
            files that might have been modified since the dirstate was
            written, but need to be read to be sure (size is the same
            but mtime differs)
          status.modified:
            files that have definitely been modified since the dirstate
            was written (different size or mode)
          status.clean:
            files that have definitely not been modified since the
            dirstate was written
        '''
        listignored, listclean, listunknown = ignored, clean, unknown
        lookup, modified, added, unknown, ignored = [], [], [], [], []
        removed, deleted, clean = [], [], []

        madd = modified.append
        aadd = added.append
        uadd = unknown.append
        iadd = ignored.append
        radd = removed.append
        dadd = deleted.append
        cadd = clean.append
        mexact = match.exact

        map = {
            pygit2.GIT_STATUS_INDEX_NEW: added.append,
            pygit2.GIT_STATUS_INDEX_NEW | pygit2.GIT_STATUS_WT_MODIFIED: added.append,
            pygit2.GIT_STATUS_WT_NEW: unknown.append,
            pygit2.GIT_STATUS_CURRENT: clean.append,
            pygit2.GIT_STATUS_IGNORED: ignored.append,
            pygit2.GIT_STATUS_INDEX_DELETED: removed.append,
            pygit2.GIT_STATUS_WT_DELETED: deleted.append,
            # FIXME: need to differentiate staged vs unstaged modified
            pygit2.GIT_STATUS_WT_MODIFIED: modified.append,
            pygit2.GIT_STATUS_INDEX_MODIFIED: modified.append,
        }
        statuses = self._repo._repo.status()

        for path in sorted(statuses):
            status = statuses[path]
            map[status](path)
        return (lookup, scmutil.status(modified, added, removed, deleted,
                                       unknown, ignored, clean))

    def copies(self):
        # type: () -> Dict[str, str]
        # FIXME:
        return {}


class gitnamespaces(namespaces.namespaces):
    """provides an interface to register and operate on multiple namespaces. See
    the namespace class below for details on the namespace object.

    """

    _names_version = 0

    def __init__(self):
        self._names = util.sortdict()
        columns = templatekw.getlogcolumns()
        #
        # # we need current mercurial named objects (bookmarks, tags, and
        # # branches) to be initialized somewhere, so that place is here
        # bmknames = lambda repo: repo._bookmarks.keys()
        # bmknamemap = lambda repo, name: tolist(repo._bookmarks.get(name))
        # bmknodemap = lambda repo, node: repo.nodebookmarks(node)
        # n = namespace("bookmarks", templatename="bookmark",
        #               logfmt=columns['bookmark'],
        #               listnames=bmknames,
        #               namemap=bmknamemap, nodemap=bmknodemap,
        #               builtin=True)
        # self.addnamespace(n)
        #
        tagnames = lambda repo: [t for t, n in repo.tagslist()]
        tagnamemap = lambda repo, name: tolist(repo._tagscache.tags.get(name))
        tagnodemap = lambda repo, node: repo.nodetags(node)
        n = namespace("tags", templatename="tag",
                      logfmt=columns['tag'],
                      listnames=tagnames,
                      namemap=tagnamemap, nodemap=tagnodemap,
                      deprecated={'tip'},
                      builtin=True)
        self.addnamespace(n)

        bnames = lambda repo: repo.branchmap().keys()
        bnamemap = lambda repo, name: tolist(repo.branchtip(name, True))
        bnodemap = lambda repo, node: [repo[node].branch()]
        n = namespace("branches", templatename="branch",
                      logfmt=columns['branch'],
                      listnames=bnames,
                      namemap=bnamemap, nodemap=bnodemap,
                      builtin=True)
        self.addnamespace(n)


class gitrepository(object):
    def __init__(self, baseui, path, create=False, intents=None):
        # type: (uimod.ui, str, bool, Any) -> None
        self.requirements = set()
        self.filtername = None
        self._phasedefaults = []
        self._bookmarks = {}
        self.obsstore = False
        self._revbranchcache = None
        # generic mapping between names and nodes
        self.names = gitnamespaces()

        # wvfs: rooted at the repository root, used to access the working copy
        self.wvfs = vfsmod.vfs(path, expandpath=True, realpath=True)
        # vfs: rooted at .hg, used to access repo files outside of .hg/store
        self.vfs = None
        # svfs: usually rooted at .hg/store, used to access repository history
        # If this is a shared repository, this vfs may point to another
        # repository's .hg/store directory.
        self.svfs = None
        self.root = self.wvfs.base
        self.path = self.wvfs.join(".git")
        self.origroot = path

        # This is only used by context.workingctx.match in order to
        # detect files in subrepos.
        self.auditor = pathutil.pathauditor(
            self.root, callback=self._checknested)
        # This is only used by context.basectx.match in order to detect
        # files in subrepos.
        self.nofsauditor = pathutil.pathauditor(
            self.root, callback=self._checknested, realfs=False, cached=True)

        self.baseui = baseui
        self.ui = baseui.copy()
        self.ui.copy = baseui.copy # prevent copying repo configuration
        self.vfs = vfsmod.vfs(self.path, cacheaudited=True)
        if (self.ui.configbool('devel', 'all-warnings') or
            self.ui.configbool('devel', 'check-locks')):
            self.vfs.audit = self._getvfsward(self.vfs.audit)

        try:
            self.ui.readconfig(self.vfs.join("hgrc"), self.root)
            # self._loadextensions()
        except IOError:
            pass

        color.setup(self.ui)

        if not self.vfs.isdir():
            if create:
                pygit2.init_repository(self.path, False)
            else:
                raise error.RepoError(_("repository %s not found") % path)
        elif create:
            raise error.RepoError(_("repository %s already exists") % path)

        self._repo = pygit2.Repository(self.path)

        # FIXME: move to propertycache
        self.dirstate = gitdirstate(self, self.ui, self.root)

    def close(self):
        pass

    def _checknested(self, path):
        return False

    def peer(self):
        # FIXME: create a peer object? use localpeer?
        return self

    # unchanged
    def unfiltered(self):
        return self

    def filtered(self, name, visibilityexceptions=None):
        return self

    @propertycache
    def changelog(self):
        return gitchangelog(self)

    def __getitem__(self, changeid):
        if changeid is None:
            return gitworkingctx(self)
        if isinstance(changeid, context.basectx):
            return changeid
        # if isinstance(changeid, slice):
        #     # wdirrev isn't contiguous so the slice shouldn't include it
        #     return [context.changectx(self, i)
        #             for i in xrange(*changeid.indices(len(self)))
        #             if i not in self.changelog.filteredrevs]
        try:
            return gitchangectx(self, changeid)
        except error.WdirUnsupported:
            return gitworkingctx(self)

    def __contains__(self, changeid):
        """True if the given changeid exists

        error.LookupError is raised if an ambiguous node specified.
        """
        try:
            self[changeid]
            return True
        except error.RepoLookupError:
            return False

    def __nonzero__(self):
        return True

    __bool__ = __nonzero__

    # unchanged
    def __len__(self):
        # no need to pay the cost of repoview.changelog
        unfi = self.unfiltered()
        return len(unfi.changelog)

    # unchanged
    def __iter__(self):
        return iter(self.changelog)

    # unchanged
    def revs(self, expr, *args):
        expr = revsetlang.formatspec(expr, *args)
        m = revset.match(None, expr)
        return m(self)

    # unchanged
    def set(self, expr, *args):
        for r in self.revs(expr, *args):
            yield self[r]

    # unchanged
    def anyrevs(self, specs, user=False, localalias=None):
        if user:
            m = revset.matchany(self.ui, specs,
                                lookup=revset.lookupfn(self),
                                localalias=localalias)
        else:
            m = revset.matchany(None, specs, localalias=localalias)
        return m(self)

    # unchanged
    def url(self):
        return 'file:' + self.root

    # unchanged
    @propertycache
    def _tagscache(self):
        '''Returns a tagscache object that contains various tags related
        caches.'''

        # This simplifies its cache management by having one decorated
        # function (this one) and the rest simply fetch things from it.
        class tagscache(object):
            def __init__(self):
                # These two define the set of tags for this repository. tags
                # maps tag name to node; tagtypes maps tag name to 'global' or
                # 'local'. (Global tags are defined by .hgtags across all
                # heads, and local tags are defined in .hg/localtags.)
                # They constitute the in-memory cache of tags.
                self.tags = self.tagtypes = None

                self.nodetagscache = self.tagslist = None

        cache = tagscache()
        cache.tags, cache.tagtypes = self._findtags()

        return cache

    def tags(self):
        return self._tagscache.tags

    def _findtags(self):
        repo = self._repo
        # strip refs/tags/
        tags = {tn[10:]: repo.lookup_reference(tn).target
                for tn in repo.references if tn.startswith('refs/tags/')}
        tagtypes = dict((tag, 'global') for tag in tags)
        return tags, tagtypes

    def tagtype(self, tagname):
        '''
        return the type of the given tag. result can be:

        'local'  : a local tag
        'global' : a global tag
        None     : tag does not exist
        '''
        # FIXME:
        return 'local'

    def tagslist(self):
        # type: () -> List[Tuple[bytes, bytes]]
        '''return a list of tags ordered by revision'''
        if not self._tagscache.tagslist:
            # FIXME: we don't sort by revision
            self._tagscache.tagslist = list(self.tags().iteritems())

        return self._tagscache.tagslist

    def nodetags(self, node):
        # type: (bytes) -> Any
        return []

    def nodebookmarks(self, node):
        # type: (bytes) -> Any
        return []

    # FIXME: cache this
    def branchmap(self):
        # type: () -> Dict[str, List[pygit2.Oid]]
        '''returns a dictionary {branch: [branchheads]} with branchheads
        ordered by increasing revision number'''
        repo = self._repo
        return {bname: [repo.branches[bname].target]
                for bname in repo.branches.local}

    def branchheads(self, branch=None, start=None, closed=False):
        if branch is None:
            branch = self[None].branch()
        try:
            return self.branchmap()[branch]
        except KeyError:
            return []

    def revbranchcache(self):
        if not self._revbranchcache:
            class revbranchcache(object):
                def __init__(self, bmap):
                    self.lookup = {v[0]: k for k, v in bmap.items()}

                # FIXME: in hg, every rev is assigned to at least one branch.
                # in git, the answer to this is not so clear.
                def branchinfo(self, rev):
                    return self.lookup[rev], False

            self._revbranchcache = revbranchcache(self.branchmap())
        return self._revbranchcache

    def branchtip(self, branch, ignoremissing=False):
        try:
            return self.branchmap()[branch][0]
        except KeyError:
            if not ignoremissing:
                raise error.RepoLookupError(_("unknown branch '%s'") % branch)
            else:
                pass

    # unchanged
    def lookup(self, key):
        return scmutil.revsymbol(self, key).node()

    # unchanged
    def lookupbranch(self, key):
        if key in self.branchmap():
            return key

        return scmutil.revsymbol(self, key).branch()

    # unchanged
    def local(self):
        return self

    def getcwd(self):
        return self.dirstate.getcwd()

    def pathto(self, f, cwd=None):
        return self.dirstate.pathto(f, cwd)

    # --

    @contextlib.contextmanager
    def lock(self, wait=True):
        yield

    @contextlib.contextmanager
    def wlock(self, wait=True):
        yield
        # if self.dirstate.pendingparentchange():
        #     self.dirstate.invalidate()
        # else:
        #     self.dirstate.write(None)
        self.dirstate.write(None)

    def commit(self, text="", user=None, date=None, match=None, force=False,
               editor=False, extra=None):
        """Add a new revision to current repository.

        Revision information is gathered from the working directory,
        match can be used to filter the committed files. If editor is
        supplied, it is called to get a commit message.
        """
        if extra is None:
            extra = {}

        def fail(f, msg):
            raise error.Abort('%s: %s' % (f, msg))

        if not match:
            match = matchmod.always(self.root, '')

        if not force:
            vdirs = []
            match.explicitdir = vdirs.append
            match.bad = fail

        wctx = self[None]
        merge = len(wctx.parents()) > 1

        if not force and merge and not match.always():
            raise error.Abort(_('cannot partially commit a merge '
                               '(do not specify files or patterns)'))

        status = self.status(match=match, clean=force)
        if force:
            status.modified.extend(status.clean) # mq may commit clean files

        # make sure all explicit patterns are matched
        if not force:
            self.checkcommitpatterns(wctx, vdirs, match, status, fail)

        cctx = context.workingcommitctx(self, status,
                                        text, user, date, extra)

        # internal config: ui.allowemptycommit
        allowemptycommit = (wctx.branch() != wctx.p1().branch()
                            or extra.get('close') or merge or cctx.files()
                            or self.ui.configbool('ui', 'allowemptycommit'))
        if not allowemptycommit:
            return None

        if merge and cctx.deleted():
            raise error.Abort(_("cannot commit merge with missing files"))

        ms = mergemod.mergestate.read(self)
        mergeutil.checkunresolved(ms)

        if editor:
            cctx._text = editor(self, cctx, subs)
        edited = (text != cctx._text)

        # Save commit message in case this transaction gets rolled back
        # (e.g. by a pretxncommit hook).  Leave the content alone on
        # the assumption that the user will use the same editor again.
        msgfn = self.savecommitmessage(cctx._text)

        # commit subs and write new state
        if subs:
            for s in sorted(commitsubs):
                sub = wctx.sub(s)
                self.ui.status(_('committing subrepository %s\n') %
                               subrepoutil.subrelpath(sub))
                sr = sub.commit(cctx._text, user, date)
                newstate[s] = (newstate[s][0], sr)
            subrepoutil.writestate(self, newstate)

        p1, p2 = self.dirstate.parents()
        hookp1, hookp2 = hex(p1), (p2 != nullid and hex(p2) or '')
        try:
            self.hook("precommit", throw=True, parent1=hookp1,
                      parent2=hookp2)
            tr = self.transaction('commit')
            ret = self.commitctx(cctx, True)
        except: # re-raises
            if edited:
                self.ui.write(
                    _('note: commit message saved in %s\n') % msgfn)
            raise
            # update bookmarks, dirstate and mergestate
            cctx.markcommitted(ret)
            ms.reset()
            tr.close()

        def commithook(node=hex(ret), parent1=hookp1, parent2=hookp2):
            # type: (bytes, Any, Any) -> Any
            # hack for command that use a temporary commit (eg: histedit)
            # temporary commit got stripped before hook release
            if self.changelog.hasnode(ret):
                self.hook("commit", node=node, parent1=parent1,
                          parent2=parent2)

        return ret

    # unchanged
    def status(self, node1='.', node2=None, match=None,
               ignored=False, clean=False, unknown=False,
               listsubrepos=False):
        '''a convenience method that calls node1.status(node2)'''
        return self[node1].status(node2, match, ignored, clean, unknown,
                                  listsubrepos)

    def postdsstatus(self):
        """Used by workingctx to get the list of post-dirstate-status hooks."""
        return []

    def heads(self, start=None):
        assert start is None
        return [x[0] for x in self.branchmap().values()]


def instance(ui, path, create, intents=None):
    # type: (uimod.ui, str, Any, Any) -> Any
    return gitrepository(ui, util.urllocalpath(path), create,
                         intents=intents)

# --- Overrides ---

class gitfullreposet(smartset.generatorset):
    def __new__(cls, repo, iterasc=None, root=None, heads=None):
        return super(gitfullreposet, cls).__new__(cls, None, iterasc)

    def __init__(self, repo, iterasc=None, root=None, heads=None):
        # type: (gitrepository, Optional[bool], Optional[OidProxy], Optional[Iterable[OidProxy]]) -> None
        self.repo = repo
        self.gitrepo = repo._repo
        self.root = oid(root) if root is not None else None
        if heads is not None:
            self.heads = [oid(h) for h in heads]
        else:
            self.heads = [self.gitrepo.branches[branch].peel().id for branch
                          in self.gitrepo.branches]
        super(gitfullreposet, self).__init__(self._revgen(), iterasc=iterasc)

    def _revgen(self):
        order = pygit2.GIT_SORT_TOPOLOGICAL | pygit2.GIT_SORT_REVERSE
        walker = self.gitrepo.walk(None, order)
        for head in self.heads:
            walker.push(head)
        if self.root is not None:
            # to match mercurial, we want to hide the parents of root
            for parent_id in self.gitrepo[self.root].parent_ids:
                walker.hide(parent_id)
        for i, x in enumerate(walker):
            yield OidProxy(x.id, i)

    def __contains__(self, item):
        return True

    def __and__(self, other):
        """As self contains the whole repo, all of the other set should also be
        in self. Therefore `self & other = other`.

        This boldly assumes the other contains valid revs only.
        """
        # other not a smartset, make is so
        if not util.safehasattr(other, 'isascending'):
            # filter out hidden revision
            # (this boldly assumes all smartset are pure)
            #
            # `other` was used with "&", let's assume this is a set like
            # object.
            other = smartset.baseset(other)

        other.sort(reverse=self.isdescending())
        return other


def formatrevnode(ui, rev, node):
    # type: (uimod.ui, int, bytes) -> str
    """Format given revision and node depending on the current verbosity"""
    return '%s' % node

def meaningfulparents(repo, ctx):
    # type: (repository.completelocalrepository, context.basectx) -> Any
    """Return list of meaningful (or all if debug) parentrevs for rev.

    For merges (two non-nullrev revisions) both parents are meaningful.
    Otherwise the first parent revision is considered meaningful if it
    is not the preceding revision.
    """
    parents = ctx.parents()
    if len(parents) > 1:
        return parents
    if repo.ui.debugflag:
        return [parents[0], repo['null']]
    return parents

def reachableroots(repo, roots, heads, includepath=False):
    # type: (Repo, smartset.abstractsmartset, smartset.abstractsmartset, bool) -> smartset.abstractsmartset
    """return (heads(::<roots> and ::<heads>))

    If includepath is True, return (<roots>::<heads>)."""
    if not roots:
        return smartset.baseset()

    roots = list(roots)
    heads = list(heads)

    assert len(roots) == 1

    return gitfullreposet(repo, root=roots[0], heads=heads)

def revancestors(repo, revs, followfirst=False, startdepth=None,
                 stopdepth=None, cutfunc=None):
    # type: (repository.completelocalrepository, smartset.abstractsmartset, bool, Any, Any, Any) -> smartset.fullreposet
    revs = list(revs)
    return gitfullreposet(repo, heads=revs)

def _phase(repo, subset, *targets):
    """helper to select all rev in <targets> phases"""
    return smartset.baseset()

def lower(s):
    return s.lower()

def upper(s):
    return s.upper()

nodehex = node.hex
def hex_(x):
    if isinstance(x, pygit2.Oid):
        return str(x)
    else:
        return nodehex(x)

# pygit2 returns unicode, and handles encoding on its own, though I'm
# not completely sure this is free of collateral damage
encoding.lower = lower
encoding.upper = upper

# def short(n):
#     return node.hex(bytes(n)[:6])
#
# node.short = short
node.hex = hex_
context.hex = hex_
dagop.reachableroots = reachableroots
dagop.revancestors = revancestors

scmutil.formatrevnode = formatrevnode
scmutil.meaningfulparents = meaningfulparents
scmutil.casecollisionauditor = lambda *args, **kwargs: None

smartset.fullreposet = gitfullreposet
# spansets no longer make sense.
# this will error if start/stop value is provided, but we want to know that.
smartset.spanset = gitfullreposet

revset._phase = _phase

def overridepredicate(decl):
    """
    Decorator to replace a revset predicate
    """
    name = revset.predicate._getname(decl)
    origfunc = revset.predicate._table.pop(name)

    def deco(func):
        func._safe = origfunc._safe
        func._takeorder = origfunc._takeorder
        func._weight = origfunc._weight
        revset.predicate._table[name] = func
        revset.symbols[name] = func
        setattr(revset, func.__name__, func)
        # FIXME: also replace origfunc in i18nfunctions?
        return func
    return deco

@overridepredicate('branch(string or set)')
def branch(repo, subset, x):
    # type: (gitrepository, abstractsmartset, Tuple) -> abstractsmartset
    """
    All changesets belonging to the given branch or the branches of the given
    changesets.

    Pattern matching is supported for `string`. See
    :hg:`help revisions.patterns`.
    """
    def getbranchrevs(r):
        return set(branches_with(repo._repo, r))

    # FIXME: look into sorting by branch name, to keep results stable
    branchrevs = set()
    revspec = False

    try:
        b = revset.getstring(x, '')
    except error.ParseError:
        # not a string, but another revspec, e.g. tip()
        revspec = True
    else:
        kind, pattern, matcher = stringutil.stringmatcher(b)
        branchmap = repo.branchmap()
        if kind == 'literal':
            # note: falls through to the revspec case if no branch with
            # this name exists and pattern kind is not specified explicitly
            if pattern in branchmap:
                branchrevs.add(branchmap[b][0])
            elif b.startswith('literal:'):
                raise error.RepoLookupError(_("branch '%s' does not exist")
                                            % pattern)
            else:
                revspec = True
        else:
            branchrevs.update(r[0] for b, r in branchmap.items() if matcher(b))

    if revspec:
        # get all the branches in x
        s = revset.getset(repo, gitfullreposet(repo), x)
        for r in s:
            branchrevs.update(getbranchrevs(r))

    if not branchrevs:
        # FIXME: return empty set or subset?
        raise NotImplementedError

    brs = list(branchrevs)
    s = gitfullreposet(repo, heads=brs)
    return subset & s


import mercurial.hg
mercurial.hg.localrepo = sys.modules[__name__]
