# services/notification_service.py

# Change this:
# from .. import models, schemas

# To this:
from sqlalchemy.orm import Session
from database import SessionLocal  # or wherever your db session comes from
import models
import schemas
from datetime import datetime
from typing import Optional, List

class NotificationService:
    """Service to handle all notification creations across the app"""
    
    @staticmethod
    def create_notification(
        db: Session,
        user_id: int,
        role: str,
        title: str,
        message: str,
        type: str,
        related_id: Optional[int] = None,
        priority: str = "normal",
        action_url: Optional[str] = None,
        extra_data: Optional[dict] = None
    ):
        """Base method to create a single notification"""
        notification = models.Notification(
            user_id=user_id,
            role=role,
            title=title,
            message=message,
            type=type,
            related_id=related_id,
            priority=priority,
            action_url=action_url,
            extra_data=extra_data
        )
        db.add(notification)
        return notification

    @staticmethod
    def notify_complaint_created(db: Session, complaint, user_id: int):
        """Notify when a complaint is created"""
        # Notify the creator
        NotificationService.create_notification(
            db=db,
            user_id=user_id,
            role="farmer",
            title="✅ Complaint Submitted",
            message=f"Your complaint '{complaint.title}' has been submitted successfully.",
            type="complaint_created",
            related_id=complaint.id,
            priority="normal",
            action_url=f"/complaint/{complaint.id}",
            extra_data={"status": "pending"}
        )
        
        # Notify all admins
        admins = db.query(models.User).filter(models.User.role == "admin").all()
        for admin in admins:
            NotificationService.create_notification(
                db=db,
                user_id=admin.id,
                role="admin",
                title="📢 New Complaint Filed",
                message=f"New {complaint.type} complaint: '{complaint.title}' from {complaint.location}",
                type="admin_alert",
                related_id=complaint.id,
                priority="high" if complaint.type in ["Pest Attack", "Theft"] else "normal",
                action_url=f"/admin/complaint/{complaint.id}",
                extra_data={"complaint_id": complaint.id}
            )