#!/bin/bash

set -e

mkdir gittest
cd gittest
git init

# --
touch file-A.txt
touch file-B.txt
mkdir subdir
touch subdir/file-C.txt
git add file-A.txt file-B.txt subdir/file-C.txt
git commit -m "initial commit"

# --
echo "edit1" >> file-A.txt
git commit -am "modify file-A"
git tag "v1.0"

# --
git checkout -b branch1
echo "edit2" >> file-A.txt
git commit -am "modify file-A again"

# --
touch subdir/file-D.txt
git add subdir/file-D.txt
git commit -m "add file-D"

# --
git checkout master
echo "edit1" >> file-B.txt
git commit -am "modify file-B"

# --
git merge branch1 -m "merge branch1"

# --
git checkout -b branch2
echo "edit1" >> subdir/file-C.txt
git commit -am "modify file-C"

# --
git checkout master
git rm file-B.txt
git commit -am "remove file-B"
git tag "v1.1"
