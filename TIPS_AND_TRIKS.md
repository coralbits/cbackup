## How to give permissions to backup. **USE AT YOUR OWN RISK!**

Sometimes it is ok to use a normal account to access to everything to do the
backups, but it is possible to give access only to backup, and even allow
to do things with `root` privileges.

This trick needs several files, but should do the job.

Get you the SSH key that cbackup will use (`cat ~/.ssh/id_rsa.pub`), lets call
it SSH_KEY as it is quite long.

Add this line to `/var/backups/.ssh/authorized_keys`, create the file/path
if necesary:

```
command="/var/backups/runallowed.sh",no-port-forwarding,no-x11-forwarding,no-agent-forwarding ssh-rsa SSH_KEY root@ubuntu1404
```

at `/var/backups/runallowed.sh` paste this simple script:

```sh
#!/bin/sh

if [ "$( grep "$SSH_ORIGINAL_COMMAND" /var/backups/allowed_commands )" = "$SSH_ORIGINAL_COMMAND" ]; then
        $SSH_ORIGINAL_COMMAND
else
        logger "Attempted exec invalid command: $SSH_ORIGINAL_COMMAND"
        exit 1
fi
```

and at `/var/backups/allowed_commands` paste, one per line, the allowed commands
needed for the backup, for example:

```
pg_dump -Fc mydatabase
tar cz /homes/
```

These will be the commands as written at the `stdout` rules.

Finally you have to give the backup user permissions to do its duty. For example
grant read priileges on databases. Or at worst, add lines like these to
`/etc/sudoers.d/` files:

### How to use sudoers to allow backup commands

```
backup ALL= NOPASSWD: /var/backups/tarhomes.sh
```

And at the allowed commands use:

```sh
sudo /var/backups/tarhomes.sh
```

where `/var/backups/tarhomes.sh` does the appropiate stdout action.

Allowing to execute with sudo a command allows all possible arguments, so you
can not rely on them to limit the sudo actions.

## Postgres allow to perform pg_dump to backup user

In the pgsql console:

```sql
CREATE USER backup;
ALTER ROLE bakcup WITH LOGIN;
GRANT CONNECT ON DATABASE mydatabase TO backup;
GRANT SELECT ON ALL TABLES IN SCHEMA public to backup;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public to backup;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO backup;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON SEQUENCES TO backup;
```

The third line chooses which database is allowed. This asumes ident auth
enabled. If not check the `~/.pgpass` file.
