from __future__ import annotations

import platform
import re
import subprocess
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class HardwareProfile:
    platform: str
    chip: str
    memory_gb: float
    cpu_cores: int
    gpu_cores: int
    metal_supported: bool

    def public_dict(self) -> dict[str, str | float | int | bool]:
        return asdict(self)


def _mac_profile() -> str:
    result = subprocess.run(
        ["system_profiler", "SPHardwareDataType", "SPDisplaysDataType"],
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    )
    return result.stdout


def _match_int(pattern: str, text: str, default: int = 0) -> int:
    match = re.search(pattern, text)
    return int(match.group(1)) if match else default


def detect_hardware() -> HardwareProfile:
    system = platform.system()
    if system == "Darwin":
        details = _mac_profile()
        chip_match = re.search(r"Chip:\s*(.+)", details)
        memory = _match_int(r"Memory:\s*(\d+)\s*GB", details)
        cpu_cores = _match_int(r"Total Number of Cores:\s*(\d+)", details)
        gpu_matches = re.findall(r"Total Number of Cores:\s*(\d+)", details)
        gpu_cores = int(gpu_matches[-1]) if len(gpu_matches) > 1 else 0
        return HardwareProfile(
            platform="macOS",
            chip=chip_match.group(1).strip() if chip_match else platform.processor() or "Apple Silicon",
            memory_gb=float(memory),
            cpu_cores=cpu_cores,
            gpu_cores=gpu_cores,
            metal_supported="Metal: Supported" in details or "Metal Support:" in details,
        )
    return HardwareProfile(
        platform=system,
        chip=platform.processor() or "unknown",
        memory_gb=0,
        cpu_cores=0,
        gpu_cores=0,
        metal_supported=False,
    )
