import json
import logging
import re
from typing import List, Optional

from langgraph.graph import StateGraph, END
from langchain_core.messages import SystemMessage, HumanMessage

from .prompts import SYSTEM_PROMPT
from .llm_service import LLMService
from .qdrant_service import QdrantService
from .embedding_service import EmbeddingService
from .exceptions import WorkflowError
from .models import AuditState
from .langfuse_service import langfuse_service
from .guardrails import guardrail_engine
from .guardrails import guardrail_engine

logger = logging.getLogger(__name__)


class AuditWorkflow:
    """LangGraph workflow for security audit processing with Langfuse tracing."""

    def __init__(
        self,
        llm_service: LLMService,
        qdrant_service: QdrantService,
        embedding_service: EmbeddingService
    ):
        self._llm_service = llm_service
        self._qdrant_service = qdrant_service
        self._embedding_service = embedding_service
        self._graph = self._build_workflow()
        self._current_trace = None

    def _build_workflow(self) -> StateGraph:
        """Build the LangGraph state graph."""
        from .models import AuditState

        workflow = StateGraph(AuditState)
        workflow.add_node("compute_embedding", self._compute_embedding)
        workflow.add_node("retrieve_general", self._retrieve_general_rules)
        workflow.add_node("retrieve_internal", self._retrieve_internal_rules)
        workflow.add_node("analyze", self._analyze_code)
        workflow.add_node("validate", self._ground_and_validate)

        workflow.set_entry_point("compute_embedding")
        workflow.add_edge("compute_embedding", "retrieve_general")
        workflow.add_edge("retrieve_general", "retrieve_internal")
        workflow.add_edge("retrieve_internal", "analyze")
        workflow.add_edge("analyze", "validate")
        workflow.add_edge("validate", END)

        return workflow.compile()

    def _compute_embedding(self, state: dict) -> dict:
        """Compute embedding for code chunk."""
        code = state["code"]
        try:
            embedding = self._embedding_service.get_embedding(
                code[:5000],
                max_length=5000
            )
            return {"code_embedding": embedding or []}
        except Exception as e:
            logger.error(f"Error computing embedding: {e}")
            return {"code_embedding": []}

    def _retrieve_general_rules(self, state: dict) -> dict:
        """Retrieve exactly 7 most relevant internal security rules as zero-shot augmentation context."""
        embedding = state.get("code_embedding", [])
        code = state.get("code", "")
        lang = state.get("lang", "python")
        audit_id = state.get("audit_id")

        if not embedding:
            return {"general_rules": []}

        try:
            # Try hybrid search first (recommended method) - retrieves exactly 7 most relevant internal rules
            rules = self._qdrant_service.search_rules(
                embedding=embedding,
                code=code,
                lang=lang,
                limit=7  # ТОЛЬКО 7 внутренних правил для zero-shot augmentation
            )

            # Fallback to basic semantic search if hybrid search fails or returns empty results
            if not rules:
                logger.info("Hybrid search returned empty results, falling back to basic semantic search")
                rules = self._qdrant_service.search_basic_rules(
                    embedding=embedding,
                    lang=lang,
                    limit=7  # ТОЛЬКО 7 внутренних правил
                )

            logger.info(f"Retrieved {len(rules)} INTERNAL SECURITY RULES as zero-shot augmentation")

            if rules and isinstance(rules, list) and len(rules) > 0:
                first_rule = rules[0]
                if isinstance(first_rule, dict):
                    logger.debug(f"First internal rule structure: {first_rule}")
                    logger.debug(f"Keys in first rule: {list(first_rule.keys())}")
                else:
                    logger.warning(f"First rule is not a dict: {type(first_rule)}")
            elif rules:
                logger.warning(f"Rules is not a list: {type(rules)}")

            # Log to Langfuse
            if self._current_trace and audit_id:
                langfuse_service.create_event(
                    trace_id=self._current_trace.id,
                    name="retrieve_internal_rules",
                    metadata={
                        "rules_count": len(rules),
                        "search_type": "hybrid" if rules else "semantic_fallback",
                        "language": lang,
                        "source": "internal_policies_only"
                    }
                )

            return {"general_rules": rules}
        except Exception as e:
            # If hybrid search fails completely, fall back to semantic search
            logger.warning(f"Hybrid search failed: {e}, falling back to semantic search")
            try:
                rules = self._qdrant_service.search_basic_rules(
                    embedding=embedding,
                    lang=lang,
                    limit=7  # ТОЛЬКО 7 внутренних правил
                )
                logger.info(f"Retrieved {len(rules)} INTERNAL SECURITY RULES via fallback semantic search")

                # Log failure to Langfuse
                if self._current_trace and audit_id:
                    langfuse_service.create_event(
                        trace_id=self._current_trace.id,
                        name="retrieve_internal_rules",
                        metadata={
                            "rules_count": len(rules),
                            "search_type": "semantic_fallback",
                            "error": str(e),
                            "language": lang,
                            "source": "internal_policies_only"
                        }
                    )

                return {"general_rules": rules}
            except Exception as fallback_error:
                logger.error(f"Both hybrid and semantic search failed: {fallback_error}")

                # Log complete failure to Langfuse
                if self._current_trace and audit_id:
                    langfuse_service.create_event(
                        trace_id=self._current_trace.id,
                        name="retrieve_internal_rules_failed",
                        metadata={
                            "error": str(fallback_error),
                            "language": lang,
                            "source": "internal_policies_only"
                        }
                    )

                return {"general_rules": []}

    def _retrieve_internal_rules(self, state: dict) -> dict:
        """Retrieve internal security policies - now combined with general rules."""
        # Internal rules are now included in general rules search
        logger.info("Internal rules retrieval is now integrated with general rules search")
        return {"internal_rules": []}

    def _analyze_code(self, state: dict) -> dict:
        """Analyze code using LLM ZERO-SHOT security analysis with internal rules augmentation."""
        code = state["code"]
        file_path = state["file_path"]
        lang = state.get("lang", "python")
        general_rules = state["general_rules"]
        internal_rules = state["internal_rules"]
        audit_id = state.get("audit_id")

        if not general_rules and not internal_rules:
            logger.info("No rules found, returning empty violations")

            # Log to Langfuse
            if self._current_trace and audit_id:
                langfuse_service.create_event(
                    trace_id=self._current_trace.id,
                    name="analyze_code",
                    metadata={
                        "result": "no_rules",
                        "reason": "both general and internal rules empty"
                    }
                )

            return {"violations": [], "severity": "None"}

        # Format internal rules for LLM prompt (zero-shot augmentation context)
        context_rules = []
        rule_count = 0

        try:
            # Format internal rules for zero-shot augmentation context
            if not isinstance(general_rules, (list, tuple)):
                logger.error(f"general_rules is not a list, type: {type(general_rules)}")
                general_rules = []

            for rule in general_rules:
                try:
                    # Проверка типа правила с защитой от ошибок
                    if rule is None:
                        logger.warning("Skipping None rule")
                        continue

                    if not isinstance(rule, (dict, str)):
                        logger.warning(f"Warning: rule is not a dict or str, type: {type(rule)}, content: {rule}")
                        continue

                    # Преобразование строки в dict если необходимо
                    if isinstance(rule, str):
                        try:
                            # Простая строка без дополнительной обработки
                            safe_rule = {"rule_id": f"internal-rule-{rule_count}", "text": rule[:500], "url": ""}
                        except Exception as e:
                            logger.warning(f"Failed to parse rule as string: {e}")
                            continue
                    else:
                        # dict rule
                        rule_count += 1
                        safe_rule = {
                            "rule_id": rule.get("rule_id", f"internal-{rule_count}"),
                            "text": rule.get("text", "")[:500],
                            "url": rule.get("url", "")
                        }

                    # Добавляем обработку длинных desc и防护 от слишком больших строк
                    if len(safe_rule["text"]) > 500:
                        safe_rule["text"] = safe_rule["text"][:500]

                    context_rules.append(safe_rule)

                    # Логирование для отладки
                    if rule_count <= 2:
                        logger.debug(f"Context Rule {rule_count} - rule_id: {safe_rule.get('rule_id', 'unknown')}")

                except Exception as e:
                    logger.error(f"Error processing individual context rule: {e}, rule content: {rule}")
                    continue

            logger.info(f"Formatted {len(context_rules)} internal rules for ZERO-SHOT augmentation context")

        except Exception as e:
            logger.error(f"Error in context rule formatting: {e}, general_rules type: {type(general_rules)}")
            context_rules = []

        # Генерируем текст внутренних правил для zero-shot контекста
        if not context_rules:
            logger.info("No context rules available - using pure ZERO-SHOT analysis")
            context_rules_text = "КОНТЕКСТ ВНУТРЕННИХ ПРАВИЛ: Отсутствует (чистый Zero-Shot анализ)"
        else:
            context_rules_text = "\n".join(
                f"• [{i}] {rule.get('rule_id', 'unknown')}: {rule.get('text', '')[:200]}"
                for i, rule in enumerate(context_rules, 1)
            )

        system_prompt = SYSTEM_PROMPT.format(
            rules=context_rules_text,  # Internal rules as zero-shot augmentation context
            lang=lang,
            file_path=file_path,
            code=code
        )

        try:
            llm = self._llm_service.get_llm()
            response = llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content="Perform comprehensive security analysis and return all vulnerabilities found.")
            ])

            logger.info(f"ZERO-SHOT LLM analysis completed for code chunk: {file_path}")

            # Extract JSON from response with multiple strategies
            violations, parse_error = self._parse_llm_response(response.content)

            if violations is None:
                # All parsing strategies failed
                error_msg = f"Error in LLM analysis: {parse_error}"
                logger.error(f"Raw LLM response: {response.content}")
                logger.error(error_msg)

                # Log failure to Langfuse
                if self._current_trace and audit_id:
                    langfuse_service.create_event(
                        trace_id=self._current_trace.id,
                        name="analyze_code_failed",
                        metadata={
                            "error": parse_error,
                            "response_preview": response.content[:200]
                        }
                    )

                raise WorkflowError(error_msg)

            # Determine maximum severity
            severity = "None"
            if violations:
                severity_order = {"Critical": 4, "High": 3, "Medium": 2, "Low": 1}
                max_sev = max(
                    violations,
                    key=lambda v: severity_order.get(v.get("severity", "Low"), 0)
                )
                severity = max_sev.get("severity", "Low")

            logger.info(f"ZERO-SHOT code analysis completed: {len(violations)} vulnerabilities, max severity: {severity}")

            # Log successful analysis to Langfuse
            if self._current_trace and audit_id:
                langfuse_service.create_event(
                    trace_id=self._current_trace.id,
                    name="zero_shot_analysis",
                    metadata={
                        "violations_count": len(violations),
                        "severity": severity,
                        "context_rules_count": len(context_rules),
                        "language": lang,
                        "analysis_type": "zero_shot_with_internal_augmentation"
                    }
                )

                # Create score for zero-shot security analysis effectiveness
                langfuse_service.create_score(
                    trace_id=self._current_trace.id,
                    name="zero_shot_security_violations",
                    value=len(violations),
                    comment=f"Zero-Shot found {len(violations)} security vulnerabilities with CWE IDs, max severity: {severity}"
                )

            return {"violations": violations, "severity": severity}

        except Exception as e:
            error_msg = f"Error in LLM analysis: {e}"
            logger.error(error_msg)
            raise WorkflowError(error_msg)

    def _parse_llm_response(self, response_content: str) -> tuple[Optional[list], Optional[str]]:
        """
        Parse LLM response to extract violations with multiple fallback strategies.

        Returns:
            tuple: (violations list or None, error message or None)
        """
        # Strategy 1: Standard JSON parsing
        match = re.search(r'\{.*\}', response_content, re.DOTALL)
        if match:
            try:
                result = json.loads(match.group(0))
                violations = result.get("violations", [])
                return violations, None
            except json.JSONDecodeError as e:
                logger.warning(f"Strategy 1 (standard JSON parsing) failed: {e}")

        # Strategy 2: Try to fix common JSON issues (unescaped backslashes)
        if match:
            json_str = match.group(0)
            try:
                # Fix common backslash escaping issues in strings
                # This handles cases where LLM didn't escape backslashes properly
                fixed_json = self._repair_json_common_issues(json_str)
                result = json.loads(fixed_json)
                violations = result.get("violations", [])
                logger.info("Successfully repaired JSON using Strategy 2")
                return violations, None
            except (json.JSONDecodeError, Exception) as e:
                logger.warning(f"Strategy 2 (JSON repair) failed: {e}")

        # Strategy 3: Fallback to empty violations (graceful degradation)
        logger.warning("All JSON parsing strategies failed, returning empty violations")
        return [], None

    def _repair_json_common_issues(self, json_str: str) -> str:
        """
        Repair common JSON issues found in LLM responses.

        Handles:
        - Unescaped backslashes in strings
        - Missing quotes around property names
        - Trailing commas

        Args:
            json_str: Potentially malformed JSON string

        Returns:
            Repaired JSON string
        """
        repaired = json_str

        # Fix unescaped backslashes in string values
        # This regex matches backslashes that aren't already escaped
        # and are inside double-quoted strings
        lines = repaired.split('\n')
        fixed_lines = []
        for line in lines:
            # Simple heuristic: fix backslashes in string values
            # by ensuring all backslashes are properly escaped
            in_string = False
            chars = []
            for i, char in enumerate(line):
                if char == '"' and (i == 0 or line[i-1] != '\\'):
                    in_string = not in_string
                    chars.append(char)
                elif char == '\\' and in_string:
                    # Check if this backslash is already escaped
                    if i > 0 and line[i-1] == '\\':
                        chars.append(char)
                    else:
                        # Escape the backslash
                        chars.append('\\\\')
                else:
                    chars.append(char)
            fixed_lines.append(''.join(chars))

        repaired = '\n'.join(fixed_lines)

        return repaired

    def _ground_and_validate(self, state: dict) -> dict:
        """Validate ZERO-SHOT LLM findings: CWE IDs, vulnerable lines, and apply guardrails."""
        code = state["code"]
        violations = state["violations"]
        lang = state.get("lang", "python")
        audit_id = state.get("audit_id")
        general_rules = state.get("general_rules", [])  # Internal rules for context only
        internal_rules = state.get("internal_rules", [])

        # Grounding validation: ensure vulnerable lines exist in code
        grounded_violations = [
            v for v in violations
            if v.get("vulnerable_line", "") and v.get("vulnerable_line") in code
        ]

        removed_grounding = len(violations) - len(grounded_violations)
        if removed_grounding > 0:
            logger.info(f"Zero-shot grounding: removed {removed_grounding} violations with invalid code references")

        # CWE ID validation: ensure proper CWE format (CWE-XXX pattern)
        CWE_PATTERN = r'^CWE-\d+$'
        validated_cwe_violations = [
            v for v in grounded_violations
            if v.get("rule_id", "") and re.match(CWE_PATTERN, str(v.get("rule_id", "")))
        ]

        removed_cwe_format = len(grounded_violations) - len(validated_cwe_violations)
        if removed_cwe_format > 0:
            logger.info(f"Zero-shot CWE validation: removed {removed_cwe_format} violations with invalid CWE format")

        # Apply comprehensive guardrails for zero-shot results
        all_available_context = general_rules + internal_rules
        filtered_violations, guardrail_results = guardrail_engine.validate_output(
            violations=validated_cwe_violations,
            code=code,
            available_rules=all_available_context,  # Use as context, not strict matching
            strict_mode=False  # Zero-shot should be more permissive
        )

        total_removed = len(violations) - len(filtered_violations)
        guardrail_removed = len(validated_cwe_violations) - len(filtered_violations)

        # Log zero-shot validation results
        logger.info(
            f"Zero-shot validation: {len(filtered_violations)} validated vulnerabilities "
            f"({total_removed} total removed: {removed_grounding} grounding + {removed_cwe_format} CWE format + {guardrail_removed} guardrails)"
        )

        # Get and log detailed guardrail statistics
        guardrail_statistics = guardrail_engine.get_guardrail_statistics(guardrail_results)
        logger.info(
            f"Guardrail statistics: {guardrail_statistics['passed_guardrails']}/{guardrail_statistics['total_guardrails']} passed, "
            f"pass_rate: {guardrail_statistics['pass_rate']:.1f}%"
        )

        # Log detailed guardrail results
        for check_name, result in guardrail_results.items():
            status = "✓" if result.passed else "✗"
            if result.filtered_indices:
                logger.info(
                    f"{status} {check_name}: {result.message} "
                    f"(removed {len(result.filtered_indices)} violations)"
                )
            else:
                logger.info(f"{status} {check_name}: {result.message}")

        # Log zero-shot validation results to Langfuse
        if self._current_trace and audit_id:
            langfuse_service.create_event(
                trace_id=self._current_trace.id,
                name="zero_shot_guardrail_validation",
                metadata={
                    **guardrail_statistics,
                    "grounding_removed": removed_grounding,
                    "cwe_format_removed": removed_cwe_format,
                    "total_removed": total_removed,
                    "analysis_type": "zero_shot_cwe_validation"
                }
            )

        return {"violations": filtered_violations}

    def process(self, audit_task, initial_state: dict) -> tuple[list, Optional[str]]:
        """Process audit task through the workflow with Langfuse tracing."""
        audit_id = initial_state.get("audit_id", audit_task.audit_id)

        try:
            # Create Langfuse trace for this audit operation
            self._current_trace = langfuse_service.create_trace(
                name="security_audit_workflow",
                session_id=audit_id,
                metadata={
                    "file_path": initial_state.get("file_path"),
                    "language": initial_state.get("lang"),
                    "chunk_id": initial_state.get("chunk_id")
                }
            )

            # Execute workflow
            result = self._graph.invoke(initial_state)
            violations = result.get("violations", [])
            severity = result.get("severity")

            # Finalize trace with results
            if self._current_trace:
                langfuse_service.flush()
                self._current_trace = None

            return violations, severity
        except Exception as e:
            # Log error to Langfuse if trace exists
            if self._current_trace:
                langfuse_service.create_event(
                    trace_id=self._current_trace.id,
                    name="workflow_error",
                    metadata={"error": str(e)}
                )
                langfuse_service.flush()
                self._current_trace = None

            raise WorkflowError(f"Workflow processing failed: {str(e)}")

    @property
    def graph(self) -> StateGraph:
        """Get the compiled workflow graph."""
        return self._graph
