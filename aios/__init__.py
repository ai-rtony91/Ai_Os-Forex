"""AIOS package with lazy compatibility for the root command.

The package marker keeps ``aios.py`` from shadowing trader module imports.
Importing trader code does not load or start the master runtime.
"""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

__all__ = ["main"]


def main() -> int:
    """Delegate the compatibility runner to the canonical ``aios.py`` command."""
    command_path = Path(__file__).resolve().parents[1] / "aios.py"
    spec = spec_from_file_location("_aios_root_command", command_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load AIOS command: {command_path}")
    command = module_from_spec(spec)
    spec.loader.exec_module(command)
    return command.main()
