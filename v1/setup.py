from __future__ import annotations

import os
import platform

from setuptools import Extension, setup


def _compile_args() -> list[str]:
    if os.name == "nt":
        return ["/O2"]
    args = ["-O3", "-DNDEBUG"]
    if platform.system().lower() != "windows":
        args.append("-march=native")
    return args


setup(
    ext_modules=[
        Extension(
            "nonail._fastcore",
            sources=["nonail/_fastcore.cpp"],
            language="c++",
            extra_compile_args=_compile_args(),
        )
    ]
)
