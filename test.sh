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

./cbackup.py --plan $TESTPLAN $TMPDIR/backups/ || true

[ "$( grep Traceback $TMPDIR/email.html )" ] && error "Should not have any traceback"

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
error(){
  echo "\e[0;37;41m"
  echo -n "$*"
  echo "\e[0m"
  exit 1
}

check_file localhost--etc-hosts
check_file localhost--tmp-cbackuptest--cbackup-dir-cbackup-date.txt
check_file localhost--tmp-cbackuptest--cbackup-dir-.tgz
check_file localhost-network.status

if [ "$GPG" ]; then
  if [ -e "$TMPDIR/backups/$DATE-localhost--tmp-cbackuptest--cbackup-dir-.tgz" ]; then
    error "Created unencrypted file $TMPDIR/backups/$DATE-localhost--tmp-cbackuptest--cbackup-dir-.tgz!"
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
    error "Hosts files are not equal:\n$( sha1sum $1 $2)"
  fi
}

result_code(){
  if [ ! "$(grep ".*$1.*$2.*$3.*$4.*$5.*" $TMPDIR/email.html)" ]; then
    error "Error on [$1] [$2] result not as expected: $*"
  fi
}
not_result_code(){
  if [ "$(grep ".*$1.*$2.*$3.*$4.*$5.*" $TMPDIR/email.html)" ]; then
    error "Error on [$1] [$2] result as NOT expected: $*"
  fi
}

mkdir -p $TMPDIR/recover/

recover localhost--etc-hosts hosts
check_same /etc/hosts $TMPDIR/recover/hosts

recover localhost--tmp-cbackuptest--cbackup-dir-cbackup-date.txt cbackup-date.txt
check_same  $TMPDIR/cbackup-dir/cbackup-date.txt $TMPDIR/recover/cbackup-date.txt

recover localhost--tmp-cbackuptest--cbackup-dir-.tgz tgz
check_same  $TMPDIR/cbackup-dir/cbackup-date.txt $TMPDIR/recover/tgz/$TMPDIR/cbackup-dir/cbackup-date.txt

ip a | grep -v lft > $TMPDIR/ipa
recover localhost-network.status network.status
check_same $TMPDIR/recover/network.status $TMPDIR/ipa
[ -e "$TMPDIR/email.html" ] || error "Missing email"

result_code localhost pre mkdir OK
result_code localhost pre date OK
not_result_code localhost "*" "*" ERROR
not_result_code localhost pre date OK "bytes"
result_code localhost path /etc/hosts OK "bytes"
result_code localhost path cbackup-dir OK "bytes"
result_code willfail "*" "*" ERROR
result_code willfail noperm ERROR
result_code willfail more ERROR

echo
echo Incremental
echo

./cbackup.py -i --plan $TESTPLAN $TMPDIR/backups/ || true

[ "$( grep Incremental $TMPDIR/email.html )" ] || error "Missing Incremental mark at email"
[ "$( grep Traceback $TMPDIR/email.html )" ] && error "Should not have any traceback"

result_code localhost pre mkdir OK
result_code localhost pre date OK
not_result_code localhost "*" "*" ERROR
result_code localhost path /etc/hosts OK "bytes"
result_code localhost path cbackup-dir OK "bytes"
result_code willfail "*" "*" ERROR
result_code willfail noperm ERROR
result_code willfail more ERROR
