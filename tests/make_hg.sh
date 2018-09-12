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
hg commit -m "initial commit" --user "Chad Dombrova <chad@noemail.com>" --date "Fri Aug 31 12:00:00 2018 -0700"

# --
echo "edit1" >> file-A.txt
hg commit -m "modify file-A" --user "Chad Dombrova <chad@noemail.com>" --date "Fri Aug 31 12:10:00 2018 -0700"
hg tag "v1.0"

# --
hg branch branch1
echo "edit2" >> file-A.txt
hg commit -m "modify file-A again" --user "Chad Dombrova <chad@noemail.com>" --date "Fri Aug 31 12:20:00 2018 -0700"

# --
touch subdir/file-D.txt
hg add subdir/file-D.txt
hg commit -m "add file-D" --user "Chad Dombrova <chad@noemail.com>" --date "Fri Aug 31 12:30:00 2018 -0700"

# --
hg up default
echo "edit1" >> file-B.txt
hg commit -m "modify file-B" --user "Chad Dombrova <chad@noemail.com>" --date "Fri Aug 31 12:40:00 2018 -0700"

# --
hg merge branch1
hg commit -m "merge branch1" --user "Chad Dombrova <chad@noemail.com>" --date "Fri Aug 31 12:50:00 2018 -0700"

# --
hg branch branch2
echo "edit1" >> subdir/file-C.txt
hg commit -m "modify file-C" --user "Chad Dombrova <chad@noemail.com>" --date "Fri Aug 31 13:00:00 2018 -0700"

# --
hg up default
hg rm file-B.txt
hg commit -m "remove file-B" --user "Chad Dombrova <chad@noemail.com>" --date "Fri Aug 31 13:10:00 2018 -0700"
hg tag "v1.1"
