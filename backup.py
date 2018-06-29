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
    ssh_opts = [
        host.get('host'), "-C",
        "-o", "PreferredAuthentications=password",
        "-o", "PubkeyAuthentication=no"
    ]
    sudo = []
    if host.get('ansible_become', 'no') == 'yes':
        sudo = ["sudo"]
    if host.get('ansible_ssh_user'):
        ssh_opts += ["-l", host.get('ansible_ssh_user')]
    if host.get('ssh_port'):
        ssh_opts += ["-p", host.get('ssh_port')]
    return (ssh_opts, sudo)


def ssh(host, *cmd, simulate=None, **kwargs):
    logging.info("Run %s:'%s' (...) // %s" % (
        host["host"], "' '".join(cmd[:10]), kwargs))
    if simulate is None:
        simulate = globals()['simulate']

    if simulate:
        return True

    ssh_opts, sudo = parse_ssh_options(host)
    try:
        return sh.ssh(*ssh_opts, "--", *sudo, *cmd, **kwargs)
    except Exception as e:
        logging.error(
            "Error %d executing SSH %s -- '%s': %s" % (
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
    logging.info("Backup of %s:%s" % (host["host"], path))

    if path.endswith('/'):
        outfile = "%s/%s-%s-%s.tgz" % (
            destdir, date, host['host'], path.replace('/', '-'))
        if incremental:
            ok = ssh(host, "find", path, "-mtime", "-%f" % incremental, "|",
                     "xargs", "tar", "--no-recursion", "cz", path, _out=outfile)
        else:
            ok = ssh(host, "tar", "cz", path, _out=outfile)
        tar = True
    else:
        outfile = "%s/%s-%s-%s" % (
            destdir, date, host['host'], path.replace('/', '-'),
        )
        tar = False

    if gpg_key:
        genopts = dict(_piped=True)
    else:
        genopts = dict(_out=outfile)

    if tar:
        if incremental:
            findcmd = ssh(
                host,
                "find", path, "-type", "f", "-mtime", "-%f" % incremental,
                _ok_code=[0, 1], simulate=False)
            files = [x for x in findcmd.stdout.decode('utf8').split('\n') if x]
            logging.info("Backup of %s files" % len(files))
            if files:
                gencmd = ssh(
                    host,
                    "tar", "--no-recursion", "-cz", *files,
                    _err=warn_strip, **genopts)
            else:
                logging.info("No files to backup. Skipping.")
                all_ok = False
                return False
        else:
            gencmd = ssh(
                host, "tar", "cz", path, _err=warn_strip, **genopts)
    else:
        gencmd = ssh(host, "cat", path, _err=warn_strip, **genopts)

    ok = True
    if gpg_key:
        outfile = outfile + '.gpg'
        if not simulate:
            gpgout = sh.gpg2(
                gencmd, "-e", "-r", gpg_key,
                _err=warn_strip, _out=outfile)
            gpgout.wait()
            try:
                ok = (gpgout.exit_code == 0) and (gencmd.exit_code == 0)
            except sh.ErrorReturnCode_2:
                logging.error("Partial backup. Some files missing.")
                ok = True
            except Exception as ex:
                logging.error(type(ex))
                ok = False
                all_ok = False
    else:
        gencmd.wait()
        ok = (gencmd.exit_code == 0)

    if not simulate:
        try:
            size = os.path.getsize(outfile)
            assert size > 256, "File too small."
            logging.info("%s -- %.2f MB" % (outfile, size / (1024 * 1024.0)))
        except Exception:
            all_ok = False
            ok = False
    else:
        logging.info("Nothing created. In simulation mode.")
        ok = True

    if not ok:
        all_ok = False
        logging.error("FILE NOT CREATED OR TOO SMALL")


    return outfile


def parse_host_line(line):
    line = line.split()
    ret = {"host": line[0]}
    for optval in line[1:]:
        opt, val = optval.split("=")
        ret[opt] = val

    return ret


def read_hosts_file(filename):
    ret = []
    for line in open(filename):
        line = line.strip()
        if not line or line.startswith('#') or line.startswith('['):
            continue
        ret.append(parse_host_line(line))
    return ret


BACKUP_PLAN = yaml.safe_load(open('backup-plan.yaml'))


def get_all(host, what):
    for i in (BACKUP_PLAN.get("all") or {}).get(what, []):
        yield i
    for i in (BACKUP_PLAN.get(host) or {}).get(what, []):
        yield i


def backup_host(h):
    global all_ok
    logging.info("Backup host %s", h)
    host = h["host"]
    if '@' in host:
        host = host.split('@')[1]

    for pre in get_all(host, 'pre'):
        pre = shlex.split(pre)
        preok = ssh(h, *pre)
        if not preok:
            logging.error(
                "Error performing backup for %s:%s. "
                "Might fail later." % (h, pre))
            all_ok = False

    gpg_key = h.get('gpg_key')
    if not gpg_key:
        gpg_key = BACKUP_PLAN["all"].get("gpg_key")

    for path in get_all(host, 'paths'):
        backup(h, path, gpg_key=gpg_key)

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
  all: {pre, paths, post}
  hostname: {pre, paths, post}

  `all` will be executed for all hosts.

Where {pre, backup, post} are lists of:
  `pre`    commands to execute on the remote server before backup: setup
  `paths`  directories (end with /) or files to backup
  `post`   commands to execute on the remote server after backup: cleanup

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

    OPTIONS = ("ih", ['since=', 'dry', 'simulate', 'help', 'full'])
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

    if '--since=' in optlist:
        days = float(optlist["--since="])
        logging.info("Since %f days ago" % days)
        incremental = days

    if '--full' in optlist:
        incremental = False

    if args:
        hosts = [parse_host_line(x) for x in args]
    else:
        hosts = read_hosts_file("hosts")

    logging.info("Will backup %s" % [x["host"] for x in hosts])

    for h in hosts:
        backup_host(h)

    if all_ok:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == '__main__':
    main()
