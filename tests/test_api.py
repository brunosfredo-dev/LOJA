"""End-to-end API smoke tests with real SQLAlchemy and isolated SQLite DB.
Run: python -m pytest tests -q
"""
import io
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEST_DB = ROOT / 'kritikus_test.db'
os.environ['DATABASE_URL'] = f'sqlite:///{TEST_DB}'
os.environ.pop('RENDER', None)
os.environ.pop('ENVIRONMENT', None)

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from app.database import Base, engine
from app.main import app

@pytest.fixture(autouse=True)
def clean_database():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)

@pytest.fixture
def clients():
    a=TestClient(app)
    b=TestClient(app)
    a.get('/api/auth/bootstrap')
    b.get('/api/auth/bootstrap')
    return a,b

def csrf(c):
    return {'X-CSRF-Token':c.get('/api/auth/bootstrap').json()['csrf_token']}

def register(c,name):
    result=c.post('/api/auth/register',json={'username':name,'password':'StrongPassword123'},headers=csrf(c))
    assert result.status_code==201,result.text
    return result.json()['user']

def create_image():
    im=Image.new('RGB',(80,80),(10,90,150))
    buff=io.BytesIO();im.save(buff,'PNG');return buff.getvalue()

def upload(c):
    r=c.post('/api/media/upload',files={'file':('test.png',create_image(),'image/png')},headers=csrf(c))
    assert r.status_code==201,r.text
    return r.json()['media_id']

def post_art(c,media_id):
    r=c.post('/api/posts',json={'kind':'artes','title':'Arte Teste','description':'Uma pequena arte',
                                'tags':['Personagens','Arte Digital'],'image_media_id':media_id},headers=csrf(c))
    assert r.status_code==201,r.text
    return r.json()['post']

def test_health_and_frontend(clients):
    a,_=clients
    assert a.get('/').status_code==200
    assert 'KRITIKUS' in a.get('/').text
    assert a.get('/assets/script.js').status_code==200
    assert a.get('/api/health').json()['status']=='ok'

def test_auth_csrf_and_password(clients):
    a,b=clients
    assert a.post('/api/auth/register',json={'username':'ana','password':'StrongPassword123'}).status_code==403
    assert a.post('/api/auth/register',json={'username':'ana','password':'123'},headers=csrf(a)).status_code==422
    register(a,'ana')
    assert a.post('/api/auth/register',json={'username':'ana','password':'StrongPassword123'},headers=csrf(a)).status_code==409
    assert b.post('/api/auth/login',json={'username':'ana','password':'wrong'},headers=csrf(b)).status_code==401
    ok=b.post('/api/auth/login',json={'username':'ana','password':'StrongPassword123'},headers=csrf(b))
    assert ok.status_code==200
    assert b.get('/api/auth/bootstrap').json()['user']['username']=='ana'
    assert b.post('/api/auth/logout',headers=csrf(b)).status_code==200
    assert b.get('/api/auth/bootstrap').json()['user'] is None

def test_post_and_interactions(clients):
    a,b=clients
    register(a,'ana');register(b,'bruno')
    pic=upload(a); post=post_art(a,pic); id=post['id']
    assert a.get('/api/media/'+pic).headers['content-type']=='image/webp'
    assert b.get('/api/posts?tag=personagens').json()['total']==1
    assert b.get('/api/posts?q=Arte%20Teste').json()['total']==1
    assert b.get('/api/posts?kind=filmes').json()['total']==0
    assert b.get(f'/api/posts/{id}').json()['post']['views_count']==1
    assert b.post(f'/api/posts/{id}/like',headers=csrf(b)).json()['liked'] is True
    assert b.post(f'/api/posts/{id}/save',headers=csrf(b)).json()['saved'] is True
    assert b.get('/api/posts?saved=true').json()['total']==1
    assert b.post('/api/users/ana/follow',headers=csrf(b)).json()['following'] is True
    assert b.get('/api/users/ana').json()['followers_count']==1
    assert b.post(f'/api/posts/{id}/comments',json={'text':'Adorei a arte!'},headers=csrf(b)).status_code==201
    detail=a.get(f'/api/posts/{id}').json()
    assert detail['post']['likes_count']==1 and detail['post']['comments_count']==1
    assert len(detail['comments'])==1
    assert b.delete(f'/api/posts/{id}',headers=csrf(b)).status_code==403
    notifications=a.get('/api/notifications').json()
    assert notifications['unread']==3
    assert a.post('/api/notifications/read',headers=csrf(a)).status_code==200
    assert a.get('/api/notifications').json()['unread']==0
    comment_id=detail['comments'][0]['id']
    assert a.delete(f'/api/comments/{comment_id}',headers=csrf(a)).status_code==200
    assert a.delete(f'/api/posts/{id}',headers=csrf(a)).status_code==200
    assert a.get(f'/api/posts/{id}').status_code==404

def test_profile_updates_and_reports(clients):
    a,b=clients
    register(a,'ana');register(b,'bruno')
    p=post_art(a,upload(a))
    assert b.post('/api/reports',json={'post_id':p['id'],'reason':'Spam e conteúdo suspeito'},headers=csrf(b)).status_code==201
    assert b.get('/api/admin/reports').status_code==403
    assert a.post('/api/users/me/avatar',files={'file':('avatar.png',create_image(),'image/png')},headers=csrf(a)).status_code==200
    assert a.patch('/api/users/me',json={'bio':'Artist','theme':'light'},headers=csrf(a)).json()['user']['theme']=='light'
    assert a.patch('/api/users/me',json={'current_password':'wrong','new_password':'NewPass123'},headers=csrf(a)).status_code==403
    assert a.patch('/api/users/me',json={'current_password':'StrongPassword123','new_password':'NewPass123'},headers=csrf(a)).status_code==200
    assert a.get('/api/auth/bootstrap').json()['user']['bio']=='Artist'
    assert b.post('/api/auth/login',json={'username':'ana','password':'NewPass123'},headers=csrf(b)).status_code==200

def test_invalid_media_and_film_without_image(clients):
    a,b=clients;register(a,'ana')
    fail=a.post('/api/media/upload',files={'file':('bad.svg',b'<svg></svg>','image/svg+xml')},headers=csrf(a))
    assert fail.status_code==415
    film=a.post('/api/posts',json={'kind':'filmes','title':'Filme teste','tags':['Animação']},headers=csrf(a))
    assert film.status_code==201,film.text
    no_art=a.post('/api/posts',json={'kind':'artes','title':'Arte sem imagem'},headers=csrf(a))
    assert no_art.status_code==422

def test_moderation_and_edit_permissions(clients):
    from app.database import SessionLocal
    from app.models import User
    a,b=clients
    register(a,'ana'); register(b,'moderadora')
    post=post_art(a,upload(a))
    report=b.post('/api/reports',json={'post_id':post['id'],'reason':'A imagem viola as regras'},headers=csrf(b))
    assert report.status_code==201
    with SessionLocal() as db:
        mod=db.query(User).filter_by(username='moderadora').one()
        mod.is_admin=True
        db.commit()
    assert b.get('/api/admin/reports').status_code==403
    assert b.post('/api/admin/unlock',json={'password':'StrongPassword123'},headers=csrf(b)).status_code==200
    items=b.get('/api/admin/reports')
    assert items.status_code==200 and len(items.json()['items'])==1
    report_id=items.json()['items'][0]['id']
    assert b.post(f'/api/admin/reports/{report_id}',json={'action':'hide'},headers=csrf(b)).status_code==200
    assert a.get('/api/posts').json()['total']==0
    assert a.get(f'/api/posts/{post["id"]}').status_code==404


def test_edit_post_and_session_revocation(clients):
    a,b=clients
    register(a,'ana')
    media=upload(a)
    post=post_art(a,media)
    patch=a.patch(f'/api/posts/{post["id"]}',json={
        'kind':'artes','title':'Título novo','description':'Novo texto','tags':['Rascunhos'],
        'image_media_id':media},headers=csrf(a))
    assert patch.status_code==200 and patch.json()['post']['title']=='Título novo'
    assert a.get('/api/posts?tag=personagens').json()['total']==0
    assert a.get('/api/posts?tag=rascunhos').json()['total']==1
    assert a.get('/api/media/'+media).status_code==200
    b.post('/api/auth/login',json={'username':'ana','password':'StrongPassword123'},headers=csrf(b))
    assert b.get('/api/auth/bootstrap').json()['user']['username']=='ana'
    updated=a.patch('/api/users/me',json={
        'current_password':'StrongPassword123','new_password':'AnotherStrongPass123'},headers=csrf(a))
    assert updated.status_code==200
    assert b.get('/api/auth/bootstrap').json()['user'] is None
    assert b.post('/api/posts',json={'kind':'filmes','title':'Filme'},headers=csrf(b)).status_code==401


def test_username_display_name_and_unique_constraint(clients):
    a,b=clients
    register(a,'artist'); register(b,'otheruser')
    assert a.patch('/api/users/me',json={'username':'newartist'},headers=csrf(a)).status_code==403
    renamed=a.patch('/api/users/me',json={'username':'newartist','display_name':'Artist Name',
                            'bio':'Art and film critic','current_password':'StrongPassword123'},headers=csrf(a))
    assert renamed.status_code==200,renamed.text
    assert renamed.json()['user']['username']=='newartist'
    assert renamed.json()['user']['display_name']=='Artist Name'
    assert a.get('/api/users/newartist').status_code==200
    assert a.get('/api/users/artist').status_code==404
    conflict=b.patch('/api/users/me',json={'username':'newartist','current_password':'StrongPassword123'},headers=csrf(b))
    assert conflict.status_code==409
    assert a.patch('/api/users/me',json={'username':'admin','current_password':'StrongPassword123'},headers=csrf(a)).status_code==422


def test_comment_replies_and_user_report(clients):
    a,b=clients
    ana=register(a,'ana');bob=register(b,'bruno')
    post=post_art(a,upload(a))
    original=b.post(f'/api/posts/{post["id"]}/comments',json={'text':'Crítica original'},headers=csrf(b))
    cid=original.json()['id']
    reply=a.post(f'/api/posts/{post["id"]}/comments',json={'text':'Obrigado pela crítica!','parent_id':cid},headers=csrf(a))
    assert reply.status_code==201,reply.text
    got=a.get(f'/api/posts/{post["id"]}').json()['comments']
    assert got[1]['parent_id']==cid
    assert b.get('/api/notifications').json()['items'][0]['kind']=='reply'
    bad=b.post('/api/posts/99999/comments',json={'text':'Spam','parent_id':cid},headers=csrf(b))
    assert bad.status_code==404
    report=b.post('/api/reports',json={'user_id':ana['id'],'reason':'Comportamento abusivo'},headers=csrf(b))
    assert report.status_code==201
    assert b.post('/api/reports',json={'user_id':ana['id'],'reason':'Comportamento abusivo'},headers=csrf(b)).status_code==409
    assert b.post('/api/reports',json={'user_id':bob['id'],'reason':'Contra mim'},headers=csrf(b)).status_code==422
    assert a.post('/api/reports',json={'user_id':ana['id'],'reason':'Contra mim'},headers=csrf(a)).status_code==422


def test_admin_security_metrics_ban_audit_and_restore(clients):
    from app.database import SessionLocal
    from app.models import User
    a,b=clients
    ana=register(a,'ana');register(b,'moderadora')
    post=post_art(a,upload(a))
    with SessionLocal() as db:
        u=db.query(User).filter_by(username='moderadora').one();u.is_admin=True;db.commit()
    assert a.get('/admin').status_code==200
    assert a.get('/api/admin/summary').status_code==403
    assert b.get('/api/admin/summary').status_code==403
    assert b.post('/api/admin/unlock',json={'password':'wrong'},headers=csrf(b)).status_code==403
    assert b.get('/api/admin/summary').status_code==403
    assert b.post('/api/admin/unlock',json={'password':'StrongPassword123'},headers=csrf(b)).status_code==200
    summary=b.get('/api/admin/summary')
    assert summary.status_code==200,summary.text
    assert summary.json()['metrics']['users']==2
    assert len(summary.json()['trend'])==14
    assert summary.json()['trend'][-1]['posts']==1
    assert b.post(f'/api/admin/users/{ana["id"]}/ban',json={'reason':'12345'}).status_code==403
    assert b.post(f'/api/admin/users/{ana["id"]}/ban',json={'reason':'Violação repetida das regras'},headers=csrf(b)).status_code==200
    assert a.get('/api/auth/bootstrap').json()['user'] is None
    assert b.get('/api/admin/users').json()['items'][0]['username']=='moderadora'
    assert b.post(f'/api/admin/users/{ana["id"]}/unban',json={'reason':'Revisão do caso'},headers=csrf(b)).status_code==200
    assert b.post(f'/api/admin/posts/{post["id"]}/visibility',json={'hidden':True,'reason':'Conteúdo inadequado'},headers=csrf(b)).status_code==200
    assert a.get(f'/api/posts/{post["id"]}').status_code==404
    assert b.post(f'/api/admin/posts/{post["id"]}/visibility',json={'hidden':False,'reason':'Revisado e aprovado'},headers=csrf(b)).status_code==200
    assert a.get(f'/api/posts/{post["id"]}').status_code==200
    log=b.get('/api/admin/audit').json()['items']
    assert len(log)==4 and log[0]['action']=='restore_post'
    assert b.post('/api/admin/lock',headers=csrf(b)).status_code==200
    assert b.get('/api/admin/audit').status_code==403


def test_admin_report_resolution_and_hidden_comments(clients):
    from app.database import SessionLocal
    from app.models import User
    a,b=clients
    register(a,'ana');register(b,'moderadora')
    post=post_art(a,upload(a))
    comment=b.post(f'/api/posts/{post["id"]}/comments',json={'text':'Precisa ser avaliado'},headers=csrf(b)).json()['id']
    report=a.post('/api/reports',json={'comment_id':comment,'reason':'Comentário ofensivo'},headers=csrf(a))
    assert report.status_code==201
    with SessionLocal() as db:
        mod=db.query(User).filter_by(username='moderadora').one();mod.is_admin=True;db.commit()
    b.post('/api/admin/unlock',json={'password':'StrongPassword123'},headers=csrf(b))
    r=b.get('/api/admin/reports').json()['items'][0]
    review=b.post(f'/api/admin/reports/{r["id"]}',json={'action':'hide','reason':'Avaliação confirmada'},headers=csrf(b))
    assert review.status_code==200,review.text
    assert a.get(f'/api/posts/{post["id"]}').json()['comments']==[]
    assert a.get(f'/api/posts/{post["id"]}').json()['post']['comments_count']==0
    assert b.get('/api/admin/reports?status=resolved').json()['items'][0]['id']==r['id']
