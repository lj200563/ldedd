from sqlalchemy import create_engine, Column, Integer, String, Text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from config import config_manager
from logger import logger

Base = declarative_base()

class Token(Base):
    __tablename__ = 'tokens'
    id = Column(Integer, primary_key=True)
    cookie = Column(String(768), nullable=False, unique=True)

engine = None
SessionLocal = None

def init_db():
    global engine, SessionLocal
    sql_dsn = config_manager.get("SERVER.SQL_DSN")
    if sql_dsn:
        try:
            engine = create_engine(sql_dsn)
            SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
            Base.metadata.create_all(bind=engine)
            logger.info("Database initialized successfully.", "Database")
        except Exception as e:
            logger.error(f"Database initialization failed: {e}", "Database")
            engine = None
            SessionLocal = None
    else:
        logger.warning("SQL_DSN not configured. Database support is disabled.", "Database")

def get_db():
    if SessionLocal:
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()
    else:
        yield None
