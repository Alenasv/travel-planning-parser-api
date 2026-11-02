from typing import List, Optional

from pydantic import BaseModel, Field


class UserLocation(BaseModel):
    lat: float = Field(ge=-90, le=90, allow_inf_nan=False)
    lon: float = Field(ge=-180, le=180, allow_inf_nan=False)


class RecommendRequest(BaseModel):
    user_preferences: List[str]
    top_k: int = Field(default=10, ge=1, le=10, strict=True)
    start_metro: Optional[str] = None
    user_location: Optional[UserLocation] = None


class RecommendedPlace(BaseModel):
    id: str
    name: str
    category: str
    metro: Optional[str] = None
    address: Optional[str] = None
    work_time: Optional[str] = None


class RecommendResponse(BaseModel):
    places: List[RecommendedPlace]
