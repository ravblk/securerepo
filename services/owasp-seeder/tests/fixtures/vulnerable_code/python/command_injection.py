"""
Базовый пример: Command Injection уязвимость

Функции содержат критические уязвимости command injection через использование
shell=True в subprocess и небезопасной обработки пользовательского ввода.
"""

import subprocess
import os

def ping_system(target_ip):
  
    command = f"ping -c 4 {target_ip}"
    result = subprocess.run(command, shell=True, capture_output=True)

    # Безопасная альтернатива:
    # result = subprocess.run(["ping", "-c", "4", target_ip], capture_output=True)

    return result.stdout.decode()

def execute_system_command(command):

    os.system(command)

    # Безопасная альтернатива:
    # subprocess.run(command.split(), capture_output=True)

def grep_in_files(pattern, filename):

    command = f"grep '{pattern}' {filename}"
    result = subprocess.run(command, shell=True, capture_output=True)

    # Безопасная альтернатива:
    # with open(filename, 'r') as f:
    #     return [line for line in f if pattern in line]

    return result.stdout.decode()