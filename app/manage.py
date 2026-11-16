"""CLI maintenance. First deploy: python -m app.manage. Cleanup: python -m app.manage cleanup-media."""
import os
import sys
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from .database import SessionLocal
from .models import User, Post, Media
from .security import normalize_username, hash_password

def bootstrap_admin():
    username, password = os.getenv('ADMIN_USERNAME'), os.getenv('ADMIN_PASSWORD')
    if not username and not password:
        return
    if not username or not password or len(password) < 8:
        raise RuntimeError('ADMIN_USERNAME e ADMIN_PASSWORD devem ser definidos (senha de pelo menos 8 caracteres).')
    name = normalize_username(username)
    with SessionLocal() as db:
        existing = db.scalar(select(User).where(User.username == name))
        if existing:
            if not existing.is_admin:
                raise RuntimeError('O nome de administrador já pertence a outra conta. Escolha outro ADMIN_USERNAME.')
            return
        db.add(User(username=name, password_hash=hash_password(password), is_admin=True))
        db.commit()
        print('Conta de moderação criada com segurança.')

def cleanup_media():
    """Delete orphan images older than 24 hours. Safe to run occasionally in maintenance."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    count = 0
    with SessionLocal() as db:
        old = db.scalars(select(Media).where(Media.created_at < cutoff)).all()
        for image in old:
            if (not db.scalar(select(Post.id).where(Post.image_media_id == image.id).limit(1))
                and not db.scalar(select(User.id).where(User.avatar_media_id == image.id).limit(1))):
                db.delete(image)
                count += 1
        db.commit()
    print(f'Arquivos órfãos removidos: {count}')

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'cleanup-media':
        cleanup_media()
    else:
        bootstrap_admin()
