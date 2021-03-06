#!src/build/run_python
#
# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Generates a C++ file used for constructing a NaClManifestFileHandler object.

Example:
...
const posix_translation::NaClManifestEntry kRuntimeFiles[67] = {
 // { name, mode, size, mtime }
 { "/system/lib/libc.so", 0100755, 2054063, 1393551434 },
 { "/system/lib/libc_malloc_debug_leak.so", 0100755, 185355, 1393551434 },
...
"""

import argparse
import os
import re
import stat
import string
import sys


def _get_metadata(filename):
  try:
    st = os.stat(filename)
    if st.st_mode & stat.S_IXUSR:
      mode = stat.S_IFREG | 0755
    else:
      mode = stat.S_IFREG | 0644
    size = st.st_size
    mtime = st.st_mtime
  except OSError, e:
    sys.exit(e)
  return mode, size, mtime


def _write_file(output_filename, namespace, variable_name,
                content, num_elements):
  with open(output_filename, 'w') as f:
    include_guard = re.sub(r'[^A-Za-z0-9]', '_', output_filename).upper()
    # A symbol starting with _[A-Z] is reserved by the compiler.
    include_guard = re.sub(r'^_([A-Z])', r'\1', include_guard)
    include_guard = re.sub(r'^[0-9]+', '', include_guard)
    cc_file = string.Template(
        """// Generated by create_runtime_file_list.py. DO NOT EDIT.

#include "posix_translation/nacl_manifest_file.h"

namespace ${namespace} {

extern const posix_translation::NaClManifestEntry
${variable_name}[${length}] = {
  // { name, mode, size, mtime }
${content}};
extern const size_t ${variable_name}Len = ${length};

}  // namespace ${namespace}
""")
    f.write(cc_file.substitute(dict(namespace=namespace,
                                    variable_name=variable_name,
                                    content=content,
                                    length=num_elements)))


def _generate_runtime_file_list(input_filenames, src_dir, dest_dir,
                                namespace, variable_name, output_filename):
  content = ''
  num_files = len(input_filenames)
  for i in xrange(num_files):
    filename = input_filenames[i]
    if filename.endswith('/'):
      print '%s should not end with /' % filename
      sys.exit(1)
    mode, size, mtime = _get_metadata(filename)
    if filename.startswith(src_dir):
      filename = filename.replace(src_dir, dest_dir, 1)
    else:
      filename = os.path.join(dest_dir, os.path.basename(filename))
    content += '  { "%s", 0%o, %d, %d },\n' % (
        filename, mode, size, mtime)
  _write_file(output_filename, namespace, variable_name, content, num_files)


def main(args):
  parser = argparse.ArgumentParser()
  parser.add_argument('-o', '--output', metavar='FILE', required=True,
                      help='Write the output to filename.')
  parser.add_argument('-s', '--src-dir', metavar='SRC_DIR', required=True,
                      help='A directory name to be replaced with --dest-dir.')
  parser.add_argument('-d', '--dest-dir', metavar='DEST_DIR', required=True,
                      help='A directory name which replaces --src-dir.')
  parser.add_argument('-n', '--namespace', metavar='NAMESPACE', required=True,
                      help='A namespace for the generated file.')
  parser.add_argument('-v', '--variable-name', metavar='VARIABLE_NAME',
                      required=True,
                      help='A variable name for the generated file.')
  parser.add_argument(dest='input', metavar='INPUT', nargs='+',
                      help='Input file(s) to process.')
  args = parser.parse_args()

  _generate_runtime_file_list(args.input, args.src_dir, args.dest_dir,
                              args.namespace, args.variable_name, args.output)
  return 0


if __name__ == '__main__':
  sys.exit(main(sys.argv[1:]))
