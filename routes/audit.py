import json

from flask import request, session

from models.repositories import execute


def log_action(action: str, entity_type: str, entity_id=None, details=None) -> None:
    payload = json.dumps(details or {}, ensure_ascii=True)
    execute(
        """
        INSERT INTO audit_logs(user_id, username, action, entity_type, entity_id, details, ip_address)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session.get("user_id"),
            session.get("username"),
            action,
            entity_type,
            str(entity_id) if entity_id is not None else None,
            payload,
            request.remote_addr,
        ),
    )
