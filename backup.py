#!/usr/bin/python3
import sh, sys, datetime, os, yaml, logging, shlex

logging.basicConfig(filename='backups.log',level=logging.INFO,format='%(levelname)s -- %(asctime)s -- %(message)s', datefmt='%Y-%m-%d %H:%M:%S')


def parse_ssh_options(host):
    ssh_opts=[host.get('host')]
    sudo=[]
    if host.get('ansible_become', 'no')=='yes':
        sudo=["sudo"]
    if host.get('ansible_ssh_user'):
        ssh_opts += ["-l", host.get('ansible_ssh_user')]
    if host.get('ssh_port'):
        ssh_opts += ["-p", host.get('ssh_port')]
    return (ssh_opts, sudo)

def backup(host, path, tofile):
    logging.info("Backup of %s:/%s"%(host["host"], path))

    ssh_opts, sudo = parse_ssh_options(host)

    try:
        sh.ssh(*ssh_opts, "--", *sudo, "tar cz", path, _out=tofile)
    except Exception as e:
        logging.error(e)
    try:
        size = os.path.getsize(tofile)
        assert size>0
        logging.info("%s -- %.2f MB"%(tofile, size/(1024*1024.0)))
    except:
        logging.warning("FILE NOT CREATED")

def parse_host_line(line):
    line=line.split()
    ret={"host":line[0]}
    for optval in line[1:]:
        opt,val=optval.split("=")
        ret[opt]=val
            

    return ret

def read_hosts_file(filename):
    ret = []
    for l in open(filename):
        l=l.strip()
        if not l or l.startswith('#') or l.startswith('['):
            continue
        ret.append(parse_host_line(l))
    return ret

BACKUP_PLAN = yaml.load(open('backup-plan.yaml'))
def get_all_backups(host):
    for i in BACKUP_PLAN.get("all",{}).get("paths",[]):
        yield i
    for i in BACKUP_PLAN.get(host,{}).get("paths",[]):
        yield i
def get_all_pres(host):
    for i in BACKUP_PLAN.get("all",{}).get("pre",[]):
        yield i
    for i in BACKUP_PLAN.get(host,{}).get("pre",[]):
        yield i


def main():
    logging.info("---- STARTING NEW BACKUP ----")

    if len(sys.argv)>1:
        hosts = [parse_host_line(x) for x in sys.argv[1:]]
    else:
        hosts = read_hosts_file("hosts")
    date = datetime.datetime.now().strftime("%Y%m%d")

    for h in hosts:
        logging.info("BACKUP %s", h)
        for pre in get_all_pres(h["host"]):
            logging.info("Run %s", pre)
            pre = shlex.split(pre)
            ssh, sudo = parse_ssh_options(h)
            try:
                sh.ssh(*ssh, "--", *sudo, *pre)
            except Exception as e:
                logging.error(e)
        for path in get_all_backups(h["host"]):
            outfile = "backups/%s-%s-%s.tgz"%(date, h['host'], path.replace('/','-'))
            backup(h, path, outfile) 
            try:
                os.unlink("%s.gpg"%outfile)
            except:
                pass
            logging.info("Encrypt %s"%outfile)
            sh.gpg2("-e","-r","BF996E91",outfile)
            try:
                os.unlink(outfile)
            except:
                pass


if __name__=='__main__':
    main()
