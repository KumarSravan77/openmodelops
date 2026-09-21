package main

import (
	"crypto/tls"
	"log/slog"
	"net/http"
	"os"
	"time"

	platformadmission "github.com/KumarSravan77/openmodelops/go/internal/admission"
)

func main() {
	mux := http.NewServeMux()
	mux.Handle("/validate", platformadmission.Handler{})
	mux.HandleFunc("/healthz", func(response http.ResponseWriter, _ *http.Request) { response.WriteHeader(http.StatusOK) })
	server := &http.Server{Addr: env("LISTEN_ADDRESS", ":8443"), Handler: mux, ReadHeaderTimeout: 5 * time.Second, ReadTimeout: 10 * time.Second, WriteTimeout: 10 * time.Second, IdleTimeout: 60 * time.Second, MaxHeaderBytes: 1 << 20}
	cert, key := os.Getenv("TLS_CERT_FILE"), os.Getenv("TLS_KEY_FILE")
	if cert == "" || key == "" {
		slog.Error("TLS_CERT_FILE and TLS_KEY_FILE are required")
		os.Exit(1)
	}
	server.TLSConfig = &tls.Config{MinVersion: tls.VersionTLS13}
	slog.Info("starting admission service", "address", server.Addr)
	if err := server.ListenAndServeTLS(cert, key); err != nil && err != http.ErrServerClosed {
		slog.Error("admission service stopped", "error", err)
		os.Exit(1)
	}
}

func env(name, fallback string) string {
	if value := os.Getenv(name); value != "" {
		return value
	}
	return fallback
}
