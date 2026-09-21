package admission

import (
	"encoding/json"
	"fmt"
	"net/http"
	"strings"

	platform "github.com/KumarSravan77/openmodelops/go/internal/platform"
	admissionv1 "k8s.io/api/admission/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
)

type Handler struct{}

func (Handler) ServeHTTP(response http.ResponseWriter, request *http.Request) {
	response.Header().Set("Content-Type", "application/json")
	var review admissionv1.AdmissionReview
	if err := json.NewDecoder(http.MaxBytesReader(response, request.Body, 1<<20)).Decode(&review); err != nil {
		http.Error(response, "invalid admission review", http.StatusBadRequest)
		return
	}
	if review.Request == nil {
		http.Error(response, "missing admission request", http.StatusBadRequest)
		return
	}
	result := &admissionv1.AdmissionResponse{UID: review.Request.UID, Allowed: true}
	if review.Request.Operation == admissionv1.Create || review.Request.Operation == admissionv1.Update {
		object := &unstructured.Unstructured{}
		if err := json.Unmarshal(review.Request.Object.Raw, &object.Object); err != nil {
			result.Allowed = false
			result.Result = &metav1.Status{Message: "object is not valid JSON"}
		} else if spec, err := platform.Parse(object); err != nil {
			result.Allowed = false
			result.Result = &metav1.Status{Message: err.Error()}
		} else if problems := platform.Validate(spec); len(problems) > 0 {
			result.Allowed = false
			result.Result = &metav1.Status{Reason: metav1.StatusReasonInvalid, Message: strings.Join(problems, "; "), Code: http.StatusUnprocessableEntity}
		}
	}
	review.Request = nil
	review.Response = result
	if err := json.NewEncoder(response).Encode(review); err != nil {
		http.Error(response, fmt.Sprintf("encode response: %v", err), http.StatusInternalServerError)
	}
}
