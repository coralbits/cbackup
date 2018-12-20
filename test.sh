#!/bin/sh
set -e


TMPDIR=/tmp/cbackuptest/
TESTPLAN=$TMPDIR/testplan.yaml
GPG="$1"
rm -rf $TMPDIR
mkdir -p $TMPDIR

# It needs SSH connection to localhost

if [ ! "$GPG" ]; then
  echo "Run with:"
  echo " $0 [TEST_GPG_KEY_ID]"
  echo "Or will be tested without GPG"

  grep -v "GPGKEY" test.yaml > $TESTPLAN
else
  sed 's/GPGKEY/'$GPG'/' test.yaml > $TESTPLAN
fi

sed -i 's#BACKUPDIR#'$TMPDIR'#' $TESTPLAN

mkdir -p $TMPDIR/backups/

find $TMPDIR

./cbackup.py --plan $TESTPLAN $TMPDIR/backups/
DATE=$( date +"%Y%m%d" )


echo
echo "Check created files"
echo


check_file(){
  local FILENAME=$TMPDIR/backups/$DATE-$1
  if [ ! -f $FILENAME -a ! -f $FILENAME.gpg ]; then
    echo "File $FILENAME not created"
    exit 1
  fi
}

check_file localhost--etc-hosts
check_file localhost--tmp-cbackuptest--cbackup-dir-cbackup-date.txt
check_file localhost--tmp-cbackuptest--cbackup-dir-.tgz

if [ "$GPG" ]; then
  if [ -e "$TMPDIR/backups/$DATE-localhost--tmp-cbackuptest--cbackup-dir-.tgz" ]; then
    echo "Created unencrypted file $TMPDIR/backups/$DATE-localhost--tmp-cbackuptest--cbackup-dir-.tgz!"
    exit 1
  fi
fi

echo
echo "Try recover"
echo

recover(){
  if [ "$GPG" ]; then
    gpg -d $TMPDIR/backups/$DATE-$1.gpg > $TMPDIR/backups/$DATE-$1
  fi
  if [ "$2" = "tgz" ]; then
    mkdir -p $TMPDIR/recover/$2
    tar xfz $TMPDIR/backups/$DATE-$1 -C $TMPDIR/recover/$2
  else
    cp $TMPDIR/backups/$DATE-$1 $TMPDIR/recover/$2
  fi
}
check_same(){
  if [ "$( cat $1 | sha1sum )" != "$( cat $2 | sha1sum )" ]; then
    echo "Hosts files are not equal"
    sha1sum $1
    sha1sum $2
    exit 1
  fi
}


mkdir -p $TMPDIR/recover/

recover localhost--etc-hosts hosts
check_same /etc/hosts $TMPDIR/recover/hosts

recover localhost--tmp-cbackuptest--cbackup-dir-cbackup-date.txt cbackup-date.txt
check_same  $TMPDIR/cbackup-dir/cbackup-date.txt $TMPDIR/recover/cbackup-date.txt

recover localhost--tmp-cbackuptest--cbackup-dir-.tgz tgz
check_same  $TMPDIR/cbackup-dir/cbackup-date.txt $TMPDIR/recover/tgz/$TMPDIR/cbackup-dir/cbackup-date.txt
