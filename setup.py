from setuptools import setup, find_packages
import os
import sys

# Ensure numpy is installed before attempting to use it
try:
    import numpy as np
except ImportError:
    os.system(f"{sys.executable} -m pip install numpy==1.24.3")
    import numpy as np

try:
    from Cython.Build import cythonize
except ImportError:
    os.system(f"{sys.executable} -m pip install Cython==3.0.8")
    from Cython.Build import cythonize

# Read requirements from requirements.txt
with open("requirements.txt") as f:
    required = f.read().splitlines()

setup(
    name="low-latency-sample",
    version="0.1.0",
    packages=find_packages(),
    ext_modules=cythonize(
        "src/optimized_metrics.pyx",
        compiler_directives={
            "language_level": "3",
        },
    ),
    include_dirs=[np.get_include()],
    install_requires=required,
    python_requires=">=3.8",
    description="Low latency orderbook processing with Cython optimization",
    author="Indy McCarthy",
    author_email="indymccarthy@gmail.com",
)
