"""Deterministic mixed Git diffs for demos and visual regression tests."""

import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from dunkr.app import DunkrApp


@dataclass(frozen=True)
class DemoRepository:
    """A temporary repository and the mixed working-tree diff it contains."""

    root: Path
    """Repository root used to resolve changed-file paths."""

    diff: str
    """Deterministic unified diff spanning every demo change kind."""


def _git(root: Path, *args: str) -> str:
    """Run Git in ``root`` and return its text output."""
    return subprocess.run(
        ["git", *args],
        check=True,
        cwd=root,
        capture_output=True,
        text=True,
    ).stdout


def _write(root: Path, relative_path: str, content: str | bytes) -> None:
    """Write fixture content, creating its parent directories when needed."""
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content)


@contextmanager
def create_demo_repository() -> Iterator[DemoRepository]:
    """Yield a temporary Git repository with a stable mixed diff."""
    with TemporaryDirectory(prefix="dunkr-demo-") as temporary_directory:
        root = Path(temporary_directory)
        _git(root, "init", "--quiet")
        _git(root, "config", "user.name", "dunkr demo")
        _git(root, "config", "user.email", "demo@example.invalid")
        _write(
            root,
            "src/calculator.py",
            "def add(left: int, right: int) -> int:\n"
            "    total = left + right\n"
            "    return total\n\n"
            "def subtract(left: int, right: int) -> int:\n"
            "    return left - right\n\n"
            "def multiply(left: int, right: int) -> int:\n"
            "    return left * right\n\n"
            "def divide(left: float, right: float) -> float:\n"
            "    if right == 0:\n"
            "        raise ValueError('Division by zero is undefined')\n"
            "    return left / right\n\n"
            "def power(base: float, exponent: float) -> float:\n"
            "    return base ** exponent\n",
        )
        _write(
            root,
            "legacy/old_config.py",
            "DEBUG = False\nPORT = 8000\nLOG_LEVEL = 'INFO'\nDATABASE_URL = 'sqlite:///legacy.db'\n",
        )
        _write(
            root,
            "assets/old_name.txt",
            "A stable asset name with initial configuration details.\n",
        )
        _write(
            root,
            "src/old_module.py",
            "def greeting(name: str = 'world') -> str:\n"
            "    return f'hello {name}'\n\n"
            "def farewell(name: str = 'friend') -> str:\n"
            "    return f'goodbye {name}'\n\n"
            "def status_check() -> dict[str, bool]:\n"
            "    return {'healthy': True}\n",
        )
        _write(
            root,
            "src/deeply/nested/subfolder/very_long_file_name_with_detailed_logic.py",
            "class FinancialMetricsCalculatorEngine:\n"
            "    def __init__(self, initial_balance: float = 0.0, default_tax_rate: float = 0.15) -> None:\n"
            "        self.initial_balance = initial_balance\n"
            "        self.default_tax_rate = default_tax_rate\n\n"
            "    def calculate_complex_financial_metrics_with_custom_thresholds_and_formatting(self, account_balance: float, interest_rate: float, tax_deductions: float = 0.0, apply_compound_annual_growth: bool = True) -> dict[str, float]:\n"
            "        net_interest = account_balance * interest_rate\n"
            "        taxable_amount = max(0.0, net_interest - tax_deductions)\n"
            "        final_balance = account_balance + net_interest - (taxable_amount * self.default_tax_rate)\n"
            "        return {'balance': final_balance, 'interest': net_interest, 'tax': taxable_amount}\n",
        )
        _write(root, "assets/logo.bin", b"\x00\x01original\xff")
        _write(root, "notes/no_newline.txt", "before")
        _git(root, "add", ".")
        _git(root, "commit", "--quiet", "-m", "Base demo tree")

        _write(
            root,
            "src/calculator.py",
            "def add(left: int, right: int) -> int:\n"
            "    total = left + right\n"
            "    return total + 1  # Add precision offset\n\n"
            "def subtract(left: int, right: int) -> int:\n"
            "    return left - right  # Subtraction logic\n\n"
            "def multiply(left: int, right: int) -> int:\n"
            "    return left * right * 2  # Double multiplication\n\n"
            "def divide(left: float, right: float) -> float:\n"
            "    if right == 0.0:\n"
            "        raise ValueError('Division by zero is strictly forbidden in this application context')\n"
            "    return left / right\n\n"
            "def power(base: float, exponent: float) -> float:\n"
            "    return pow(base, exponent)\n",
        )
        _write(
            root,
            "docs/guide.md",
            "# Comprehensive User Guide and Technical Documentation\n\n"
            "Welcome to the dunkr diff browser documentation suite.\n\n"
            "## Getting Started\n\n"
            "1. Install dunkr using `uv tool install dunkr`.\n"
            "2. Run dunkr inside any Git repository to inspect working tree changes.\n"
            "3. Use the directory tree panel to navigate between changed files.\n\n"
            "## Features & Capabilities\n\n"
            "- Side-by-side unified Git diff view.\n"
            "- Pinned line numbers column on left edge.\n"
            "- Independent horizontal scrollbars fixed at pane bottoms.\n"
            "- Synchronized vertical scrolling across both left and right panes.\n",
        )
        _git(root, "add", "docs/guide.md")
        (root / "legacy/old_config.py").unlink()
        _git(root, "mv", "assets/old_name.txt", "assets/new_name.txt")
        _git(root, "mv", "src/old_module.py", "src/new_module.py")
        _write(
            root,
            "src/new_module.py",
            "def greeting(name: str = 'dunkr user') -> str:\n"
            "    return f'hello {name}'\n\n"
            "def farewell(name: str = 'friend') -> str:\n"
            "    return f'goodbye {name}'\n\n"
            "def status_check() -> dict[str, bool]:\n"
            "    return {'healthy': True, 'ready': True}\n",
        )
        _write(
            root,
            "src/deeply/nested/subfolder/very_long_file_name_with_detailed_logic.py",
            "class FinancialMetricsCalculatorEngine:\n"
            "    def __init__(self, initial_balance: float = 0.0, default_tax_rate: float = 0.15, Enable_high_precision_rounding: bool = True) -> None:\n"
            "        self.initial_balance = initial_balance\n"
            "        self.default_tax_rate = default_tax_rate\n"
            "        self.enable_high_precision_rounding = enable_high_precision_rounding\n\n"
            "    def calculate_complex_financial_metrics_with_custom_thresholds_and_formatting(self, account_balance: float, interest_rate: float, tax_deductions: float = 0.0, apply_compound_annual_growth: bool = True, custom_financial_formatting_option_enabled: bool = False) -> dict[str, float]:\n"
            "        net_interest = account_balance * interest_rate * (1.05 if apply_compound_annual_growth else 1.0)\n"
            "        taxable_amount = max(0.0, net_interest - tax_deductions)\n"
            "        final_balance = account_balance + net_interest - (taxable_amount * self.default_tax_rate)\n"
            "        result = {'balance': round(final_balance, 4), 'interest': round(net_interest, 4), 'tax': round(taxable_amount, 4)}\n"
            "        return result\n",
        )
        _write(root, "assets/logo.bin", b"\x00\x01changed\xfe")
        _write(root, "notes/no_newline.txt", "after")

        path_groups = (
            ("src/calculator.py",),
            ("docs/guide.md",),
            ("legacy/old_config.py",),
            ("assets/old_name.txt", "assets/new_name.txt"),
            ("src/old_module.py", "src/new_module.py"),
            ("src/deeply/nested/subfolder/very_long_file_name_with_detailed_logic.py",),
            ("assets/logo.bin",),
            ("notes/no_newline.txt",),
        )
        diff = "".join(
            _git(root, "diff", "--no-color", "--find-renames=20%", "HEAD", "--", *paths)
            for paths in path_groups
        )
        yield DemoRepository(root=root, diff=diff)


def main() -> int:
    """Launch dunkr with the deterministic mixed-diff fixture."""
    with create_demo_repository() as demo:
        DunkrApp(diff=demo.diff, project_root=demo.root).run()
    return 0
