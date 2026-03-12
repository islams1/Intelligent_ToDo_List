# models/task.py
from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class Task(BaseModel): # غيرنا الاسم لـ Task عشان يطابق الـ router
    id: Optional[int] = None
    task: str
    date: str
    time: str
    description: str = ""
    priority: str = "Medium"
    status: str = "Pending"
    calendar_id: Optional[str] = None
    created_at: datetime = datetime.now()