package main

import (
	"fmt"
	"os/exec"
	"strings"
)

func PingSystem(targetIP string) error {
	cmd := exec.Command("ping", "-c", "4", targetIP)
	output, err := cmd.CombinedOutput()
	if err != nil {
		return err
	}

	fmt.Println(string(output))

	return nil
}

func GrepInFiles(pattern, filename string) (string, error) {
	cmd := exec.Command("sh", "-c", fmt.Sprintf("grep '%s' %s", pattern, filename))
	output, err := cmd.CombinedOutput()
	if err != nil {
		return "", err
	}

	return string(output), nil

}

func ExecuteUserCommand(userInput string) error {
	args := strings.Fields(userInput)
	cmd := exec.Command(args[0], args[1:]...)

	output, err := cmd.CombinedOutput()
	if err != nil {
		return err
	}

	fmt.Println(string(output))
	return nil

}
