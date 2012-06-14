#!/usr/bin/python

import os, sys, zipfile, re, urlparse

log_re = re.compile(r'(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2})\s+(\w+)\s+(\w+)\s+((([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.){3}([0-9]|[1-9][0-9]|1[0-9?]{2}|2[0-4][0-9]|25[0-5]))\s+(\w+)\s+([^\s]+)\s+([^\s]+)\s+\d+\s+-\s+((([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.){3}([0-9]|[1-9][0-9]|1[0-9?]{2}|2[0-4][0-9]|25[0-5]))\s+([^\s]+)\s+([^\s]+)\s+-\s+-\s+([\w.]+)\s+\d+\s\d+\s\d+\s\d+\s\d+\s\d+')

def process_log(log):
  for line in log.split('\n'):
    m = log_re.match(line.strip())
    if m:
      access_date = m.group(1)
      access_time = m.group(2)
      source_ip_addr = m.group(12)
      ping_url = m.group(10).find('Ping')
      if ping_url and ping_url > 0:
        # First version of ping script had a mistake of using '?' instead of '&'
        # Patch it up before parsing
        query_string = m.group(11).replace('?', '&')
        criterias = urlparse.parse_qs(query_string)
        if criterias.has_key('timestamp') and criterias.has_key('uuid'):
          timestamp = criterias['timestamp'][0]
          print "%s\t%s\t%s-%s-%s" % (source_ip_addr, criterias['uuid'][0], timestamp[0:4], timestamp[4:6], timestamp[6:])
          pass
        pass
      pass
    pass
  pass


def usage(cmd):
  print "%s [log-file]" % cmd
  pass

if __name__ == "__main__":
  if len(sys.argv) < 2:
    usage(os.path.basename(sys.argv[0]))
    sys.exit(1)
    pass
  source_file = sys.argv[1]
  basename = ""
  ext = ""
  try:
    basename, ext = os.path.splitext(source_file)
  except:
    pass
  if ext == ".zip":
    logs = zipfile.ZipFile(sys.argv[1])
    for name in logs.namelist():
      log = logs.read(name)
      process_log(log)
      pass
    pass
  else:
    logs = open(source_file)
    log = logs.read()
    process_log(log)
    pass
  pass
