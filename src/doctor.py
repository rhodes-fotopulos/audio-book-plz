from __future__ import annotations

import platform
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import nltk
import ollama
import psutil
from rich.console import Console
from rich.table import Table

from src.attribution.llm_client import MODEL_8B, MODEL_14B
from src.matching.speaker_index import ANNOTATOR_FILES

# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

LIBRITTS_DATA_DIR = Path.home() / ".local" / "share" / "libritts-p" / "data"


@dataclass
class CheckResult:
    name: str
    status: str  # "ok", "warn", "fail"
    message: str
    fix_hint: str = ""


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def check_apple_silicon() -> CheckResult:
    machine = platform.machine()
    if machine == "arm64":
        return CheckResult("Apple Silicon", "ok", f"Architecture: {machine}")
    return CheckResult(
        "Apple Silicon",
        "fail",
        f"Architecture: {machine}",
        fix_hint="This app requires Apple Silicon (M1+).",
    )


def check_macos_version() -> CheckResult:
    ver_str = platform.mac_ver()[0]
    if not ver_str:
        return CheckResult(
            "macOS Version",
            "warn",
            "Could not determine macOS version",
            fix_hint="macOS 13+ recommended.",
        )
    major = int(ver_str.split(".")[0])
    if major >= 13:
        return CheckResult("macOS Version", "ok", f"macOS {ver_str}")
    return CheckResult(
        "macOS Version",
        "warn",
        f"macOS {ver_str}",
        fix_hint="macOS 13+ recommended.",
    )


def check_ram() -> CheckResult:
    total_bytes = psutil.virtual_memory().total
    total_gb = total_bytes / (1024**3)
    if total_gb >= 16:
        return CheckResult("RAM", "ok", f"{total_gb:.0f} GB")
    return CheckResult(
        "RAM",
        "warn",
        f"{total_gb:.0f} GB",
        fix_hint=f"16GB RAM recommended. 8GB may work with {MODEL_8B} model.",
    )


def check_python_version() -> CheckResult:
    ver = sys.version_info
    ver_str = f"{ver.major}.{ver.minor}.{ver.micro}"
    if ver >= (3, 11):
        return CheckResult("Python Version", "ok", ver_str)
    return CheckResult(
        "Python Version",
        "fail",
        ver_str,
        fix_hint="Install Python 3.11: brew install python@3.11",
    )


def check_ffmpeg() -> CheckResult:
    path = shutil.which("ffmpeg")
    if path:
        return CheckResult("ffmpeg", "ok", f"Found: {path}")
    return CheckResult(
        "ffmpeg",
        "fail",
        "Not found",
        fix_hint="Install ffmpeg: brew install ffmpeg",
    )


def check_ollama_installed() -> CheckResult:
    path = shutil.which("ollama")
    if path:
        return CheckResult("Ollama Installed", "ok", f"Found: {path}")
    return CheckResult(
        "Ollama Installed",
        "fail",
        "Not found",
        fix_hint="Install Ollama: brew install ollama",
    )


def check_ollama_running() -> CheckResult:
    try:
        with urlopen("http://localhost:11434/api/version", timeout=3) as resp:
            data = resp.read().decode()
        return CheckResult("Ollama Running", "ok", f"Responded: {data.strip()}")
    except (URLError, OSError, TimeoutError):
        return CheckResult(
            "Ollama Running",
            "fail",
            "Could not connect to Ollama",
            fix_hint="Start Ollama: brew services start ollama",
        )


def check_ollama_model() -> CheckResult:
    try:
        models = ollama.list()
    except Exception:
        return CheckResult(
            "Ollama Model",
            "warn",
            "Ollama not running, skipping model check",
        )

    for model in models.models:
        if model.model.startswith("qwen3.5:") or model.model.startswith("qwen3:"):
            return CheckResult("Ollama Model", "ok", f"Found: {model.model}")

    return CheckResult(
        "Ollama Model",
        "fail",
        "No Qwen3.5 model found",
        fix_hint=f"Pull model: ollama pull {MODEL_14B}",
    )


def check_libritts_data() -> CheckResult:
    missing: list[str] = []
    for fname in ANNOTATOR_FILES:
        if not (LIBRITTS_DATA_DIR / fname).exists():
            missing.append(fname)
    if not missing:
        return CheckResult("LibriTTS-P Data", "ok", f"All files present in {LIBRITTS_DATA_DIR}")
    return CheckResult(
        "LibriTTS-P Data",
        "fail",
        f"Missing: {', '.join(missing)}",
        fix_hint="Run setup.sh to download LibriTTS-P data",
    )


def check_nltk_data() -> CheckResult:
    try:
        nltk.data.find("tokenizers/punkt_tab")
        return CheckResult("NLTK Data", "ok", "punkt_tab found")
    except LookupError:
        return CheckResult(
            "NLTK Data",
            "fail",
            "punkt_tab not found",
            fix_hint='python -c "import nltk; nltk.download(\'punkt_tab\')"',
        )


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

_ALL_CHECKS = [
    check_apple_silicon,
    check_macos_version,
    check_ram,
    check_python_version,
    check_ffmpeg,
    check_ollama_installed,
    check_ollama_running,
    check_ollama_model,
    check_libritts_data,
    check_nltk_data,
]

STATUS_COLORS = {
    "ok": "green",
    "warn": "yellow",
    "fail": "red",
}


def run_doctor() -> bool:
    """Run all system health checks and display results.

    Returns True only if zero checks have status "fail".
    """
    console = Console()
    results: list[CheckResult] = []

    for check_fn in _ALL_CHECKS:
        results.append(check_fn())

    # Build table
    table = Table(title="Audio Book Plz - System Health Check")
    table.add_column("Check", style="bold")
    table.add_column("Status")
    table.add_column("Message")

    for r in results:
        color = STATUS_COLORS.get(r.status, "white")
        table.add_row(r.name, f"[{color}]{r.status}[/{color}]", r.message)

    console.print(table)

    # Collect failures
    failures = [r for r in results if r.status == "fail"]
    if failures:
        console.print()
        console.print("[bold red]Fix hints:[/bold red]")
        for r in failures:
            if r.fix_hint:
                console.print(f"  - {r.name}: {r.fix_hint}")

    return len(failures) == 0
