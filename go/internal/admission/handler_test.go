package admission

import (
	"bytes"
	"encoding/json"
	"net/http/httptest"
	"testing"

	admissionv1 "k8s.io/api/admission/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/types"
)

func invoke(t *testing.T, object map[string]any) admissionv1.AdmissionReview {
	t.Helper()
	raw, _ := json.Marshal(object)
	review := admissionv1.AdmissionReview{TypeMeta: metav1.TypeMeta{APIVersion: "admission.k8s.io/v1", Kind: "AdmissionReview"}, Request: &admissionv1.AdmissionRequest{UID: types.UID("one"), Operation: admissionv1.Create, Object: runtime.RawExtension{Raw: raw}}}
	body, _ := json.Marshal(review)
	recorder := httptest.NewRecorder()
	Handler{}.ServeHTTP(recorder, httptest.NewRequest("POST", "/validate", bytes.NewReader(body)))
	var result admissionv1.AdmissionReview
	if err := json.Unmarshal(recorder.Body.Bytes(), &result); err != nil {
		t.Fatal(err)
	}
	return result
}

func TestRejectsUnpinnedImage(t *testing.T) {
	result := invoke(t, map[string]any{"spec": map[string]any{"image": "model:latest", "approved": true, "resources": map[string]any{"cpuRequest": "1", "memoryRequest": "1Gi", "cpuLimit": "2", "memoryLimit": "2Gi"}}})
	if result.Response.Allowed {
		t.Fatal("expected mutable image to be rejected")
	}
}

func TestAllowsGovernedWorkload(t *testing.T) {
	result := invoke(t, map[string]any{"spec": map[string]any{"image": "model@sha256:abc", "approved": true, "resources": map[string]any{"cpuRequest": "1", "memoryRequest": "1Gi", "cpuLimit": "2", "memoryLimit": "2Gi"}}})
	if !result.Response.Allowed {
		t.Fatalf("expected admission: %s", result.Response.Result.Message)
	}
}
