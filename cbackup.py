#!/usr/bin/python3
import sh
import sys
import datetime
import os
import yaml
import logging
import shlex
import traceback
import getopt

VERSION = '0.1'

# set to true, to only print actions
simulate = False
date = datetime.datetime.now().strftime("%Y%m%d")
destdir = None
incremental = False
all_ok = True
backup_plan = []


logging.basicConfig(filename='backups.log', level=logging.INFO,
                    format='%(levelname)s -- %(asctime)s -- %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S')
# logging.getLogger().addHandler(logging.StreamHandler())


# Custom logger class with multiple destinations
class ColoredHandler(logging.Handler):
    LEVEL_TO_COLOR = {
        0: '\033[0;36m',
        10: '\033[0;34m',
        20: '\033[1;m',
        30: '\033[0;33m',
        40: '\033[0;31m',
        50: '\033[1;31m',
    }
    RESET = '\033[1;m'
    FORMAT = '{levelname:5} -- {datetime} -- {color}{message}{reset}'

    def handle(self, record):
        color = ColoredHandler.LEVEL_TO_COLOR[record.levelno]
        try:
            message = record.msg % record.args
        except Exception:
            message = record.msg
        print(ColoredHandler.FORMAT.format(
            color=color,
            reset=ColoredHandler.RESET,
            datetime=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            message=message,
            levelname=record.levelname
        ))


logging.getLogger().addHandler(ColoredHandler())


def parse_ssh_options(host):
    print(host)
    ssh_opts = [
        host.get('host'), "-C",
        # "-o", "PreferredAuthentications=password",
        # "-o", "PubkeyAuthentication=no"
    ]
    sudo = []
    if host.get('become'):
        sudo = [host.get('become')]
    if host.get('user'):
        ssh_opts += ["-l", host.get('user')]
    if host.get('port'):
        ssh_opts += ["-p", host.get('port')]
    return (ssh_opts, sudo)


def ssh(host, *cmd, simulate=None, **kwargs):
    logging.info("[%s] Run %s:'%s' (...) // %s" % (
        host["host"], host["host"], "' '".join(cmd[:10]), kwargs))
    if simulate is None:
        simulate = globals()['simulate']

    if simulate:
        return True

    ssh_opts, sudo = parse_ssh_options(host)
    try:
        return sh.ssh(*ssh_opts, "--", *sudo, *cmd, **kwargs, _out_bufsize=1024*1024, _no_err=True)
    except Exception as e:
        logging.error(
            "[%s] Error %d executing SSH %s -- '%s': %s" % (
                host["host"],
                e.exit_code, host, "' '".join(cmd), e))
        return False


def encrypt(gpg_key, filename):
    logging.info("Encrypt %s" % filename)
    if simulate:
        return True
    try:
        sh.gpg2("-e", "-r", gpg_key, filename)
        os.unlink(filename)
    except Exception:
        logging.error("Could not encrypt %s" % filename)
        traceback.print_exc()


def warn_strip(s):
    logging.warn(s.strip())


def backup(host, path, gpg_key=None):
    global all_ok
    hostname = host["host"]
    logging.info("[%s] Backup of %s:%s" % (hostname, hostname, path))

    if path.endswith('/'):
        outfile = "%s.tgz" % path
        tar = True
    else:
        outfile = path
        tar = False

    if tar:
        if incremental:
            findcmd = ssh(
                host,
                "find", path, "-type", "f", "-mtime", "-%f" % incremental,
                _ok_code=[0, 1], simulate=False)
            files = [x for x in findcmd.stdout.decode('utf8').split('\n') if x]
            logging.info("[%s] Backup of %s files" % (hostname, len(files)))
            if files:
                return backup_stdout(
                    host,
                    outfile,
                    ["tar", "--no-recursion", "-cz", *files],
                    gpg_key
                )
            else:
                logging.info("[%s] No files to backup. Skipping." % hostname)
                all_ok = False
                return False
        else:
            return backup_stdout(host, outfile, ["tar", "cz", path], gpg_key)
    else:
        return backup_stdout(host, outfile, ["cat", path], gpg_key)


def backup_stdout(host, name, cmd, gpg_key=None):
    global all_ok
    hostname = host["host"]
    outfile = "%s/%s-%s-%s" % (
        destdir, date, host['host'], name.replace('/', '-'))
    if gpg_key:
        logging.info("[%s] Encrypt with GPG key: %s" % (hostname, gpg_key))
        genopts = dict(_piped="direct")
        outfile = outfile+'.gpg'
    else:
        logging.info("[%s] No encryption." % hostname)
        genopts = dict(_out=outfile)

    if not isinstance(cmd, list):
        cmd = shlex.split(cmd)

    gencmd = ssh(host, *cmd, _err=warn_strip, **genopts)

    ok = True
    if gpg_key:
        if not simulate:
            gpgout = sh.gpg2(
                gencmd, "-e", "-r", gpg_key,
                _err=warn_strip, _out=outfile, _out_bufsize=1024*1024)
            gpgout.wait()
            try:
                ok = (gpgout.exit_code == 0) and (gencmd.exit_code == 0)
            except sh.ErrorReturnCode_2:
                logging.error("[%s] Partial backup. Some files missing." % hostname)
                ok = True
            except Exception as ex:
                logging.error("[%s] %s" % (hostname, type(ex)))
                ok = False
                all_ok = False
    else:
        gencmd.wait()
        ok = (gencmd.exit_code == 0)

    if not simulate:
        try:
            size = os.path.getsize(outfile)
            logging.info("[%s] %s -- %.2f MB" % (hostname, outfile, size / (1024 * 1024.0)))
            assert size != 0, "File empty!"
            if size < 1024:
                logging.warn("[%s] %s is TOO small! (%s bytes)" % (hostname, outfile, size))
        except Exception:
            all_ok = False
            ok = False
    else:
        logging.info("[%s] Nothing created. In simulation mode." % hostname)
        ok = True

    if not ok:
        all_ok = False
        logging.error("[%s] FILE NOT CREATED OR TOO SMALL" % hostname)

    return outfile


def host_auth(hostname):
    user = None
    if '@' in hostname:
        user, hostname = hostname.split('@')
    data = backup_plan.get(hostname)
    if not data:
        raise Exception("Unknown host %s" % hostname)
    return {
        "host": hostname,
        **data.get('auth', {})
    }


def read_all_auths():
    ret = [
        host_auth(i)
        for i in backup_plan.keys()
        if i != 'default'
    ]

    return ret


def get_all(host, what):
    for i in (backup_plan.get("default") or {}).get(what, []):
        yield i
    for i in (backup_plan.get(host) or {}).get(what, []):
        yield i


def get_all_items(host, what):
    for i in (backup_plan.get("default") or {}).get(what, {}).items():
        yield i
    for i in (backup_plan.get(host) or {}).get(what, {}).items():
        yield i


def backup_host(h):
    global all_ok
    logging.info("[%s] Backup host %s", h, h)
    host = h["host"]
    if '@' in host:
        host = host.split('@')[1]

    for pre in get_all(host, 'pre'):
        pre = shlex.split(pre)
        preok = ssh(h, *pre)
        if preok is False:
            logging.error(
                "[%s] Error performing backup for %s:%s. "
                "Might fail later. %s" % (h, h, pre, preok))
            all_ok = False

    gpg_key = h.get('gpg_key')
    if not gpg_key:
        gpg_key = backup_plan["default"].get("gpg_key")

    for path in get_all(host, 'paths'):
        backup(h, path, gpg_key=gpg_key)

    for name, cmd in get_all_items(host, 'stdout'):
        backup_stdout(h, name, cmd, gpg_key=gpg_key)

    # post always, as is cleanup
    for post in get_all(host, 'post'):
        post = shlex.split(post)
        ssh(h, *post)


def help():
    print("""\
backup.py -- Simple backups -- v%(version)s

Run:
  backup.py [options] <destdir> [hosts]

  [options] are optional
  <destdir> is mandatory, and backup will create files based on the
            date, hostname, dir/file
  [hosts]   optional host list. If not exists, will use all from
            `backup-plan.yaml`


Needs a backup-plan.yaml with:
  default: {pre, paths, post}
  hostname: {pre, paths, post}

  `default` will be executed for all hosts.

Where {pre, backup, post} are lists of:
  `pre`    commands to execute on the remote server before backup: setup
  `paths`  directories (end with /) or files to backup
  `post`   commands to execute on the remote server after backup: cleanup
  `stdout` dictionary of command to capture stdout for backup, for example pg_dump

Options:
    -h    | --help           -- Show this help
    -v    | --version        -- Shows current version and exits
    -i    | --incremental    -- Only changes since yesterday
    --since=days             -- Only changes since `days` before. Can be float.
    --dry | --simulate       -- Say what will be executed, but do not execute
    --full                   -- Full backup (default)

""" % dict(version=VERSION))


def main():
    global simulate
    global destdir
    global incremental
    global backup_plan

    OPTIONS = (
        "ih",
        [
         'since=', 'dry', 'simulate', 'incremental',
         'help', 'full', 'p=', 'plan='
        ]
    )
    try:
        optlist, args = getopt.getopt(sys.argv[1:], *OPTIONS)
        optlist = dict(optlist)
    except getopt.GetoptError as e:
        help()
        print("Error: ", e)
        print()
        sys.exit(1)
    if not args or '-h' in optlist or '--help' in optlist:
        help()
        return
    if '-v' in optlist or '--version' in optlist:
        print(VERSION)
        return
    if any(x for x in args if x.startswith('--')):
        help()
        print("Error: All options should go at the beginning.")
        print()
        sys.exit(1)

    if '--plan' in optlist or '--p' in optlist:
        planfile = optlist.get('--plan') or optlist.get('--p')
    else:
        planfile = os.path.join(os.path.dirname(__file__), 'backup-plan.yaml')
    logging.info("Backup plan from %s" % planfile)
    backup_plan = yaml.safe_load(open(planfile))

    destdir = args[0]
    args = args[1:]

    logging.info("---- STARTING NEW BACKUP ----")
    assert os.path.isdir(destdir), \
        "Need a backup directory file as first argument"

    if '--simulate' in optlist or '--dry' in optlist:
        logging.info("Dry run.")
        simulate = True

    if '-i' in optlist or '--incremental' in optlist:
        logging.info("Incremental simple")
        incremental = 1

    if '--since' in optlist:
        days = float(optlist["--since"])
        logging.info("Since %f days ago" % days)
        incremental = days

    if '--full' in optlist:
        incremental = False

    if args:
        hosts = [host_auth(x) for x in args]
    else:
        hosts = read_all_auths()

    logging.info("Will backup %s" % [x["host"] for x in hosts])

    for h in hosts:
        try:
            backup_host(h)
        except Exception as e:
            traceback.print_exc()
            logging.error("FATAL error on backup of %s: %s" % (str(h), str(e)))

    if all_ok:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == '__main__':
    main()
