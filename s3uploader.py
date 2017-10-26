#!/usr/bin/env python

import gzip
import snappy
import uuid
import time
import subprocess
import pyinotify
import argparse
import re
import math
import os
import sys
import logging
import threading
from time import strftime
from datetime import datetime
from queue import Queue

log = logging.getLogger()
log.setLevel(logging.INFO)
ch = logging.StreamHandler(sys.stdout)
ch.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)
log.addHandler(ch)

parser = argparse.ArgumentParser()
parser.add_argument('--log-dir', '-d', action="store", help='Log dir to watch', default="/var/log/nginx")
parser.add_argument('--path-pattern', '-p', action="store", help='Log name pattern match', default='.*(.1.gz)$')
parser.add_argument('--aws-s3-bucket', '-b', action="store", help='AWS S3 bucket name', required=True)
parser.add_argument('--file-prefix', '-f', action="store", help='Add defined prefix to uploaded file name. If not defined then adding random(8) from UUID. Hostname can be added here', required=False)
parser.add_argument('--aws-access-key', '-a', action="store", help='AWS access key or from ENV AWS_ACCESS_KEY_ID')
parser.add_argument('--aws-secret-key', '-s', action="store", help='AWS secret key or from ENV AWS_SECRET_ACCESS_KEY')
parser.add_argument('--s3-storage-class', '-S', action="store", help='S3 storage class in AWS', default="REDUCED_REDUNDANCY")
parser.add_argument('--s3-app-dir', '-A', action="store", help='S3 in bucket dir name for this app', required=True)
parser.add_argument('--snzip-path', '-P', action="store", help='SNZIP binary location', required=False)
parser.add_argument('--tmp-compress', '-t', action="store", help='TMP dir for compressions', default="/tmp")
parser.add_argument('--compression', '-C', action="store", help='File compression/re-compression before S3 send', default="python-snappy", choices=['gzip', 'python-snappy', 'snzip-hadoop-snappy', 'snzip-framing-format', 'snzip-snappy-java', 'snzip-snappy-in-java', 'snzip-raw'])
parser.add_argument('--datetime-format', '-D', action="store", help='Datetime format to be used in S3 path', default="%Y/%m/%d/%H/%M")
args = parser.parse_args()

q = Queue()


class MyEventHandler(pyinotify.ProcessEvent):
    def process_IN_CREATE(self, event):
        parse_event(event.pathname)

    def process_IN_CLOSE_WRITE(self, event):
        parse_event(event.pathname)


def s3upload(pathname, bucketname, access_key, secret_key, dir_struc):
    environ = os.environ.copy()
    compress_start = time.time()
    log.info("Starting compression...")
    pathname = compress(pathname)
    compression_time = copy_time(time.time() - compress_start)
    keyname = os.path.basename(pathname)
    log.info("Compressed {0} in {1}".format(keyname, compression_time))
    start = time.time()
    destpath = "s3://{0}/{1}/{2}".format(bucketname, dir_struc, dstname(keyname))
    command = "/usr/local/bin/aws s3 cp --storage-class {storage_class} {source} {dest}".format(
              source=pathname,
              dest=destpath,
              storage_class=args.s3_storage_class
            )
    #log.info("Uploading file {0}".format(pathname))
    copy = subprocess.Popen(
            command,
            env=environ,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=True
            )
    log.debug("Running: {}".format(args))
    log.debug(copy.communicate())
    if copy.returncode == 0:
            log.info("Sending to {1} SUCCESS! {2} in {3}".format(pathname, destpath, file_size(pathname), copy_time(time.time() - start)))
            if os.path.isfile(pathname):
                  os.remove(pathname)
            if os.path.isfile(pathnoext(pathname)):
                  os.remove(pathnoext(pathname))
            error = False
    else:
            error = True
    if error:
        log.exception("Error sending file {}".format(pathname))
        sys.exit(1)


def in_bytes(size):
    for x in ['bytes', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024.0:
            return "%4.2f %s" % (size, x)
        size /= 1024.0


def copy_time(ctime):
    return "%4.4f %s" % (ctime, "sec")


def file_size(pathname):
    if os.path.isfile(pathname):
        fileinfo = os.stat(pathname)
        return in_bytes(fileinfo.st_size)

def parse_event(pathname):
    pattern = re.compile(args.path_pattern)
    pathmatch = pattern.match(pathname)
    s3choose(pathmatch, pathname)


def checkgzip(pathname):
    if pathname.endswith('.gz'):
           try:
             file = gzip.open(pathname, 'rb')
             return pathname
           except:
             return None
    elif gzip.open(pathname, 'rb'):
             return pathname
    else:
             return None


def ungzip_path(pathname, path_ungziped):
    pn_file = gzip.open(pathname, 'rb')
    pn_new = open(path_ungziped, 'wb')
    pn_new.writelines(pn_file)
    pn_new.close()
    return path_ungziped


def gzip_path(path, path_gziped):
    in_data = open(path, "rb").read()
    gzf = gzip.open(path_gziped, "wb")
    gzf.write(in_data)
    gzf.close()
    return path_gziped


def snappy_path(path, path_snappy):
    in_data = open(path, "rb")
    out_data = open(path_snappy, 'wb')
    snappy.stream_compress(in_data, out_data)
    out_data.close()
    in_data.close()
    return path_snappy


def snzip_snappy_path(path, path_snappy):
    if 'snzip-hadoop-snappy' in args.compression:
          snzip_compress_mode = "-t hadoop-snappy"
    elif 'snzip-framing-format' in args.compression:
          snzip_compress_mode = ""
    elif 'snzip-snappy-java' in args.compression:
          snzip_compress_mode = "-t snappy-java"
    elif 'snzip-snappy-in-java' in args.compression:
          snzip_compress_mode = "-t snappy-in-java"
    elif 'snzip-raw' in args.compression:
          snzip_compress_mode = "-t raw"
    environ = os.environ.copy()
    snzip_command = "{0} {1} -c {2}".format(
                  args.snzip_path,
                  snzip_compress_mode,
                  path
                )
    #log.info("snzip {0} to {1}".format(path,destpath))
    with open(path_snappy,"w+") as stdout:
      snzip_cps = subprocess.Popen(
                snzip_command,
                env=environ,
                stdout=stdout,
                stderr=subprocess.PIPE,
                shell=True
                )
      snzip_cps.wait()
    if snzip_cps.returncode == 0:
            return path_snappy
            error = False
    else:
            error = True
    if error:
        log.exception("Error compressing with snzip {}".format(path))
        sys.exit(1)


def pathnoext(pathname):
    return os.path.splitext(pathname)[0]


def tmpsubdir(tmpdir):
    return tmpdir + "/s3uploader_temp"


def compress(pathname):
    compress_start = time.time()
    tmp = args.tmp_compress
    tmpdir = tmpsubdir(tmp)
    if not os.path.exists(tmpdir):
           os.makedirs(tmpdir)
    pathname_noext = pathnoext(pathname)
    basename_noext = os.path.basename(pathname_noext)
    pnew = tmpdir + "/" + basename_noext
    pnew_gzip = pnew + ".gz"
    pnew_snappy = pnew + ".snappy"
    if args.compression == "gzip":
       if checkgzip(pathname):
          log.info("Not compressed {0}".format(pathname))
          return pathname
       else:
          log.info("Compressing {0} using gzip".format(pathname))
          return gzip_path(pnew, pnew_gziped)
    elif args.compression == "python-snappy":
       if checkgzip(pathname):
          pnongz = ungzip_path(pathname, pnew)
          log.info("Compressing {0} using snappy".format(pnongz))
          return snappy_path(pnongz, pnew_snappy)
       else:
          log.info("Compressing {0} using snappy".format(pathname))
          return snappy_path(pathname, pnew_snappy)
    elif 'snzip' in args.compression:
       if checkgzip(pathname):
          pnongz = ungzip_path(pathname, pnew)
          log.info("Compressing {0} using {1}".format(pnongz, args.compression))
          return snzip_snappy_path(pnongz, pnew_snappy)
       else:
          log.info("Compressing {0} using {1}".format(pathname, args.compression))
          return snzip_snappy_path(pathname, pnew_snappy)


def dstname(pathname):
    if args.file_prefix:
       prefix = args.file_prefix
    else:
       prefix = random_name(8)
    return prefix + "_" + pathname


def random_name(string_length=8):
    random = str(uuid.uuid4())
    random = random.replace("-", "")
    return random[0:string_length]


def datedir():
    appname = args.s3_app_dir
    datetime_format = args.datetime_format
    dirname = datetime.now().strftime(datetime_format)
    return appname + "/" + dirname


def worker():
    bucketname = args.aws_s3_bucket

    if args.aws_access_key:
        access_key = args.aws_access_key
    else:
        access_key = os.environ['AWS_ACCESS_KEY_ID']

    if args.aws_secret_key:
        secret_key = args.aws_secret_key
    else:
        secret_key = os.environ['AWS_SECRET_ACCESS_KEY']

    if not q.empty():
        item = q.get()
        dir_struc = datedir()
        s3upload(item, bucketname, access_key, secret_key, dir_struc)


def s3choose(parsedpath, pathname):
    if parsedpath:
        log.info("Path {0} matched adding to queue".format(pathname))
        q.put(pathname)
    else:
        log.debug("file not match - {0} - skipping sending to S3".format(pathname))


def main():

    if 'snzip' in args.compression:
       if not args.snzip_path:
                log.exception("Error install snzip binary and set snzip_path")
                sys.exit(1)

    wm = pyinotify.WatchManager()
    log.info("Watching {0} with pattern {1} ....".format(args.log_dir, args.path_pattern))

    notifier = pyinotify.Notifier(wm, MyEventHandler())
    ret = wm.add_watch(args.log_dir, pyinotify.IN_CLOSE_WRITE, rec=True)

    while True:
       try:
          notifier.process_events()
          if notifier.check_events():
             notifier.read_events()
             t = threading.Thread(target=worker)
             t.daemon = True
             t.start()
       except KeyboardInterrupt:
           notifier.stop()
           t.join()
           q.join()
           break

if __name__ == '__main__':
    main()
