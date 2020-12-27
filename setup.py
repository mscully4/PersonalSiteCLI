from distutils.core import setup

setup(
    name="PersonalSiteCLI",
    version="1.0",
    author="mjscully",
    check_format=True,  # Enable build-time format checking
    test_mypy=True,  # Enable type checking
    test_flake8=True,  # Enable linting at build time)
)
