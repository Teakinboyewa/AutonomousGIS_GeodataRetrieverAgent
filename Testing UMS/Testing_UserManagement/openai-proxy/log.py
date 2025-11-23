from sqlalchemy import Column, Integer, String, BigInteger
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker

# database config
DATABASE_URL = 'sqlite+aiosqlite:///./openai_log.db'
engine = create_async_engine(DATABASE_URL)
Base = declarative_base()


# database model
class OpenAILog(Base):
    """
    OpenAI API call log
    """
    __tablename__ = 'openai_logs'

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    # request url
    request_url = Column(String)
    # request method
    request_method = Column(String)
    # request time, timestamp in millisecond
    request_time = Column(BigInteger)
    # response duration, in seconds
    response_duration = Column(BigInteger)
    # response status code
    status_code = Column(Integer)
    # request content
    request_content = Column(String)
    # response header
    response_header = Column(String)
    # response content
    response_content = Column(String)

    def to_dict(self):
        return {
            'id': self.id,
            'request_url': self.request_url,
            'request_method': self.request_method,
            'request_time': self.request_time,
            'response_duration': self.response_duration,
            'status_code': self.status_code,
            'request_content': self.request_content,
            'response_header': self.response_header,
            'response_content': self.response_content,
        }


async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

SessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def save_log(log: OpenAILog):
    async with SessionLocal() as session:
        session.add(log)
        await session.commit()
