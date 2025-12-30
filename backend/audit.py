"""Audit logging for LLM actions."""
import json
import logging
from datetime import datetime
from pathlib import Path

AUDIT_LOG_DIR = Path("logs/audit")
AUDIT_LOG_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger("llm_audit")
logger.setLevel(logging.INFO)

# File handler
fh = logging.FileHandler(AUDIT_LOG_DIR / "llm_actions.log")
fh.setFormatter(logging.Formatter(
    '%(asctime)s - %(levelname)s - %(message)s'
))
logger.addHandler(fh)


def log_llm_action(
    notebook_id: str,
    user_id: str,
    action: str,
    details: dict
):
    """Log LLM action for audit trail."""
    logger.info(json.dumps({
        "timestamp": datetime.utcnow().isoformat(),
        "notebook_id": notebook_id,
        "user_id": user_id,
        "action": action,
        "details": details
    }))

