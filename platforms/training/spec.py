from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ResourceSpec:
    workers: int = 1
    cpu_per_worker: int = 2
    gpu_per_worker: int = 0
    memory_gb_per_worker: int = 8

    def __post_init__(self) -> None:
        if self.workers < 1 or self.workers > 256:
            raise ValueError("workers must be between 1 and 256")
        if self.cpu_per_worker < 1 or self.memory_gb_per_worker < 1 or self.gpu_per_worker < 0:
            raise ValueError("invalid worker resources")


@dataclass(frozen=True)
class TrainingSpec:
    run_id: str
    image_digest: str
    dataset_uri: str
    dataset_digest: str
    entrypoint: str
    resources: ResourceSpec = field(default_factory=ResourceSpec)
    environment: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.image_digest.startswith("sha256:") or not self.dataset_digest.startswith("sha256:"):
            raise ValueError("training image and dataset must be immutable sha256 digests")
        if any(key.lower().endswith(("secret", "password", "token", "key")) for key in self.environment):
            raise ValueError("secrets must use workload identity or secret references, not environment values")


def ray_job(spec: TrainingSpec) -> dict:
    """Portable RayJob custom resource body for Kubernetes submission."""
    worker_env = [{"name": key, "value": value} for key, value in sorted(spec.environment.items())]
    return {
        "apiVersion": "ray.io/v1",
        "kind": "RayJob",
        "metadata": {"name": f"training-{spec.run_id}"},
        "spec": {
            "entrypoint": spec.entrypoint,
            "shutdownAfterJobFinishes": True,
            "rayClusterSpec": {
                "rayVersion": "2.49.0",
                "headGroupSpec": {
                    "rayStartParams": {"dashboard-host": "0.0.0.0"},
                    "template": {
                        "spec": {
                            "containers": [
                                {"name": "ray-head", "image": f"training-image@{spec.image_digest}", "env": worker_env}
                            ]
                        }
                    },
                },
                "workerGroupSpecs": [
                    {
                        "groupName": "workers",
                        "replicas": spec.resources.workers,
                        "minReplicas": spec.resources.workers,
                        "maxReplicas": spec.resources.workers,
                        "rayStartParams": {},
                        "template": {
                            "spec": {
                                "containers": [
                                    {
                                        "name": "ray-worker",
                                        "image": f"training-image@{spec.image_digest}",
                                        "env": worker_env,
                                        "resources": {
                                            "requests": {
                                                "cpu": str(spec.resources.cpu_per_worker),
                                                "memory": f"{spec.resources.memory_gb_per_worker}Gi",
                                                **(
                                                    {"nvidia.com/gpu": str(spec.resources.gpu_per_worker)}
                                                    if spec.resources.gpu_per_worker
                                                    else {}
                                                ),
                                            }
                                        },
                                    }
                                ]
                            }
                        },
                    }
                ],
            },
        },
    }
