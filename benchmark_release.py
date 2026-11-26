"""Bounded local application benchmark using concurrent Streamlit AppTest sessions."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import statistics
import threading
from time import perf_counter

from streamlit.testing.v1 import AppTest


def memory_mib():
    if os.name != "nt":
        return {}
    import ctypes
    from ctypes import wintypes

    class Counters(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("faults", wintypes.DWORD),
                    *[(name, ctypes.c_size_t) for name in (
                        "peak", "working", "quota_peak_paged", "quota_paged",
                        "quota_peak_nonpaged", "quota_nonpaged", "pagefile", "peak_pagefile")]]
    process = ctypes.windll.kernel32.GetCurrentProcess
    process.restype = wintypes.HANDLE
    result = Counters()
    result.size = ctypes.sizeof(result)
    if not ctypes.windll.psapi.GetProcessMemoryInfo(
        wintypes.HANDLE(process()), ctypes.byref(result), result.size
    ):
        raise ctypes.WinError()
    return {"working_set": round(result.working / 2**20, 2),
            "peak_working_set": round(result.peak / 2**20, 2)}


def scenario(repetitions, gate):
    gate.wait(timeout=30)
    samples = {}

    def measure(label, action):
        start = perf_counter()
        action()
        samples.setdefault(label, []).append(round(1000 * (perf_counter() - start), 2))
        if app.exception:
            raise RuntimeError(app.exception[0].message)

    app = AppTest.from_file(str(Path(__file__).with_name("app.py")), default_timeout=90)
    measure("overview startup", app.run)
    if app.metric[0].value != "1,500,000,000":
        raise RuntimeError("Unexpected national total")
    for _ in range(repetitions):
        measure("geography navigation", lambda: app.sidebar.radio[0].set_value("Geographic Intelligence").run())
        measure("state selector", lambda: app.sidebar.selectbox[0].set_value("Delhi").run())
        measure("comparison basket", lambda: app.sidebar.multiselect[0].set_value(["Delhi", "Kerala", "Goa"]).run())
        measure("populated comparison and report", lambda: app.sidebar.radio[0].set_value("State Comparison").run())
        measure("explorer navigation", lambda: app.sidebar.radio[0].set_value("Population Explorer").run())
        measure("advanced explorer", lambda: app.radio(key="advanced_view_Population Explorer")
                .set_value("Multidimensional Explorer").run())
        measure("overview navigation", lambda: app.sidebar.radio[0].set_value("Executive Overview").run())
    return samples


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sessions", type=int, choices=(1, 3, 5, 10), default=1)
    parser.add_argument("--repetitions", type=int, choices=range(1, 6), default=3)
    args = parser.parse_args()
    start = perf_counter()
    before = memory_mib()
    gate = threading.Barrier(args.sessions)
    with ThreadPoolExecutor(max_workers=args.sessions) as pool:
        runs = list(pool.map(lambda _: scenario(args.repetitions, gate), range(args.sessions)))
    after = memory_mib()
    results = {}
    for label in runs[0]:
        values = [value for run in runs for value in run[label]]
        results[label] = {"n": len(values), "median": round(statistics.median(values), 2),
                          "max": round(max(values), 2)}
        if len(values) >= 10:
            results[label]["p95"] = round(statistics.quantiles(values, n=100, method="inclusive")[94], 2)
    print(json.dumps({"pid": os.getpid(), "sessions": args.sessions, "seconds": round(perf_counter()-start, 2),
                      "errors": 0, "operation_ms": results, "memory_before_mib": before, "memory_after_mib": after}))


if __name__ == "__main__":
    main()
