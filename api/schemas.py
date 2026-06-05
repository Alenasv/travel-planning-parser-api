from pydantic import BaseModel
from typing import List, Optional

class RecommendRequest(BaseModel):
    user_preferences: List[str]
    top_k: int = 10
    start_metro: Optional[str] = None