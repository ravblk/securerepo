"""
Comprehensive Guardrails System for Security Audit Validation
Implements multi-layer trust and safety for LLM-based security analysis
"""
import logging
import re
import json
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass
from datetime import datetime
from collections import Counter

logger = logging.getLogger(__name__)


@dataclass
class GuardrailResult:
    """Result of a guardrail check"""
    guardrail_type: str
    passed: bool
    message: str
    filtered_indices: List[int] = None
    metadata: Dict = None

    def __post_init__(self):
        if self.filtered_indices is None:
            self.filtered_indices = []
        if self.metadata is None:
            self.metadata = {}


class InputValidator:
    """Validates input code and context before processing"""

    def __init__(self, max_code_length: int = 10000):
        self.max_code_length = max_code_length
        self.dangerous_patterns = [
            r'<script[^>]*>',
            r'javascript:',
            r'on\w+\s*=',
            r'eval\s*\(',
            r'__import__\s*\(',
            r'\.exec\s*\(',
        ]

    def validate_code(self, code: str, lang: str = "python") -> Tuple[bool, Optional[str]]:
        """Validate input code for safety and format"""
        if not code or not code.strip():
            return False, "Code is empty"

        if len(code) > self.max_code_length:
            return False, f"Code exceeds maximum length of {self.max_code_length} characters"

        # Check for dangerous patterns
        for pattern in self.dangerous_patterns:
            if re.search(pattern, code, re.IGNORECASE):
                return False, f"Potentially dangerous pattern detected: {pattern}"

        # Language-specific validation
        lang_validators = {
            "python": self._validate_python,
            "go": self._validate_go,
            "javascript": self._validate_javascript,
            "typescript": self._validate_typescript,
        }

        validator = lang_validators.get(lang.lower())
        if validator:
            is_valid, error = validator(code)
            if not is_valid:
                return False, error

        return True, None

    def _validate_python(self, code: str) -> Tuple[bool, Optional[str]]:
        """Validate Python code structure"""
        basic_patterns = [
            r'import\s+',
            r'from\s+\w+\s+import',
            r'def\s+\w+\s*\(',
            r'class\s+\w+\s*:',
        ]

        if not any(re.search(pattern, code, re.MULTILINE) for pattern in basic_patterns):
            return False, "Code doesn't appear to be valid Python"

        return True, None

    def _validate_go(self, code: str) -> Tuple[bool, Optional[str]]:
        """Validate Go code structure"""
        basic_patterns = [
            r'package\s+\w+',
            r'import\s+(\(|"[^"]+")',
            r'func\s+\w+\s*\(',
            r'type\s+\w+\s+',
        ]

        if not any(re.search(pattern, code, re.MULTILINE) for pattern in basic_patterns):
            return False, "Code doesn't appear to be valid Go"

        return True, None

    def _validate_javascript(self, code: str) -> Tuple[bool, Optional[str]]:
        """Validate JavaScript code structure"""
        basic_patterns = [
            r'(const|let|var)\s+\w+\s*=',
            r'function\s+\w+\s*\(',
            r'class\s+\w+\s*{',
            r'=>\s*{',
        ]

        if not any(re.search(pattern, code, re.MULTILINE) for pattern in basic_patterns):
            return False, "Code doesn't appear to be valid JavaScript"

        return True, None

    def _validate_typescript(self, code: str) -> Tuple[bool, Optional[str]]:
        """Validate TypeScript code structure"""
        basic_patterns = [
            r'(const|let|var)\s+\w+\s*:\s*\w+',
            r'function\s+\w+\s*\(',
            r'interface\s+\w+\s*{',
            r':\s*\w+\[\]',
        ]

        if not any(re.search(pattern, code, re.MULTILINE) for pattern in basic_patterns):
            return False, "Code doesn't appear to be valid TypeScript"

        return True, None


class OutputValidator:
    """Validates LLM output for quality and correctness"""

    def __init__(self):
        self.required_fields = ["rule_id", "rule_url", "severity", "explanation", "vulnerable_line"]
        self.valid_severities = ["Critical", "High", "Medium", "Low"]

    def validate_json_structure(self, violations: List[Dict]) -> GuardrailResult:
        """Validate JSON structure of violations"""
        invalid_indices = []
        issues = []

        for i, violation in enumerate(violations):
            if not isinstance(violation, dict):
                invalid_indices.append(i)
                issues.append(f"Violation {i}: Not a dictionary")
                continue

            missing_fields = [field for field in self.required_fields if field not in violation]
            if missing_fields:
                invalid_indices.append(i)
                issues.append(f"Violation {i}: Missing fields - {missing_fields}")
                continue

            # Validate severity
            severity = violation.get("severity", "")
            if severity and severity not in self.valid_severities:
                invalid_indices.append(i)
                issues.append(f"Violation {i}: Invalid severity '{severity}'")

        if invalid_indices:
            return GuardrailResult(
                guardrail_type="json_validation",
                passed=False,
                message=f"JSON structure validation failed: {len(invalid_indices)} invalid violations",
                filtered_indices=invalid_indices,
                metadata={"issues": issues}
            )

        return GuardrailResult(
            guardrail_type="json_validation",
            passed=True,
            message="All violations have valid JSON structure"
        )

    def validate_grounding(self, violations: List[Dict], code: str) -> GuardrailResult:
        """Validate that vulnerable lines exist in the original code"""
        ungrounded_indices = []
        code_normalized = code.replace(" ", "").replace("\t", "").replace("\n", "")
        code_lines = code.split('\n')

        for i, violation in enumerate(violations):
            vulnerable_line = violation.get("vulnerable_line", "")
            if not vulnerable_line:
                ungrounded_indices.append(i)
                continue

            # Try exact match first
            if vulnerable_line not in code:
                # Try normalized match
                line_normalized = vulnerable_line.replace(" ", "").replace("\t", "").replace("\n", "")
                if line_normalized not in code_normalized:
                    # Try partial match with individual lines
                    found_in_lines = False
                    for line in code_lines:
                        if vulnerable_line.strip() in line.strip() or line.strip() in vulnerable_line.strip():
                            found_in_lines = True
                            break

                    if not found_in_lines:
                        ungrounded_indices.append(i)

        if ungrounded_indices:
            rejected = len(ungrounded_indices) / len(violations) * 100
            return GuardrailResult(
                guardrail_type="grounding_check",
                passed=False,
                message=f"Grounding check failed: {len(ungrounded_indices)} violations not found in code ({rejected:.1f}%)",
                filtered_indices=ungrounded_indices,
                metadata={
                    "ungrounded_count": len(ungrounded_indices),
                    "ungrounded_percentage": rejected
                }
            )

        return GuardrailResult(
            guardrail_type="grounding_check",
            passed=True,
            message="All violations are properly grounded in the code"
        )

    def validate_rule_references(self, violations: List[Dict], available_rules: List[Dict]) -> GuardrailResult:
        """Validate that rule_ids and URLs are valid"""
        invalid_indices = []
        available_rule_ids = {rule.get("rule_id", "") for rule in available_rules}

        for i, violation in enumerate(violations):
            rule_id = violation.get("rule_id", "")
            rule_url = violation.get("rule_url", "")

            # Check if rule_id exists in available rules
            if rule_id and rule_id not in available_rule_ids and rule_id != "unknown":
                invalid_indices.append(i)

            # Check URL format
            if rule_url and rule_url != "N/A":
                if not re.match(r'^https?://', rule_url):
                    invalid_indices.append(i)

        if invalid_indices:
            return GuardrailResult(
                guardrail_type="rule_reference",
                passed=False,
                message=f"Rule reference validation failed: {len(invalid_indices)} violations reference non-existent rules",
                filtered_indices=invalid_indices,
                metadata={
                    "invalid_references": invalid_indices,
                    "available_rule_ids": list(available_rule_ids)
                }
            )

        return GuardrailResult(
            guardrail_type="rule_reference",
            passed=True,
            message="All rule references are valid"
        )


class SafetyValidator:
    """Validates safety and compliance of audit results"""

    def validate_hallucinations(self, violations: List[Dict], available_rules: List[Dict]) -> GuardrailResult:
        """Detect potential LLM hallucinations"""
        hallucinated_indices = []
        available_rule_ids = {rule.get("rule_id", "") for rule in available_rules}

        for i, violation in enumerate(violations):
            rule_id = violation.get("rule_id", "")
            explanation = violation.get("explanation", "")

            # Check if rule_id exists
            if rule_id and rule_id not in available_rule_ids:
                hallucinated_indices.append(i)
                continue

            # Check for generic explanations that might indicate hallucination
            generic_patterns = [
                r"^(violates|breaks|contradicts)\s+rule\s\d+",
                r"^(this|the)\s+code\s+(is|contains|has|has)\s+(a\s+)?(security\s+)?(issue|vulnerability|problem)",
                r"^(found|detected)\s+(a\s+)?(security\s+)?(issue|vulnerability|problem)",
            ]

            if any(re.match(pattern, explanation.lower()) for pattern in generic_patterns):
                # Check if explanation is too generic (short)
                if len(explanation) < 50:
                    hallucinated_indices.append(i)

        if hallucinated_indices:
            return GuardrailResult(
                guardrail_type="hallucination_check",
                passed=False,
                message=f"Hallucination check failed: {len(hallucinated_indices)} violations potentially hallucinated",
                filtered_indices=hallucinated_indices,
                metadata={
                    "hallucinated_count": len(hallucinated_indices),
                    "hallucinated_indices": hallucinated_indices
                }
            )

        return GuardrailResult(
            guardrail_type="hallucination_check",
            passed=True,
            message="No hallucinations detected"
        )

    def validate_severity_consistency(self, violations: List[Dict]) -> GuardrailResult:
        """Validate that severity levels are consistent with explanations"""
        inconsistent_indices = []
        severity_keywords = {
            "Critical": ["exploitable", "remote code execution", "arbitrary code", "privilege escalation",
                        "complete bypass", "code injection", "command injection", "sql injection"],
            "High": ["injection", "xss", "csrf", "authentication bypass", "authorization", "arbitrary file"],
            "Medium": ["information disclosure", "denial of service", "brute force", "weak authentication"],
            "Low": ["information leak", "best practice", "recommendation", "improvement"]
        }

        for i, violation in enumerate(violations):
            severity = violation.get("severity", "Medium")
            explanation = violation.get("explanation", "").lower()

            expected_keywords = severity_keywords.get(severity, [])

            # For higher severity, check if expected keywords are present
            if severity in ["Critical", "High"]:
                has_required_keywords = any(keyword in explanation for keyword in expected_keywords)

                if not has_required_keywords and len(explanation) > 30:
                    inconsistent_indices.append({
                        "index": i,
                        "severity": severity,
                        "issue": "High severity without appropriate keywords",
                        "explanation_snippet": explanation[:50]
                    })

        if inconsistent_indices:
            return GuardrailResult(
                guardrail_type="severity_consistency",
                passed=False,
                message=f"Severity consistency check failed: {len(inconsistent_indices)} inconsistent violations",
                filtered_indices=[item["index"] for item in inconsistent_indices],
                metadata={"inconsistent_violations": inconsistent_indices}
            )

        return GuardrailResult(
            guardrail_type="severity_consistency",
            passed=True,
            message="Severity levels are consistent with explanations"
        )


class QualityValidator:
    """Validates quality and completeness of audit results"""

    def validate_explanation_quality(self, violations: List[Dict]) -> GuardrailResult:
        """Validate that explanations are meaningful and specific"""
        poor_quality_indices = []
        min_explanation_length = 20

        for i, violation in enumerate(violations):
            explanation = violation.get("explanation", "")

            if len(explanation) < min_explanation_length:
                poor_quality_indices.append(i)
                continue

            # Check for template-like responses
            template_patterns = [
                r"^(violates|breaks|contradicts)\s+rule",
                r"^(this|the)\s+code\s+(is|contains|has)",
                r"^(found|detected)\s+(a\s+)?(security\s+)?(issue|vulnerability|problem)",
            ]

            if any(re.match(pattern, explanation.lower()) for pattern in template_patterns):
                if len(explanation) < 50:
                    poor_quality_indices.append(i)

        if poor_quality_indices:
            return GuardrailResult(
                guardrail_type="explanation_quality",
                passed=False,
                message=f"Explanation quality check failed: {len(poor_quality_indices)} poor quality explanations",
                filtered_indices=poor_quality_indices,
                metadata={
                    "poor_quality_count": len(poor_quality_indices)
                }
            )

        return GuardrailResult(
            guardrail_type="explanation_quality",
            passed=True,
            message="All explanations are meaningful and specific"
        )

    def detect_duplicates(self, violations: List[Dict]) -> GuardrailResult:
        """Detect duplicate or similar violations"""
        duplicates = []

        for i in range(len(violations)):
            for j in range(i + 1, len(violations)):
                if self._are_duplicates(violations[i], violations[j]):
                    duplicates.append((i, j))

        if duplicates:
            # Keep only the first occurrence of each duplicate
            duplicate_indices_to_remove = [j for (i, j) in duplicates]

            return GuardrailResult(
                guardrail_type="duplicate_detection",
                passed=False,
                message=f"Duplicate detection found: {len(duplicates)} duplicate violations",
                filtered_indices=duplicate_indices_to_remove,
                metadata={
                    "duplicate_pairs": duplicates
                }
            )

        return GuardrailResult(
            guardrail_type="duplicate_detection",
            passed=True,
            message="No duplicate violations found"
        )

    def _are_duplicates(self, violation1: Dict, violation2: Dict) -> bool:
        """Check if two violations are duplicates"""
        # Check same rule_id and vulnerable_line
        same_rule = violation1.get("rule_id") == violation2.get("rule_id")
        same_line = violation1.get("vulnerable_line") == violation2.get("vulnerable_line")

        if same_rule and same_line:
            return True

        # Check similar explanations (simple similarity check)
        expl1 = violation1.get("explanation", "")
        expl2 = violation2.get("explanation", "")

        if expl1 and expl2:
            # Check if explanations are very similar
            similarity = self._string_similarity(expl1, expl2)
            if similarity > 0.8:  # 80% similarity threshold
                return True

        return False

    def _string_similarity(self, str1: str, str2: str) -> float:
        """Calculate simple string similarity"""
        if not str1 or not str2:
            return 0.0

        set1 = set(str1.lower().split())
        set2 = set(str2.lower().split())

        intersection = set1 & set2
        union = set1 | set2

        if not union:
            return 0.0

        return len(intersection) / len(union)


class GuardrailEngine:
    """Main guardrail validation engine"""

    def __init__(self, enabled_checks: List[str] = None):
        self.input_validator = InputValidator()
        self.output_validator = OutputValidator()
        self.safety_validator = SafetyValidator()
        self.quality_validator = QualityValidator()
        self.enabled_checks = enabled_checks or [
            "json_validation",
            "grounding_check",
            "explanation_quality",
            "duplicate_detection"
        ]
        logger.info(f"GuardrailEngine initialized with enabled checks: {self.enabled_checks}")

    def validate_input(self, code: str, lang: str = "python") -> Tuple[bool, Optional[str]]:
        """Validate input code before processing"""
        is_valid, error = self.input_validator.validate_code(code, lang)
        return is_valid, error

    def validate_output(
        self,
        violations: List[Dict],
        code: str,
        available_rules: List[Dict],
        strict_mode: bool = False
    ) -> Tuple[List[Dict], Dict[str, GuardrailResult]]:
        """
        Validate output violations with multiple guardrails

        Args:
            violations: LLM output violations
            code: Original code that was analyzed
            available_rules: Security rules that were available to LLM
            strict_mode: If True, reject entire output on any guardrail failure

        Returns:
            Tuple of (filtered_violations, guardrail_results)
        """
        if not violations:
            return [], {}

        guardrail_results = {}
        indices_to_remove = set()

        # Map all available validators with their names
        all_validators = {
            "json_validation": lambda: self.output_validator.validate_json_structure(violations),
            "grounding_check": lambda: self.output_validator.validate_grounding(violations, code),
            "rule_reference": lambda: self.output_validator.validate_rule_references(violations, available_rules),
            "hallucination_check": lambda: self.safety_validator.validate_hallucinations(violations, available_rules),
            "severity_consistency": lambda: self.safety_validator.validate_severity_consistency(violations),
            "explanation_quality": lambda: self.quality_validator.validate_explanation_quality(violations),
            "duplicate_detection": lambda: self.quality_validator.detect_duplicates(violations),
        }

        # Filter to only enabled validators
        enabled_validators = {
            name: validator
            for name, validator in all_validators.items()
            if name in self.enabled_checks
        }

        logger.info(f"Running {len(enabled_validators)} enabled guardrail checks: {list(enabled_validators.keys())}")

        # Run enabled validators
        for name, validator_func in enabled_validators.items():
            try:
                result = validator_func()
                guardrail_results[name] = result

                if not result.passed and strict_mode:
                    # In strict mode, fail completely on any validation error
                    logger.error(f"Strict mode enabled - failing on guardrail '{name}'")
                    return [], guardrail_results

                indices_to_remove.update(result.filtered_indices)

            except Exception as e:
                logger.error(f"Error in guardrail '{name}': {e}")
                guardrail_results[name] = GuardrailResult(
                    guardrail_type=name,
                    passed=False,
                    message=f"Guardrail error: {str(e)}"
                )
                if strict_mode:
                    return [], guardrail_results

        # Filter violations
        filtered_violations = [
            violation for i, violation in enumerate(violations)
            if i not in indices_to_remove
        ]

        logger.info(
            f"Guardrail validation completed: "
            f"{len(filtered_violations)}/{len(violations)} violations passed "
            f"({len(indices_to_remove)} removed, {len(violations) - len(filtered_violations)} filtered)"
        )

        # Summary statistics
        passed_count = sum(1 for result in guardrail_results.values() if result.passed)
        failed_count = len(guardrail_results) - passed_count

        logger.info(
            f"Guardrail summary: {passed_count}/{len(guardrail_results)} passed, "
            f"{failed_count} failed"
        )

        return filtered_violations, guardrail_results

    def get_guardrail_statistics(self, guardrail_results: Dict[str, GuardrailResult]) -> Dict:
        """Generate statistics about guardrail performance"""
        total_violations_removed = sum(len(result.filtered_indices) for result in guardrail_results.values())

        passed_guardrails = sum(1 for result in guardrail_results.values() if result.passed)
        failed_guardrails = len(guardrail_results) - passed_guardrails

        return {
            "total_guardrails": len(guardrail_results),
            "passed_guardrails": passed_guardrails,
            "failed_guardrails": failed_guardrails,
            "pass_rate": (passed_guardrails / len(guardrail_results) * 100) if guardrail_results else 0,
            "total_violations_filtered": total_violations_removed,
            "guardrail_details": {
                name: {
                    "passed": result.passed,
                    "filtered_count": len(result.filtered_indices),
                    "message": result.message
                }
                for name, result in guardrail_results.items()
            }
        }


# Singleton instance for application-wide use (config will be imported at module level)
def _create_guardrail_engine():
    """Create singleton GuardrailEngine instance with settings from config."""
    try:
        from .config import settings
        return GuardrailEngine(enabled_checks=settings.guardrails_enabled_checks)
    except Exception as e:
        logger.warning(f"Could not create GuardrailEngine with settings: {e}. Using default enabled checks.")
        return GuardrailEngine()

guardrail_engine = _create_guardrail_engine()


def create_custom_guardrail_engine(enabled_checks: List[str]) -> GuardrailEngine:
    """
    Create a custom GuardrailEngine instance with specific enabled checks.

    Args:
        enabled_checks: List of guardrail check names to enable. Options:
            - json_validation
            - grounding_check
            - rule_reference
            - hallucination_check
            - severity_consistency
            - explanation_quality
            - duplicate_detection

    Returns:
        GuardrailEngine instance configured with specified checks

    Example:
        engine = create_custom_guardrail_engine(["json_validation", "grounding_check"])
    """
    return GuardrailEngine(enabled_checks=enabled_checks)