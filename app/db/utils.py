import traceback
from app.db.models import ErrorLog

def log_error(db, entity_id, job_type, error):
    """Utility to persist errors and mark status as failed."""
    error_log = ErrorLog(
        entity_id=entity_id,
        job_type=job_type,
        error_message=str(error),
        stack_trace=traceback.format_exc()
    )
    db.add(error_log)
    db.commit()