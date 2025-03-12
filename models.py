from sqlalchemy import create_engine, Column, Integer, String, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

# Use Heroku's DATABASE_URL environment variable in production
DATABASE_URL = os.getenv('DATABASE_URL', "sqlite:///./test.db")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class SoloFight(Base):
    __tablename__ = "solo_fights"

    id = Column(Integer, primary_key=True, index=True)
    world = Column(String, index=True)
    location = Column(String, index=True)
    dungeon = Column(String, index=True)
    mob_name = Column(String, index=True)
    mob_types = Column(String, index=True)
    notes = Column(Text)

Base.metadata.create_all(bind=engine)
