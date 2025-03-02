from setuptools import setup, find_packages

setup(
    name="my-folder-app",
    version="0.1",
    packages=find_packages(),
    install_requires=[
        "pandas",
        "aiofiles",
        "python-dotenv",
    ],
) 