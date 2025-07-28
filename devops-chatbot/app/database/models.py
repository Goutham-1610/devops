from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any, Annotated
from datetime import datetime
from bson import ObjectId

class PyObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate
    
    @classmethod
    def validate(cls, v, handler=None):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectId")
        return ObjectId(v)
    
    @classmethod
    def __get_pydantic_json_schema__(cls, field_schema):
        field_schema.update(type="string")
        return field_schema

# Type alias for ObjectId fields
PydanticObjectId = Annotated[PyObjectId, Field(default_factory=PyObjectId)]

class Message(BaseModel):
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    role: str  # "user" or "bot"
    content: str
    command_type: Optional[str] = None  # "deploy", "monitor", "heal", etc.

class Conversation(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={ObjectId: str}
    )
    
    id: Optional[PydanticObjectId] = Field(default_factory=PyObjectId, alias="_id")
    user_id: str
    channel: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    messages: List[Message] = []

class DeploymentLog(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={ObjectId: str}
    )
    
    id: Optional[PydanticObjectId] = Field(default_factory=PyObjectId, alias="_id")
    app_name: str
    user_id: str
    channel: str
    command: str
    status: str  # "success", "failed", "in_progress"
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    details: Dict[str, Any] = {}
    execution_time: Optional[float] = None

class SystemMetrics(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={ObjectId: str}
    )
    
    id: Optional[PydanticObjectId] = Field(default_factory=PyObjectId, alias="_id")
    server_name: str = "localhost"
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    cpu_percent: float
    memory_percent: float
    disk_percent: float
    active_processes: int
    system_load: List[float] = []  # 1min, 5min, 15min load averages
