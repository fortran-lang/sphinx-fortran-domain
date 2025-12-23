# While setup.py will be deprecated we maintain one for retro-compatibility with older pip versions
from pathlib import Path
from setuptools import setup, find_packages

HERE = Path(__file__).parent

def read(fname):
    return (HERE / fname).read_text(encoding="utf-8")

setup(
    name="sphinx-fortran-domain",
    version=read("VERSION").strip(),
    description="A modern Sphinx domain for Fortran",
    long_description=read("README.md"),
    long_description_content_type="text/markdown",
    python_requires=">=3.9",
    install_requires=[
        "Sphinx>=6",
    ],
    extras_require={
        "test": [
            "pytest>=7",
        ],
    },
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    include_package_data=True,
    zip_safe=False,
)