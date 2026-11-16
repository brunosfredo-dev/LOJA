/* Kritikus — interface connected to the Python REST API.
   No user/password/post data is persisted in localStorage. */
'use strict';
const $ = (id) => document.getElementById(id);
const state = { user:null, csrf:'', kind:'artes', tag:'', query:'', page:1, hasMore:false,
                profile:null, profileTab:'posts', profilePage:1, profileMore:false,
                view:'feed', posts:[], profilePosts:[], opened:null, editId:null, searchTimer:null };
const escapeHTML = (v) => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c]));
const handle = (v) => escapeHTML(v);
const safeImage = (url) => {
  if (!url || typeof url !== 'string') return '';
  if (/^\/api\/media\/[a-f0-9-]{36}$/i.test(url)) return url;
  try { const u = new URL(url); return u.protocol === 'https:' ? u.href : ''; } catch { return ''; }
};
let toastTimer;
function aviso(message, isError=false) {
  const el = $('toast'); el.textContent = message; el.className = isError?'erro':'';
  el.style.display='block'; clearTimeout(toastTimer);
  toastTimer=setTimeout(() => { el.style.display='none'; },4200);
}
async function api(path, {method='GET', body, form}={}) {
  const headers={Accept:'application/json'};
  if (method !== 'GET') headers['X-CSRF-Token']=state.csrf;
  if (body !== undefined) headers['Content-Type']='application/json';
  let response;
  try {
    response=await fetch('/api'+path,{method, headers, credentials:'same-origin',
                   body:form ?? (body===undefined?undefined:JSON.stringify(body))});
  } catch { throw Error('Não foi possível conectar ao servidor. Verifique sua internet.'); }
  let data;
  try { data=await response.json(); } catch { data={}; }
  if (!response.ok) {
    let detail=data.detail;
    if (Array.isArray(detail)) detail=detail.map(e=>e.msg).join('; ');
    if (response.status===401 && !path.startsWith('/auth/login')) {
      state.user=null; atualizarInterfaceUsuario();
    }
    throw Error(typeof detail==='string'?detail:`Erro ${response.status} ao comunicar com o servidor.`);
  }
  return data;
}
async function executar(fn) { try { return await fn(); } catch(e) { aviso(e.message || 'Algo deu errado.',true); return null; } }
function precisaLogin(msg='Entre na sua conta para continuar.') { if (state.user) return true; aviso(msg,true); abrirEntrar(); return false; }
function aplicarTema(theme) { document.body.classList.toggle('tema-claro',theme==='light'); }
function atualizarInterfaceUsuario() {
  const logged=!!state.user;
  $('btn-entrar').style.display=logged?'none':'inline-block';
  $('btn-cadastrar').style.display=logged?'none':'inline-block';
  $('icone-perfil-id').style.display=logged?'flex':'none';
  $('menu-admin').style.display=logged&&state.user.is_admin?'list-item':'none';
  const pic=safeImage(state.user?.avatar_url);
  $('img-perfil-nav').style.display=pic?'block':'none';
  $('icone-perfil-padrao-nav').style.display=pic?'none':'inline-block';
  if(pic) $('img-perfil-nav').src=pic;
  if(logged) aplicarTema(state.user.theme);
}
function atualizarBadge(n) {
  const badge=$('badge-notificacoes');
  badge.style.display=n?'inline':'none'; badge.textContent=String(n>99?'99+':n);
}
async function carregarSessao() {
  const d=await api('/auth/bootstrap');
  state.user=d.user; state.csrf=d.csrf_token;
  atualizarInterfaceUsuario(); atualizarBadge(d.unread_notifications||0);
}
function abrirEntrar() { fecharModaisAutenticacao(); $('modal-entrar').style.display='block'; }
function abrirCadastrar() { fecharModaisAutenticacao(); $('modal-cadastrar').style.display='block'; }
function fecharModaisAutenticacao() { $('modal-entrar').style.display='none'; $('modal-cadastrar').style.display='none'; }
async function criarConta(e) {
  e.preventDefault();
  const form=e.target, button=form.querySelector('button[type="submit"]'); button.disabled=true;
  try {
    const d=await api('/auth/register',{method:'POST',body:{username:$('usuario-cadastrar').value,
                                       password:$('senha-cadastrar').value}});
    state.user=d.user; state.csrf=d.csrf_token; atualizarInterfaceUsuario();
    fecharModaisAutenticacao(); form.reset(); aviso('Conta criada! Bem-vindo ao Kritikus.'); await trocarAba('artes');
  } catch(e){ aviso(e.message,true); } finally {button.disabled=false;}
}
async function fazerLogin(e) {
  e.preventDefault();const button=e.target.querySelector('button[type="submit"]'); button.disabled=true;
  try {
    const d=await api('/auth/login',{method:'POST',body:{username:$('usuario-entrar').value,
                                      password:$('senha-entrar').value}});
    state.user=d.user; state.csrf=d.csrf_token; atualizarInterfaceUsuario();
    fecharModaisAutenticacao(); e.target.reset(); aviso('Você entrou na sua conta.'); await trocarAba(state.kind);
    const me=await api('/auth/bootstrap');atualizarBadge(me.unread_notifications||0);
  } catch(e){aviso(e.message,true);} finally {button.disabled=false;}
}
async function logout() {
  await executar(async()=>{const d=await api('/auth/logout',{method:'POST'});
    state.user=null;state.csrf=d.csrf_token;atualizarInterfaceUsuario();atualizarBadge(0);
    fecharMenuLateral(); mostrarInicio(); aviso('Você saiu da conta.');});
}
function abrirMenuLateral(){ $('menu-lateral').classList.add('aberta'); $('sobreposicao-menu-lateral').style.display='block'; }
function fecharMenuLateral(){ $('menu-lateral').classList.remove('aberta'); $('sobreposicao-menu-lateral').style.display='none'; }
function fecharModal(){ $('modal-detalhes').style.display='none'; $('conteudo-corpo-modal').replaceChildren(); state.opened=null; liberarScroll(); }
function liberarScroll() { if (![...document.querySelectorAll('.modal')].some(m=>m.style.display==='block')) document.body.style.overflow='auto'; }
function mostrarArea(area) {
  state.view=area;
  $('container-feed').style.display=area==='feed'?'grid':'none';
  $('btn-carregar-mais').style.display='none';
  $('container-busca-usuarios').style.display='none';
  $('container-perfil').style.display=area==='perfil'?'block':'none';
  $('container-pagina').style.display=area==='pagina'?'block':'none';
  $('cabecalho-inicio').style.display=area==='feed'?'block':'none';
  document.querySelector('.barra-filtros').style.display=area==='feed'?'flex':'none';
  fecharMenuLateral();
}
function fotoHTML(post, large=false) {
  const img=safeImage(post.image_url);
  if (!img) return `<div class="${large?'container-imagem-modal sem-imagem':'post-sem-imagem'}"><i class="fas fa-film"></i></div>`;
  return large?`<div class="container-imagem-modal"><img src="${handle(img)}" alt="Imagem da publicação" class="imagem-modal" loading="lazy"></div>`:
               `<img src="${handle(img)}" alt="${handle(post.title)}" loading="lazy">`;
}
function montarCartao(post, context='feed') {
  return `<article class="cartao" data-action="abrir-post" data-id="${post.id}" tabindex="0" role="button" aria-label="Abrir ${handle(post.title)}">
    ${fotoHTML(post)}
    <div class="info-cartao"><div class="titulo-cartao">${handle(post.title)}</div>
    <div class="autor-cartao autor-clicavel" data-action="perfil" data-username="${handle(post.author.username)}">@${handle(post.author.username)}</div>
    <div class="acoes-cartao">
      <button type="button" class="btn-acao ${post.liked?'curtido ativo-curtir':''}" data-action="curtir" data-id="${post.id}" aria-label="Curtir publicação"><i class="fas fa-heart"></i><span>${post.likes_count}</span></button>
      <span class="btn-acao"><i class="fas fa-comment"></i> ${post.comments_count}</span>
    </div>${context==='perfil'&&state.user?.id===post.author.id?`<div class="acoes-extras"><button class="acao-secundaria" data-action="editar" data-id="${post.id}">Editar</button><button class="acao-perigosa" data-action="excluir-post" data-id="${post.id}">Excluir</button></div>`:''}
    </div></article>`;
}
function renderFeed(items, append=false) {
  const feed=$('container-feed');
  if(!append) feed.replaceChildren();
  if(!items.length&&!append){feed.innerHTML='<p class="subtexto">Nenhuma publicação encontrada. Que tal criar a primeira?</p>';return;}
  feed.insertAdjacentHTML('beforeend',items.map(i=>montarCartao(i)).join(''));
}
async function carregarFeed(append=false) {
  if(state.view!=='feed')return;
  const params=new URLSearchParams({page:String(state.page),limit:'18'});
  if(state.kind&&!state.query)params.set('kind',state.kind);
  if(state.tag) params.set('tag',state.tag);
  if(state.query) params.set('q',state.query);
  const data=await api('/posts?'+params);
  state.posts=append?[...state.posts,...data.items]:data.items;
  renderFeed(data.items,append);
  state.hasMore=data.has_more;
  $('btn-carregar-mais').style.display=data.has_more?'block':'none';
  if(state.query&&!append) await renderizarUsuariosBusca();
}
async function renderizarUsuariosBusca() {
  const box=$('container-busca-usuarios');
  const d=await api('/users?q='+encodeURIComponent(state.query));
  box.style.display=d.items.length?'block':'none';
  box.innerHTML=d.items.length?`<h3>Perfis encontrados</h3>${d.items.map(u=>`<button data-action="perfil" data-username="${handle(u.username)}">@${handle(u.username)}</button>`).join('')}`:'';
}
async function trocarAba(tab) {
  if(!['artes','filmes'].includes(tab))return;
  state.kind=tab;state.tag='';state.query='';state.page=1;
  $('entrada-pesquisa').value='';
  $('aba-artes').classList.toggle('ativo',tab==='artes');
  $('aba-filmes').classList.toggle('ativo',tab==='filmes');
  $('titulo-secao').textContent=tab==='artes'?'Explorar Artes':'Discussões sobre Filmes';
  const names=tab==='artes'?['Tudo','Arte Digital','Personagens','Rascunhos']:
                               ['Todos os Gêneros','Animação','Ficção Científica','Análises com Spoilers'];
  $('etiquetas-dinamicas').innerHTML=names.map((t,i)=>`<button class="btn-etiqueta ${i===0?'ativo':''}" data-action="filtro" data-tag="${handle(t)}">${handle(t)}</button>`).join('');
  mostrarArea('feed');await executar(()=>carregarFeed());
}
function filterByTag(tag, btn) {
  state.tag=tag==='Tudo'||tag==='Todos os Gêneros'?'':tag.toLocaleLowerCase('pt-BR');
  state.page=1; state.query='';$('entrada-pesquisa').value='';
  document.querySelectorAll('.btn-etiqueta').forEach(el=>el.classList.toggle('ativo',el===btn));
  executar(()=>carregarFeed());
}
function mostrarInicio(){ fecharModal();fecharModaisAutenticacao();fecharModalCriar();trocarAba('artes'); history.replaceState(null,'',location.pathname); }
async function openModalById(id){
  const data=await executar(()=>api('/posts/'+Number(id)));if(!data)return;
  state.opened=data.post; renderDetalhes(data.post,data.comments);
  $('modal-detalhes').style.display='block';document.body.style.overflow='hidden';
  history.replaceState(null,'','#post-'+id);
}
function openModal(item){ return openModalById(item.id); }
function renderDetalhes(post, comments) {
  const isOwner=state.user?.id===post.author.id, isAdmin=!!state.user?.is_admin;
  $('conteudo-corpo-modal').innerHTML=`
    ${fotoHTML(post,true)}<div class="container-info-modal">
      <div class="barra-acao-modal">
        <button class="btn-modal ${post.liked?'ativo-curtir':''}" data-action="curtir" data-id="${post.id}"><i class="fas fa-heart"></i> ${post.liked?'Curtido':'Curtir'}</button>
        <button class="btn-modal" data-action="foco-comentario"><i class="fas fa-comment"></i> Comentar</button>
        <button class="btn-modal ${post.saved?'ativo-salvar':''}" data-action="salvar" data-id="${post.id}"><i class="fas fa-bookmark"></i> ${post.saved?'Salvo':'Salvar'}</button>
      </div>
      <div class="cabecalho-modal"><div class="area-titulo-modal"><h2>${handle(post.title)}</h2>
        <div class="autor-modal">por <span class="autor-clicavel" data-action="perfil" data-username="${handle(post.author.username)}">@${handle(post.author.username)}</span></div>
        <p style="margin-top:10px;white-space:pre-wrap;color:var(--text-muted)">${handle(post.description)}</p></div>
        ${!isOwner?`<button class="btn-seguir ${post.following?'seguindo':''}" data-action="seguir" data-username="${handle(post.author.username)}"><i class="fas ${post.following?'fa-check':'fa-plus'}"></i> ${post.following?'Seguindo':'Seguir'}</button>`:''}
      </div>
      <div class="estatisticas-modal"><span><i class="fas fa-heart"></i> ${post.likes_count} curtidas</span><span><i class="fas fa-comment"></i> ${post.comments_count} comentários</span><span><i class="fas fa-eye"></i> ${post.views_count} visualizações</span></div>
      <div class="etiquetas-modal">${post.tags.map(t=>`<span class="etiqueta-modal">${handle(t)}</span>`).join('')}</div>
      <div class="acoes-extras">${isOwner||isAdmin?`<button class="acao-secundaria" data-action="editar" data-id="${post.id}">Editar</button><button class="acao-perigosa" data-action="excluir-post" data-id="${post.id}">Excluir</button>`:''}
      ${!isOwner&&state.user?`<button class="acao-secundaria" data-action="denunciar-post" data-id="${post.id}"><i class="fas fa-flag"></i> Denunciar publicação</button>`:''}</div>
      <section class="secao-comentarios"><h3>Comentários (${comments.length})</h3>
        <form id="form-comentario" class="caixa-adicionar-comentario"><input id="entrada-comentario" required maxlength="1500" placeholder="${state.user?'Escreva um comentário...':'Entre na sua conta para comentar'}" ${state.user?'':'disabled'}>
          <button class="btn-criar" type="submit" ${state.user?'':'disabled'}><i class="fas fa-paper-plane"></i></button></form>
        <div id="lista-comentarios">${comments.length?comments.map(c=>`<div class="item-comentario"><div class="autor-comentario-falso autor-clicavel" data-action="perfil" data-username="${handle(c.author.username)}">@${handle(c.author.username)}</div><div class="texto-comentario-falso" style="white-space:pre-wrap">${handle(c.text)}</div>
          ${c.can_delete?`<button class="btn-excluir-comentario" data-action="excluir-comentario" data-id="${c.id}" aria-label="Excluir comentário"><i class="fas fa-times"></i></button>`:''}
          ${state.user&&!c.can_delete?`<button class="acao-secundaria" style="margin:8px 0" data-action="denunciar-comentario" data-id="${c.id}">Denunciar</button>`:''}</div>`).join(''):'<p class="subtexto">Nenhum comentário ainda.</p>'}</div>
      </section>
    </div>`;
}
async function atualizarModal(){ if(state.opened) {const d=await api('/posts/'+state.opened.id+'?track_view=false'); state.opened=d.post;renderDetalhes(d.post,d.comments);} }
async function atualizarVisao(){
  if(state.view==='feed')await carregarFeed();
  if(state.view==='perfil')await carregarPerfilPosts();
}
async function togglePostLike(id){ if(!precisaLogin('Faça login para curtir.'))return;
  await executar(async()=>{await api(`/posts/${id}/like`,{method:'POST'});await atualizarVisao();await atualizarModal();}); }
async function togglePostSave(id){ if(!precisaLogin('Faça login para salvar.'))return;
  await executar(async()=>{const r=await api(`/posts/${id}/save`,{method:'POST'});aviso(r.saved?'Publicação salva.':'Removido dos salvos.');await atualizarVisao();await atualizarModal();}); }
async function toggleFollowUser(username){ if(!precisaLogin('Entre para seguir perfis.'))return;
  await executar(async()=>{await api(`/users/${encodeURIComponent(username)}/follow`,{method:'POST'});
    if(state.view==='perfil')await mostrarPerfil(state.profile);
    await atualizarModal();}); }
async function adicionarComentario(e){ e.preventDefault();if(!precisaLogin()||!state.opened)return;
  const text=$('entrada-comentario').value.trim();if(!text)return;
  await executar(async()=>{await api(`/posts/${state.opened.id}/comments`,{method:'POST',body:{text}});
    await atualizarModal();await atualizarVisao();});
}
async function deletarComentario(id){ if(!confirm('Excluir este comentário?'))return;
  await executar(async()=>{await api(`/comments/${id}`,{method:'DELETE'});await atualizarModal();await atualizarVisao();}); }
async function deletarPost(id){if(!confirm('Excluir essa publicação permanentemente?'))return;
  await executar(async()=>{await api(`/posts/${id}`,{method:'DELETE'});fecharModal();aviso('Publicação excluída.');await atualizarVisao();}); }
async function denunciar(post_id=null,comment_id=null){if(!precisaLogin())return;
  const reason=prompt('Qual é o motivo da denúncia? (mínimo 5 caracteres)');if(reason===null)return;
  if(reason.trim().length<5)return aviso('Escreva um motivo com pelo menos 5 caracteres.',true);
  await executar(async()=>{await api('/reports',{method:'POST',body:{post_id,comment_id,reason:reason.trim()}});
    aviso('Denúncia enviada para moderação.');});
}
async function mostrarPerfil(username=null){
  const target=(username || state.user?.username || '').replace(/^@/,'');
  if(!target){precisaLogin('Entre para abrir seu perfil.');return;}
  fecharModal(); state.profile=target;
  const profile=await executar(()=>api('/users/'+encodeURIComponent(target)));
  if(!profile)return;
  mostrarArea('perfil'); state.profileTab='posts';state.profilePage=1;
  $('nome-usuario-perfil').textContent='@'+profile.user.username;
  $('seguidores-perfil').innerHTML=`<strong>${profile.followers_count}</strong> Seguidores`;
  $('seguindo-perfil').innerHTML=`<strong>${profile.following_count}</strong> Seguindo`;
  const pic=safeImage(profile.user.avatar_url);
  $('exibicao-img-perfil').style.display=pic?'block':'none';
  $('icone-perfil-padrao').style.display=pic?'none':'inline-block';
  if(pic)$('exibicao-img-perfil').src=pic;
  const own=profile.is_me, action=$('acoes-perfil'), avatar=$('container-avatar-perfil');
  avatar.classList.toggle('pode-editar',own);avatar.style.cursor=own?'pointer':'default';
  avatar.onclick=own?abrirTrocaDeFoto:null;
  $('sobreposicao-editar-avatar').style.display=own?'flex':'none';
  action.innerHTML=`<p class="perfil-bio">${handle(profile.user.bio||'Nenhuma biografia ainda.')}</p>`+
    (own?`<button class="btn-entrar" data-action="configuracoes">Editar perfil</button>`:
       `<button class="btn-seguir ${profile.following?'seguindo':''}" data-action="seguir" data-username="${handle(target)}"><i class="fas ${profile.following?'fa-check':'fa-plus'}"></i> ${profile.following?'Seguindo':'Seguir'}</button>`);
  $('aba-salvos').style.display=own?'inline-block':'none';
  $('aba-minhas-publicacoes').textContent=own?'Minhas Publicações':'Publicações de @'+target;
  $('aba-minhas-publicacoes').classList.add('ativo');$('aba-salvos').classList.remove('ativo');
  history.replaceState(null,'','#user-'+encodeURIComponent(target));
  await executar(()=>carregarPerfilPosts());
}
async function trocarAbaPerfil(tab){
  state.profileTab=(tab==='salvos'||tab==='saved')?'saved':'posts';state.profilePage=1;
  $('aba-minhas-publicacoes').classList.toggle('ativo',state.profileTab==='posts');
  $('aba-salvos').classList.toggle('ativo',state.profileTab==='saved');
  await executar(()=>carregarPerfilPosts());
}
async function carregarPerfilPosts(append=false){
  const params=new URLSearchParams({limit:'18',page:String(state.profilePage)});
  if(state.profileTab==='saved') params.set('saved','true');
  else params.set('author',state.profile);
  const d=await api('/posts?'+params);
  state.profileMore=d.has_more;
  const container=$('feed-perfil');
  if(!append)container.innerHTML='';
  if(!d.items.length&&!append)container.innerHTML='<p class="subtexto">Nenhuma publicação encontrada.</p>';
  else container.insertAdjacentHTML('beforeend',d.items.map(i=>montarCartao(i,'perfil')).join(''));
  $('btn-mais-perfil').style.display=d.has_more?'block':'none';
}
function abrirTrocaDeFoto(){ $('entrada-foto-perfil').click(); }
async function salvarFotoPerfil(e){
  if(!e.target.files?.[0])return;
  const form=new FormData(); form.append('file',e.target.files[0]);
  await executar(async()=>{const d=await api('/users/me/avatar',{method:'POST',form});state.user=d.user;
    atualizarInterfaceUsuario(); await mostrarPerfil(state.user.username); aviso('Foto de perfil atualizada.');});
  e.target.value='';
}
function abrirModalCriar(post=null) {
  if(!precisaLogin('Entre para publicar.'))return;
  const p=post&&typeof post==='object'?post:null;
  state.editId=p?.id??null;
  $('formulario-criar').reset();
  $('tipo-publicacao').value=p?.kind||state.kind;
  $('titulo-publicacao').value=p?.title||'';
  $('descricao-publicacao').value=p?.description||'';
  $('etiquetas-publicacao').value=p?.tags?.join(', ')||'';
  $('url-imagem-publicacao').value=p?.image_url?.startsWith('https://')?p.image_url:'';
  $('titulo-modal-criar').textContent=p?'Editar publicação':'Criar Novo Post';
  $('texto-botao-publicar').textContent=p?'Salvar alterações':'Publicar no Kritikus';
  $('modal-criar').style.display='block';document.body.style.overflow='hidden';
}
function fecharModalCriar(){
  $('modal-criar').style.display='none';$('formulario-criar').reset();state.editId=null;liberarScroll();
}
async function salvarPost(e){
  e.preventDefault();if(!precisaLogin())return;
  const button=e.target.querySelector('button[type="submit"]');button.disabled=true;
  try {
    const kind=$('tipo-publicacao').value;
    const payload={kind,title:$('titulo-publicacao').value.trim(),description:$('descricao-publicacao').value.trim(),
                   tags:$('etiquetas-publicacao').value.split(',').map(t=>t.trim()).filter(Boolean).slice(0,8),
                   image_external_url:$('url-imagem-publicacao').value.trim()||null,image_media_id:null};
    const f=$('arquivo-imagem-publicacao').files[0];
    if(f){const form=new FormData();form.append('file',f);const uploaded=await api('/media/upload',{method:'POST',form});payload.image_media_id=uploaded.media_id;payload.image_external_url=null;}
    else if(state.editId&&!payload.image_external_url){
      const existing=state.opened?.id===state.editId?state.opened:await api('/posts/'+state.editId).then(r=>r.post);
      if(existing.image_url?.startsWith('/api/media/'))payload.image_media_id=existing.image_url.split('/').pop();
      else payload.image_external_url=existing.image_url;
    }
    const editing=state.editId;
    await api(editing?'/posts/'+editing:'/posts',{method:editing?'PATCH':'POST',body:payload});
    fecharModal();fecharModalCriar();aviso(editing?'Publicação atualizada.':'Sua publicação foi publicada!');
    await trocarAba(kind);
  }catch(err){aviso(err.message,true);}finally{button.disabled=false;}
}
function pagina(title, content){ fecharModal();mostrarArea('pagina');$('container-pagina').innerHTML=`<h2>${handle(title)}</h2>${content}`; }
async function mostrarSalvos(){if(!precisaLogin())return;await mostrarPerfil(state.user.username);await trocarAbaPerfil('saved');}
async function mostrarNotificacoes(){if(!precisaLogin())return;
  const d=await executar(()=>api('/notifications'));if(!d)return;
  const tipo={follow:'começou a seguir você.',like:'curtiu sua publicação.',comment:'comentou sua publicação.'};
  pagina('Notificações',`<div class="painel"><div class="card-painel-btn"><button class="btn-entrar" data-action="ler-notificacoes">Marcar todas como lidas</button></div>
  ${d.items.length?d.items.map(n=>`<div class="lista-notificacao ${n.is_read?'':'nao-lida'}"><button ${n.post_id?`data-action="abrir-post" data-id="${n.post_id}"`:''}>
  <strong>@${handle(n.actor)}</strong> ${handle(tipo[n.kind]||'interagiu com você.')}<div class="subtexto">${new Date(n.created_at).toLocaleString('pt-BR')}</div></button>
  </div>`).join(''):'<p>Você ainda não tem notificações.</p>'}</div>`);
  atualizarBadge(d.unread);
}
function mostrarAjuda(){
  pagina('Ajuda e regras da comunidade',`<div class="painel">
    <h3>Sobre o Kritikus</h3><p>Espaço para compartilhar trabalhos artísticos, debater filmes e trocar críticas construtivas.</p>
    <h3>Regras de convivência</h3><p>Respeite as pessoas. Não publique assédio, ameaças, discriminação, conteúdo ilegal ou dados privados. Não se aproprie de artes ou imagens de terceiros. Identifique spoilers nas tags ou no título quando necessário.</p>
    <h3>Direitos autorais</h3><p>Publique apenas imagens que você criou ou tem permissão para compartilhar. Créditos não substituem autorização.</p>
    <h3>Segurança</h3><p>Use uma senha exclusiva. Denuncie publicações ou comentários que violem as regras. As denúncias ficam disponíveis à moderação.</p>
    <h3>Dados</h3><p>Seu nome de usuário, suas publicações e suas interações públicas aparecem para outras pessoas. Não publique informações pessoais que queira manter privadas.</p>
    <p class="subtexto">Antes de abrir inscrições públicas, o operador do Kritikus deve publicar a política de privacidade e os termos completos, com informações de contato reais.</p>
  </div>`);
}
function mostrarConfiguracoes(){if(!precisaLogin())return;
  pagina('Configurações de conta',`<div class="painel"><h3>Meu perfil</h3><p>Seu usuário: @${handle(state.user.username)}</p>
    <form id="form-configuracoes"><label for="bio-config">Biografia</label><textarea id="bio-config" maxlength="500" rows="3">${handle(state.user.bio)}</textarea>
      <label for="tema-config">Aparência</label><select id="tema-config"><option value="dark" ${state.user.theme==='dark'?'selected':''}>Escuro</option><option value="light" ${state.user.theme==='light'?'selected':''}>Claro</option></select>
      <button class="btn-criar" type="submit">Salvar configurações</button></form></div>
    <div class="painel"><h3>Segurança</h3><form id="form-senha"><label>Senha atual</label><input type="password" id="senha-antiga" autocomplete="current-password" required>
      <label>Nova senha (mínimo 8 caracteres)</label><input type="password" id="senha-nova" autocomplete="new-password" minlength="8" required>
      <button type="submit" class="btn-entrar">Alterar senha</button></form></div>`);
}
async function mudarTema(){if(!precisaLogin())return;
  await executar(async()=>{const d=await api('/users/me',{method:'PATCH',body:{theme:state.user.theme==='dark'?'light':'dark'}});
    state.user=d.user;state.csrf=d.csrf_token;atualizarInterfaceUsuario();aviso('Tema atualizado.');});}
async function mostrarModeracao(){if(!state.user?.is_admin)return aviso('Acesso restrito.',true);
  const d=await executar(()=>api('/admin/reports'));if(!d)return;
  pagina('Moderação · Denúncias pendentes',`<div class="painel">${d.items.length?d.items.map(r=>`<div class="lista-notificacao"><div>
    <strong>Denúncia #${r.id}</strong><div>${handle(r.reason)}</div><div class="subtexto">${r.post_id?'Publicação #'+r.post_id:'Comentário #'+r.comment_id}</div>
    </div><div class="card-painel-btn"><button class="acao-secundaria" data-action="moderar" data-id="${r.id}" data-review="dismiss">Ignorar</button>
    <button class="acao-perigosa" data-action="moderar" data-id="${r.id}" data-review="hide">Remover conteúdo</button></div></div>`).join(''):'<p>Não há denúncias pendentes.</p>'}</div>`);
}
async function handleSidebar(action){fecharMenuLateral();
  if(action==='perfil')return mostrarPerfil();
  if(action==='salvos')return mostrarSalvos();
  if(action==='notificacoes')return mostrarNotificacoes();
  if(action==='tema')return mudarTema();
  if(action==='configuracoes')return mostrarConfiguracoes();
  if(action==='ajuda')return mostrarAjuda();
  if(action==='moderacao')return mostrarModeracao();
  if(action==='sair')return logout();
}
// Single event router: dynamic content never inserts executable user strings in inline handlers.
document.addEventListener('click',async e=>{
  const link=e.target.closest('[data-menu]');if(link){e.preventDefault();await handleSidebar(link.dataset.menu);return;}
  const el=e.target.closest('[data-action]');if(!el)return;
  e.preventDefault();e.stopPropagation();
  const id=Number(el.dataset.id), name=el.dataset.username;
  switch(el.dataset.action){
    case 'abrir-post':await openModalById(id);break;
    case 'perfil':await mostrarPerfil(name);break;
    case 'curtir':await togglePostLike(id);break;
    case 'salvar':await togglePostSave(id);break;
    case 'seguir':await toggleFollowUser(name);break;
    case 'editar': {
      const d=await executar(()=>api('/posts/'+id));if(d){fecharModal();abrirModalCriar(d.post);}break;
    }
    case 'excluir-post':await deletarPost(id);break;
    case 'excluir-comentario':await deletarComentario(id);break;
    case 'denunciar-post':await denunciar(id);break;
    case 'denunciar-comentario':await denunciar(null,id);break;
    case 'foco-comentario':$('entrada-comentario')?.focus();break;
    case 'filtro':filterByTag(el.dataset.tag,el);break;
    case 'mais-feed':state.page++;await executar(()=>carregarFeed(true));break;
    case 'mais-perfil':state.profilePage++;await executar(()=>carregarPerfilPosts(true));break;
    case 'configuracoes':mostrarConfiguracoes();break;
    case 'ler-notificacoes':await executar(async()=>{await api('/notifications/read',{method:'POST'});atualizarBadge(0);await mostrarNotificacoes();});break;
    case 'moderar':if(confirm('Confirmar ação de moderação?'))await executar(async()=>{await api('/admin/reports/'+id,{method:'POST',body:{action:el.dataset.review}});await mostrarModeracao();});break;
  }
});
document.addEventListener('submit',async e=>{
  if(e.target.id==='form-comentario')return adicionarComentario(e);
  if(e.target.id==='form-configuracoes'){
    e.preventDefault();await executar(async()=>{const d=await api('/users/me',{method:'PATCH',body:{bio:$('bio-config').value,theme:$('tema-config').value}});
      state.user=d.user;state.csrf=d.csrf_token;atualizarInterfaceUsuario();aviso('Configurações salvas.');});
  }
  if(e.target.id==='form-senha'){
    e.preventDefault();await executar(async()=>{const d=await api('/users/me',{method:'PATCH',body:{current_password:$('senha-antiga').value,new_password:$('senha-nova').value}});
      state.user=d.user;state.csrf=d.csrf_token;e.target.reset();aviso('Senha alterada. Sessões anteriores foram invalidadas.');});
  }
});
document.addEventListener('keydown',e=>{
  if(e.key==='Escape'){fecharModal();fecharModalCriar();fecharModaisAutenticacao();fecharMenuLateral();}
  if((e.key==='Enter'||e.key===' ')&&e.target.matches('.cartao[data-action="abrir-post"]')){e.preventDefault();openModalById(e.target.dataset.id);}
});
window.addEventListener('click',e=>{
  if(e.target===$('modal-detalhes'))fecharModal();
  if(e.target===$('modal-criar'))fecharModalCriar();
  if(e.target===$('modal-entrar')||e.target===$('modal-cadastrar'))fecharModaisAutenticacao();
});
$('entrada-pesquisa').addEventListener('input',e=>{
  clearTimeout(state.searchTimer);
  state.searchTimer=setTimeout(()=>{
    const val=e.target.value.trim();
    if(state.view!=='feed')mostrarArea('feed');
    state.query=val;state.page=1;state.tag='';
    document.querySelectorAll('.btn-etiqueta').forEach((b,i)=>b.classList.toggle('ativo',i===0));
    executar(()=>carregarFeed());
  },330);
});
window.addEventListener('hashchange',()=>{if(location.hash.startsWith('#post-'))openModalById(location.hash.substring(6));});
(async function iniciar(){
  try{
    await carregarSessao();await trocarAba('artes');
    if(location.hash.startsWith('#post-'))await openModalById(location.hash.substring(6));
    if(location.hash.startsWith('#user-'))await mostrarPerfil(decodeURIComponent(location.hash.substring(6)));
  }catch(e){ aviso('Falha ao carregar o Kritikus: '+e.message,true); }
})();
