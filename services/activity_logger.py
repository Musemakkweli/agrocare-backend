# services/activity_logger.py

import models


def log_activity(db, user_id, activity_type, description, metadata=None, status="success"):
    activity = models.ActivityHistory(
        user_id=user_id,
        activity_type=activity_type,
        description=description,
        activity_metadata=metadata or {},
        status=status
    )

    db.add(activity)
    db.commit()