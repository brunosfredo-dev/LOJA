"""Kritikus REST API and web application, Render compatible."""
import os
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from fastapi import FastAPI, Request, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import FileResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import func, select, or_, delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .database import engine, get_db
from .models import (User, Post, PostTag, Like, Save, Follow, Comment,
                     Notification, Report, Media)
from .security import (normalize_username, hash_password, verify_password,
                       require_user, require_csrf, issue_session, throttle_check, throttle_fail, rate_limit)
from .media import store_image, MAX_UPLOAD

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND = BASE_DIR / 'frontend'
IS_PROD = bool(os.getenv('RENDER') or os.getenv('ENVIRONMENT') == 'production')
SECRET = os.getenv('SESSION_SECRET')
if IS_PROD and (not SECRET or len(SECRET) < 32):
    raise RuntimeError('Configure SESSION_SECRET com pelo menos 32 caracteres no Render.')
if not SECRET:
    SECRET = 'local-development-only-change-me-2026'

app = FastAPI(title='Kritikus API', version='1.0.0', docs_url=None if IS_PROD else '/api/docs',
              openapi_url=None if IS_PROD else '/api/openapi.json')
app.add_middleware(SessionMiddleware, secret_key=SECRET, session_cookie='kritikus_session',
                   same_site='lax', https_only=IS_PROD, max_age=604800)
app.mount('/assets', StaticFiles(directory=str(FRONTEND)), name='assets')

@app.middleware('http')
async def response_headers(request: Request, call_next):
    length = request.headers.get('content-length')
    if request.url.path in ('/api/media/upload', '/api/users/me/avatar') and length and length.isdecimal() and int(length) > MAX_UPLOAD + 500_000:
        return JSONResponse(status_code=413, content={'detail': 'Imagem acima do limite de 5 MB.'})
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
    if IS_PROD:
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    return response

class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=35)
    password: str = Field(min_length=1, max_length=150)

class PostPayload(BaseModel):
    kind: str
    title: str = Field(min_length=1, max_length=140)
    description: str = Field(default='', max_length=5000)
    tags: list[str] = Field(default_factory=list, max_length=8)
    image_media_id: str | None = None
    image_external_url: str | None = None

class CommentPayload(BaseModel):
    text: str = Field(min_length=1, max_length=1500)

class AccountPayload(BaseModel):
    bio: str | None = Field(default=None, max_length=500)
    theme: str | None = None
    current_password: str | None = None
    new_password: str | None = None

class ReportPayload(BaseModel):
    post_id: int | None = None
    comment_id: int | None = None
    reason: str = Field(min_length=5, max_length=500)

class ReviewPayload(BaseModel):
    action: str


def who(request: Request, db: Session):
    uid = request.session.get('uid')
    user = db.get(User, uid) if isinstance(uid, int) else None
    if not user or user.is_banned or request.session.get('sv') != user.session_version:
        return None
    return user


def authorized(request: Request, db: Session):
    return require_user(request, db)


def iso(dt):
    return dt.isoformat() if dt else None


def avatar_url(user):
    return f'/api/media/{user.avatar_media_id}' if user.avatar_media_id else None


def user_data(user):
    return dict(id=user.id, username=user.username, bio=user.bio, avatar_url=avatar_url(user),
                theme=user.theme, is_admin=user.is_admin, created_at=iso(user.created_at))


def get_counts(db, posts, viewer):
    ids = [p.id for p in posts]
    if not ids:
        return {}
    def counts(model):
        return dict(db.execute(select(model.post_id, func.count()).where(model.post_id.in_(ids))
                               .group_by(model.post_id)).all())
    likes, comments = counts(Like), counts(Comment)
    liked, saved, followed = set(), set(), set()
    if viewer:
        liked = set(db.scalars(select(Like.post_id).where(Like.user_id == viewer.id, Like.post_id.in_(ids))).all())
        saved = set(db.scalars(select(Save.post_id).where(Save.user_id == viewer.id, Save.post_id.in_(ids))).all())
        author_ids = list({p.user_id for p in posts})
        followed = set(db.scalars(select(Follow.followed_id).where(Follow.follower_id == viewer.id,
                                                                   Follow.followed_id.in_(author_ids))).all())
    return {p.id: dict(id=p.id, kind=p.kind, title=p.title, description=p.description,
                       tags=p.tags or [], image_url=f'/api/media/{p.image_media_id}' if p.image_media_id else p.image_external_url,
                       author=user_data(p.author), likes_count=likes.get(p.id, 0),
                       comments_count=comments.get(p.id, 0), views_count=p.views,
                       liked=p.id in liked, saved=p.id in saved,
                       following=p.user_id in followed, created_at=iso(p.created_at)) for p in posts}


def remove_unused_media(db, media_id):
    if not media_id:
        return
    referenced_in_posts = db.scalar(select(Post.id).where(Post.image_media_id == media_id).limit(1))
    referenced_in_profiles = db.scalar(select(User.id).where(User.avatar_media_id == media_id).limit(1))
    if not referenced_in_posts and not referenced_in_profiles:
        item = db.get(Media, media_id)
        if item:
            db.delete(item)

def post_or_404(db, post_id):
    post = db.get(Post, post_id)
    if not post or post.is_hidden:
        raise HTTPException(404, 'Publicação não encontrada.')
    return post


def notify(db, recipient_id, actor_id, kind, post_id=None):
    if recipient_id != actor_id:
        db.add(Notification(recipient_id=recipient_id, actor_id=actor_id, kind=kind, post_id=post_id))


def clean_tags(tags):
    cleaned = []
    for t in tags:
        tag = re.sub(r'\s+', ' ', t.strip())[:48]
        if tag and tag.casefold() not in {x.casefold() for x in cleaned}:
            cleaned.append(tag)
    return cleaned


def external_image(url):
    if not url:
        return None
    try:
        u = urlsplit(url.strip())
        if u.scheme != 'https' or not u.hostname or u.username or u.password or len(url) > 900:
            raise ValueError()
        if u.hostname in ('localhost', '127.0.0.1', '::1'):
            raise ValueError()
    except ValueError:
        raise HTTPException(422, 'Use um endereço HTTPS válido para a imagem.')
    return url.strip()


def validate_post(db, data, user):
    title = data.title.strip()
    if not title:
        raise HTTPException(422, 'O título não pode ficar vazio.')
    if data.kind not in ('artes', 'filmes'):
        raise HTTPException(422, 'Categoria inválida.')
    tags = clean_tags(data.tags)
    image = db.get(Media, data.image_media_id) if data.image_media_id else None
    if data.image_media_id and (not image or image.uploader_id != user.id):
        raise HTTPException(422, 'Imagem não encontrada ou sem permissão.')
    url = external_image(data.image_external_url)
    if data.kind == 'artes' and not (image or url):
        raise HTTPException(422, 'Envie uma imagem ou informe um link para o mural de artes.')
    return title, tags, url

@app.get('/')
def homepage():
    return FileResponse(FRONTEND / 'index.html', headers={'Cache-Control': 'no-cache'})

@app.get('/api/health')
def health(db: Session = Depends(get_db)):
    db.execute(select(1))
    return {'status': 'ok', 'database': 'connected'}

@app.get('/api/auth/bootstrap')
def bootstrap(request: Request, db: Session = Depends(get_db)):
    if not request.session.get('csrf'):
        request.session['csrf'] = secrets.token_urlsafe(32)
    user = who(request, db)
    unread = db.scalar(select(func.count()).select_from(Notification).where(
        Notification.recipient_id == user.id, Notification.is_read.is_(False))) if user else 0
    return {'user': user_data(user) if user else None,
            'csrf_token': request.session['csrf'], 'unread_notifications': unread}

@app.post('/api/auth/register', status_code=201)
def register(body: Credentials, request: Request, db: Session = Depends(get_db), _=Depends(require_csrf)):
    username = normalize_username(body.username)
    if len(body.password) < 8:
        raise HTTPException(422, 'A senha precisa ter pelo menos 8 caracteres.')
    if db.scalar(select(User.id).where(User.username == username)):
        raise HTTPException(409, 'Esse nome de usuário já está em uso.')
    signup_key, signup_attempts = throttle_check(request, db, '__register__')
    user = User(username=username, password_hash=hash_password(body.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'Esse nome de usuário já está em uso.')
    db.refresh(user)
    throttle_fail(db, signup_key, signup_attempts)
    issue_session(request, user)
    return {'user': user_data(user), 'csrf_token': request.session['csrf']}

@app.post('/api/auth/login')
def login(body: Credentials, request: Request, db: Session = Depends(get_db), _=Depends(require_csrf)):
    username = normalize_username(body.username)
    key, attempts = throttle_check(request, db, username)
    user = db.scalar(select(User).where(User.username == username))
    if not user or not verify_password(body.password, user.password_hash):
        throttle_fail(db, key, attempts)
        raise HTTPException(401, 'Usuário ou senha incorretos.')
    if user.is_banned:
        raise HTTPException(403, 'Conta suspensa.')
    if attempts:
        db.delete(attempts)
        db.commit()
    issue_session(request, user)
    return {'user': user_data(user), 'csrf_token': request.session['csrf']}

@app.post('/api/auth/logout')
def logout(request: Request, _=Depends(require_csrf)):
    request.session.clear()
    request.session['csrf'] = secrets.token_urlsafe(32)
    return {'ok': True, 'csrf_token': request.session['csrf']}

@app.get('/api/media/{media_id}')
def get_media(media_id: str, db: Session = Depends(get_db)):
    if not re.fullmatch(r'[a-f0-9-]{36}', media_id):
        raise HTTPException(404, 'Imagem não encontrada.')
    file = db.get(Media, media_id)
    if not file:
        raise HTTPException(404, 'Imagem não encontrada.')
    return Response(file.content, media_type=file.mime_type, headers={'Cache-Control': 'public, max-age=31536000, immutable'})

@app.post('/api/media/upload', status_code=201)
async def upload_media(request: Request, file: UploadFile = File(...), db: Session = Depends(get_db),
                       _=Depends(require_csrf)):
    user = authorized(request, db)
    rate_limit(db, user.id, 'upload', 25)
    data = await file.read(MAX_UPLOAD + 1)
    media_id = store_image(db, user.id, data)
    db.commit()
    return {'media_id': media_id, 'image_url': f'/api/media/{media_id}'}

@app.get('/api/posts')
def get_posts(request: Request, kind: str | None = None, tag: str | None = None, q: str | None = Query(None, max_length=100),
              author: str | None = None, saved: bool = False,
              page: int = Query(1, ge=1, le=10000), limit: int = Query(20, ge=1, le=40),
              db: Session = Depends(get_db)):
    viewer = who(request, db)
    stmt = select(Post).where(Post.is_hidden.is_(False))
    if kind:
        if kind not in ('artes', 'filmes'):
            raise HTTPException(422, 'Categoria inválida.')
        stmt = stmt.where(Post.kind == kind)
    if author:
        stmt = stmt.join(User, User.id == Post.user_id).where(User.username == normalize_username(author))
    if tag:
        stmt = stmt.join(PostTag).where(PostTag.name == tag.strip().casefold())
    if q and q.strip():
        # Search also matches author usernames, case-insensitively.
        term = f'%{q.strip()}%'
        stmt = stmt.where(or_(Post.title.ilike(term), Post.description.ilike(term),
                              Post.user_id.in_(select(User.id).where(User.username.ilike(term))),
                              Post.id.in_(select(PostTag.post_id).where(PostTag.name.ilike(term)))))
    if saved:
        if not viewer:
            raise HTTPException(401, 'Entre para consultar itens salvos.')
        stmt = stmt.join(Save, Save.post_id == Post.id).where(Save.user_id == viewer.id)
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    posts = db.scalars(stmt.order_by(Post.created_at.desc(), Post.id.desc())
                       .limit(limit).offset((page - 1) * limit)).all()
    serialized = get_counts(db, posts, viewer)
    return {'items': [serialized[p.id] for p in posts], 'page': page, 'total': total,
            'has_more': page * limit < total}

@app.post('/api/posts', status_code=201)
def create_post(body: PostPayload, request: Request, db: Session = Depends(get_db), _=Depends(require_csrf)):
    user = authorized(request, db)
    rate_limit(db, user.id, 'post', 20)
    title, tags, url = validate_post(db, body, user)
    post = Post(user_id=user.id, kind=body.kind, title=title, description=body.description.strip(),
                tags=tags, image_media_id=body.image_media_id, image_external_url=url)
    db.add(post)
    db.flush()
    db.add_all([PostTag(post_id=post.id, name=t.casefold()) for t in tags])
    db.commit()
    return {'post': get_counts(db, [post], user)[post.id]}

@app.get('/api/posts/{post_id}')
def get_post(post_id: int, request: Request, track_view: bool = True, db: Session = Depends(get_db)):
    post = post_or_404(db, post_id)
    if track_view:
        post.views += 1
        db.commit()
    viewer = who(request, db)
    comments = db.scalars(select(Comment).where(Comment.post_id == post_id)
                          .order_by(Comment.created_at.asc(), Comment.id.asc()).limit(300)).all()
    return {'post': get_counts(db, [post], viewer)[post.id],
            'comments': [{'id': c.id, 'text': c.text, 'author': user_data(c.author),
                          'created_at': iso(c.created_at),
                          'can_delete': bool(viewer and (viewer.id in (c.user_id, post.user_id) or viewer.is_admin))}
                         for c in comments]}

@app.patch('/api/posts/{post_id}')
def edit_post(post_id: int, body: PostPayload, request: Request, db: Session = Depends(get_db), _=Depends(require_csrf)):
    user = authorized(request, db)
    post = post_or_404(db, post_id)
    if post.user_id != user.id and not user.is_admin:
        raise HTTPException(403, 'Sem permissão para editar.')
    title, tags, url = validate_post(db, body, user)
    old_image_id = post.image_media_id
    post.kind, post.title, post.description, post.tags = body.kind, title, body.description.strip(), tags
    post.image_media_id, post.image_external_url = body.image_media_id, url
    db.flush()
    if old_image_id != post.image_media_id:
        remove_unused_media(db, old_image_id)
    db.execute(delete(PostTag).where(PostTag.post_id == post.id))
    db.add_all([PostTag(post_id=post.id, name=t.casefold()) for t in tags])
    db.commit()
    return {'post': get_counts(db, [post], user)[post.id]}

@app.delete('/api/posts/{post_id}')
def delete_post(post_id: int, request: Request, db: Session = Depends(get_db), _=Depends(require_csrf)):
    user = authorized(request, db)
    post = db.get(Post, post_id)
    if not post:
        raise HTTPException(404, 'Publicação não encontrada.')
    if post.user_id != user.id and not user.is_admin:
        raise HTTPException(403, 'Sem permissão para excluir.')
    old_image_id = post.image_media_id
    db.delete(post)
    db.flush()
    remove_unused_media(db, old_image_id)
    db.commit()
    return {'ok': True}

@app.post('/api/posts/{post_id}/like')
def toggle_like(post_id: int, request: Request, db: Session = Depends(get_db), _=Depends(require_csrf)):
    user = authorized(request, db)
    post = post_or_404(db, post_id)
    previous = db.get(Like, (user.id, post.id))
    if previous:
        db.delete(previous)
        liked = False
    else:
        db.add(Like(user_id=user.id, post_id=post.id))
        notify(db, post.user_id, user.id, 'like', post.id)
        liked = True
    db.commit()
    return {'liked': liked, 'likes_count': db.scalar(select(func.count()).select_from(Like).where(Like.post_id == post.id))}

@app.post('/api/posts/{post_id}/save')
def toggle_save(post_id: int, request: Request, db: Session = Depends(get_db), _=Depends(require_csrf)):
    user = authorized(request, db)
    post = post_or_404(db, post_id)
    existing = db.get(Save, (user.id, post.id))
    if existing:
        db.delete(existing)
    else:
        db.add(Save(user_id=user.id, post_id=post.id))
    db.commit()
    return {'saved': existing is None}

@app.post('/api/posts/{post_id}/comments', status_code=201)
def create_comment(post_id: int, body: CommentPayload, request: Request, db: Session = Depends(get_db), _=Depends(require_csrf)):
    user = authorized(request, db)
    post = post_or_404(db, post_id)
    if not body.text.strip():
        raise HTTPException(422, 'O comentário não pode estar vazio.')
    rate_limit(db, user.id, 'comment', 50)
    item = Comment(post_id=post.id, user_id=user.id, text=body.text.strip())
    db.add(item)
    notify(db, post.user_id, user.id, 'comment', post.id)
    db.commit()
    return {'id': item.id}

@app.delete('/api/comments/{comment_id}')
def delete_comment(comment_id: int, request: Request, db: Session = Depends(get_db), _=Depends(require_csrf)):
    user = authorized(request, db)
    comment = db.get(Comment, comment_id)
    if not comment:
        raise HTTPException(404, 'Comentário não encontrado.')
    if user.id not in (comment.user_id, comment.post.user_id) and not user.is_admin:
        raise HTTPException(403, 'Sem permissão.')
    db.delete(comment)
    db.commit()
    return {'ok': True}

@app.get('/api/users')
def find_users(q: str = Query('', max_length=100), db: Session = Depends(get_db)):
    term = q.strip().lstrip('@')
    if not term:
        return {'items': []}
    users = db.scalars(select(User).where(User.username.ilike(f'%{term}%'), User.is_banned.is_(False))
                       .order_by(User.username).limit(12)).all()
    return {'items': [user_data(u) for u in users]}

@app.get('/api/users/{username}')
def profile(username: str, request: Request, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == normalize_username(username), User.is_banned.is_(False)))
    if not user:
        raise HTTPException(404, 'Perfil não encontrado.')
    viewer = who(request, db)
    return {'user': user_data(user),
            'followers_count': db.scalar(select(func.count()).select_from(Follow).where(Follow.followed_id == user.id)),
            'following_count': db.scalar(select(func.count()).select_from(Follow).where(Follow.follower_id == user.id)),
            'following': bool(viewer and db.get(Follow, (viewer.id, user.id))),
            'is_me': bool(viewer and viewer.id == user.id)}

@app.post('/api/users/{username}/follow')
def toggle_follow(username: str, request: Request, db: Session = Depends(get_db), _=Depends(require_csrf)):
    viewer = authorized(request, db)
    user = db.scalar(select(User).where(User.username == normalize_username(username), User.is_banned.is_(False)))
    if not user:
        raise HTTPException(404, 'Perfil não encontrado.')
    if user.id == viewer.id:
        raise HTTPException(422, 'Não é possível seguir a si mesmo.')
    follow = db.get(Follow, (viewer.id, user.id))
    if follow:
        db.delete(follow)
    else:
        rate_limit(db, viewer.id, 'follow', 35)
        db.add(Follow(follower_id=viewer.id, followed_id=user.id))
        notify(db, user.id, viewer.id, 'follow')
    db.commit()
    return {'following': follow is None, 'followers_count': db.scalar(select(func.count()).select_from(Follow).where(Follow.followed_id == user.id))}

@app.patch('/api/users/me')
def update_account(body: AccountPayload, request: Request, db: Session = Depends(get_db), _=Depends(require_csrf)):
    user = authorized(request, db)
    if body.bio is not None:
        user.bio = body.bio.strip()
    if body.theme is not None:
        if body.theme not in ('dark', 'light'):
            raise HTTPException(422, 'Tema inválido.')
        user.theme = body.theme
    if body.new_password is not None:
        if not body.current_password or not verify_password(body.current_password, user.password_hash):
            raise HTTPException(403, 'Senha atual incorreta.')
        if len(body.new_password) < 8 or len(body.new_password) > 150:
            raise HTTPException(422, 'Nova senha deve ter entre 8 e 150 caracteres.')
        user.password_hash = hash_password(body.new_password)
        user.session_version += 1
        issue_session(request, user)
    db.commit()
    return {'user': user_data(user), 'csrf_token': request.session.get('csrf')}

@app.post('/api/users/me/avatar')
async def update_avatar(request: Request, file: UploadFile = File(...), db: Session = Depends(get_db),
                        _=Depends(require_csrf)):
    user = authorized(request, db)
    binary = await file.read(MAX_UPLOAD + 1)
    old = user.avatar_media_id
    user.avatar_media_id = store_image(db, user.id, binary, avatar=True)
    db.commit()
    if old:
        remove_unused_media(db, old)
        db.commit()
    return {'user': user_data(user)}

@app.get('/api/notifications')
def notifications(request: Request, db: Session = Depends(get_db), page: int = Query(1, ge=1)):
    user = authorized(request, db)
    items = db.scalars(select(Notification).where(Notification.recipient_id == user.id)
                       .order_by(Notification.created_at.desc(), Notification.id.desc())
                       .offset((page-1)*30).limit(30)).all()
    unread = db.scalar(select(func.count()).select_from(Notification).where(
        Notification.recipient_id == user.id, Notification.is_read.is_(False)))
    return {'items': [{'id': n.id, 'kind': n.kind, 'actor': n.actor.username if n.actor else 'Usuário',
                       'post_id': n.post_id, 'is_read': n.is_read, 'created_at': iso(n.created_at)} for n in items],
            'unread': unread}

@app.post('/api/notifications/read')
def read_notifications(request: Request, db: Session = Depends(get_db), _=Depends(require_csrf)):
    user = authorized(request, db)
    db.query(Notification).filter(Notification.recipient_id == user.id, Notification.is_read.is_(False)).update({'is_read': True})
    db.commit()
    return {'ok': True}

@app.post('/api/reports', status_code=201)
def create_report(body: ReportPayload, request: Request, db: Session = Depends(get_db), _=Depends(require_csrf)):
    user = authorized(request, db)
    rate_limit(db, user.id, 'report', 10)
    if bool(body.post_id) == bool(body.comment_id):
        raise HTTPException(422, 'Informe somente um post ou comentário.')
    if body.post_id:
        post_or_404(db, body.post_id)
    if body.comment_id and not db.get(Comment, body.comment_id):
        raise HTTPException(404, 'Comentário não encontrado.')
    db.add(Report(reporter_id=user.id, post_id=body.post_id, comment_id=body.comment_id, reason=body.reason.strip()))
    db.commit()
    return {'ok': True}


def admin_only(request, db):
    user = authorized(request, db)
    if not user.is_admin:
        raise HTTPException(403, 'Apenas moderadores.')
    return user

@app.get('/api/admin/reports')
def admin_reports(request: Request, db: Session = Depends(get_db)):
    admin_only(request, db)
    rows = db.scalars(select(Report).where(Report.status == 'pending')
                      .order_by(Report.created_at.asc()).limit(100)).all()
    return {'items': [{'id': r.id, 'post_id': r.post_id, 'comment_id': r.comment_id,
                       'reason': r.reason, 'created_at': iso(r.created_at)} for r in rows]}

@app.post('/api/admin/reports/{report_id}')
def review_report(report_id: int, body: ReviewPayload, request: Request,
                  db: Session = Depends(get_db), _=Depends(require_csrf)):
    admin_only(request, db)
    report = db.get(Report, report_id)
    if not report:
        raise HTTPException(404, 'Denúncia não encontrada.')
    if body.action not in ('dismiss', 'hide'):
        raise HTTPException(422, 'Ação inválida.')
    if body.action == 'hide':
        if report.post_id:
            post = db.get(Post, report.post_id)
            if post: post.is_hidden = True
        if report.comment_id:
            comment = db.get(Comment, report.comment_id)
            if comment: db.delete(comment)
    report.status = 'resolved' if body.action == 'hide' else 'dismissed'
    db.commit()
    return {'ok': True}
