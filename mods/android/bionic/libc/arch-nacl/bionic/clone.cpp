// Copyright (C) 2014 The Android Open Source Project
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//      http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.
//
// Defines __nacl_clone, which creates a new thread.
//

#include <errno.h>
#include <pthread.h>
#include <stdlib.h>

#include "nacl_signals.h"
#include "private/bionic_tls.h"
#include <irt_syscalls.h>

// We use these slots to pass the thread function and its argument as
// these slots are not used during the initialization of threads.
#define TLS_SLOT_THREAD_FUNC TLS_SLOT_OPENGL_API
#define TLS_SLOT_THREAD_ARGS TLS_SLOT_OPENGL

extern "C" void __start_thread(int (*fn)(void*), void* arg);

// The entry point of new threads.
static void run_thread() {
  void **tls = (void **)__nacl_irt_tls_get();
  int (*fn)(void *) = (int (*)(void *))tls[TLS_SLOT_THREAD_FUNC];
  void *arg = tls[TLS_SLOT_THREAD_ARGS];
  tls[TLS_SLOT_THREAD_FUNC] = tls[TLS_SLOT_THREAD_ARGS] = NULL;
  __start_thread(fn, arg);
}

#if !defined(BARE_METAL_BIONIC)
pid_t __allocate_tid();
#endif

extern "C" __LIBC_HIDDEN__ pid_t __nacl_clone(int (*fn)(void*),
                                              void* ignored_child_stack,
                                              uint32_t flags,
                                              void* arg,
                                              int* parent_tid,
                                              void** tls,
                                              int* child_tid) {
  int tid;
#if !defined(BARE_METAL_BIONIC)
  tid = __allocate_tid();
  if (tid < 0) {
    errno = ENOMEM;
    return -1;
  }
#endif

  // The stack will be put before TLS.
  // See the comment of pthread_create in
  // libc/bionic/pthread_create.cpp for detail.
  void **child_stack = (void **)(((uintptr_t)tls & ~15));

  // Pass |fn| and |arg| using TLS.
  tls[TLS_SLOT_THREAD_FUNC] = (void*)fn;
  tls[TLS_SLOT_THREAD_ARGS] = (void*)arg;
#if defined(BARE_METAL_BIONIC)
  nacl_irt_tid_t assigned_tid;
  int result = __nacl_irt_thread_create_v0_2(&run_thread, child_stack, tls,
                                             &assigned_tid);
  if (result == 0) {
    // Set the child thread's signal mask. This should not be racy since
    // pthread_create sets a mutex that blocks the child thread from continuing
    // until it is fully initialized.
    __nacl_signal_thread_init(assigned_tid);
    tid = assigned_tid;
  }
#else
  int result = __nacl_irt_thread_create(&run_thread, child_stack, tls);
#endif
  if (result != 0) {
    errno = result;
    return -1;
  }
  if (flags & CLONE_PARENT_SETTID)
    *parent_tid = tid;
  return tid;
}
