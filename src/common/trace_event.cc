// Copyright (c) 2013 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "common/trace_event.h"
#include "common/trace_event_ppapi.h"
#include "ppapi/c/dev/ppb_trace_event_dev.h"

#define TRACE_VALUE_TYPE_CONVERTABLE  (static_cast<unsigned char>(8))

namespace arc {
namespace trace {

namespace {
  const PPB_Trace_Event_Dev* g_trace_iface = NULL;
}

void Init(const PPB_Trace_Event_Dev* iface) {
  g_trace_iface = iface;
}

const unsigned char* GetCategoryEnabled(const char* category_name) {
  if (g_trace_iface) {
    // This casting is due to limitations in PPAPI. It is unable to return
    // a const pointer, and all pointer return types are necessarily void*.
    return reinterpret_cast<const unsigned char*>(
            g_trace_iface->GetCategoryEnabled(category_name));
  }
  // In case the interface is not enabled, return a valid non-enabled category
  // pointer.
  static const unsigned char dummy = 0;
  return &dummy;
}

// Checks if any trace value types are convertables, which are not
// handled by PPAPI trace.
// TODO(kmixter): Define a ConvertableToTraceFormat type and generate
// a string from any convertable objects.
static bool AreAnyTypesUnsupported(int num_args,
                                   const unsigned char* arg_types) {
  for (int i = 0; i < num_args; ++i) {
    if (arg_types[i] == TRACE_VALUE_TYPE_CONVERTABLE) {
      return true;
    }
  }
  return false;
}

void AddTraceEvent(char phase,
                  const unsigned char* category_enabled,
                  const char* name,
                  uint64_t id,
                  int num_args,
                  const char** arg_names,
                  const unsigned char* arg_types,
                  const uint64_t* arg_values,
                  unsigned char flags) {
  if (g_trace_iface) {
    if (AreAnyTypesUnsupported(num_args, arg_types)) {
      // Get rid of all arguments to avoid passing unsupported ones.
      num_args = 0;
    }
    // |category_enabled| has to be passed as (const void*) because PPAPI has no
    // concept of pointers of different types being used as parameters.
    g_trace_iface->AddTraceEvent(phase,
        reinterpret_cast<const void*>(category_enabled), name, id, num_args,
        arg_names, arg_types, arg_values, flags);
  }
}

void AddTraceEventWithThreadIdAndTimestamp(
    char phase,
    const unsigned char* category_enabled,
    const char* name,
    uint64_t id,
    int thread_id,
    uint64_t timestamp,
    int num_args,
    const char** arg_names,
    const unsigned char* arg_types,
    const uint64_t* arg_values,
    unsigned char flags) {
  if (g_trace_iface) {
    if (AreAnyTypesUnsupported(num_args, arg_types)) {
      // Get rid of all arguments to avoid passing unsupported ones.
      num_args = 0;
    }
    g_trace_iface->AddTraceEventWithThreadIdAndTimestamp(phase,
        reinterpret_cast<const void*>(category_enabled), name, id, thread_id,
        timestamp, num_args, arg_names, arg_types, arg_values, flags);
  }
}

void SetThreadName(const char* thread_name) {
  if (g_trace_iface)
    g_trace_iface->SetThreadName(thread_name);
}

}  // namespace trace
}  // namespace arc
