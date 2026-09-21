package main

import (
	"flag"
	"os"

	platformoperator "github.com/KumarSravan77/openmodelops/go/internal/operator"
	"k8s.io/apimachinery/pkg/runtime/schema"
	clientgoscheme "k8s.io/client-go/kubernetes/scheme"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/healthz"
	"sigs.k8s.io/controller-runtime/pkg/log/zap"
	metricsserver "sigs.k8s.io/controller-runtime/pkg/metrics/server"
)

func main() {
	var metricsAddress, healthAddress string
	flag.StringVar(&metricsAddress, "metrics-bind-address", ":8080", "metrics address")
	flag.StringVar(&healthAddress, "health-probe-bind-address", ":8081", "health address")
	options := zap.Options{Development: false}
	options.BindFlags(flag.CommandLine)
	flag.Parse()
	ctrl.SetLogger(zap.New(zap.UseFlagOptions(&options)))

	manager, err := ctrl.NewManager(ctrl.GetConfigOrDie(), ctrl.Options{
		Scheme:                 clientgoscheme.Scheme,
		Metrics:                metricsserver.Options{BindAddress: metricsAddress},
		HealthProbeBindAddress: healthAddress,
		LeaderElection:         true,
		LeaderElectionID:       "openmodelops-operator.openmodelops.io",
	})
	if err != nil {
		ctrl.Log.Error(err, "unable to create manager")
		os.Exit(1)
	}
	for _, kind := range []string{"ModelDeployment", "AgentDeployment", "EvaluationRun"} {
		reconciler := &platformoperator.Reconciler{Client: manager.GetClient(), GVK: schema.GroupVersionKind{Group: "platform.openmodelops.io", Version: "v1alpha1", Kind: kind}}
		if err := reconciler.SetupWithManager(manager); err != nil {
			ctrl.Log.Error(err, "unable to register controller", "kind", kind)
			os.Exit(1)
		}
	}
	_ = manager.AddHealthzCheck("healthz", healthz.Ping)
	_ = manager.AddReadyzCheck("readyz", healthz.Ping)
	if err := manager.Start(ctrl.SetupSignalHandler()); err != nil {
		ctrl.Log.Error(err, "manager stopped")
		os.Exit(1)
	}
}
