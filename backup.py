#!/usr/bin/python3
import sh
import sys
import datetime
import os
import yaml
import logging
import shlex
import traceback

# set to true, to only print actions
simulate = False
date = datetime.datetime.now().strftime("%Y%m%d")
destdir = None


logging.basicConfig(filename='backups.log', level=logging.INFO,
                    format='%(levelname)s -- %(asctime)s -- %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S')
logging.getLogger().addHandler(logging.StreamHandler())


def parse_ssh_options(host):
    ssh_opts = [host.get('host'), "-C"]
    sudo = []
    if host.get('ansible_become', 'no') == 'yes':
        sudo = ["sudo"]
    if host.get('ansible_ssh_user'):
        ssh_opts += ["-l", host.get('ansible_ssh_user')]
    if host.get('ssh_port'):
        ssh_opts += ["-p", host.get('ssh_port')]
    return (ssh_opts, sudo)


def ssh(host, *cmd, **kwargs):
    logging.info("Run %s:'%s'" % (host, "' '".join(cmd)))
    if simulate:
        return True
    ssh_opts, sudo = parse_ssh_options(host)
    try:
        sh.ssh(*ssh_opts, "--", *sudo, *cmd, **kwargs)
        return True
    except Exception as e:
        logging.error("Error executing SSH %s -- '%s': %s" % (host, "' '".join(cmd), e))
        return False

def encrypt(gpg_key, filename):
    logging.info("Encrypt %s" % filename)
    if simulate:
        return True
    try:
        sh.gpg2("-e", "-r", gpg_key, filename)
        os.unlink(filename)
    except:
        logging.error("Could not encrypt %s" % filename)
        traceback.print_exc()


def backup(host, path):
    logging.info("Backup of %s:/%s" % (host["host"], path))

    if path.endswith('/'):
        outfile = "%s/%s-%s-%s.tgz" % (
            destdir, date, host['host'], path.replace('/', '-'))
        ok = ssh(host, "tar", "cz", path, _out=outfile)
    else:
        outfile = "%s/%s-%s-%s" % (
            destdir, date, host['host'], path.replace('/', '-'),
        )
        ok = ssh(host, "cat", path, _out=outfile)

    if ok and not simulate:
        try:
            size = os.path.getsize(outfile)
            assert size > 0
            logging.info("%s -- %.2f MB" % (outfile, size / (1024 * 1024.0)))
        except Exception:
            logging.warning("FILE NOT CREATED")

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
    logging.info("BACKUP %s", h)
    host = h["host"]
    if '@' in host:
        host = host.split('@')[1]

    ok = True
    for pre in get_all(host, 'pre'):
        pre = shlex.split(pre)
        ok = ok and ssh(h, *pre)

    if not ok:
        logging.error("Do not perform backup for %s" % h)
    else:
        for path in get_all(host, 'paths'):
            outfile = backup(h, path)
            try:
                os.unlink("%s.gpg" % outfile)
            except Exception:
                pass
            gpg_key = h.get('gpg_key')
            if not gpg_key:
                gpg_key = BACKUP_PLAN["all"].get("gpg_key")
            if gpg_key:
                encrypt(gpg_key, outfile)

    # post always, as is cleanup
    for post in get_all(host, 'post'):
        post = shlex.split(post)
        ssh(h, *post)


def main():
    global simulate
    global destdir

    logging.info("---- STARTING NEW BACKUP ----")
    destdir = sys.argv[1]
    assert os.path.isdir(destdir), \
        "Need a backup directory file as first argument"

    if '--simulate' in sys.argv:
        sys.argv = [x for x in sys.argv if x != '--simulate']
        simulate = True

    if len(sys.argv) > 2:
        hosts = [parse_host_line(x) for x in sys.argv[2:]]
    else:
        hosts = read_hosts_file("hosts")

    for h in hosts:
        backup_host(h)


if __name__ == '__main__':
    main()
