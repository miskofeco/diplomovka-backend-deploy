from sqlalchemy import Column, String, ARRAY, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.types import TypeDecorator
import json

Base = declarative_base()

class JSONBType(TypeDecorator):
    impl = JSONB
    
    def process_bind_param(self, value, dialect):
        if value is not None:
            # Convert dict to JSON string if it's not already
            return json.dumps(value) if isinstance(value, dict) else value
        return value
    
    def process_result_value(self, value, dialect):
        if value is not None:
            # Convert JSON string to dict if it's not already
            return json.loads(value) if isinstance(value, str) else value
        return value

class Article(Base):
    __tablename__ = 'articles'
    
    # ... other columns ...
    political_orientation = Column(JSONBType)
    source_orientation = Column(JSONBType)
