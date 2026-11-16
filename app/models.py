"""Normalized persistent social graph and content models."""
from datetime import datetime, timezone
from sqlalchemy import (String, Text, ForeignKey, Boolean, Integer, DateTime,
                        UniqueConstraint, Index, LargeBinary, JSON)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base

def utcnow():
    return datetime.now(timezone.utc)

class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    bio: Mapped[str] = mapped_column(String(500), default='', nullable=False)
    display_name: Mapped[str] = mapped_column(String(60), default='', nullable=False)
    avatar_media_id: Mapped[str | None] = mapped_column(String(36))
    theme: Mapped[str] = mapped_column(String(12), default='dark', nullable=False)
    session_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

class Media(Base):
    __tablename__ = 'media'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    uploader_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    mime_type: Mapped[str] = mapped_column(String(40), nullable=False)
    content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class Post(Base):
    __tablename__ = 'posts'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(12), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(140), nullable=False)
    description: Mapped[str] = mapped_column(Text, default='', nullable=False)
    tags: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    image_media_id: Mapped[str | None] = mapped_column(String(36), ForeignKey('media.id', ondelete='SET NULL'))
    image_external_url: Mapped[str | None] = mapped_column(String(900))
    views: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True, nullable=False)
    author: Mapped[User] = relationship(User, foreign_keys=[user_id])
    comments: Mapped[list['Comment']] = relationship(back_populates='post', cascade='all, delete-orphan', passive_deletes=True)
    __table_args__ = (Index('ix_posts_kind_created', 'kind', 'created_at'),)

class PostTag(Base):
    __tablename__ = 'post_tags'
    post_id: Mapped[int] = mapped_column(ForeignKey('posts.id', ondelete='CASCADE'), primary_key=True)
    name: Mapped[str] = mapped_column(String(48), primary_key=True, index=True)

class Comment(Base):
    __tablename__ = 'comments'
    id: Mapped[int] = mapped_column(primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey('posts.id', ondelete='CASCADE'), index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    text: Mapped[str] = mapped_column(String(1500), nullable=False)
    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey('comments.id', ondelete='SET NULL'), index=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    author: Mapped[User] = relationship(User)
    post: Mapped[Post] = relationship(back_populates='comments')

class Like(Base):
    __tablename__ = 'likes'
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey('posts.id', ondelete='CASCADE'), primary_key=True, index=True)

class Save(Base):
    __tablename__ = 'saves'
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey('posts.id', ondelete='CASCADE'), primary_key=True, index=True)

class Follow(Base):
    __tablename__ = 'follows'
    follower_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    followed_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), primary_key=True, index=True)

class Notification(Base):
    __tablename__ = 'notifications'
    id: Mapped[int] = mapped_column(primary_key=True)
    recipient_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True, nullable=False)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'))
    post_id: Mapped[int | None] = mapped_column(ForeignKey('posts.id', ondelete='SET NULL'))
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    actor: Mapped[User | None] = relationship(User, foreign_keys=[actor_id])

class Report(Base):
    __tablename__ = 'reports'
    id: Mapped[int] = mapped_column(primary_key=True)
    reporter_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    post_id: Mapped[int | None] = mapped_column(ForeignKey('posts.id', ondelete='CASCADE'))
    comment_id: Mapped[int | None] = mapped_column(ForeignKey('comments.id', ondelete='CASCADE'))
    user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default='pending', nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (Index('ix_reports_status_created', 'status', 'created_at'),)

class AuthThrottle(Base):
    __tablename__ = 'auth_throttles'
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class AdminAudit(Base):
    __tablename__ = 'admin_audit'
    id: Mapped[int] = mapped_column(primary_key=True)
    admin_id: Mapped[int | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'), index=True)
    action: Mapped[str] = mapped_column(String(60), nullable=False)
    target_type: Mapped[str] = mapped_column(String(30), nullable=False)
    target_id: Mapped[int] = mapped_column(Integer, nullable=False)
    details: Mapped[str] = mapped_column(String(500), default='', nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    admin: Mapped[User | None] = relationship(User)
