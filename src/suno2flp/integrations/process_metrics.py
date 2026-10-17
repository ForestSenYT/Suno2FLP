"""Observed lifetime peaks for the current Windows process, not a memory sandbox."""

import ctypes
import os
import sys
from pathlib import Path


def peak_process_memory() -> tuple[int, int]:
    if sys.platform != "win32":
        raise ValueError("Native memory observation requires Windows")
    system_root = os.environ.get("SYSTEMROOT")
    if not system_root:
        raise ValueError("Windows SYSTEMROOT is required for process memory observation")

    class Counters(ctypes.Structure):
        _fields_ = [
            ("cb", ctypes.c_uint32),
            ("page_faults", ctypes.c_uint32),
            ("peak_working_set", ctypes.c_size_t),
            ("working_set", ctypes.c_size_t),
            ("peak_paged_pool", ctypes.c_size_t),
            ("paged_pool", ctypes.c_size_t),
            ("peak_nonpaged_pool", ctypes.c_size_t),
            ("nonpaged_pool", ctypes.c_size_t),
            ("commit", ctypes.c_size_t),
            ("peak_commit", ctypes.c_size_t),
        ]

    kernel = ctypes.WinDLL(str(Path(system_root) / "System32/kernel32.dll"), use_last_error=True)
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    kernel.K32GetProcessMemoryInfo.argtypes = (
        ctypes.c_void_p,
        ctypes.POINTER(Counters),
        ctypes.c_uint32,
    )
    kernel.K32GetProcessMemoryInfo.restype = ctypes.c_int
    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    if not kernel.K32GetProcessMemoryInfo(
        kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    peaks = int(counters.peak_working_set), int(counters.peak_commit)
    if min(peaks) <= 0:
        raise ValueError("Windows did not report valid native process memory peaks")
    return peaks
