# logrotate2s3
Python daemon s3 upload logs using inotify after logrotate

**Description**

Inotify on files create in specified logs dir. Then using some simple regex match files to upload to S3 defined bucket with logs backup. You can for example match all ^.*.1.gz after no delayed compress in logrotate and send instantly when it will be rotated to S3. This python is threaded and you can specify how many threads you like to run. All this options described in help by running s3uploader.py -h or --help

You need define you app log dir in bucket and all logs will be placed there with YYYY/MM/DD/HH/mm/ and all logs will be prefixed with 8 chars random from uuid to be sure that in this minute we have all logs uniq.

Using AWS cli on the bottom because it works and we don't need to reimplement this using Boto. There is multiple S3 upload with multipart implementations but there is always something wrong especially with bigger files like we have in rotated logs.

**Instalation**

Need some dependencies:

```
pip3 install pyinotify awscli python-snappy
```

If you like to use snzip snappy formats you need to install snzip binary https://github.com/kubo/snzip

Help:

```
python3 s3uploader.py -h
usage: s3uploader.py [-h] [--log-dir LOG_DIR] [--path-pattern PATH_PATTERN]
                     --aws-s3-bucket AWS_S3_BUCKET [--file-prefix FILE_PREFIX]
                     [--aws-access-key AWS_ACCESS_KEY]
                     [--aws-secret-key AWS_SECRET_KEY]
                     [--s3-storage-class S3_STORAGE_CLASS] --s3-app-dir
                     S3_APP_DIR [--snzip-path SNZIP_PATH]
                     [--tmp-compress TMP_COMPRESS]
                     [--compression {gzip,python-snappy,snzip-hadoop-snappy,snzip-framing-format,snzip-snappy-java,snzip-snappy-in-java,snzip-raw}]

optional arguments:
  -h, --help            show this help message and exit
  --log-dir LOG_DIR, -d LOG_DIR
                        Log dir to watch
  --path-pattern PATH_PATTERN, -p PATH_PATTERN
                        Log name pattern match
  --aws-s3-bucket AWS_S3_BUCKET, -b AWS_S3_BUCKET
                        AWS S3 bucket name
  --file-prefix FILE_PREFIX, -f FILE_PREFIX
                        Add defined prefix to uploaded file name. If not
                        defined then adding random(8) from UUID. Hostname can
                        be added here
  --aws-access-key AWS_ACCESS_KEY, -a AWS_ACCESS_KEY
                        AWS access key or from ENV AWS_ACCESS_KEY_ID
  --aws-secret-key AWS_SECRET_KEY, -s AWS_SECRET_KEY
                        AWS secret key or from ENV AWS_SECRET_ACCESS_KEY
  --s3-storage-class S3_STORAGE_CLASS, -S S3_STORAGE_CLASS
                        S3 storage class in AWS
  --s3-app-dir S3_APP_DIR, -A S3_APP_DIR
                        S3 in bucket dir name for this app
  --snzip-path SNZIP_PATH, -P SNZIP_PATH
                        SNZIP binary location
  --tmp-compress TMP_COMPRESS, -t TMP_COMPRESS
                        TMP dir for compressions
  --compression {gzip,python-snappy,snzip-hadoop-snappy,snzip-framing-format,snzip-snappy-java,snzip-snappy-in-java,snzip-raw}, -C {gzip,python-snappy,snzip-hadoop-snappy,snzip-framing-format,snzip-snappy-java,snzip-snappy-in-java,snzip-raw}
                        File compression/re-compression before S3 send
```

Usage example:
Export AWS credentials in ENV

```
export AWS_ACCESS_KEY_ID="<s3uploader_aws_key>"
export AWS_SECRET_ACCESS_KEY="<s3uploader_aws_secret>"
```

Now run s3uploader (default compression is python-snappy but you can look in https://github.com/kubo/snzip for more snappy in snzip)

```
python3 s3uploader.py --log-dir /var/log/nginx/ -p '.*(.1.gz)$' -b my-logs-bucket -A nginx
```

All this can be run from supervisord:

For nginx logs from nginx or syslog handled.

```
[program:s3uploader-nginx]
environment =
    AWS_ACCESS_KEY_ID=<s3uploader_aws_key>,
    AWS_SECRET_ACCESS_KEY=<s3uploader_aws_secret>
command=python3 /usr/bin/local/s3uploader.py --log-dir /var/log/nginx/ -p '.*(.1.gz)$' -b my-logs-bucket -A nginx -C gzip -t /var/log/ -f %(ENV_HOSTNAME)s
process_name=%(program_name)s
numprocs=1
directory=/tmp
umask=022
priority=99
autostart=true
autorestart=true
startsecs=1
startretries=99
exitcodes=0,2
stopsignal=TERM
stopwaitsecs=1
user=www-data
redirect_stderr=true
stderr_logfile=/var/log/s3uploader/error.log
stderr_logfile_maxbytes=25MB
stderr_logfile_backups=10
stderr_capture_maxbytes=1MB
stdout_logfile=/var/log/s3uploader/s3uploader.log
stdout_logfile_maxbytes=25MB
stdout_logfile_backups=10
stdout_capture_maxbytes=1MB
```
For os logs filtering.

```
[program:s3uploader-os]
environment =
    AWS_ACCESS_KEY_ID=<s3uploader_aws_key>,
    AWS_SECRET_ACCESS_KEY=<s3uploader_aws_secret>
command=python3 /usr/local/bin/s3uploader.py --log-dir /var/log/ -p '.*(syslog.1|kern.log.1|auth.log.1)$' -b my-logs-bucket -A system-logs -C gzip -t /var/log/ -f %(ENV_HOSTNAME)s
process_name=%(program_name)s
numprocs=1
directory=/tmp
umask=022
priority=99
autostart=true
autorestart=true
startsecs=1
startretries=99
exitcodes=0,2
stopsignal=TERM
stopwaitsecs=1
user=www-data
redirect_stderr=true
stderr_logfile=/var/log/s3uploader/error.log
stderr_logfile_maxbytes=25MB
stderr_logfile_backups=10
stderr_capture_maxbytes=1MB
stdout_logfile=/var/log/s3uploader/s3uploader.log
stdout_logfile_maxbytes=25MB
stdout_logfile_backups=10
stdout_capture_maxbytes=1MB
```

**Performance**

On AWS c3.large (eu-west-1 and bucket in US standard) and default 3 threads i was able to transfer 10 logs (almost 800MB in total) in 45seconds.


** simple .deb package build **
```
fpm -s dir -t deb -n s3uploader -v 0.0.1 s3uploader=/usr/local/bin/
```
