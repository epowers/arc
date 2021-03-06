# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""This module provides a function to prepare unpacked CRXs.

When this script is invoked, it accepts the same options as those of
launch_chrome.py and prepares the files that would be needed to invoke
launch_chrome.py with the same options. This usage is intended mainly for
generating files which are needed to run Chrome remotely on a Chrome OS
device.
"""

import atexit
import json
import os
import pipes
import subprocess

from src.build import build_common
from src.build import launch_chrome_options
from src.build.build_options import OPTIONS
from src.build.metadata import manager
from src.build.util import file_util

_DOGFOOD_METADATA_PATH = 'third_party/examples/apk/dogfood.meta'


def _remove_ndk_libraries(apk_path):
  """Remove ndk libraries installed by previous launches.

  Package Manager installs shared libraries that match ABI but it doesn't
  remove them from previous installation.  If apk does not contain the library
  for current ABI, installer does not produce an error.  In this case
  application may launch successfully using previously installed library.  We
  want to see an error instead.
  """
  apk_name = os.path.splitext(os.path.basename(apk_path))[0]
  if apk_name:
    native_library_directory = os.path.join(build_common.get_arc_root(),
                                            build_common.get_android_root(),
                                            'data', 'app-lib',
                                            apk_name)
    file_util.rmtree(native_library_directory, ignore_errors=True)


def _generate_shell_command(parsed_args):
  shell_cmd = []
  if parsed_args.mode == 'atftest' and not parsed_args.run_test_as_app:
    target = '$instrument'
    if parsed_args.start_test_component:
      target = parsed_args.start_test_component
    shell_cmd.extend(['am', 'instrument'])
    # Set target test classes and packages.
    # Note that, the name may contain '$' character, so we need to escape them
    # here.
    if parsed_args.run_test_classes:
      shell_cmd.extend(
          ['-e', 'class', pipes.quote(parsed_args.run_test_classes)])
    if parsed_args.run_test_packages:
      shell_cmd.extend(
          ['-e', 'package', pipes.quote(parsed_args.run_test_packages)])
    if parsed_args.atf_gtest_list:
      shell_cmd.extend(
          ['-e', 'atf-gtest-list', pipes.quote(parsed_args.atf_gtest_list)])
    if parsed_args.atf_gtest_filter:
      shell_cmd.extend(
          ['-e', 'atf-gtest-filter',
           pipes.quote(parsed_args.atf_gtest_filter)])
    shell_cmd.extend(['-r', '-w', target, ';'])
    shell_cmd.extend(['stop', ';'])
  return shell_cmd


def _convert_launch_chrome_options_to_external_metadata(parsed_args):
  metadata = parsed_args.additional_metadata

  for definition in manager.get_metadata_definitions():
    value = getattr(parsed_args, definition.python_name, None)
    if value is not None:
      metadata[definition.name] = value

  if bool(parsed_args.jdb_port or parsed_args.gdb):
    metadata['disableChildPluginRetry'] = True
    metadata['disableHeartbeat'] = True
    metadata['sleepOnBlur'] = False

  if (parsed_args.mode == 'atftest' or parsed_args.mode == 'system' or
      OPTIONS.get_system_packages()):
    # An app may briefly go through empty stack while running
    # addAccounts() in account manager service.
    # TODO(igorc): Find a more precise detection mechanism to support GSF,
    # implement empty stack timeout, or add a flag if this case is more common.
    metadata['allowEmptyActivityStack'] = True

  command = _generate_shell_command(parsed_args)
  if command:
    metadata['shell'] = command

  metadata['isDebugCodeEnabled'] = OPTIONS.is_debug_code_enabled()

  return metadata


def _generate_apk_to_crx_args(parsed_args, metadata=None,
                              combined_metadata_file=None):
  crx_args = []
  crx_args.extend(parsed_args.apk_path_list)
  if parsed_args.verbose:
    crx_args.extend(['--verbose'])
  if parsed_args.use_test_app:
    crx_args.extend(['--use-test-app'])
  if parsed_args.use_all_play_services:
    crx_args.extend(['--use-all-play-services'])
  if parsed_args.obb_main:
    crx_args.extend(['--obb-main', parsed_args.obb_main])
  if parsed_args.obb_patch:
    crx_args.extend(['--obb-patch', parsed_args.obb_patch])
  if parsed_args.mode == 'system':
    crx_args.extend(['--system'])
  crx_args.extend(['--badging-check', 'suppress'])
  crx_args.extend(['--destructive'])
  if parsed_args.app_template:
    crx_args.extend(['--template', parsed_args.app_template])
  if metadata:
    with file_util.create_tempfile_deleted_at_exit() as metadata_file:
      json.dump(metadata, metadata_file)
    crx_args.extend(['--metadata', metadata_file.name])
  if combined_metadata_file:
    crx_args.extend(['--combined-metadata', combined_metadata_file])
  crx_args.extend(['-o', parsed_args.arc_data_dir])
  additional_permissions = []
  if parsed_args.additional_android_permissions:
    additional_permissions.extend(
        parsed_args.additional_android_permissions.split(','))
  # All Android apps now have an implicit INTERNET permission.
  additional_permissions.append('INTERNET')
  if additional_permissions:
    crx_args.extend(['--additional-android-permissions',
                     ','.join(additional_permissions)])
  return crx_args


def _build_crx(parsed_args):
  external_metadata = _convert_launch_chrome_options_to_external_metadata(
      parsed_args)
  apk_to_crx_args = _generate_apk_to_crx_args(
      parsed_args,
      metadata=external_metadata,
      combined_metadata_file=(
          _DOGFOOD_METADATA_PATH if parsed_args.dogfood_metadata else None))
  env = build_common.remove_arc_pythonpath(os.environ)
  env['ANDROID_HOME'] = 'third_party/android-sdk'

  # Return True on success, otherwise False.
  result = subprocess.call(
      ['python',
       os.path.join(build_common.get_tools_dir(), 'apk_to_crx.zip')] +
      apk_to_crx_args,
      env=env)
  return result == 0


def prepare_crx(parsed_args):
  for apk_path in parsed_args.apk_path_list:
    _remove_ndk_libraries(apk_path)
  if parsed_args.build_crx:
    if not _build_crx(parsed_args):
      return -1
  return 0


def prepare_crx_with_raw_args(args):
  parsed_args = launch_chrome_options.parse_args(args)
  return prepare_crx(parsed_args)


def update_shell_command(args):
  """Update the shell command of arc_metadata in the CRX manifest."""
  parsed_args = launch_chrome_options.parse_args(args)
  shell_command = _generate_shell_command(parsed_args)
  if not shell_command:
    return
  update_arc_metadata({'shell': shell_command},
                      args)


def update_arc_metadata(additional_metadata, args):
  """Update arc_metadata in the CRX manifest using additional_metadata."""
  parsed_args = launch_chrome_options.parse_args(args)
  manifest_path = os.path.join(parsed_args.arc_data_dir, 'manifest.json')
  with open(manifest_path) as f:
    manifest = json.load(f)
  arc_metadata = manifest['arc_metadata']
  arc_metadata.update(additional_metadata)
  with open(manifest_path, 'w') as f:
    json.dump(manifest, f,
              sort_keys=True, indent=2, separators=(',', ': '))


def remove_crx_at_exit_if_needed(parsed_args):
  """Remove the unpacked CRX directory at exit if needed.

  Here are major scenarios where this function is used and the CRX directory is
  removed at the end of the script.
  * When launch_chrome is invoked with --use-temporary-data-dirs, the CRX
    directory is removed.
  * run_integration_tests removes the CRX directory used for the tests by using
    this function at the finalize step.

  NOTE: When --nocrxbuild is specified for launch_chrome.py
  (i.e. parsed_args.build_crx == False), this means the CRX is not created on
  the fly at the beginning of launch_chrome.py but created in a different way
  (e.g created in the previous run, copied from a remote machine, and packaged
  manually by running apk_to_crx.py). In such cases, the CRX is considered as
  special one and preserved even if --use-temporary-data-dirs is specified.
  """
  def remove_arc_data_dir():
    if os.path.exists(parsed_args.arc_data_dir):
      file_util.rmtree_with_retries(parsed_args.arc_data_dir)
  if parsed_args.use_temporary_data_dirs and parsed_args.build_crx:
    atexit.register(remove_arc_data_dir)
