# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for prep_launch_chrome."""

import unittest

from src.build import launch_chrome_options
from src.build import prep_launch_chrome
from src.build.build_options import OPTIONS


class PrepLaunchChromeTest(unittest.TestCase):

  def setUp(self):
    OPTIONS.parse([])

  def metadata_from_command_line(self, command):
    args = launch_chrome_options.parse_args(command.split(' '))
    metadata = (prep_launch_chrome.
                _convert_launch_chrome_options_to_external_metadata(args))
    del metadata['isDebugCodeEnabled']
    return metadata

  def test_command_line_flags_to_external_metadata(self):
    metadata = self.metadata_from_command_line('./launch_chrome.py run -D')
    self.assertDictEqual(metadata, {})

    metadata = self.metadata_from_command_line('./launch_chrome.py run -D '
                                               '--enable-arc-strace')
    self.assertDictEqual(metadata, {'enableArcStrace': True})

    metadata = self.metadata_from_command_line('./launch_chrome.py run')
    self.assertEqual(metadata['stderrLog'], 'W')

    metadata = self.metadata_from_command_line('./launch_chrome.py perftest '
                                               '--remote 127.0.0.1 '
                                               '--remote-host-type=chromeos')
    self.assertIn('minimumLaunchDelay', metadata)

    metadata = self.metadata_from_command_line('./launch_chrome.py run '
                                               '--orientation=landscape '
                                               '--enable-external-directory')
    self.assertEquals(metadata['orientation'], 'landscape')
    self.assertEquals(metadata['enableExternalDirectory'], True)


if __name__ == '__main__':
  unittest.main()
