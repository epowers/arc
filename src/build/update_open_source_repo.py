#!src/build/run_python

# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import argparse
import logging
import os
import subprocess
import sys

from src.build import build_common
from src.build import open_source
from src.build import prepare_open_source_commit
from src.build.util import git

_OPEN_SOURCE_URL = 'https://chromium.googlesource.com/arc/arc'


def _update_submodules(dest):
  logging.info('Submodule update')
  subprocess.check_call(['git', 'submodule', 'sync'], cwd=dest)
  subprocess.check_call(['git', 'submodule', 'update', '--init', '--force'],
                        cwd=dest)


def _clone_repo_if_needed(dest):
  if not os.path.exists(dest):
    logging.info('Cloning open source repo to "%s"' % dest)
    subprocess.check_call(['git', 'clone', '--recursive', _OPEN_SOURCE_URL,
                           dest])


def _validate_local_repository(dest):
  if not git.is_git_dir(dest):
    sys.exit('directory "%s" is not a valid git repo' % dest)


def _check_out_matching_branch(dest, branch):
  # We have to update all the remotes to make sure we can find the remote branch
  # this checkout comes from.  On buildbots, only master and tags are fetched by
  # default.  We have to fetch tags in the destination repo explicitly too.
  subprocess.check_call(['git', 'remote', 'update'])
  subprocess.check_call(['git', 'remote', 'update'], cwd=dest)
  subprocess.check_call(['git', 'fetch', '--tags'], cwd=dest)
  if not git.has_remote_branch(branch, cwd=dest):
    sys.exit('Open source repository does not have the remote branch %s' %
             branch)
  logging.info('Checking out %s branch' % branch)
  # |branch| is the portion after the last slash, e.g., 'master', not
  # 'origin/master'.  There should be a local branch with the same name that
  # was created when the remote was updated with the new branch.
  subprocess.check_call(['git', 'checkout', branch], cwd=dest)
  subprocess.check_call(['git', 'pull'], cwd=dest)
  _update_submodules(dest)


def _test_changes(dest):
  logging.info('Testing changes in open source tree')
  configure_options_file = 'out/configure.options'

  # This script should run under src/build/run_python, so PYTHONPATH should
  # contain the paths to ARC repository. To avoid importing modules from
  # the ARC repository (rather than the created testee open-source repository)
  # accidentally, here remove ARC related paths from the PYTHONPATH.
  # Note that the PYTHONPATH for open source repo is set in
  # {dest}/src/build/run_python executed in the ./configure below.
  env = build_common.remove_arc_pythonpath(os.environ)
  with open(configure_options_file) as f:
    configure_args = f.read().split()
  subprocess.check_call(['./configure'] + configure_args, cwd=dest, env=env)
  subprocess.check_call(['ninja', 'all', '-j50'], cwd=dest)


def _set_git_user(name, email, dest):
  logging.info('Setting user "%s <%s>"' % (name, email))
  subprocess.check_call(['git', 'config', '--local', 'user.name', name],
                        cwd=dest)
  subprocess.check_call(['git', 'config', '--local', 'user.email', email],
                        cwd=dest)


def _commit_changes(dest, label):
  logging.info('Commiting changes to open source tree')
  subprocess.check_call(['git', 'add', '-A'], cwd=dest)
  subprocess.check_call(['git', 'commit', '--allow-empty', '-m',
                         'Updated to %s' % label],
                        cwd=dest)


def _sync_head_tags(dest, src):
  """Synchronize any tags currently pointing at HEAD to the open source repo,
     leaving any existing tags in place."""
  tags = subprocess.check_output(['git', 'tag', '--points-at', 'HEAD'], cwd=src)
  for tag in tags.splitlines():
    logging.warning('Updating tag %s' % tag)
    subprocess.call(['git', 'tag', '-a', '-m', tag, tag], cwd=dest)


def _push_changes(dest):
  logging.info('Pushing changes to open source remote repository')
  subprocess.check_call(['git', 'push'], cwd=dest)
  subprocess.check_call(['git', 'push', '--tags'], cwd=dest)


def _reset_and_clean_repo(dest):
  logging.info('Resetting local open source repository')
  subprocess.check_call(['git', 'reset', '--hard'], cwd=dest)
  subprocess.check_call(['git', 'submodule', 'foreach',
                         'git', 'reset', '--hard'], cwd=dest)
  logging.info('Clearing untracked files from repository')
  # -f -f is intentional, this will get rid of untracked modules left behind.
  subprocess.check_call(['git', 'clean', '-f', '-f', '-d'], cwd=dest)
  subprocess.check_call(['git', 'submodule', 'foreach',
                         'git', 'clean', '-f', '-f', '-d', '-x'], cwd=dest)


def _validate_args(args):
  if not args.branch:
    args.branch = git.get_remote_branch(git.get_last_landed_commit())


# Updates or clones from scratch the open source repository at the location
# provided on the command line.  The resultant repo is useful to pass into
# prepare_open_source_commit.py to then populate the repo with a current
# snapshot.
def main():
  assert not open_source.is_open_source_repo(), ('Cannot be run from open '
                                                 'source repo.')
  parser = argparse.ArgumentParser()
  parser.add_argument('--branch', default=None,
                      help='Which branch in the open source repo to push')
  parser.add_argument('--force', action='store_true',
                      help='Overwrite any changes in the destination')
  parser.add_argument('--push-changes', action='store_true',
                      help=('Push changes to the destination repository\'s '
                            'remote'))
  parser.add_argument('--verbose', '-v', action='store_true',
                      help='Get verbose output')
  parser.add_argument('dest')
  args = parser.parse_args(sys.argv[1:])
  if args.verbose:
    logging.getLogger().setLevel(logging.INFO)
  _validate_args(args)

  _clone_repo_if_needed(args.dest)
  _validate_local_repository(args.dest)
  if (git.get_uncommitted_files(cwd=args.dest) and not args.force):
    logging.error('%s has uncommitted files, use --force to override')
    return 1
  _reset_and_clean_repo(args.dest)
  _check_out_matching_branch(args.dest, args.branch)
  # Submodules abandoned between branches will still leave their directories
  # around which can confuse prepare_open_source_commit, so we clean them out.
  _reset_and_clean_repo(args.dest)

  prepare_open_source_commit.run(args.dest, args.force)

  _test_changes(args.dest)
  if args.push_changes:
    commit_label = subprocess.check_output(['git', 'describe']).strip()
    _set_git_user('arc-push', 'arc-push@chromium.org', args.dest)
    _commit_changes(args.dest, commit_label)
    _sync_head_tags(args.dest, '.')
    _push_changes(args.dest)
  else:
    _reset_and_clean_repo(args.dest)
  return 0


if __name__ == '__main__':
  sys.exit(main())
