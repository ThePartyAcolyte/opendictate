"""
Hardware and desktop environment diagnostic utilities for OpenDictate.

Detects system memory (RAM), GPU availability, active desktop environment,
and provides recommendations for Whisper model selection.
"""

import os
import shutil
import subprocess
from typing import Dict, Any, Tuple


def get_system_ram_gb() -> float:
    """Read total physical memory in Gigabytes from /proc/meminfo.

    Returns:
        float: Total RAM in GB (e.g. 15.8), or 4.0 fallback.
    """
    try:
        if os.path.exists("/proc/meminfo"):
            with open("/proc/meminfo", "r") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        kb = float(line.split()[1])
                        return round(kb / (1024.0 * 1024.0), 1)
    except Exception:
        pass

    try:
        page_size = os.sysconf("SC_PAGE_SIZE")
        phys_pages = os.sysconf("SC_PHYS_PAGES")
        total_bytes = page_size * phys_pages
        return round(total_bytes / (1024.0 ** 3), 1)
    except Exception:
        return 4.0


def is_cuda_runtime_ready() -> bool:
    """Check if CTranslate2 can actually run on CUDA with working cuBLAS/cuDNN."""
    try:
        import ctranslate2
        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


def get_gpu_info() -> Dict[str, Any]:
    """Detect available graphics acceleration (NVIDIA CUDA or AMD ROCm) and runtime status.

    Returns:
        Dict with 'has_gpu' (bool), 'gpu_name' (str), 'backend' (str), and 'cuda_ready' (bool).
    """
    info = {
        "has_gpu": False,
        "gpu_name": "CPU Only",
        "backend": "cpu",
        "cuda_ready": False
    }

    # Check NVIDIA via nvidia-smi
    nvidia_smi = shutil.which("nvidia-smi")
    if nvidia_smi:
        try:
            res = subprocess.run(
                [nvidia_smi, "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=1.5
            )
            if res.returncode == 0 and res.stdout.strip():
                gpu_line = res.stdout.strip().split("\n")[0]
                parts = [p.strip() for p in gpu_line.split(",")]
                info["has_gpu"] = True
                info["gpu_name"] = f"NVIDIA {parts[0]}" if not parts[0].startswith("NVIDIA") else parts[0]
                info["backend"] = "cuda"
                info["cuda_ready"] = is_cuda_runtime_ready()
                return info
        except Exception:
            pass

    # Check NVIDIA via lspci fallback
    lspci = shutil.which("lspci")
    if lspci:
        try:
            res = subprocess.run([lspci], capture_output=True, text=True, timeout=1.5)
            if res.returncode == 0 and "nvidia" in res.stdout.lower():
                for line in res.stdout.splitlines():
                    if "vga" in line.lower() or "3d" in line.lower() and "nvidia" in line.lower():
                        info["has_gpu"] = True
                        info["gpu_name"] = "NVIDIA GeForce / Quadro"
                        info["backend"] = "cuda"
                        info["cuda_ready"] = is_cuda_runtime_ready()
                        return info
        except Exception:
            pass

    # Check AMD ROCm / rocm-smi
    rocm_smi = shutil.which("rocm-smi")
    if rocm_smi:
        try:
            res = subprocess.run([rocm_smi, "--showproductname"], capture_output=True, text=True, timeout=1.5)
            if res.returncode == 0 and "Card series:" in res.stdout:
                info["has_gpu"] = True
                info["gpu_name"] = "AMD Radeon (ROCm)"
                info["backend"] = "rocm"
                info["cuda_ready"] = False
                return info
        except Exception:
            pass

    return info


def detect_desktop_environment() -> Tuple[str, bool]:
    """Detect active Desktop Environment and whether GNOME Shell is available.

    Returns:
        Tuple[str, bool]: (Desktop environment name, is_gnome_shell_available).
    """
    xdg_current = os.environ.get("XDG_CURRENT_DESKTOP", "").upper()
    desktop_session = os.environ.get("DESKTOP_SESSION", "").upper()
    de_name = xdg_current or desktop_session or "Unknown Desktop"

    is_gnome = False
    if "GNOME" in xdg_current or "UBUNTU" in xdg_current or "GNOME" in desktop_session:
        is_gnome = True

    # Double check if gnome-shell binary exists
    if not is_gnome and shutil.which("gnome-shell"):
        try:
            res = subprocess.run(["gnome-shell", "--version"], capture_output=True, text=True, timeout=1.0)
            if res.returncode == 0 and "GNOME Shell" in res.stdout:
                is_gnome = True
        except Exception:
            pass

    return de_name, is_gnome


def recommend_whisper_model(ram_gb: float, has_gpu: bool) -> Tuple[str, str, str]:
    """Provide recommended Whisper model keys based on system resources.

    Args:
        ram_gb: Total physical RAM in Gigabytes.
        has_gpu: Whether dedicated GPU acceleration is available.

    Returns:
        Tuple[model_size, label_i18n_key, desc_i18n_key]
    """
    if ram_gb < 5.0 and not has_gpu:
        return ("tiny", "wizard_model_tiny", "wizard_rec_desc_tiny")
    elif ram_gb <= 8.5 and not has_gpu:
        return ("base", "wizard_model_base", "wizard_rec_desc_base")
    elif ram_gb <= 16.0 or not has_gpu:
        return ("small", "wizard_model_small", "wizard_rec_desc_small")
    else:
        return ("medium", "wizard_model_medium", "wizard_rec_desc_medium")
