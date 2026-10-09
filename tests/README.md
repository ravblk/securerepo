# Vulnerability Detection Test Suite

================================================================================================

## Overview

This test suite validates the effectiveness of the SecureRepo audit worker in detecting security vulnerabilities. It scans known vulnerable code fixtures, runs the audit worker, and compares results against a ground truth model.

**Purpose:** Measure Recall (detection rate), Precision (accuracy), and F1-Score of vulnerability detection.

---

## Test Structure

```
tests/
├── fixtures/
│   ├── __init__.py
│   ├── vulnerable_code_ground_truth.yaml    # Ground truth model (expected findings)
│   └── vulnerable_code/                     # Located in services/owasp-seeder/tests/fixtures/
│       └── python/
│           ├── sql_injection.py
│           ├── xss_vulnerability.py
│           ├── command_injection.py
│           └── hardcoded_secrets.py
├── test_vulnerability_detection.py           # Main test script
└── vulnerability_detection_report.txt        # Generated after test run
```

---

## Ground Truth Model

The ground truth model (`vulnerable_code_ground_truth.yaml`) defines all expected vulnerabilities:

| File | Vulnerabilities | Severity Breakdown |
|------|----------------|-------------------|
| `sql_injection.py` | 2 (SQL Injection) | 2x HIGH |
| `xss_vulnerability.py` | 3 (XSS) | 2x HIGH, 1x MEDIUM |
| `command_injection.py` | 3 (Command Injection) | 3x HIGH |
| `hardcoded_secrets.py` | 16 (Secrets) | 8x HIGH, 7x MEDIUM, 1x LOW |

**Total: 24 vulnerabilities**
- HIGH: 14 (58.3%)
- MEDIUM: 8 (33.3%)
- LOW: 2 (8.3%)

---

## Running the Tests

### Quick Start

```bash
# Install test dependencies
pip install -r requirements-test.txt

# Run the test
python tests/test_vulnerability_detection.py
```

### Integration with CI/CD

```bash
# Generate metrics for CI/CD
python tests/test_vulnerability_detection.py

# Metrics will be saved to:
# - tests/vulnerability_detection_report.txt (human-readable)
# - tests/vulnerability_detection_metrics.json (machine-readable)
```

---

## Test Metrics

### Calculated Metrics

- **Recall (Detection Rate):** TP / (TP + FN)
  - Percentage of ground truth vulnerabilities detected
  - **Target:** >= 50%

- **Precision:** TP / (TP + FP)
  - Percentage of detected findings that are real
  - **Target:** >= 50%

- **F1-Score:** 2 * (Precision * Recall) / (Precision + Recall)
  - Harmonic mean of precision and recall
  - **Target:** >= 0.4

### Metrics Breakdown

Metrics are broken down by:
- **Severity:** HIGH, MEDIUM, LOW
- **Vulnerability Type:** SQL_INJECTION, XSS, COMMAND_INJECTION, HARDCODED_SECRETS, etc.

---

## Example Output

```
================================================================================
VULNERABILITY DETECTION EFFECTIVENESS TEST REPORT
================================================================================

📊 OVERALL METRICS:
  Total Ground Truth Vulnerabilities: 24
  Total Detected Vulnerabilities:      28
  True Positives:                      20
  False Positives:                     8
  False Negatives:                     4

📈 PERFORMANCE METRICS:
  Recall (Detection Rate):   83.3%
  Precision:                 71.4%
  F1-Score:                  0.767

📊 BY SEVERITY:

  HIGH:
    TP: 12, FP: 5, FN: 2
    Recall: 85.7%

  MEDIUM:
    TP: 6, FP: 2, FN: 2
    Recall: 75.0%

🏆 QUALITY ASSESSMENT:
  ✅ EXCELLENT - High recall (>80%)
  ✅ GOOD PRECISION - Low false positive rate

================================================================================
```

---

## Understanding the Results

### Recall >= 80% ✅ EXCELLENT
The system detects most vulnerabilities. Good for production use.

### Recall 60-80% ⚠️ GOOD
The system detects most but misses some. Consider improving detection rules.

### Recall 40-60% ⚠️ FAIR
The system misses significant number of vulnerabilities. Needs improvement.

### Recall < 40% ❌ POOR
The system fails to detect most vulnerabilities. Major issues.

### Precision >= 70% ✅ GOOD PRECISION
Low false positive rate. Users get mostly relevant findings.

### Precision < 50% ❌ LOW PRECISION
Many false alarms. Too much noise for users.

---

## Improving Detection

### If Recall is Low

1. **Review False Negatives:**
   - Check which vulnerabilities are being missed
   - Add or improve detection rules
   - Enhance LLM prompts

2. **Adjust Chunking:**
   - Smaller chunks may miss context
   - Larger chunks may be less precise
   - Experiment with chunk size

3. **Improve Vector Search:**
   - Add more security rules to Qdrant
   - Tune embedding similarity thresholds
   - Use hybrid search (keyword + semantic)

### If Precision is Low

1. **Review False Positives:**
   - Identify patterns of incorrect detections
   - Add negative examples to training
   - Refine detection rules

2. **Tune LLM Prompts:**
   - Increase specificity
   - Require code context
   - Add severity guidelines

---

## Adding New Test Cases

### 1. Create Vulnerable Code

Add new vulnerable file to `services/owasp-seeder/tests/fixtures/vulnerable_code/`:

```python
# new_vulnerability.py
def insecure_function(user_input):
    # Vulnerable code here
    pass
```

### 2. Update Ground Truth

Add to `tests/fixtures/vulnerable_code_ground_truth.yaml`:

```yaml
vulnerabilities:
  - file: "python/new_vulnerability.py"
    findings:
      - vulnerability_type: "NEW_TYPE"
        severity: "HIGH"
        line: 42
        vulnerable_line: 'some vulnerable code'
        description: "Description here"
        rule_id: "new_rule_id"
        code_snippet: "..."
```

### 3. Re-run Tests

```bash
python tests/test_vulnerability_detection.py
```

---

## Integrating with Audit Worker

**Current Implementation:** Uses simulated detection (`_simulate_vulnerability_detection()`).

**To use actual audit worker:**

```python
def run_audit_on_vulnerable_code(self, repo_path: Path) -> List[dict]:
    """Run actual audit worker on vulnerable code repository."""

    # Create temporary git repo
    temp_dir = tempfile.mkdtemp()
    try:
        # Setup git repo with vulnerable code
        subprocess.run(['git', 'init'], cwd=temp_dir)
        subprocess.run(['git', 'add', '.'], cwd=str(repo_path))
        subprocess.run(['git', 'commit', '-m', 'Initial commit'], cwd=str(repo_path))

        # Call audit API
        api_url = "http://api:8000/audit/start"
        response = requests.post(api_url, json={
            "repo_url": f"file://{repo_path}",
            "branch": "main",
            "lang": "python"
        })

        audit_id = response.json()['audit_id']

        # Wait for completion (poll or SSE)
        # ...

        # Get results
        results_url = f"http://api:8000/audit/{audit_id}/report"
        response = requests.get(results_url, headers=... )

        return response.json()['findings']

    finally:
        shutil.rmtree(temp_dir)
```

---

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Vulnerability Detection Test

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -r requirements-test.txt

      - name: Run vulnerability detection test
        run: |
          python tests/test_vulnerability_detection.py

      - name: Check metrics thresholds
        run: |
          python -c "
          import json
          with open('tests/vulnerability_detection_metrics.json') as f:
              metrics = json.load(f)
              assert metrics['recall'] >= 0.5, f'Recall too low: {metrics[\"recall\"]:.1%}'
              assert metrics['precision'] >= 0.5, f'Precision too low: {metrics[\"precision\"]:.1%}'
          "

      - name: Upload report
        uses: actions/upload-artifact@v3
        with:
          name: detection-report
          path: tests/vulnerability_detection_report.txt
```

---

## Troubleshooting

### Test Fails with Import Error

```bash
# Ensure services are in PYTHONPATH
export PYTHONPATH="${PYTHONPATH}:$(pwd)/services"
python tests/test_vulnerability_detection.py
```

### Ground Truth File Not Found

```bash
# Check file exists
ls -la tests/fixtures/vulnerable_code_ground_truth.yaml

# Ensure YAML syntax is valid
python -m yaml tests/fixtures/vulnerable_code_ground_truth.yaml
```

### Zero Vulnerabilities Detected

```bash
# Check if vulnerable code files exist
ls -la services/owasp-seeder/tests/fixtures/vulnerable_code/python/

# Check file permissions
chmod 644 services/owasp-seeder/tests/fixtures/vulnerable_code/python/*.py
```

---

## Future Enhancements

- [ ] Integrate with actual audit worker (replace simulation)
- [ ] Add vulnerability type-specific tests
- [ ] Implement automated test case generation
- [ ] Add regression testing (track improvements/degredations)
- [ ] Generate HTML report with visualizations
- [ ] Add performance benchmarking (latency, throughput)
- [ ] Test multi-language detection (JavaScript, Java, Go)
- [ ] Add test for false positive rate on clean code

---

## License

Part of the SecureRepo project.
