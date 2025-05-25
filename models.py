from sqlalchemy import create_engine, Column, Integer, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime
from config import DB_PATH

Base = declarative_base()
engine = create_engine(f"sqlite:///{DB_PATH}", echo=False, future=True)
SessionLocal = sessionmaker(bind=engine)

class Sample(Base):
    __tablename__ = "samples"
    id   = Column(Integer, primary_key=True)
    ts   = Column(DateTime, default=datetime.utcnow, index=True)
    ldr  = Column(Integer)
    pwm  = Column(Integer)
    ref  = Column(Integer)
    session_id = Column(Integer)

Base.metadata.create_all(engine)