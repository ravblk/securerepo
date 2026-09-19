# Guardrails Configuration Guide

## Overview
The Guardrails Engine provides configurable validation layers for LLM-based security audit results. Each guardrail can be enabled/disabled independently to balance between strict security validation and practical utility.

## Available Guardrails

| Guardrail | Purpose | Default | Aggressive Level |
|-----------|---------|---------|------------------|
| `json_validation` | Ensures valid JSON structure and required fields | ✅ Enabled | Low |
| `grounding_check` | Verifies vulnerable lines exist in original code | ✅ Enabled | Medium |
| `rule_reference` | Validates rule_id and URL match available rules | ❌ Disabled | High |
| `hallucination_check` | Detects potential LLM hallucinations | ❌ Disabled | Very High |
| `severity_consistency` | Ensures severity matches explanation keywords | ❌ Disabled | High |
| `explanation_quality` | Validates explanations are meaningful | ✅ Enabled | Low |
| `duplicate_detection` | Removes duplicate or similar violations | ✅ Enabled | Low |

## Configuration Options

### 1. Production Configuration (Recommended)
**Use for:** Regular security audits with balanced approach

```yaml
GUARDRAILS_ENABLED: "true"
GUARDRAILS_ENABLED_CHECKS: '["json_validation", "grounding_check", "explanation_quality", "duplicate_detection"]'
GUARDRAILS_STRICT_MODE: "false"
```

**Characteristics:**
- ✅ Retains valid violations
- ✅ Removes obvious issues (JSON errors, ungrounded lines)
- ✅ Prevents duplicates
- ✅ Minimal false positives
- ⚠️ May retain violations with incorrect rule references

### 2. Strict Security Mode
**Use for:** High-security environments, compliance audits

```yaml
GUARDRAILS_ENABLED: "true"
GUARDRAILS_ENABLED_CHECKS: '["json_validation", "grounding_check", "rule_reference", "explanation_quality", "duplicate_detection"]'
GUARDRAILS_STRICT_MODE: "false"
```

**Characteristics:**
- ✅ Ensures rule references are valid
- ✅ Higher confidence in results
- ❌ May lose violations with valid issues but incorrect rule IDs
- ⚠️ Rule database must be comprehensive

### 3. Lenient Development Mode
**Use for:** Development, testing, exploring capabilities

```yaml
GUARDRAILS_ENABLED: "true"
GUARDRAILS_ENABLED_CHECKS: '["json_validation", "duplicate_detection"]'
GUARDRAILS_STRICT_MODE: "false"
```

**Characteristics:**
- ✅ Maximum violations retained
- ✅ Good for exploration
- ❌ May include false positives
- ❌ Manual review required

### 4. Ultra-Strict Mode
**Use for:** Production with zero tolerance for errors

```yaml
GUARDRAILS_ENABLED: "true"
GUARDRAILS_ENABLED_CHECKS: '["json_validation", "grounding_check", "rule_reference", "hallucination_check", "severity_consistency", "explanation_quality", "duplicate_detection"]'
GUARDRAILS_STRICT_MODE: "true"
```

**Characteristics:**
- ⚠️ **Violations filtered increase dramatically**
- ⚠️ May result in empty results
- ✅ Highest confidence in remaining results
- ❌ Not recommended for most use cases

### 5. Custom Configuration
**Use for:** Specific security requirements

Enable/disable specific checks:

```yaml
GUARDRAILS_ENABLED_CHECKS: '["json_validation", "grounding_check", "hallucination_check"]'
```

## Performance Impact

Based on testing with 8 LLM-generated violations:

| Configuration | Violations Retained | False Positive Rate | Processing Time |
|--------------|---------------------|-------------------|-----------------|
| Production (4 checks) | 100% | Low | Fastest |
| Strict (5 checks) | 25-50% | Low | Fast |
| Development (2 checks) | 100% | High | Fastest |
| Ultra-Strict (7 checks) | 0-25% | None | Slower |

## Common Issues

### Issue: "Rule reference validation failed"
**Cause:** LLM references rules not in your rule database

**Solutions:**
1. **Modify the LLM prompt** to only include available rules
2. **Use production configuration** (disable rule_reference check)
3. **Expand rule database** to cover OWASP/CWE standards

### Issue: "Severity consistency check failed"
**Cause:** Explanation doesn't contain expected keywords for severity level

**Affected Rules:**
- High severity expects: "injection", "xss", "csrf", "authentication", "authorization", "file"

**Solutions:**
1. **Improve LLM prompt** to require specific terminology
2. **Expand severity_keywords** in guardrails.py line 311-316
3. **Disable this check** for more lenient validation

### Issue: "Hallucination check failed"
**Cause:** LLM creates violations for non-existent rules

**Solutions:**
1. **Disable hallucination_check** in configuration
2. **Use rule_reference check** instead (less aggressive)
3. **Update available_rules** to include OWASP/CWE rules

## Migration Guide

### From All Guardrails to Production Config

**Before:**
```python
# Results: 25% retention rate, high false positive filtering
```

**After:**
```python
# Results: 100% retention rate, valid violations preserved
GUARDRAILS_ENABLED_CHECKS: '["json_validation", "grounding_check", "explanation_quality", "duplicate_detection"]'
```

### Benefits
- ✅ 75% more violations retained
- ✅ Valid security issues not lost
- ✅ Faster processing
- ✅ Better LLM utilization

## Advanced Usage

### Custom Guardrail Engine

```python
from audit.guardrails import create_custom_guardrail_engine

# Create engine with specific checks
engine = create_custom_guardrail_engine([
    "json_validation",
    "grounding_check",
    "explanation_quality"
])

# Use engine manually
filtered_violations, results = engine.validate_output(
    violations=llm_violations,
    code=source_code,
    available_rules=rule_database,
    strict_mode=False
)
```

### Monitor Guardrail Performance

```python
# Get statistics on guardrail performance
stats = guardrail_engine.get_guardrail_statistics(guardrail_results)

# Example output:
{
    "total_guardrails": 4,
    "passed_guardrails": 4,
    "failed_guardrails": 0,
    "pass_rate": 100.0,
    "total_violations_filtered": 0,
    "guardrail_details": {
        "json_validation": {"passed": true, "filtered_count": 0, "message": "..."},
        "grounding_check": {"passed": true, "filtered_count": 0, "message": "..."},
        # ... etc
    }
}
```

## Recommendations

### For Most Users
Use the **Production Configuration** - it provides the best balance:
- Valid security issues are retained
- Obvious errors are caught
- Low false positive rate
- Fast processing

### For Security-First Environments
Use **Strict Security Mode** when rule references are critical:
- Rule database is comprehensive
- Team wants highest confidence in results
- Can tolerate some loss of valid violations

### For Development/Testing
Use **Lenient Development Mode** when:
- Exploring LLM capabilities
- Testing new codebases
- Want maximum information for manual review
- Willing to review false positives manually

## Environment Variables

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `GUARDRAILS_ENABLED` | bool | `true` | Enable/disable guardrails system |
| `GUARDRAILS_ENABLED_CHECKS` | JSON array | See below | List of enabled guardrail checks |
| `GUARDRAILS_STRICT_MODE` | bool | `false` | Fail completely on any guardrail error |
| `GUARDRAILS_MAX_CODE_LENGTH` | int | `10000` | Maximum code length for validation |
| `GUARDRAILS_MIN_EXPLANATION_LENGTH` | int | `20` | Minimum explanation length for quality check |

**Default GUARDRAILS_ENABLED_CHECKS:**
```json
["json_validation", "grounding_check", "explanation_quality", "duplicate_detection"]
```

## Troubleshooting

### All violations filtered
**Possible causes:**
1. Strict mode enabled
2. Conflicting guardrail checks
3. Rule database incomplete

**Solutions:**
1. Try production configuration
2. Review rule database completeness
3. Check Langfuse logs for specific failures

### Processing too slow
**Possible causes:**
1. Too many guardrails enabled
2. Complex validation logic

**Solutions:**
1. Use production configuration (4 checks)
2. Disable expensive checks like hallucination_check
3. Consider caching guardrail results

### Too many false positives
**Possible causes:**
1. Insufficient guardrails
2. LLM generating incorrect rule references

**Solutions:**
1. Add rule_reference check
2. Improve LLM prompt
3. Review severity consistency thresholds

## Conclusion

The guardrails system is designed to be flexible and configurable. Start with the production configuration and adjust based on your specific security requirements and tolerance for false positives.

**Key principle:** Use the minimum number of checks needed to achieve your security and quality goals. More checks = more filtering = potential loss of valid findings.
