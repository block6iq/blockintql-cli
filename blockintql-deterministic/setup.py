from setuptools import setup, find_packages

setup(
    name="blockintql-deterministic",
    version="0.1.1",
    version="0.1.0",
    packages=find_packages(),
    package_data={"blockintql_deterministic": ["py.typed"]},
    python_requires=">=3.10",
    install_requires=[],
    description="Deterministic screening core and sonar_consensus_v1 swarm.",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    author="Block6IQ",
    license="MIT",
    url="https://github.com/block6iq/blockintql-cli",
)
