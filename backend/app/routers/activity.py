from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel, Field
import datetime

from app.database import get_db
from app import models

router = APIRouter(tags=["activity"])


class ActivityPayload(BaseModel):
    """
    Payload for incoming activity tracking events from the Flutter app.
    We accept device_id instead of user_id so the frontend doesn't need 
    to know its internal database ID.
    """
    device_id: str = Field(..., max_length=255)
    action_type: str = Field(..., max_length=100)
    query_text: Optional[str] = None
    product_id: Optional[int] = None
    timestamp: Optional[datetime.datetime] = None


@router.post("/activity", status_code=status.HTTP_201_CREATED)
def log_activity(payload: ActivityPayload, db: Session = Depends(get_db)):
    """
    Logs user activity (searches, clicks, views) to track engagement.
    Automatically creates a new User row if the device_id is seen for the first time.
    """
    # 1. Upsert User based on device_id
    user = db.query(models.User).filter(models.User.device_id == payload.device_id).first()
    
    if not user:
        user = models.User(device_id=payload.device_id)
        db.add(user)
        # Flush pushes the INSERT to the DB and populates user.id without committing the transaction yet
        db.flush() 
        
    # 2. Log Activity
    activity = models.UserActivity(
        user_id=user.id,
        action_type=payload.action_type,
        query_text=payload.query_text,
        product_id=payload.product_id,
    )
    
    # Use client timestamp if provided, otherwise rely on the DB's server_default (now())
    if payload.timestamp:
        activity.timestamp = payload.timestamp
        
    db.add(activity)
    db.commit()
    
    return {"status": "success", "activity_id": activity.id}


from sqlalchemy import func, desc

@router.get("/analytics")
def get_analytics(db: Session = Depends(get_db)):
    """
    Returns aggregated statistics from the user_activity table.
    """
    # 1. Most searched categories (using query_text)
    most_searched = db.query(
        models.UserActivity.query_text, 
        func.count(models.UserActivity.id).label('count')
    ).filter(
        models.UserActivity.action_type == 'search',
        models.UserActivity.query_text.isnot(None)
    ).group_by(
        models.UserActivity.query_text
    ).order_by(
        desc('count')
    ).limit(10).all()
    
    # 2. Most clicked products
    most_clicked = db.query(
        models.Product.name,
        func.count(models.UserActivity.id).label('count')
    ).join(
        models.Product, models.UserActivity.product_id == models.Product.id
    ).filter(
        models.UserActivity.action_type == 'click'
    ).group_by(
        models.Product.id, models.Product.name
    ).order_by(
        desc('count')
    ).limit(10).all()
    
    # 3. Average time between a search and a subsequent click
    # To remain database-agnostic and handle "first click after a search" safely,
    # we can compute this sequentially in memory over the recent activity.
    activities = db.query(
        models.UserActivity.user_id,
        models.UserActivity.action_type,
        models.UserActivity.timestamp
    ).filter(
        models.UserActivity.action_type.in_(['search', 'click'])
    ).order_by(
        models.UserActivity.user_id,
        models.UserActivity.timestamp
    ).all()
    
    time_diffs = []
    last_search_time = {}
    
    for user_id, action_type, timestamp in activities:
        # Ensure timestamp is offset-aware or naive consistently, datetime subtraction handles it 
        # if both come from DB.
        if action_type == 'search':
            last_search_time[user_id] = timestamp
        elif action_type == 'click':
            if user_id in last_search_time:
                diff = (timestamp - last_search_time[user_id]).total_seconds()
                # Sanity check: Only count clicks that happen within 1 hour of a search
                if 0 <= diff < 3600: 
                    time_diffs.append(diff)
                # Clear the search so we only measure time to the *first* click
                del last_search_time[user_id]
                
    avg_time_seconds = sum(time_diffs) / len(time_diffs) if time_diffs else 0.0
    
    return {
        "most_searched_categories": [{"query": q, "count": c} for q, c in most_searched],
        "most_clicked_products": [{"product": p, "count": c} for p, c in most_clicked],
        "average_seconds_search_to_click": round(avg_time_seconds, 2)
    }

