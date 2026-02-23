# utils.py
from sqlalchemy.orm import Session
import models

def create_notification(
    db: Session,
    user_id: int,
    title: str,
    message: str,
    type: str,
    priority: str = "normal",
    related_id: int | None = None,
    action_url: str | None = None,
    extra_data: dict | None = None
):
    """
    Automatically create a notification for a user.
    """
    notification = models.Notification(
        user_id=user_id,
        title=title,
        message=message,
        type=type,
        priority=priority,
        related_id=related_id,
        action_url=action_url,
        extra_data=extra_data
    )
    db.add(notification)
    db.commit()
    db.refresh(notification)
    return notification