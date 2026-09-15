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
        """Retrieve general security rules from Qdrant using hybrid semantic + keyword search."""
        embedding = state.get("code_embedding", [])
        code = state.get("code", "")
        lang = state.get("lang", "python")
        audit_id = state.get("audit_id")

        if not embedding:
            return {"general_rules": []}

        try:
            # Try hybrid search first (recommended method)
            rules = self._qdrant_service.search_general_rules_hybrid(
                embedding=embedding,
                code=code,
                lang=lang,
                limit=3
            )

            # Fallback to semantic-only if hybrid search fails or returns empty results
            if not rules:
                logger.info("Hybrid search returned empty results, falling back to semantic search")
                rules = self._qdrant_service.search_general_rules(
                    embedding=embedding,
                    lang=lang,
                    limit=3
                )

            logger.info(f"Retrieved {len(rules)} general rules via hybrid search")

            if rules and isinstance(rules, list) and len(rules) > 0:
                first_rule = rules[0]
                if isinstance(first_rule, dict):
                    logger.debug(f"First general rule structure: {first_rule}")
                    logger.debug(f"Keys in first rule: {list(first_rule.keys())}")
                else:
                    logger.warning(f"First rule is not a dict: {type(first_rule)}")
            elif rules:
                logger.warning(f"Rules is not a list: {type(rules)}")

            # Log to Langfuse
            if self._current_trace and audit_id:
                langfuse_service.create_event(
                    trace_id=self._current_trace.id,
                    name="retrieve_general_rules",
                    metadata={
                        "rules_count": len(rules),
                        "search_type": "hybrid" if rules else "semantic_fallback",
                        "language": lang
                    }
                )

            return {"general_rules": rules}
        except Exception as e:
            # If hybrid search fails completely, fall back to semantic search
            logger.warning(f"Hybrid search failed: {e}, falling back to semantic search")
            try:
                rules = self._qdrant_service.search_general_rules(
                    embedding=embedding,
                    lang=lang,
                    limit=3
                )
                logger.info(f"Retrieved {len(rules)} general rules via fallback semantic search")

                # Log failure to Langfuse
                if self._current_trace and audit_id:
                    langfuse_service.create_event(
                        trace_id=self._current_trace.id,
                        name="retrieve_general_rules",
                        metadata={
                            "rules_count": len(rules),
                            "search_type": "semantic_fallback",
                            "error": str(e),
                            "language": lang
                        }
                    )

                return {"general_rules": rules}
            except Exception as fallback_error:
                logger.error(f"Both hybrid and semantic search failed: {fallback_error}")

                # Log complete failure to Langfuse
                if self._current_trace and audit_id:
                    langfuse_service.create_event(
                        trace_id=self._current_trace.id,
                        name="retrieve_general_rules_failed",
                        metadata={
                            "error": str(fallback_error),
                            "language": lang
                        }
                    )

                return {"general_rules": []}

    def _retrieve_internal_rules(self, state: dict) -> dict:
        """Retrieve internal security policies from Qdrant using hybrid semantic + keyword search."""
        embedding = state.get("code_embedding", [])
        code = state.get("code", "")
        audit_id = state.get("audit_id")

        if not embedding:
            return {"internal_rules": []}

        try:
            # Try hybrid search first (recommended method for internal policies)
            rules = self._qdrant_service.search_internal_rules_hybrid(
                embedding=embedding,
                code=code,
                limit=2
            )

            # Fallback to semantic-only if hybrid search fails or returns empty results
            if not rules:
                logger.info("Hybrid search returned empty results, falling back to semantic search")
                rules = self._qdrant_service.search_internal_rules(
                    embedding=embedding,
                    limit=2
                )

            logger.info(f"Retrieved {len(rules)} internal rules via hybrid search")

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
                        "search_type": "hybrid" if rules else "semantic_fallback"
                    }
                )

            return {"internal_rules": rules}
        except Exception as e:
            # If hybrid search fails completely, fall back to semantic search
            logger.warning(f"Hybrid search failed: {e}, falling back to semantic search")
            try:
                rules = self._qdrant_service.search_internal_rules(
                    embedding=embedding,
                    limit=2
                )
                logger.info(f"Retrieved {len(rules)} internal rules via fallback semantic search")

                # Log failure to Langfuse
                if self._current_trace and audit_id:
                    langfuse_service.create_event(
                        trace_id=self._current_trace.id,
                        name="retrieve_internal_rules",
                        metadata={
                            "rules_count": len(rules),
                            "search_type": "semantic_fallback",
                            "error": str(e)
                        }
                    )

                return {"internal_rules": rules}
            except Exception as fallback_error:
                logger.error(f"Both hybrid and semantic search failed: {fallback_error}")

                # Log complete failure to Langfuse
                if self._current_trace and audit_id:
                    langfuse_service.create_event(
                        trace_id=self._current_trace.id,
                        name="retrieve_internal_rules_failed",
                        metadata={
                            "error": str(fallback_error)
                        }
                    )

                return {"internal_rules": []}

    def _analyze_code(self, state: dict) -> dict:
        """Analyze code using LLM with retrieved rules and Langfuse tracing."""
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

        # Format rules for LLM prompt (только rule_url)
        updated_rules = []
        rule_count = 0

        try:
            # Проверяем, что general_rules и internal_rules являются списками
            if not isinstance(general_rules, (list, tuple)):
                logger.error(f"general_rules is not a list, type: {type(general_rules)}")
                general_rules = []

            if not isinstance(internal_rules, (list, tuple)):
                logger.error(f"internal_rules is not a list, type: {type(internal_rules)}")
                internal_rules = []

            for rule in general_rules + internal_rules:
                try:
                    # Проверяем, каждое правило является словарем
                    if not isinstance(rule, dict):
                        logger.warning(f"Warning: rule is not a dict, type: {type(rule)}, content: {rule}")
                        continue

                    rule_count += 1
                    # Проверяем наличие необходимых ключей и добавляем значения по умолчанию
                    safe_rule = {
                        "rule_id": rule.get("rule_id", "unknown"),
                        "text": rule.get("text", "")[:500],
                        "url": rule.get("url", "")
                    }
                    updated_rules.append(safe_rule)

                    # Логирование подсвечников для отладки
                    if rule_count <= 2:
                        logger.debug(f"Rule {rule_count} - Keys: {list(rule.keys())}, rule_id: {safe_rule.get('rule_id', 'unknown')}")

                except Exception as e:
                    logger.error(f"Error processing individual rule: {e}, rule content: {rule}")
                    continue

            logger.info(f"Formatted {len(updated_rules)} rules for LLM prompt from {rule_count} total rules")

        except Exception as e:
            logger.error(f"Error in rule formatting preprocessing: {e}, general_rules type: {type(general_rules)}, internal_rules type: {type(internal_rules)}")
            # Используем запасной вариант - пустой список правил
            updated_rules = []

        # Генерируем текст правил для промпта только если есть правила
        if not updated_rules:
            logger.warning("No valid rules available for LLM prompt")
            rules_text = "No available rules"
        else:
            rules_text = "\n".join(
                f"[{i}] Rule ID: {rule.get('rule_id', 'unknown')}\n"
                f"    Description: {rule.get('text', '')}\n"
                f"    External URL (rule_url): {rule.get('url', '') if rule.get('url') else 'N/A'}\n"
                for i, rule in enumerate(updated_rules, 1)
            )

        system_prompt = SYSTEM_PROMPT.format(
            rules=rules_text,
            lang=lang,
            file_path=file_path,
            code=code
        )

        try:
            llm = self._llm_service.get_llm()
            response = llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content="Analyze the code above and return violations in JSON format.")
            ])

            logger.debug(f"LLM response: {response.content}")

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

            logger.info(f"Code analysis completed: {len(violations)} violations, severity: {severity}")

            # Log successful analysis to Langfuse
            if self._current_trace and audit_id:
                langfuse_service.create_event(
                    trace_id=self._current_trace.id,
                    name="analyze_code",
                    metadata={
                        "violations_count": len(violations),
                        "severity": severity,
                        "rules_used": len(updated_rules),
                        "language": lang
                    }
                )

                # Create score for security audit effectiveness
                langfuse_service.create_score(
                    trace_id=self._current_trace.id,
                    name="security_violations",
                    value=len(violations),
                    comment=f"Found {len(violations)} security violations, max severity: {severity}"
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
        """Validate that vulnerable lines exist in the code."""
        code = state["code"]
        violations = state["violations"]

        validated = [
            v for v in violations
            if v.get("vulnerable_line", "") and v.get("vulnerable_line") in code
        ]

        removed_count = len(violations) - len(validated)
        if removed_count > 0:
            logger.info(f"Grounded violations: removed {removed_count} invalid references")

        return {"violations": validated}

    def process(self, audit_task, initial_state: dict) -> tuple[list, Optional[str]]:
        """Process audit task through the workflow with Langfuse tracing."""
        audit_id = initial_state.get("audit_id", "unknown")

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
