# Go control plane

OpenModelOps keeps ML intelligence in Python and implements cloud-native control
plane responsibilities in Go.

## Components

| Component | Responsibility |
|---|---|
| `omo` | Local diagnostics, Kind deployment and governed-workload inspection |
| Operator | Reconcile model/agent services and evaluation jobs |
| Admission service | Reject mutable, unapproved or unbounded workloads |

## Local validation

```bash
make go-test
make go-build
go run ./go/cmd/omo doctor
```

`make kind-deploy` installs the Python platform and the Go control plane. The
installer creates a local TLS certificate, registers the fail-closed admission
webhook and waits for both Go deployments to become ready.

## Example governed workload

```yaml
apiVersion: platform.openmodelops.io/v1alpha1
kind: ModelDeployment
metadata:
  name: fraud-model
  namespace: openmodelops-managed
spec:
  image: registry.example/model@sha256:0123456789abcdef
  approved: true
  replicas: 2
  port: 8000
  resources:
    cpuRequest: 250m
    memoryRequest: 512Mi
    cpuLimit: "1"
    memoryLimit: 2Gi
```

The image digest and approval marker represent inputs from the existing model
governance plane. In a production registry, approval should be projected from a
signed release rather than manually authored.
