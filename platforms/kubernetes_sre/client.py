from __future__ import annotations

from typing import Protocol

from platforms.kubernetes_sre.models import Autoscaler, ClusterSnapshot, Workload


class KubernetesReader(Protocol):
    """Read-only cluster boundary. It deliberately exposes no mutation methods."""

    def snapshot(self, cluster: str) -> ClusterSnapshot: ...


class KubernetesWriter(Protocol):
    """Narrow write boundary used only by the separately authorized executor."""

    def scale_deployment(
        self, namespace: str, name: str, replicas: int, expected_uid: str, expected_resource_version: str
    ) -> str: ...

    def restart_deployment(
        self, namespace: str, name: str, expected_uid: str, expected_resource_version: str
    ) -> str: ...


class OfficialKubernetesClient:
    """Adapter for the official Kubernetes Python client.

    Imports are lazy so the core platform and unit tests remain runnable without a
    cluster. Authentication uses in-cluster credentials first and kubeconfig only
    when explicitly outside a cluster.
    """

    def __init__(self) -> None:
        try:
            from kubernetes import client, config
            from kubernetes.config.config_exception import ConfigException
        except ImportError as exc:
            raise RuntimeError("install openmodelops-ai-platform[kubernetes-sre]") from exc
        try:
            config.load_incluster_config()
        except ConfigException:
            config.load_kube_config()
        self._apps = client.AppsV1Api()
        self._autoscaling = client.AutoscalingV2Api()
        self._core = client.CoreV1Api()

    def snapshot(self, cluster: str) -> ClusterSnapshot:
        from datetime import UTC, datetime

        namespaces = tuple(sorted(item.metadata.name for item in self._core.list_namespace().items))
        replica_set_owners: dict[tuple[str, str], str] = {}
        for replica_set in self._apps.list_replica_set_for_all_namespaces().items:
            deployment_owner = next(
                (owner.name for owner in replica_set.metadata.owner_references or [] if owner.kind == "Deployment"),
                replica_set.metadata.name,
            )
            replica_set_owners[(replica_set.metadata.namespace, replica_set.metadata.name)] = deployment_owner
        pod_metrics: dict[tuple[str, str], dict[str, object]] = {}
        for pod in self._core.list_pod_for_all_namespaces().items:
            owners = pod.metadata.owner_references or []
            owner = owners[0].name if owners else pod.metadata.name
            if owners and owners[0].kind == "ReplicaSet":
                owner = replica_set_owners.get((pod.metadata.namespace, owner), owner)
            key = (pod.metadata.namespace, owner)
            metric = pod_metrics.setdefault(key, {"restarts": 0, "reasons": set()})
            for status in pod.status.container_statuses or []:
                metric["restarts"] = int(metric["restarts"]) + status.restart_count
                waiting = status.state.waiting if status.state else None
                if waiting and waiting.reason:
                    metric["reasons"].add(waiting.reason)

        workloads = []
        for deployment in self._apps.list_deployment_for_all_namespaces().items:
            template_containers = deployment.spec.template.spec.containers
            key = (deployment.metadata.namespace, deployment.metadata.name)
            metric = pod_metrics.get(key, {"restarts": 0, "reasons": set()})
            workloads.append(
                Workload(
                    kind="Deployment",
                    namespace=deployment.metadata.namespace,
                    name=deployment.metadata.name,
                    uid=deployment.metadata.uid,
                    resource_version=deployment.metadata.resource_version,
                    desired_replicas=deployment.spec.replicas or 0,
                    ready_replicas=deployment.status.ready_replicas or 0,
                    restart_count=int(metric["restarts"]),
                    waiting_reasons=tuple(sorted(metric["reasons"])),
                    images=tuple(container.image for container in template_containers),
                    has_readiness_probe=all(container.readiness_probe is not None for container in template_containers),
                    has_liveness_probe=all(container.liveness_probe is not None for container in template_containers),
                )
            )
        autoscalers = tuple(
            Autoscaler(
                namespace=item.metadata.namespace,
                name=item.metadata.name,
                target=item.spec.scale_target_ref.name,
                current_replicas=item.status.current_replicas or 0,
                maximum_replicas=item.spec.max_replicas,
            )
            for item in self._autoscaling.list_horizontal_pod_autoscaler_for_all_namespaces().items
        )
        return ClusterSnapshot(cluster, datetime.now(UTC), tuple(workloads), autoscalers, namespaces)

    def _deployment(self, namespace: str, name: str, uid: str, resource_version: str):
        deployment = self._apps.read_namespaced_deployment(name, namespace)
        if deployment.metadata.uid != uid or deployment.metadata.resource_version != resource_version:
            raise RuntimeError("resource changed after approval; obtain a new proposal")
        return deployment

    def scale_deployment(
        self, namespace: str, name: str, replicas: int, expected_uid: str, expected_resource_version: str
    ) -> str:
        self._deployment(namespace, name, expected_uid, expected_resource_version)
        result = self._apps.patch_namespaced_deployment_scale(name, namespace, {"spec": {"replicas": replicas}})
        return result.metadata.resource_version

    def restart_deployment(
        self, namespace: str, name: str, expected_uid: str, expected_resource_version: str
    ) -> str:
        from datetime import UTC, datetime

        self._deployment(namespace, name, expected_uid, expected_resource_version)
        patch = {
            "spec": {"template": {"metadata": {"annotations": {"openmodelops.io/restartedAt": datetime.now(UTC).isoformat()}}}}
        }
        result = self._apps.patch_namespaced_deployment(name, namespace, patch)
        return result.metadata.resource_version
