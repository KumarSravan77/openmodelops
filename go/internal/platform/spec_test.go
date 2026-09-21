package platform

import (
	"testing"

	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
)

func TestParseAndValidate(t *testing.T) {
	object := &unstructured.Unstructured{Object: map[string]any{"spec": map[string]any{
		"image": "registry/model@sha256:abc", "approved": true, "replicas": int64(2), "port": int64(8080),
		"resources": map[string]any{"cpuRequest": "100m", "memoryRequest": "128Mi", "cpuLimit": "1", "memoryLimit": "1Gi"},
	}}}
	spec, err := Parse(object)
	if err != nil {
		t.Fatal(err)
	}
	if problems := Validate(spec); len(problems) != 0 {
		t.Fatalf("unexpected problems: %v", problems)
	}
}

func TestValidationRejectsMutableUnapprovedWorkload(t *testing.T) {
	problems := Validate(WorkloadSpec{Image: "registry/model:latest", Replicas: 1, Port: 8000})
	if len(problems) < 3 {
		t.Fatalf("expected policy violations, got %v", problems)
	}
}
