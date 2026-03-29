from pathlib import Path

from setuptools import find_packages, setup


ROOT = Path(__file__).parent
README = (ROOT / "README.md").read_text(encoding="utf-8")
VERSION = {}
exec((ROOT / "blockintql" / "__init__.py").read_text(encoding="utf-8"), VERSION)


setup(
    name="blockintql",
    version=VERSION["__version__"],
    description="BlockINTQL — Sovereign Blockchain Intelligence CLI",
    long_description=README,
    long_description_content_type="text/markdown",
    author="Block6IQ",
    author_email="joe@block6iq.com",
    url="https://blockintql.com",
    packages=find_packages(include=["blockintql", "blockintql.*"]),
    install_requires=[
        "click>=8.0.0",
        "httpx>=0.27.0",
        "rich>=13.0.0",
    ],
    entry_points={
        "console_scripts": [
            "blockintql=blockintql.cli:main",
        ],
    },
    python_requires=">=3.8",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Security",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
    ],
    keywords="blockchain bitcoin ethereum forensics compliance aml kyc intelligence agents",
)
