package operator

import (
	"context"
	"fmt"
	"time"

	platform "github.com/KumarSravan77/openmodelops/go/internal/platform"
	appsv1 "k8s.io/api/apps/v1"
	batchv1 "k8s.io/api/batch/v1"
	corev1 "k8s.io/api/core/v1"
	apierrors "k8s.io/apimachinery/pkg/api/errors"
	"k8s.io/apimachinery/pkg/api/resource"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
	"k8s.io/apimachinery/pkg/runtime/schema"
	"k8s.io/apimachinery/pkg/types"
	"k8s.io/apimachinery/pkg/util/intstr"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
)

type Reconciler struct {
	client.Client
	GVK schema.GroupVersionKind
}

func (r *Reconciler) SetupWithManager(manager ctrl.Manager) error {
	object := &unstructured.Unstructured{}
	object.SetGroupVersionKind(r.GVK)
	return ctrl.NewControllerManagedBy(manager).For(object).
		Owns(&appsv1.Deployment{}).Owns(&batchv1.Job{}).Owns(&corev1.Service{}).
		Named(r.GVK.Kind).Complete(r)
}

func (r *Reconciler) Reconcile(ctx context.Context, request ctrl.Request) (ctrl.Result, error) {
	object := &unstructured.Unstructured{}
	object.SetGroupVersionKind(r.GVK)
	if err := r.Get(ctx, request.NamespacedName, object); err != nil {
		return ctrl.Result{}, client.IgnoreNotFound(err)
	}
	spec, err := platform.Parse(object)
	if err != nil {
		return ctrl.Result{}, r.setStatus(ctx, object, "Invalid", err.Error())
	}
	if problems := platform.Validate(spec); len(problems) > 0 {
		return ctrl.Result{}, r.setStatus(ctx, object, "Rejected", fmt.Sprint(problems))
	}
	if r.GVK.Kind == "EvaluationRun" {
		err = r.reconcileJob(ctx, object, spec)
	} else {
		err = r.reconcileDeployment(ctx, object, spec)
	}
	if err != nil {
		return ctrl.Result{}, err
	}
	phase, message, complete, err := r.observedState(ctx, object, spec)
	if err != nil {
		return ctrl.Result{}, err
	}
	if err := r.setStatus(ctx, object, phase, message); err != nil {
		return ctrl.Result{}, err
	}
	if !complete {
		return ctrl.Result{RequeueAfter: 5 * time.Second}, nil
	}
	return ctrl.Result{}, nil
}

func (r *Reconciler) observedState(ctx context.Context, object *unstructured.Unstructured, spec platform.WorkloadSpec) (string, string, bool, error) {
	key := types.NamespacedName{Name: object.GetName(), Namespace: object.GetNamespace()}
	if object.GetKind() == "EvaluationRun" {
		job := &batchv1.Job{}
		if err := r.Get(ctx, key, job); err != nil {
			return "", "", false, err
		}
		if job.Status.Succeeded > 0 {
			return "Completed", "evaluation job completed", true, nil
		}
		if job.Status.Failed > 1 {
			return "Failed", "evaluation job exhausted its retry budget", true, nil
		}
		return "Running", "evaluation job is running", false, nil
	}
	deployment := &appsv1.Deployment{}
	if err := r.Get(ctx, key, deployment); err != nil {
		return "", "", false, err
	}
	if deployment.Status.ObservedGeneration >= deployment.Generation && deployment.Status.AvailableReplicas >= spec.Replicas {
		return "Ready", "all desired replicas are available", true, nil
	}
	return "Progressing", "waiting for desired replicas to become available", false, nil
}

func labelsFor(object *unstructured.Unstructured) map[string]string {
	return map[string]string{"app.kubernetes.io/name": object.GetName(), "app.kubernetes.io/managed-by": "openmodelops-operator", "openmodelops.io/kind": object.GetKind()}
}

func owner(object *unstructured.Unstructured) []metav1.OwnerReference {
	controller, block := true, true
	return []metav1.OwnerReference{{APIVersion: object.GetAPIVersion(), Kind: object.GetKind(), Name: object.GetName(), UID: object.GetUID(), Controller: &controller, BlockOwnerDeletion: &block}}
}

func resources(spec platform.WorkloadSpec) corev1.ResourceRequirements {
	return corev1.ResourceRequirements{
		Requests: corev1.ResourceList{corev1.ResourceCPU: resource.MustParse(spec.CPURequest), corev1.ResourceMemory: resource.MustParse(spec.MemoryRequest)},
		Limits:   corev1.ResourceList{corev1.ResourceCPU: resource.MustParse(spec.CPULimit), corev1.ResourceMemory: resource.MustParse(spec.MemoryLimit)},
	}
}

func boolPtr(value bool) *bool { return &value }

func podSpec(object *unstructured.Unstructured, spec platform.WorkloadSpec) corev1.PodSpec {
	return corev1.PodSpec{
		ServiceAccountName: spec.ServiceAccount,
		SecurityContext:    &corev1.PodSecurityContext{RunAsNonRoot: boolPtr(true), SeccompProfile: &corev1.SeccompProfile{Type: corev1.SeccompProfileTypeRuntimeDefault}},
		Containers: []corev1.Container{{Name: "workload", Image: spec.Image, ImagePullPolicy: corev1.PullIfNotPresent,
			Ports: []corev1.ContainerPort{{Name: "http", ContainerPort: spec.Port}}, Resources: resources(spec),
			SecurityContext: &corev1.SecurityContext{AllowPrivilegeEscalation: boolPtr(false), ReadOnlyRootFilesystem: boolPtr(true), Capabilities: &corev1.Capabilities{Drop: []corev1.Capability{"ALL"}}},
		}},
	}
}

func (r *Reconciler) reconcileDeployment(ctx context.Context, object *unstructured.Unstructured, spec platform.WorkloadSpec) error {
	labels := labelsFor(object)
	key := types.NamespacedName{Name: object.GetName(), Namespace: object.GetNamespace()}
	deployment := &appsv1.Deployment{}
	err := r.Get(ctx, key, deployment)
	desired := &appsv1.Deployment{ObjectMeta: metav1.ObjectMeta{Name: key.Name, Namespace: key.Namespace, Labels: labels, OwnerReferences: owner(object)}, Spec: appsv1.DeploymentSpec{
		Replicas: &spec.Replicas, Selector: &metav1.LabelSelector{MatchLabels: labels},
		Template: corev1.PodTemplateSpec{ObjectMeta: metav1.ObjectMeta{Labels: labels}, Spec: podSpec(object, spec)},
	}}
	if apierrors.IsNotFound(err) {
		if err = r.Create(ctx, desired); err != nil {
			return err
		}
	} else if err != nil {
		return err
	} else {
		deployment.Labels, deployment.OwnerReferences, deployment.Spec = desired.Labels, desired.OwnerReferences, desired.Spec
		if err = r.Update(ctx, deployment); err != nil {
			return err
		}
	}
	service := &corev1.Service{}
	err = r.Get(ctx, key, service)
	serviceSpec := corev1.ServiceSpec{Selector: labels, Ports: []corev1.ServicePort{{Name: "http", Port: spec.Port, TargetPort: intstr.FromInt32(spec.Port)}}}
	if apierrors.IsNotFound(err) {
		return r.Create(ctx, &corev1.Service{ObjectMeta: metav1.ObjectMeta{Name: key.Name, Namespace: key.Namespace, Labels: labels, OwnerReferences: owner(object)}, Spec: serviceSpec})
	}
	if err != nil {
		return err
	}
	service.Spec.Selector, service.Spec.Ports = serviceSpec.Selector, serviceSpec.Ports
	return r.Update(ctx, service)
}

func (r *Reconciler) reconcileJob(ctx context.Context, object *unstructured.Unstructured, spec platform.WorkloadSpec) error {
	key := types.NamespacedName{Name: object.GetName(), Namespace: object.GetNamespace()}
	job := &batchv1.Job{}
	if err := r.Get(ctx, key, job); err == nil {
		return nil
	} else if !apierrors.IsNotFound(err) {
		return err
	}
	pod := podSpec(object, spec)
	pod.RestartPolicy = corev1.RestartPolicyNever
	backoff := int32(1)
	return r.Create(ctx, &batchv1.Job{ObjectMeta: metav1.ObjectMeta{Name: key.Name, Namespace: key.Namespace, Labels: labelsFor(object), OwnerReferences: owner(object)}, Spec: batchv1.JobSpec{BackoffLimit: &backoff, Template: corev1.PodTemplateSpec{ObjectMeta: metav1.ObjectMeta{Labels: labelsFor(object)}, Spec: pod}}})
}

func (r *Reconciler) setStatus(ctx context.Context, object *unstructured.Unstructured, phase, message string) error {
	currentPhase, _, _ := unstructured.NestedString(object.Object, "status", "phase")
	currentMessage, _, _ := unstructured.NestedString(object.Object, "status", "message")
	observed, _, _ := unstructured.NestedInt64(object.Object, "status", "observedGeneration")
	if currentPhase == phase && currentMessage == message && observed == object.GetGeneration() {
		return nil
	}
	_ = unstructured.SetNestedField(object.Object, phase, "status", "phase")
	_ = unstructured.SetNestedField(object.Object, message, "status", "message")
	_ = unstructured.SetNestedField(object.Object, object.GetGeneration(), "status", "observedGeneration")
	return r.Status().Update(ctx, object)
}
