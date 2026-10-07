"""Internal Windows process identity and owned Job Objects; no CLI or project discovery.

Inputs are a PID or the controller's live Popen handle. Outputs are tri-state
identity observations and confirmed job termination. Windows API/access failures
stay unknown and refuse release. Uses ctypes only; no new runtime dependency.
The job contains a process tree, not its filesystem/network authority.
"""
import ctypes
from ctypes import wintypes
import os
import time


class ProcessBackendError(ValueError):
    pass


def kernel():
    if os.name != 'nt':
        raise ProcessBackendError('Windows process backend is unavailable on this platform')
    api = ctypes.WinDLL('kernel32', use_last_error=True)
    declarations = {
        'OpenProcess': ([wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
        'CloseHandle': ([wintypes.HANDLE], wintypes.BOOL),
        'WaitForSingleObject': ([wintypes.HANDLE, wintypes.DWORD], wintypes.DWORD),
        'GetProcessTimes': ([wintypes.HANDLE, ctypes.POINTER(wintypes.FILETIME), ctypes.POINTER(wintypes.FILETIME),
                             ctypes.POINTER(wintypes.FILETIME), ctypes.POINTER(wintypes.FILETIME)], wintypes.BOOL),
        'CreateJobObjectW': ([ctypes.c_void_p, wintypes.LPCWSTR], wintypes.HANDLE),
        'SetInformationJobObject': ([wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD], wintypes.BOOL),
        'AssignProcessToJobObject': ([wintypes.HANDLE, wintypes.HANDLE], wintypes.BOOL),
        'QueryInformationJobObject': ([wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
                                      ctypes.POINTER(wintypes.DWORD)], wintypes.BOOL),
        'TerminateJobObject': ([wintypes.HANDLE, wintypes.UINT], wintypes.BOOL),
    }
    for name, (arguments, result) in declarations.items():
        function = getattr(api, name); function.argtypes = arguments; function.restype = result
    return api


def observe(pid):
    """The process handle's creation FILETIME prevents a reused PID matching an old receipt."""
    if type(pid) is not int or not 0 < pid <= 0xffffffff:
        return 'unknown', 'invalid Windows process identifier'
    api = kernel()
    handle = api.OpenProcess(0x1000 | 0x100000, False, pid)  # QUERY_LIMITED_INFORMATION | SYNCHRONIZE
    if not handle:
        error = ctypes.get_last_error()
        return ('absent', None) if error in (87, 1168) else ('unknown', 'Windows process access refused (%d)' % error)
    try:
        state = api.WaitForSingleObject(handle, 0)
        if state == 0:
            return 'absent', None
        if state != 258:
            return 'unknown', 'Windows process state could not be observed'
        created, exited, used_kernel, used_user = (wintypes.FILETIME() for _ in range(4))
        if not api.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(exited),
                                   ctypes.byref(used_kernel), ctypes.byref(used_user)):
            return 'unknown', 'Windows creation time could not be observed'
        if api.WaitForSingleObject(handle, 0) == 0:
            return 'absent', None
        return 'present', 'windows-filetime:%d' % ((created.dwHighDateTime << 32) | created.dwLowDateTime)
    finally:
        api.CloseHandle(handle)


class BasicLimits(ctypes.Structure):
    _fields_ = [('process_time', ctypes.c_longlong), ('job_time', ctypes.c_longlong),
                ('flags', wintypes.DWORD), ('min_working_set', ctypes.c_size_t),
                ('max_working_set', ctypes.c_size_t), ('active_limit', wintypes.DWORD),
                ('affinity', ctypes.c_size_t), ('priority', wintypes.DWORD), ('scheduling', wintypes.DWORD)]


class IOCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_ulonglong) for name in
                ('read_count', 'write_count', 'other_count', 'read_bytes', 'write_bytes', 'other_bytes')]


class ExtendedLimits(ctypes.Structure):
    _fields_ = [('basic', BasicLimits), ('io', IOCounters), ('process_memory', ctypes.c_size_t),
                ('job_memory', ctypes.c_size_t), ('peak_process_memory', ctypes.c_size_t), ('peak_job_memory', ctypes.c_size_t)]


class Accounting(ctypes.Structure):
    _fields_ = [(name, ctypes.c_longlong) for name in ('user_time', 'kernel_time', 'period_user_time', 'period_kernel_time')] + [
        (name, wintypes.DWORD) for name in ('page_faults', 'total_processes', 'active_processes', 'terminated_processes')]


class OwnedJob:
    """Unnamed noninherited job: all descendants die when the controller's last handle closes.

    Breakaway flags are absent. Nested job assignment may fail under an incompatible
    parent job; that refuses acknowledgement instead of weakening ownership.
    """
    def __init__(self):
        self.api = kernel()
        self.handle = self.api.CreateJobObjectW(None, None)
        if not self.handle:
            raise ProcessBackendError('Windows job could not be created')
        limits = ExtendedLimits(); limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.api.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            self.close()
            raise ProcessBackendError('Windows job ownership limits could not be established')

    def assign(self, process):
        # Popen owns a handle to the exact process created, so assignment has no PID-open race.
        handle = getattr(process, '_handle', None)
        if handle is None:
            handle = getattr(getattr(process, '_popen', None), '_handle', None)
        if handle is None or not self.api.AssignProcessToJobObject(self.handle, int(handle)):
            raise ProcessBackendError('Windows job assignment refused; target remains unacknowledged')

    def active(self):
        value = Accounting()
        if not self.api.QueryInformationJobObject(self.handle, 1, ctypes.byref(value), ctypes.sizeof(value), None):
            raise ProcessBackendError('Windows job membership could not be observed')
        return value.active_processes

    def stop(self):
        if not self.active():
            self.close(); return 'gone'
        if not self.api.TerminateJobObject(self.handle, 124):
            raise ProcessBackendError('Windows job termination was refused')
        deadline = time.monotonic() + 5
        while self.active() and time.monotonic() < deadline:
            time.sleep(0.02)
        if self.active():
            raise ProcessBackendError('Windows job still has active processes')
        self.close(); return 'killed'

    def close(self):
        if self.handle:
            if not self.api.CloseHandle(self.handle):
                raise ProcessBackendError('Windows job handle could not be closed')
            self.handle = None
