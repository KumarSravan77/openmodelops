package platform

import (
	"fmt"
	"strings"

	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
)

type WorkloadSpec struct {
	Image          string
	Replicas       int32
	Port           int32
	Approved       bool
	CPURequest     string
	MemoryRequest  string
	CPULimit       string
	MemoryLimit    string
	ServiceAccount string
}

func Parse(object *unstructured.Unstructured) (WorkloadSpec, error) {
	image, _, _ := unstructured.NestedString(object.Object, "spec", "image")
	if image == "" {
		return WorkloadSpec{}, fmt.Errorf("spec.image is required")
	}
	replicas, found, _ := unstructured.NestedInt64(object.Object, "spec", "replicas")
	if !found {
		replicas = 1
	}
	port, found, _ := unstructured.NestedInt64(object.Object, "spec", "port")
	if !found {
		port = 8000
	}
	approved, _, _ := unstructured.NestedBool(object.Object, "spec", "approved")
	serviceAccount, _, _ := unstructured.NestedString(object.Object, "spec", "serviceAccountName")
	value := func(name string) string {
		v, _, _ := unstructured.NestedString(object.Object, "spec", "resources", name)
		return v
	}
	return WorkloadSpec{
		Image: image, Replicas: int32(replicas), Port: int32(port), Approved: approved,
		CPURequest: value("cpuRequest"), MemoryRequest: value("memoryRequest"),
		CPULimit: value("cpuLimit"), MemoryLimit: value("memoryLimit"),
		ServiceAccount: serviceAccount,
	}, nil
}

func Validate(spec WorkloadSpec) []string {
	var problems []string
	if !strings.Contains(spec.Image, "@sha256:") {
		problems = append(problems, "spec.image must be pinned by sha256 digest")
	}
	if !spec.Approved {
		problems = append(problems, "spec.approved must be true before deployment")
	}
	if spec.Replicas < 1 || spec.Replicas > 100 {
		problems = append(problems, "spec.replicas must be between 1 and 100")
	}
	if spec.Port < 1 || spec.Port > 65535 {
		problems = append(problems, "spec.port must be between 1 and 65535")
	}
	if spec.CPURequest == "" || spec.MemoryRequest == "" || spec.CPULimit == "" || spec.MemoryLimit == "" {
		problems = append(problems, "spec.resources must define cpuRequest, memoryRequest, cpuLimit and memoryLimit")
	}
	return problems
}
