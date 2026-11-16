"""Database configuration; DATABASE_URL comes from Render Postgres."""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

if (os.getenv('RENDER') or os.getenv('ENVIRONMENT') == 'production') and not os.getenv('DATABASE_URL'):
    raise RuntimeError('DATABASE_URL é obrigatório em produção. Configure PostgreSQL no Render.')
url = os.environ.get('DATABASE_URL', 'sqlite:///./kritikus_local.db')
if url.startswith('postgres://'):
    url = 'postgresql://' + url[len('postgres://'):]
if url.startswith('postgresql://'):
    url = url.replace('postgresql://', 'postgresql+psycopg://', 1)
connect_args = {'check_same_thread': False} if url.startswith('sqlite:') else {}
engine = create_engine(url, pool_pre_ping=True, pool_recycle=1800, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

def get_db():
    with SessionLocal() as db:
        yield db
