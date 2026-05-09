from pydantic import BaseModel
from typing import List

class RecommendRequest(BaseModel):
    user_preferences: List[str]
    top_k: int = 10