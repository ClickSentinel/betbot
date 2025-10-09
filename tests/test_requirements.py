"""
Tests for requirements.txt to ensure all imported packages are declared.
"""

import ast
import os
import re
import sys
from pathlib import Path
from typing import Set, List, Dict

import pytest


class ImportVisitor(ast.NodeVisitor):
    """AST visitor to extract all import statements from Python files."""

    def __init__(self):
        self.imports = set()
        self.from_imports = set()

    def visit_Import(self, node):
        """Visit regular import statements like 'import package'."""
        for alias in node.names:
            # Get the top-level package name
            package = alias.name.split(".")[0]
            self.imports.add(package)
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        """Visit from-import statements like 'from package import something'."""
        if node.module:
            # Get the top-level package name
            package = node.module.split(".")[0]
            self.from_imports.add(package)
        self.generic_visit(node)


def get_all_imports_from_project() -> Set[str]:
    """Extract all package imports from the project's Python files."""
    project_root = Path(__file__).parent.parent
    all_imports = set()

    # Find all Python files in the project (excluding tests and __pycache__)
    python_files = []
    for root, dirs, files in os.walk(project_root):
        # Skip test directories, __pycache__, and .venv
        dirs[:] = [
            d for d in dirs if d not in ["tests", "__pycache__", ".venv", ".git"]
        ]

        for file in files:
            if file.endswith(".py") and not file.startswith("test_"):
                python_files.append(Path(root) / file)

    # Parse each Python file and extract imports
    for py_file in python_files:
        try:
            with open(py_file, "r", encoding="utf-8") as f:
                content = f.read()

            # Parse the AST
            tree = ast.parse(content, filename=str(py_file))
            visitor = ImportVisitor()
            visitor.visit(tree)

            # Combine both types of imports
            all_imports.update(visitor.imports)
            all_imports.update(visitor.from_imports)

        except (SyntaxError, UnicodeDecodeError) as e:
            # Skip files that can't be parsed
            print(f"Warning: Could not parse {py_file}: {e}")
            continue

    return all_imports


def get_stdlib_modules() -> Set[str]:
    """Get a set of Python standard library module names."""
    # Common standard library modules that might be imported
    stdlib_modules = {
        "os",
        "sys",
        "json",
        "time",
        "datetime",
        "asyncio",
        "logging",
        "pathlib",
        "typing",
        "collections",
        "functools",
        "itertools",
        "math",
        "random",
        "re",
        "string",
        "warnings",
        "weakref",
        "copy",
        "pickle",
        "hashlib",
        "urllib",
        "http",
        "email",
        "socket",
        "threading",
        "multiprocessing",
        "subprocess",
        "shutil",
        "tempfile",
        "glob",
        "csv",
        "configparser",
        "argparse",
        "unittest",
        "doctest",
        "pdb",
        "traceback",
        "inspect",
        "ast",
        "dis",
        "importlib",
        "pkgutil",
        "modulefinder",
        "runpy",
        "types",
        "enum",
        "abc",
        "contextlib",
        "operator",
        "heapq",
        "bisect",
        "array",
        "struct",
        "codecs",
        "unicodedata",
        "stringprep",
        "locale",
        "calendar",
        "timeit",
        "profile",
        "pstats",
        "trace",
        "gc",
        "site",
        "sysconfig",
        "platform",
        "ctypes",
        "mmap",
        "readline",
        "rlcompleter",
    }

    # Add Python version specific modules
    if sys.version_info >= (3, 8):
        stdlib_modules.add("zoneinfo")

    return stdlib_modules


def parse_requirements_txt() -> Dict[str, str]:
    """Parse requirements.txt and return a dict of package names to versions."""
    requirements_file = Path(__file__).parent.parent / "requirements.txt"

    if not requirements_file.exists():
        return {}

    requirements = {}
    with open(requirements_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()

            # Skip empty lines and comments
            if not line or line.startswith("#"):
                continue

            # Parse package name and version specifier
            # Handle formats like: package>=1.0.0, package==1.0.0, package
            match = re.match(r"^([a-zA-Z0-9_-]+)", line)
            if match:
                package_name = match.group(1).lower().replace("_", "-")
                requirements[package_name] = line

    return requirements


def normalize_package_name(name: str) -> str:
    """Normalize package names for comparison (handle underscores vs dashes)."""
    return name.lower().replace("_", "-")


def test_all_imports_in_requirements():
    """Test that all imported packages are declared in requirements.txt."""
    # Get all imports from the project
    project_imports = get_all_imports_from_project()

    # Get standard library modules
    stdlib_modules = get_stdlib_modules()

    # Get packages from requirements.txt
    requirements = parse_requirements_txt()

    # Get project root to check for local modules
    project_root = Path(__file__).parent.parent

    # Filter out standard library modules and relative imports
    third_party_imports = set()
    for imp in project_imports:
        # Skip standard library modules
        if imp in stdlib_modules:
            continue

        # Skip relative imports (empty string or starting with .)
        if not imp or imp.startswith("."):
            continue

        # Skip local modules - check if a .py file exists in the project
        # Convert dashes to underscores for filesystem checks
        imp_underscore = imp.replace("-", "_")

        local_module_paths = [
            project_root / f"{imp}.py",
            project_root / imp / "__init__.py",
            project_root / f"{imp_underscore}.py",
            project_root / imp_underscore / "__init__.py",
            project_root / "utils" / f"{imp_underscore}.py",
            project_root / "cogs" / f"{imp_underscore}.py",
        ]

        is_local_module = any(path.exists() for path in local_module_paths)

        # Also check if it's clearly a local module name pattern
        if imp in ["betbot"] or imp.startswith("betbot"):
            is_local_module = True

        if is_local_module:
            continue

        # Also skip standard library modules that might not be in our list
        if imp in ["dataclasses", "builtins"]:  # dataclasses is stdlib in Python 3.7+
            continue

        third_party_imports.add(normalize_package_name(imp))

    # Check for missing packages
    missing_packages = []
    for package in third_party_imports:
        # Check if package is in requirements (handle common name variations)
        found = False

        # Special case mappings for import name vs package name
        package_mappings = {
            "dotenv": "python-dotenv",
            "discord": "discord-py",  # In case it's discord.py vs discord
        }

        # Check direct match
        if package in requirements:
            found = True
        # Check mapped name
        elif package in package_mappings and package_mappings[package] in requirements:
            found = True
        # Check variations (underscores vs dashes)
        else:
            for req_package in requirements.keys():
                if package.replace("-", "_") == req_package.replace("-", "_"):
                    found = True
                    break

        if not found:
            missing_packages.append(package)

    # Assert no packages are missing
    if missing_packages:
        error_msg = (
            f"The following packages are imported but not in requirements.txt:\n"
            f"{', '.join(sorted(missing_packages))}\n\n"
            f"Found imports: {sorted(third_party_imports)}\n"
            f"Requirements packages: {sorted(requirements.keys())}\n\n"
            f"Please add missing packages to requirements.txt"
        )
        pytest.fail(error_msg)


def test_no_unused_requirements():
    """Test that all packages in requirements.txt are actually used."""
    # Get all imports from the project
    project_imports = get_all_imports_from_project()
    normalized_imports = {normalize_package_name(imp) for imp in project_imports}

    # Get packages from requirements.txt
    requirements = parse_requirements_txt()

    # Find potentially unused packages
    unused_packages = []
    for req_package in requirements.keys():
        # Check if this requirement is actually imported
        found = False

        # Direct match
        if req_package in normalized_imports:
            found = True

        # Check for common variations
        variations = [
            req_package.replace("-", "_"),
            req_package.replace("_", "-"),
            req_package.replace("python-", ""),  # python-dotenv -> dotenv
        ]

        for variation in variations:
            if variation in normalized_imports:
                found = True
                break

        # Special cases for packages that have different import names
        special_cases = {
            "discord-py": "discord",
            "python-dotenv": "dotenv",
            "pyyaml": "yaml",
            "pillow": "pil",
            "beautifulsoup4": "bs4",
            "msgpack-python": "msgpack",
        }

        # Handle the dotenv case specifically
        if req_package == "python-dotenv" and "dotenv" in normalized_imports:
            found = True

        if req_package in special_cases:
            if special_cases[req_package] in normalized_imports:
                found = True

        if not found:
            unused_packages.append(req_package)

    # Allow some common dev/test dependencies that might not be directly imported
    allowed_unused = {
        "pytest",
        "pytest-asyncio",
        "coverage",
        "black",
        "flake8",
        "mypy",
        "pre-commit",
        "setuptools",
        "pip",
        "wheel",
        "twine",
    }

    unused_packages = [pkg for pkg in unused_packages if pkg not in allowed_unused]

    # Warning instead of failure for unused packages (since they might be indirect dependencies)
    if unused_packages:
        print(f"\nWarning: The following packages in requirements.txt might be unused:")
        print(f"{', '.join(sorted(unused_packages))}")
        print("Consider reviewing if these are still needed.")


def test_requirements_txt_format():
    """Test that requirements.txt is properly formatted."""
    requirements_file = Path(__file__).parent.parent / "requirements.txt"

    if not requirements_file.exists():
        pytest.skip("requirements.txt not found")

    with open(requirements_file, "r", encoding="utf-8") as f:
        lines = f.readlines()

    issues = []

    for i, line in enumerate(lines, 1):
        line = line.strip()

        # Skip empty lines and comments
        if not line or line.startswith("#"):
            continue

        # Check for proper version pinning
        if not re.search(r"[><=!~]", line):
            issues.append(f"Line {i}: No version specifier for '{line}'")

        # Check for consistent formatting
        if " " in line and not line.startswith("#"):
            # Allow spaces in comments but not in package specifications
            if "#" not in line:
                issues.append(f"Line {i}: Unexpected spaces in package specification")

    if issues:
        pytest.fail(f"requirements.txt formatting issues:\n" + "\n".join(issues))


if __name__ == "__main__":
    # For manual testing
    print("Third-party imports found:")
    imports = get_all_imports_from_project()
    stdlib = get_stdlib_modules()
    third_party = {
        imp for imp in imports if imp not in stdlib and imp and not imp.startswith(".")
    }
    for imp in sorted(third_party):
        print(f"  {imp}")

    print(f"\nRequirements.txt packages:")
    reqs = parse_requirements_txt()
    for pkg in sorted(reqs.keys()):
        print(f"  {pkg}")
