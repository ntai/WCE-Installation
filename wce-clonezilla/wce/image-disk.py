#!/usr/bin/env python
import os, sys, subprocess
command = [ "/wce.py", "--image-disk"]
command += sys.argv[1:]
subprocess.call(command)
