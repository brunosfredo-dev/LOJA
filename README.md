# Kritikus — plataforma full-stack para o Render

**Versão:** 1.0.0 (MVP integrado)  
**Interface:** HTML + CSS + JavaScript, adaptada do protótipo original  
**API:** Python 3 + FastAPI  
**Banco:** PostgreSQL no Render, via SQLAlchemy 2 e migrações Alembic  
**Hospedagem:** Render Web Service + Render Postgres no mesmo Blueprint

## O que está funcionando

- Registro, login e logout com senha derivada por `scrypt`; sessão por cookie assinado, HttpOnly e Secure no Render; token CSRF nas requisições de escrita.
- Mural de Artes e Fórum de Filmes, com tags, filtro, busca (título, descrição, tags, autor), paginação e publicações por perfil.
- Criação, edição e exclusão de publicações de acordo com permissões.
- Uploads JPEG/PNG/WebP/GIF validados e convertidos para WebP com remoção de metadados; imagens hospedadas no **PostgreSQL**, não no disco efêmero do Render.
- Curtidas, salvos, comentários e seguidores reais, com contadores mantidos no servidor.
- Perfis, foto, biografia, tema claro/escuro, alteração de senha e invalidação de sessões antigas ao alterar a senha.
- Notificações persistentes de curtidas, seguidores e comentários, com leitura.
- Denúncias de posts e comentários e painel de moderação com fila e remoção/ocultação de conteúdo.
- Páginas internas de configurações, ajuda/regras, salvos, notificações e moderação; interface responsiva.
- Rate limiting por janela no banco para tentativas de login, cadastro, uploads, criação de posts/comentários, denúncias e seguir perfis.
- Endpoint de saúde `/api/health` que verifica o banco; esquema inicial versionado e aplicado com Alembic no deploy.

**Importante:** a interface era baseada em `localStorage`; o sistema novo começa com banco de dados limpo. Contas e posts locais anteriores **não** são importados automaticamente. Não reutilize as senhas antigas em texto puro.

## 1. Publicar no Render com um Blueprint

1. Extraia o ZIP e envie **todos os arquivos do projeto à raiz** de um repositório Git (incluindo `render.yaml`, `app`, `frontend`, `migrations`, `requirements.txt` e `start.sh`). Não coloque apenas a pasta `frontend` no repositório.
2. Acesse o painel do Render e selecione **New > Blueprint**. Conecte o repositório GitHub/GitLab e a branch desejada. O Render lerá `render.yaml`.
3. Revise os recursos a serem criados: **`kritikus-web`** (Python) e **`kritikus-postgres`** (PostgreSQL), ambos na região **Virginia**.
4. Confirme os custos antes de aplicar o Blueprint. O arquivo de produção usa planos **pagos e persistentes**, para não perder o banco gratuito após 30 dias.
5. O Render configura automaticamente `DATABASE_URL` com a conexão interna do banco, gera `SESSION_SECRET` e define `ENVIRONMENT=production`. **Não coloque senhas ou URLs secretas no Git.**
6. Na implantação, o comando `sh start.sh` executa `alembic upgrade head` e inicia o FastAPI. O health check `/api/health` deve retornar `{"status":"ok","database":"connected"}`.
7. Acesse a URL `.onrender.com` exibida pelo Render. Configure domínio próprio e HTTPS automático quando desejar.

### Administrador / moderação

Antes de divulgar o site, em **Web Service > Environment**, defina:

```
ADMIN_USERNAME=nome_seguro_de_moderador
ADMIN_PASSWORD=uma_senha_grande_e_unica_de_12_caracteres_ou_mais
```

Depois faça **Manual Deploy**. No boot, o sistema cria uma única conta administradora se ela ainda não existir; se o nome já existir sem privilégios, o boot falha **sem promover a conta desconhecida**. Se necessário, escolha um nome novo e redeploy. A conta entra pelo login normal e recebe a opção **Moderação** no menu. Guarde a senha fora do repositório. Depois da criação, pode remover as variáveis; a conta continuará existindo no banco.

**OBS:** sem essas variáveis o site funciona, mas **nenhum usuário terá permissões administrativas** até a conta ser criada.

### Planos e custos

`render.yaml` usa plano de serviço web `0.5c-512mb` e plano PostgreSQL `0.1c-256mb` com 5 GB de disco. Verifique a tabela de preços no painel antes de confirmar. Essa é uma arquitetura pequena para início e pode ser dimensionada no futuro.

Há uma opção `free` de Render Web Service e uma opção `free` para Postgres, mas o **Postgres Free expira após 30 dias**, e o Free Web Service tem limitações de disponibilidade. **Não use o Postgres Free para um lançamento público com dados que precisem durar.**

## 2. Rodar localmente

É necessário Python 3.11+ e pip.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

Abra `http://127.0.0.1:8000`. Localmente, sem `DATABASE_URL`, é usado um banco SQLite `kritikus_local.db` **somente para desenvolvimento**. O deploy de produção exige `DATABASE_URL` e `SESSION_SECRET`; ele não usa SQLite por acidente.

Para usar PostgreSQL localmente, defina `DATABASE_URL` na sessão do terminal. A aplicação aceita URL no formato `postgresql://...` e a adapta para `psycopg`.

## 3. Atualizar o banco sem apagar dados

As alterações de esquema são controladas pelo Alembic. No Render, as migrações pendentes rodam durante o boot do serviço. Para criar novas migrações em desenvolvimento:

```bash
alembic revision --autogenerate -m "descricao da alteracao"
alembic upgrade head
```

Revise os arquivos de migração antes de publicá-los e faça backup do banco antes de mudanças destrutivas. Nunca execute `Base.metadata.drop_all()` em produção.

## 4. Estrutura do projeto

```text
Kritikus-Render/
├── app/
│   ├── main.py           # endpoints, validações, permissões, regras de negócio
│   ├── models.py         # modelo relacional: usuários, posts, tags, interações etc.
│   ├── database.py       # engine e sessões PostgreSQL / SQLite local
│   ├── security.py       # senha, login, CSRF, limitação de tentativas
│   ├── media.py          # upload, conversão WebP, validação
│   └── manage.py         # criação do admin e limpeza de imagens órfãs
├── frontend/
│   ├── index.html
│   ├── style.css
│   ├── script.js
│   └── logokriti.png
├── migrations/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/        # revisões Alembic
├── tests/test_api.py
├── render.yaml           # infraestrutura como código
├── start.sh              # migra e sobe a API
├── alembic.ini
├── requirements.txt
└── .env.example
```

## 5. Endpoints principais

| Método | Rota | Descrição |
|---|---|---|
| GET | `/api/health` | Verifica conectividade com banco |
| GET | `/api/auth/bootstrap` | Sessão, usuário atual, CSRF, notificações |
| POST | `/api/auth/register` | Cadastro |
| POST | `/api/auth/login` | Login |
| POST | `/api/auth/logout` | Logout |
| GET | `/api/posts` | Feed, filtro, pesquisa, salvos, paginação |
| POST | `/api/posts` | Criar post |
| GET | `/api/posts/{id}` | Detalhes, visualizações e comentários |
| PATCH/DELETE | `/api/posts/{id}` | Edição/exclusão com permissão |
| POST | `/api/posts/{id}/like` | Alternar curtida |
| POST | `/api/posts/{id}/save` | Alternar item salvo |
| POST | `/api/posts/{id}/comments` | Comentar |
| DELETE | `/api/comments/{id}` | Excluir comentário autorizado |
| GET | `/api/users` | Pesquisar perfis |
| GET | `/api/users/{username}` | Perfil público |
| POST | `/api/users/{username}/follow` | Seguir/deixar de seguir |
| PATCH | `/api/users/me` | Bio, aparência, senha |
| POST | `/api/users/me/avatar` | Foto de perfil |
| POST | `/api/media/upload` | Envio de imagem (até 5 MB) |
| GET | `/api/media/{uuid}` | Recuperar imagem persistente |
| GET | `/api/notifications` | Lista de notificações |
| POST | `/api/notifications/read` | Marcar como lidas |
| POST | `/api/reports` | Denunciar conteúdo |
| GET | `/api/admin/reports` | Fila de moderação (admin) |
| POST | `/api/admin/reports/{id}` | Resolver denúncia (admin) |

**Padrão de escrita:** cliente envia o token retornado em `/api/auth/bootstrap` no cabeçalho `X-CSRF-Token`. O cookie de sessão é enviado automaticamente pelo navegador. Nenhuma senha fica no `localStorage`.

## 6. Testes

```bash
pip install pytest httpx
python -m pytest -q tests
alembic check
```

Na preparação desta entrega, **7 testes de integração passaram** com SQLite, além da validação de sintaxe do JavaScript e da migração Alembic. A implantação real no Render e os testes com PostgreSQL gerenciado **ainda precisam ser executados na sua conta**, pois o acesso ao serviço não foi fornecido. Portanto, não considere isso uma certificação de produção.

## 7. Antes de abrir inscrições públicas

O software já possui estrutura funcional, mas alguns itens dependem de operação real e não são garantidos apenas por código:

- Publicar **termos de uso e política de privacidade** completos, incluindo operador/responsável e contato, conforme a legislação aplicável, e definir canal de solicitações sobre dados pessoais.
- Definir política de moderação, acompanhar denúncias e combater spam/abuso.
- Fazer um teste final no domínio do Render, em computador e celular, com vários usuários reais.
- Configurar backup/restauração e acompanhar limites de espaço, gastos e métricas. Imagens são guardadas no banco, consumindo armazenamento PostgreSQL.
- Futuramente migrar mídias para serviço especializado de armazenamento de objetos/CDN, adicionar recuperação de senha por e-mail e verificação de e-mail antes de crescimento público.

**Limites atuais:** o aplicativo não possui recuperação de conta por e-mail, verificação de e-mail, aprovação automatizada de mídia, integração com serviço de armazenamento de objetos ou exclusão self-service da conta. Essas são melhorias recomendadas antes de escala maior ou divulgação intensa.

### Limpeza de imagens órfãs

Uploads que não foram vinculados a um post ocupam espaço no banco. Para apagar apenas arquivos não utilizados com mais de 24 horas:

```bash
python -m app.manage cleanup-media
```

Execute esse comando somente quando o banco já estiver migrado e usando a `DATABASE_URL` correta. Em produção, pode ser agendado posteriormente por um Render Cron Job.

## 8. Segurança dos segredos

- Nunca publique `DATABASE_URL`, `SESSION_SECRET` ou `ADMIN_PASSWORD`.
- `SESSION_SECRET` deve ser aleatória, com pelo menos 32 caracteres em produção.
- Habilite HTTPS, revise logs do Render, mantenha pacotes atualizados e use backups reais.
- Os planos pagos e os limites do Render mudam com o tempo; confirme as informações atuais no painel antes de contratar.
