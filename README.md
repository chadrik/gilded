# Gilded

A git command line interface based on mercurial.

I have been actively using both git and mercurial for more than a decade -- since before Github existed! -- and while I'm thankful for Github and I appreciate git's elegant object model, I'm still frustrated by git's CLI.  I also think it's a shame that more people have not used mercurial: it is the finely crafted luxury sedan to git's Mad Maxian war rig. For years I've threatened to do something stupid like port mercurial to git, so when I was recently faced with the task of converting some of our internal code from mercurial's amazing revsets over to git, the walls of my sanity finally caved, and `gilded` was born.

To be clear, this project is a science experiment. It's a fun hobby, but the further along I get the more I wonder: could this become actually useful, or am I just losing my mind?

## Installation

First, install the module and its dependencies (mercurial and pygit2):

```
pip install gilded
```

Gilded is designed as a mercurial extension.  As the name suggests, extensions are intended to extend the behavior of mercurial, but gilded abuses this system to monkey-patch the mercurial internals to be based on libgit2. As a result, once the gilded extension is loaded, mercurial will no longer be able to operate on mercurial repositories. So if you plan to use mercurial as intended, don't register gilded in your .hgrc file.

For convenience, you can set up an alias that calls `hg` and loads the extension:

```
alias au='hg --config extensions.gilded='
``` 

As an homage to mercurial's `hg` command, I recommend the name `au`, after the periodic symbol for gold.

## Commands Currently Supported

### Query

I think most of these will be pretty straight-forward. The big payoff is `log`, where you can make use of revsets to make complex queries of your git history.
 
- [ ] `annotate`
- [ ] `bisect`
- [ ] `branches`
- [ ] `cat`
- [ ] `diff`
- [ ] `files`: works for working copy, but not revisions
- [x] `glog`
- [ ] `grep`
- [x] `heads`
- [x] `help`: todo: prune irrelevant commands and options
- [ ] `identify`
- [x] `log`: todo: file-related revsets
- [ ] `manifest`
- [ ] `paths`
- [x] `root`
- [x] `status`: todo: filter .git directory, read .gitignore for performance?
- [x] `summary`
- [x] `tags`: fixme: display color is black instead of green
- [x] `version`: shows version of hg.  should also show pygit2/libgit2 version?

### Edit
These are trickier.  I'm not sure how git handles locking around writing to the index. 

- [x] `add`: fixme: adding previously tracked files -- which is valid in git -- is rejected.  either need to override this or add a new  command for staging
- [ ] `addremove`
- [ ] `backout`
- [ ] `bookmarks`: not applicable
- [ ] `branch`
- [ ] `commit`
- [ ] `copy`
- [ ] `export`
- [x] `forget`
- [ ] `graft`
- [ ] `import`
- [x] `init`
- [ ] `merge`
- [ ] `phase`: probably not applicable
- [ ] `rebase`
- [ ] `remove`
- [ ] `rename`
- [ ] `resolve`
- [ ] `revert`
- [ ] `strip`
- [ ] `tag`
- [ ] `update`

### Utility

- [ ] `archive`
- [ ] `bundle`: probably not applicable
- [ ] `config`
- [ ] `recover`: probably not applicable
- [ ] `unbundle`: probably not applicable
- [ ] `verify`: not sure what the git equivalent of this is

### Remotes

- [ ] `clone`
- [ ] `incoming`
- [ ] `outgoing`
- [ ] `pull`
- [ ] `push`
- [ ] `serve`
