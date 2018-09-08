#!/bin/bash

set -e

mkdir hgtest
cd hgtest
hg init

# --
touch file-A.txt
touch file-B.txt
mkdir subdir
touch subdir/file-C.txt
hg add file-A.txt file-B.txt subdir/file-C.txt
hg commit -m "initial commit"

# --
echo "edit1" >> file-A.txt
hg commit -m "modify file-A"
hg tag "v1.0"

# --
hg branch branch1
echo "edit2" >> file-A.txt
hg commit -m "modify file-A again"

# --
touch subdir/file-D.txt
hg add subdir/file-D.txt
hg commit -m "add file-D"

# --
hg up default
echo "edit1" >> file-B.txt
hg commit -m "modify file-B"

# --
hg merge branch1
hg commit -m "merge branch1"

# --
hg branch branch2
echo "edit1" >> subdir/file-C.txt
hg commit -m "modify file-C"

# --
hg up default
hg rm file-B.txt
hg commit -m "remove file-B"
hg tag "v1.1"