from setuptools import setup, find_packages

setup(
    name='clangd-env',
    version='0.1.3',
    packages=find_packages(),
    entry_points={
        'console_scripts': [
            'clangd-env = clangd_env.cli:main',
        ],
    },
    install_requires=[],
    author='Your Name',
    description='A tool to auto-configure clangd and debugging environment for C++/ROS projects.',
)