#!/bin/bash

set -e

mkdir gittest_master
cd gittest_master
git init

export GIT_AUTHOR_NAME="Chad Dombrova"
export GIT_AUTHOR_EMAIL="chad@noemail.com"

# --
touch file-A.txt
touch file-B.txt
mkdir subdir
touch subdir/file-C.txt
git add file-A.txt file-B.txt subdir/file-C.txt
export GIT_COMMITTER_DATE="Fri Aug 31 12:00:00 2018 -0700"
export GIT_AUTHOR_DATE=$GIT_COMMITTER_DATE
git commit -m "initial commit"

# --
echo "edit1" >> file-A.txt
export GIT_COMMITTER_DATE="Fri Aug 31 12:10:00 2018 -0700"
export GIT_AUTHOR_DATE=$GIT_COMMITTER_DATE
git commit -am "modify file-A"
git tag "v1.0"

# --
git checkout -b branch1
echo "edit2" >> file-A.txt
export GIT_COMMITTER_DATE="Fri Aug 31 12:20:00 2018 -0700"
export GIT_AUTHOR_DATE=$GIT_COMMITTER_DATE
git commit -am "modify file-A again"

# --
touch subdir/file-D.txt
git add subdir/file-D.txt
export GIT_COMMITTER_DATE="Fri Aug 31 12:30:00 2018 -0700"
export GIT_AUTHOR_DATE=$GIT_COMMITTER_DATE
git commit -m "add file-D"

# --
git checkout master
echo "edit1" >> file-B.txt
export GIT_COMMITTER_DATE="Fri Aug 31 12:40:00 2018 -0700"
export GIT_AUTHOR_DATE=$GIT_COMMITTER_DATE
git commit -am "modify file-B"

# --
export GIT_COMMITTER_DATE="Fri Aug 31 12:50:00 2018 -0700"
export GIT_AUTHOR_DATE=$GIT_COMMITTER_DATE
git merge branch1 -m "merge branch1"

# --
git checkout -b branch2
echo "edit1" >> subdir/file-C.txt
export GIT_COMMITTER_DATE="Fri Aug 31 13:00:00 2018 -0700"
export GIT_AUTHOR_DATE=$GIT_COMMITTER_DATE
git commit -am "modify file-C"

# --
git checkout master
git rm file-B.txt
export GIT_COMMITTER_DATE="Fri Aug 31 13:10:00 2018 -0700"
export GIT_AUTHOR_DATE=$GIT_COMMITTER_DATE
git commit -am "remove file-B"
git tag "v1.1"

# --
echo "edit1" >> subdir/file-D.txt
export GIT_COMMITTER_DATE="Fri Aug 31 13:20:00 2018 -0700"
export GIT_AUTHOR_DATE=$GIT_COMMITTER_DATE
git commit -am "modify file-D"

# --
cd ..
git clone gittest_master gittest
cd gittest
git checkout branch1
git checkout branch2
git checkout master
git reset --hard v1.1
