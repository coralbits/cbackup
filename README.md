# Coralbits Backup

Simple backup solution.

It has only three backup options:
 1. Backup a directory
 2. Backup stdout
 3. Run pre and post commands

Over this it can encrypt the backups, with no unencrypted data ever written
locally. So can backup directly to S3 (via https://github.com/kahing/goofys for
example).

It has no knowledge of which file is where, nor tapes nor other backup
specialized areas. It is just a simple backup.

## Use example

Create a yaml file with your backup plan at `backup-plan.yaml`:

```yaml
localhost:
  gpg_key: mygpgkeyid
  paths:
    - /home/
```

This plan means just to connect via SSH to localhost, and do a tar.gz of
`/home/`. Directories end in `/`, files do not.

To execute run:

```
./cbackup.py /var/backups/
```

By default it will use the `backup-plan.yaml` file, but can be overriden with
the `--plan` option.

If you want an incremental backup, you can add `-i` for changes since yesterday,
same time, or `--since [days]` to get all changes since that many days ago.

The files will be a concatenation of the date, hostname, and the path.

More examples in the `example.yaml` file.

## Options

```
$ ./cbackup.py
backup.py -- Simple backups -- v0.1

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
```

## Recover

Thats on you. Its is just a simple `tar.gz.gpg`.

## Roadmap

I really want to keep it simple, but these features would be cool to have:

* `[host].host` to be able to do backups on other host, not the name of the
  backup.

# Thats all!
