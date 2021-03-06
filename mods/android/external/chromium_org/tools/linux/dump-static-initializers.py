#!/usr/bin/env python
# Copyright (c) 2012 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Dump functions called by static intializers in a Linux Release binary.

Usage example:
  tools/linux/dump-static-intializers.py out/Release/chrome

A brief overview of static initialization:
1) the compiler writes out, per object file, a function that contains
   the static intializers for that file.
2) the compiler also writes out a pointer to that function in a special
   section.
3) at link time, the linker concatenates the function pointer sections
   into a single list of all initializers.
4) at run time, on startup the binary runs all function pointers.

The functions in (1) all have mangled names of the form
  _GLOBAL__I_foobar.cc
using objdump, we can disassemble those functions and dump all symbols that
they reference.
"""

import optparse
# ARC MOD BEGIN
# Import os module for added code.
import os
# ARC MOD END
import re
import subprocess
import sys
# ARC MOD BEGIN
# Use NaCl version of objdump since /usr/bin/objdump does not recognize
# all plt entries in the binary and using /usr/bin/objdump ends up with
# a corrupted result. Note this script is only for -t=nx.
from src.build import build_options
from src.build import toolchain

build_options.OPTIONS.parse_configure_file()
_BINUTILS_PREFIX = '%s/x86_64-nacl-' % toolchain.get_nacl_toolchain_path()
# ARC MOD END

# A map of symbol => informative text about it.
NOTES = {
  '__cxa_atexit@plt': 'registers a dtor to run at exit',
  'std::__ioinit': '#includes <iostream>, use <ostream> instead',
}

# Determine whether this is a git checkout (as opposed to e.g. svn).
IS_GIT_WORKSPACE = (subprocess.Popen(
    ['git', 'rev-parse'], stderr=subprocess.PIPE).wait() == 0)

class Demangler(object):
  """A wrapper around c++filt to provide a function to demangle symbols."""
  def __init__(self):
    # ARC MOD BEGIN
    # Use _BINUTILS_PREFIX.
    self.cppfilt = subprocess.Popen(['%sc++filt' % _BINUTILS_PREFIX],
    # ARC MOD END
                                    stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE)

  def Demangle(self, sym):
    """Given mangled symbol |sym|, return its demangled form."""
    self.cppfilt.stdin.write(sym + '\n')
    return self.cppfilt.stdout.readline().strip()

# Matches for example: "cert_logger.pb.cc", capturing "cert_logger".
protobuf_filename_re = re.compile(r'(.*)\.pb\.cc$')
def QualifyFilenameAsProto(filename):
  """Attempt to qualify a bare |filename| with a src-relative path, assuming it
  is a protoc-generated file.  If a single match is found, it is returned.
  Otherwise the original filename is returned."""
  if not IS_GIT_WORKSPACE:
    return filename
  match = protobuf_filename_re.match(filename)
  if not match:
    return filename
  basename = match.groups(0)
  gitlsfiles = subprocess.Popen(
    ['git', 'ls-files', '--', '*/%s.proto' % basename],
    stdout=subprocess.PIPE)
  candidate = filename
  for line in gitlsfiles.stdout:
    if candidate != filename:
      return filename # Multiple hits, can't help.
    candidate = line.strip()
  return candidate

# Regex matching the substring of a symbol's demangled text representation most
# likely to appear in a source file.
# Example: "v8::internal::Builtins::InitBuiltinFunctionTable()" becomes
# "InitBuiltinFunctionTable", since the first (optional & non-capturing) group
# picks up any ::-qualification and the last fragment picks up a suffix that
# starts with an opener.
symbol_code_name_re = re.compile(r'^(?:[^(<[]*::)?([^:(<[]*).*?$')
def QualifyFilename(filename, symbol):
  """Given a bare filename and a symbol that occurs in it, attempt to qualify
  it with a src-relative path.  If more than one file matches, return the
  original filename."""
  if not IS_GIT_WORKSPACE:
    return filename
  match = symbol_code_name_re.match(symbol)
  if not match:
    return filename
  symbol = match.group(1)
  gitgrep = subprocess.Popen(
    ['git', 'grep', '-l', symbol, '--', '*/%s' % filename],
    stdout=subprocess.PIPE)
  candidate = filename
  for line in gitgrep.stdout:
    if candidate != filename:  # More than one candidate; return bare filename.
      return filename
    candidate = line.strip()
  return candidate

# Regex matching nm output for the symbols we're interested in.
# See test_ParseNmLine for examples.
nm_re = re.compile(r'(\S+) (\S+) t (?:_ZN12)?_GLOBAL__(?:sub_)?I_(.*)')
def ParseNmLine(line):
  """Given a line of nm output, parse static initializers as a
  (file, start, size) tuple."""
  match = nm_re.match(line)
  if match:
    addr, size, filename = match.groups()
    return (filename, int(addr, 16), int(size, 16))


def test_ParseNmLine():
  """Verify the nm_re regex matches some sample lines."""
  parse = ParseNmLine(
    '0000000001919920 0000000000000008 t '
    '_ZN12_GLOBAL__I_safe_browsing_service.cc')
  assert parse == ('safe_browsing_service.cc', 26319136, 8), parse

  parse = ParseNmLine(
    '00000000026b9eb0 0000000000000024 t '
    '_GLOBAL__sub_I_extension_specifics.pb.cc')
  assert parse == ('extension_specifics.pb.cc', 40607408, 36), parse

# Just always run the test; it is fast enough.
test_ParseNmLine()


def ParseNm(binary):
  """Given a binary, yield static initializers as (file, start, size) tuples."""
  # ARC MOD BEGIN
  # Use _BINUTILS_PREFIX.
  nm = subprocess.Popen(['%snm' % _BINUTILS_PREFIX, '-S', binary], stdout=subprocess.PIPE)
  # ARC MOD END
  for line in nm.stdout:
    parse = ParseNmLine(line)
    if parse:
      # ARC MOD BEGIN UPSTREAM chromium-dump-static-initializers-clang
      # Handle symbols generated by clang.
      filename, addr, size = parse
      # Clang does not use a filename as a part of a symbol name of a
      # static initializer. It uses 'a' instead. For such symbols, we
      # use addr2line to get the filename.
      if filename == 'a':
        line_info = subprocess.check_output(
            ['addr2line', '-e', binary, '0x%x' % addr])
        # The output of addr2line is <filename>:<line number>.
        filename, line = line_info.split(':')
        filename = os.path.basename(filename)
        parse = (filename, addr, size)
      # ARC MOD END UPSTREAM
      yield parse

# Regex matching objdump output for the symbols we're interested in.
# Example line:
#     12354ab:  (disassembly, including <FunctionReference>)
disassembly_re = re.compile(r'^\s+[0-9a-f]+:.*<(\S+)>')
def ExtractSymbolReferences(binary, start, end):
  """Given a span of addresses, returns symbol references from disassembly."""
  # ARC MOD BEGIN
  # Use _BINUTILS_PREFIX.
  cmd = ['%sobjdump' % _BINUTILS_PREFIX, binary, '--disassemble',
  # ARC MOD END
         '--start-address=0x%x' % start, '--stop-address=0x%x' % end]
  objdump = subprocess.Popen(cmd, stdout=subprocess.PIPE)

  refs = set()
  for line in objdump.stdout:
    if '__static_initialization_and_destruction' in line:
      raise RuntimeError, ('code mentions '
                           '__static_initialization_and_destruction; '
                           'did you accidentally run this on a Debug binary?')
    match = disassembly_re.search(line)
    if match:
      (ref,) = match.groups()
      if ref.startswith('.LC') or ref.startswith('_DYNAMIC'):
        # Ignore these, they are uninformative.
        continue
      if ref.startswith('_GLOBAL__I_'):
        # Probably a relative jump within this function.
        continue
      refs.add(ref)

  return sorted(refs)

def main():
  parser = optparse.OptionParser(usage='%prog [option] filename')
  parser.add_option('-d', '--diffable', dest='diffable',
                    action='store_true', default=False,
                    help='Prints the filename on each line, for more easily '
                         'diff-able output. (Used by sizes.py)')
  opts, args = parser.parse_args()
  if len(args) != 1:
    parser.error('missing filename argument')
    return 1
  binary = args[0]

  demangler = Demangler()
  file_count = 0
  initializer_count = 0

  files = ParseNm(binary)
  if opts.diffable:
    files = sorted(files)
  for filename, addr, size in files:
    file_count += 1
    ref_output = []

    qualified_filename = QualifyFilenameAsProto(filename)

    if size == 2:
      # gcc generates a two-byte 'repz retq' initializer when there is a
      # ctor even when the ctor is empty.  This is fixed in gcc 4.6, but
      # Android uses gcc 4.4.
      ref_output.append('[empty ctor, but it still has cost on gcc <4.6]')
    else:
      for ref in ExtractSymbolReferences(binary, addr, addr+size):
        initializer_count += 1

        ref = demangler.Demangle(ref)
        if qualified_filename == filename:
          qualified_filename = QualifyFilename(filename, ref)

        note = ''
        if ref in NOTES:
          note = NOTES[ref]
        elif ref.endswith('_2eproto()'):
          note = 'protocol compiler bug: crbug.com/105626'

        if note:
          ref_output.append('%s [%s]' % (ref, note))
        else:
          ref_output.append(ref)

    if opts.diffable:
      if ref_output:
        print '\n'.join('# ' + qualified_filename + ' ' + r for r in ref_output)
      else:
        print '# %s: (empty initializer list)' % qualified_filename
    else:
      print '%s (initializer offset 0x%x size 0x%x)' % (qualified_filename,
                                                        addr, size)
      print ''.join('  %s\n' % r for r in ref_output)

  if opts.diffable:
    print '#',
  print 'Found %d static initializers in %d files.' % (initializer_count,
                                                       file_count)

  return 0

if '__main__' == __name__:
  sys.exit(main())
