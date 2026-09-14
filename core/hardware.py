"""
Hardware and desktop environment diagnostic utilities for OpenDictate.

Detects system memory (RAM), GPU availability, active desktop environment,
and provides recommendations for Whisper model selection.
"""

import os
import shutil
import subprocess
import logging
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
    except Exception as e:
        logging.debug(f"Error reading /proc/meminfo: {e}")

    try:
        page_size = os.sysconf("SC_PAGE_SIZE")
        phys_pages = os.sysconf("SC_PHYS_PAGES")
        total_bytes = page_size * phys_pages
        return round(total_bytes / (1024.0 ** 3), 1)
    except Exception as e:
        logging.debug(f"Error reading SC_PAGE_SIZE/SC_PHYS_PAGES sysconf: {e}")
        return 4.0


def is_cuda_runtime_ready() -> bool:
    """Check if CTranslate2 can actually run on CUDA with working cuBLAS/cuDNN and compatible driver."""
    try:
        import ctranslate2
        import numpy as np
        if ctranslate2.get_cuda_device_count() == 0:
            return False
        test_storage = ctranslate2.StorageView.from_array(
            np.array([1.0], dtype=np.float32)
        ).to_device(ctranslate2.Device.cuda)
        del test_storage
        return True
    except Exception as e:
        logging.debug(f"CUDA runtime availability check failed: {e}")
        return False


def get_cpu_core_count() -> int:
    """Return total available CPU logical cores on the system."""
    try:
        count = os.cpu_count()
        return count if count and count > 0 else 1
    except Exception as e:
        logging.debug(f"Error getting cpu_count: {e}")
        return 1


def get_supported_compute_types(device: str = "auto") -> Tuple[str, ...]:
    """Return valid CTranslate2 compute types based on selected device and CUDA availability.

    Args:
        device: Target execution device ("auto", "cpu", or "cuda").

    Returns:
        Tuple of supported compute type strings.
    """
    cuda_available = is_cuda_runtime_ready()
    if device == "cuda" or (device == "auto" and cuda_available):
        return ("default", "float16", "int8_float16", "int8", "float32")
    return ("default", "int8", "float32")


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
        except Exception as e:
            logging.debug(f"nvidia-smi detection error: {e}")

    # Check NVIDIA via lspci fallback
    lspci = shutil.which("lspci")
    if lspci:
        try:
            res = subprocess.run([lspci], capture_output=True, text=True, timeout=1.5)
            if res.returncode == 0 and "nvidia" in res.stdout.lower():
                for line in res.stdout.splitlines():
                    if ("vga" in line.lower() or "3d" in line.lower()) and "nvidia" in line.lower():
                        info["has_gpu"] = True
                        info["gpu_name"] = "NVIDIA GeForce / Quadro"
                        info["backend"] = "cuda"
                        info["cuda_ready"] = is_cuda_runtime_ready()
                        return info
        except Exception as e:
            logging.debug(f"lspci detection error: {e}")

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
        except Exception as e:
            logging.debug(f"rocm-smi detection error: {e}")

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
        except Exception as e:
            logging.debug(f"gnome-shell version check error: {e}")

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


def get_omarchy_palette() -> Dict[str, str]:
    """Extract semantic color palette from active Omarchy theme."""
    palette = {
        "bg": "#0c0b0c",
        "fg": "#FAFCFB",
        "accent": "#b59790",
        "primary": "#b59790",
        "secondary": "#a5a0b6",
        "surface": "#161416",
        "panel": "#201c21",
        "border": "#584e51",
        "error": "#c38b7b",
        "success": "#87a9b0",
        "warning": "#6B5E73",
        "muted": "#8a8588",
    }
    try:
        res = subprocess.run(
            ["omarchy", "theme", "color", "--all"],
            capture_output=True,
            text=True,
            timeout=0.8
        )
        if res.returncode == 0:
            for line in res.stdout.splitlines():
                parts = line.strip().split("\t")
                if len(parts) == 2:
                    k, v = parts[0].strip(), parts[1].strip()
                    if k in ("bg", "background"):
                        palette["bg"] = v
                    elif k in ("fg", "foreground"):
                        palette["fg"] = v
                    elif k == "accent":
                        palette["accent"] = v
                        palette["primary"] = v
                    elif k in ("cyan", "bright_cyan"):
                        palette["secondary"] = v
                    elif k in ("selection", "selection_background"):
                        palette["panel"] = v
                    elif k in ("lighter_bg", "lighter_background"):
                        palette["surface"] = v
                    elif k in ("red", "color1"):
                        palette["error"] = v
                    elif k in ("green", "color2"):
                        palette["success"] = v
                    elif k in ("yellow", "color3"):
                        palette["warning"] = v
                    elif k == "muted":
                        palette["muted"] = v
                        palette["border"] = v
    except Exception as e:
        logging.debug(f"omarchy palette extraction error: {e}")
    return palette
