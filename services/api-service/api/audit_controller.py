import logging
import uuid
from typing import Optional

from .config import settings
from .models import (
    AuditStartRequest,
    AuditStatusResponse,
    AuditListResponse,
    AuditReportResponse,
    Finding
)
from .database import (
    create_audit,
    get_audit,
    update_audit_status,
    list_audits,
    get_audit_results
)
from .exceptions import AuditNotFoundError, AccessDeniedError
from .kafka_service import KafkaService

logger = logging.getLogger(__name__)


class AuditController:
    """Controller for audit-related operations."""

    def __init__(self, kafka_service: KafkaService):
        self._kafka_service = kafka_service

    def start_audit(self, request: AuditStartRequest) -> dict:
        """Start a new security audit."""
        try:
            # Generate audit ID
            audit_id = str(uuid.uuid4())

            # Create audit record
            create_audit(
                audit_id=audit_id,
                user_id=request.user_id,
                repo_url=request.repo_url,
                branch=request.branch,
                lang=request.lang
            )

            # Send audit task to Kafka for processing
            audit_message = {
                "audit_id": audit_id,
                "user_id": request.user_id,
                "repo_url": request.repo_url,
                "branch": request.branch,
                "lang": request.lang
            }
            self._kafka_service.send_message(settings.repo_parsed_topic, audit_message)

            logger.info(f"Started audit {audit_id} for user {request.user_id}")

            return {
                "audit_id": audit_id,
                "status": "pending",
                "user_id": request.user_id
            }

        except Exception as e:
            logger.error(f"Failed to start audit: {e}")
            raise

    def get_audits_list(
        self,
        user_id: str,
        status: Optional[str] = None,
        limit: int = 10,
        offset: int = 0
    ) -> dict:
        """Get list of audits for a user."""
        try:
            audits, total = list_audits(user_id, status, limit, offset)

            items = [
                {
                    "audit_id": aud.id,
                    "user_id": aud.user_id,
                    "repo_url": aud.repo_url,
                    "branch": aud.branch,
                    "lang": aud.lang,
                    "status": aud.status,
                    "created_at": aud.created_at.isoformat(),
                    "updated_at": aud.updated_at.isoformat()
                }
                for aud in audits
            ]

            return {"items": items, "total": total}

        except Exception as e:
            logger.error(f"Failed to list audits: {e}")
            raise

    def get_audit_status(self, audit_id: str, user_id: str) -> AuditStatusResponse:
        """Get status of a specific audit."""
        try:
            audit = get_audit(audit_id)

            if not audit:
                raise AuditNotFoundError(settings.error_audit_not_found)

            if audit.user_id != user_id:
                raise AccessDeniedError(settings.error_access_denied)

            return AuditStatusResponse(
                audit_id=audit.id,
                repo_url=audit.repo_url,
                status=audit.status,
                created_at=audit.created_at,
                updated_at=audit.updated_at
            )

        except (AuditNotFoundError, AccessDeniedError):
            raise
        except Exception as e:
            logger.error(f"Failed to get audit status: {e}")
            raise

    def get_audit_report(self, audit_id: str, user_id: str) -> dict:
        """Get detailed report for a completed audit."""
        logger.info(f"Getting report for audit_id={audit_id}, user_id={user_id}")

        try:
            audit = get_audit(audit_id)

            if not audit:
                raise AuditNotFoundError(settings.error_audit_not_found)

            if audit.user_id != user_id:
                raise AccessDeniedError(settings.error_access_denied)

            if audit.status not in ("completed", "all_completed"):
                raise ValueError(settings.error_audit_not_completed)

            # Get audit results from database
            rows = get_audit_results(audit_id)

            # Transform results for frontend
            findings = []
            for row in rows:
                chunk_id, file_path, chunk_findings, chunk_severity = row

                logger.info(f"Processing chunk {chunk_id} with {len(chunk_findings)} violations")

                for violation in chunk_findings:
                    violation_severity = violation.get("severity", chunk_severity or "medium")

                    finding = Finding(
                        message=violation.get("explanation"),
                        severity=violation_severity,
                        file_path=file_path,
                        line_number="",
                        code_snippet=violation.get("vulnerable_line", ""),
                        fix_suggestion=f"Рассмотрите нарушение правила: {violation.get('rule_id', 'unknown')}",
                        description=violation.get("explanation", ""),
                        rule_id=violation.get("rule_id", ""),
                        rule_url=violation.get("rule_url", ""),
                        chunk_severity=chunk_severity
                    )
                    findings.append(finding.dict())

            logger.info(f"Generated report for audit {audit_id} with {len(findings)} findings")

            return {
                "audit_id": audit_id,
                "findings": findings
            }

        except (AuditNotFoundError, AccessDeniedError, ValueError):
            raise
        except Exception as e:
            logger.error(f"Failed to generate audit report: {e}")
            raise
