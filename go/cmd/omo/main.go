package main

import (
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"os"
	"os/exec"
	"strings"
	"time"
)

var endpoints = []struct{ Name, URL string }{
	{"mlops", "http://localhost:8001/health/ready"}, {"agents", "http://localhost:8002/health/ready"},
	{"aiops", "http://localhost:8003/health/live"}, {"factory", "http://localhost:8004/health/ready"},
	{"reviewer", "http://localhost:8005/health/ready"}, {"aria", "http://localhost:8088/health"},
}

func main() {
	if len(os.Args) < 2 {
		usage()
		os.Exit(2)
	}
	var err error
	switch os.Args[1] {
	case "doctor":
		err = doctor()
	case "kind":
		err = kind(os.Args[2:])
	case "workloads":
		err = workloads(os.Args[2:])
	case "version":
		fmt.Println("omo development")
	default:
		usage()
		os.Exit(2)
	}
	if err != nil {
		fmt.Fprintln(os.Stderr, "error:", err)
		os.Exit(1)
	}
}

func doctor() error {
	client := &http.Client{Timeout: 3 * time.Second}
	failed := 0
	for _, endpoint := range endpoints {
		response, err := client.Get(endpoint.URL)
		if err != nil {
			fmt.Printf("FAIL %-10s %v\n", endpoint.Name, err)
			failed++
			continue
		}
		_ = response.Body.Close()
		if response.StatusCode >= 300 {
			fmt.Printf("FAIL %-10s HTTP %d\n", endpoint.Name, response.StatusCode)
			failed++
		} else {
			fmt.Printf("OK   %s\n", endpoint.Name)
		}
	}
	if failed > 0 {
		return fmt.Errorf("%d service checks failed", failed)
	}
	return nil
}

func kind(args []string) error {
	if len(args) != 1 || (args[0] != "deploy" && args[0] != "smoke") {
		return errors.New("usage: omo kind {deploy|smoke}")
	}
	script := "scripts/kind-" + args[0] + ".sh"
	return run(script)
}

func workloads(args []string) error {
	if len(args) > 1 {
		return errors.New("usage: omo workloads [namespace]")
	}
	namespace := "openmodelops-managed"
	if len(args) == 1 {
		namespace = args[0]
	}
	command := exec.Command("kubectl", "get", "modeldeployments,agentdeployments,evaluationruns", "-n", namespace, "-o", "json")
	output, err := command.Output()
	if err != nil {
		return err
	}
	var result struct {
		Items []struct {
			Kind     string `json:"kind"`
			Metadata struct {
				Name string `json:"name"`
			} `json:"metadata"`
			Status map[string]any `json:"status"`
		} `json:"items"`
	}
	if err := json.Unmarshal(output, &result); err != nil {
		return err
	}
	for _, item := range result.Items {
		fmt.Printf("%-18s %-32s %v\n", item.Kind, item.Metadata.Name, item.Status["phase"])
	}
	return nil
}

func run(name string) error {
	command := exec.Command(name)
	command.Stdout, command.Stderr, command.Stdin = os.Stdout, os.Stderr, os.Stdin
	return command.Run()
}
func usage() {
	fmt.Fprintln(os.Stderr, strings.TrimSpace(`omo commands:
  doctor                 verify the shared local platform
  kind deploy|smoke      deploy or verify the Kind environment
  workloads [namespace]  list governed platform workloads
  version                print version`))
}
