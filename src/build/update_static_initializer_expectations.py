#!src/build/run_python

# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Update src/build/dump-static-initializers-*-expected.txt files."""

import os
import subprocess
import sys

from src.build import build_common
from src.build import staging


def main(args):
  script = staging.as_staging(
      'android/external/chromium_org/tools/linux/dump-static-initializers.py')
  failure = 0
  arch = 'bare_metal_i686_opt'
  for library in build_common.CHECKED_LIBRARIES:
    temp = 'src/build/dump-static-initializers-%s-expected-temp.txt' % library
    out = 'src/build/dump-static-initializers-%s-expected.txt' % library
    lib = 'out/target/%s/lib/%s' % (arch, library)
    ret = subprocess.call(
        'python src/build/run_python %s -d %s > %s' % (script, lib, temp),
        shell=True)
    if ret:
      failure = 1
    else:
      # Remove the 'Found XXX static initializers' line. Also remove results
      # for .cpp (i.e. Android) files.
      subprocess.call(('egrep -ve \'^# (.*\.cpp |Found )\' < %s |' +
                       'sed -e \'s/ T\.[0-9]*/ T.XXXXX/\' > %s') %
                      (temp, out), shell=True)
    if os.path.exists(temp):
      os.remove(temp)

  if failure:
    print '\n\nError: Failed to update all expectations!\n\n'
  return failure


if __name__ == "__main__":
  sys.exit(main(sys.argv[1:]))
