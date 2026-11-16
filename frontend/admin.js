'use strict';
const $=id=>document.getElementById(id);
const escapeHTML=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=n=>new Intl.NumberFormat('pt-BR').format(Number(n)||0);
const date=s=>s?new Date(s).toLocaleString('pt-BR'):'—';
let csrf='',view='overview',page=1,query='',filter='pending',busy=false,modalResolver=null,previousFocus=null,toastTimer;
const titles={overview:['Visão geral','PLATFORM INTELLIGENCE','Acompanhe a saúde da comunidade, crescimento e moderação.'],reports:['Denúncias','TRUST & SAFETY','Fila de denúncias recebidas e decisões de moderação.'],users:['Usuários','MEMBER MANAGEMENT','Gerencie contas e suspensões com trilha de auditoria.'],posts:['Publicações','CONTENT OPERATIONS','Controle a visibilidade dos conteúdos da plataforma.'],audit:['Auditoria','ACCOUNTABILITY','Histórico das ações realizadas pela administração.']};
function toast(message,error=false){const el=$('admin-toast');el.textContent=message;el.className='toast'+(error?' error':'');el.hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>el.hidden=true,4500);}
async function api(path,options={}){
  const headers={'Accept':'application/json',...options.headers};
  if(options.method&&options.method!=='GET')headers['X-CSRF-Token']=csrf;
  if(options.body!==undefined)headers['Content-Type']='application/json';
  let response;try{response=await fetch('/api'+path,{...options,credentials:'same-origin',headers,body:options.body===undefined?undefined:JSON.stringify(options.body)});}catch{throw Error('Sem conexão com o servidor.');}
  const data=await response.json().catch(()=>({}));
  if(!response.ok){if(response.status===401 || (response.status===403&&String(data.detail||'').includes('Confirme sua senha')))lockUI();throw Error(typeof data.detail==='string'?data.detail:`Erro HTTP ${response.status}`);}
  return data;
}
async function setup(){
  const bootstrap=await api('/auth/bootstrap');csrf=bootstrap.csrf_token;
  const session=await api('/admin/session');
  if(session.unlocked){unlocked(session.username);await navigate('overview');return;}
  $('gate-username').hidden=!!session.is_admin;
  $('gate-username').required=!session.is_admin;
  $('gate-user-label').hidden=!!session.is_admin;
  $('gate-username').value=session.username||'';
  $('gate-password').focus();
}
function lockUI(){ $('admin-app').hidden=true;$('login-overlay').hidden=false;$('gate-password').value='';}
function unlocked(name){$('login-overlay').hidden=true;$('admin-app').hidden=false;$('admin-username').textContent='@'+name;}
$('unlock-form').addEventListener('submit',async e=>{
 e.preventDefault();const btn=$('gate-submit');btn.disabled=true;$('gate-error').hidden=true;
 const username=$('gate-username').value.trim(),password=$('gate-password').value;
 try{
   const session=await api('/admin/session');
   if(!session.is_admin){
     const login=await api('/auth/login',{method:'POST',body:{username,password}});csrf=login.csrf_token;
   }
   const unlockedData=await api('/admin/unlock',{method:'POST',body:{password}});
   if(unlockedData.ok){const info=await api('/admin/session');unlocked(info.username);$('gate-password').value='';await navigate('overview');}
 }catch(err){$('gate-error').textContent=err.message;$('gate-error').hidden=false;}
 finally{btn.disabled=false;}
});
$('lock-panel').addEventListener('click',async()=>{
 try{await api('/admin/lock',{method:'POST'});lockUI();await setup();toast('Painel bloqueado.');}catch(e){toast(e.message,true);}
});
$('refresh').addEventListener('click',()=>navigate(view));
$('side-nav').addEventListener('click',e=>{const target=e.target.closest('[data-view]');if(target)navigate(target.dataset.view);});
function setHeading(which){const [title,eyebrow,caption]=titles[which];$('page-title').innerHTML=escapeHTML(title)+'<span class="title-period">.</span>';$('page-eyebrow').textContent=eyebrow;$('page-caption').textContent=caption;$('breadcrumb-current').textContent=which.toUpperCase();document.querySelectorAll('[data-view]').forEach(el=>el.classList.toggle('selected',el.dataset.view===which));}
async function navigate(which,append=false){
 if(!titles[which]||busy)return;
 if(!append){view=which;page=1;query='';filter='pending';setHeading(which);$('panel-content').innerHTML='<div class="empty-state">Carregando dados da administração...</div>';}
 busy=true;
 try{
   if(which==='overview')await overview();
   if(which==='reports')await reports(append);
   if(which==='users')await users(append);
   if(which==='posts')await posts(append);
   if(which==='audit')await audit(append);
   $('last-update').textContent='Atualizado '+new Date().toLocaleTimeString('pt-BR');
 }catch(e){toast(e.message,true);if(!append)$('panel-content').innerHTML='<div class="empty-state">Não foi possível carregar esta área.</div>';}
 finally{busy=false;}
}
function stat(label,value,extra='',warn=false){return `<div class="kpi ${warn?'warn':''}"><div class="label">${label}</div><strong>${fmt(value)}</strong><small>${extra}</small></div>`;}
function chart(points){
 const max=Math.max(1,...points.map(x=>x.posts)),width=700,height=218,left=8,right=690,top=18,bottom=186;
 const xy=points.map((p,i)=>({x:left+i*(right-left)/(points.length-1),y:bottom-p.posts/max*(bottom-top)}));
 const line=xy.map((p,i)=>(i?'L':'M')+p.x.toFixed(1)+' '+p.y.toFixed(1)).join(' ');
 const area=line+` L${right} ${bottom} L${left} ${bottom} Z`;
 return `<svg class="chart" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" aria-label="Publicações por dia nos últimos 14 dias" role="img"><defs><linearGradient id="areaGrad" x1="0" x2="0" y1="0" y2="1"><stop stop-color="#45cbc5" stop-opacity=".27"/><stop offset="1" stop-color="#45cbc5" stop-opacity="0"/></linearGradient></defs>${[0,1,2,3].map(i=>`<line class="chart-grid" x1="${left}" y1="${top+i*(bottom-top)/3}" x2="${right}" y2="${top+i*(bottom-top)/3}"/>`).join('')}<path d="${area}" fill="url(#areaGrad)"/><path class="chart-line" d="${line}"/>${xy.map(p=>`<circle class="chart-dot" cx="${p.x}" cy="${p.y}" r="3.1"/>`).join('')}<text class="chart-label" x="${left}" y="212">${escapeHTML(points[0]?.date.slice(5)||'')}</text><text class="chart-label" x="${right-36}" y="212">${escapeHTML(points.at(-1)?.date.slice(5)||'')}</text></svg>`;
}
async function overview(){const d=await api('/admin/summary'),m=d.metrics;
 $('nav-reports').textContent=fmt(m.reports_pending);
 $('panel-content').innerHTML=`<div class="kpis">${stat('Usuários cadastrados',m.users,'+'+fmt(m.new_users_7d)+' em 7 dias')}${stat('Publicações',m.posts,'+'+fmt(m.new_posts_7d)+' em 7 dias')}${stat('Comentários',m.comments,'Interações da comunidade')}${stat('Denúncias pendentes',m.reports_pending,'Requerem revisão',m.reports_pending>0)}</div>
 <div class="board-grid"><section class="board-card"><h2>Crescimento do conteúdo</h2><p class="board-caption">Publicações realizadas nos últimos 14 dias</p>${chart(d.trend)}</section>
 <section class="board-card"><h2>Saúde da comunidade</h2><p class="board-caption">Indicadores operacionais atuais</p>
 <div class="quick-stat"><span>Membros ativos (7 dias)*</span><strong>${fmt(m.active_users_7d)}</strong></div><div class="quick-stat"><span>Contas suspensas</span><strong>${fmt(m.banned_users)}</strong></div><div class="quick-stat"><span>Publicações visíveis</span><strong>${fmt(m.visible_posts)}</strong></div><div class="quick-stat"><span>Curtidas totais</span><strong>${fmt(m.likes)}</strong></div><div class="quick-stat"><span>Denúncias registradas</span><strong>${fmt(m.reports_total)}</strong></div><div class="quick-stat"><span>Visualizações de posts*</span><strong>${fmt(m.total_views)}</strong></div><div class="quick-stat"><span>Imagens no banco</span><strong>${fmt(m.media_count)}</strong></div><div class="quick-stat"><span>Armazenamento de imagens</span><strong>${(m.media_bytes/1048576).toFixed(1)} MB</strong></div>
 <p class="muted" style="font-size:11px">* Atividade = autores de posts/comentários nos últimos 7 dias; visualizações não representam visitantes únicos.</p></section></div>`;
}
const table=(headers,rows)=>`<div class="table-scroll"><table class="data-table"><thead><tr>${headers.map(h=>`<th>${escapeHTML(h)}</th>`).join('')}</tr></thead><tbody>${rows.join('')}</tbody></table></div>`;
const empty=(what)=>`<div class="empty-state"><strong>Nada por aqui.</strong>${escapeHTML(what)}</div>`;
const more=has=>has?'<button class="ghost-btn more-btn" data-action="more">Carregar mais resultados ↓</button>':'';
function frame(inner){return `<section class="data-card">${inner}</section>`;}
function reportCard(r){const target=r.user_id?`Usuário #${r.user_id}`:r.post_id?`Publicação #${r.post_id}`:`Comentário #${r.comment_id}`;
 return `<div class="report-card"><div class="report-meta"><span>DENÚNCIA #${r.id} · ${escapeHTML(date(r.created_at))} · enviada por @${escapeHTML(r.reporter)}</span><span class="pill ${r.status==='pending'?'warn':'ok'}">${escapeHTML(r.status)}</span></div><h3>${escapeHTML(target)}</h3><p>${escapeHTML(r.reason)}</p><div class="report-actions">${r.status==='pending'?`<button class="ghost-btn" data-action="review" data-id="${r.id}" data-choice="dismiss">Descartar</button><button class="ghost-btn" data-action="review" data-id="${r.id}" data-choice="resolve">Resolver</button>${!r.user_id?`<button class="ghost-btn danger" data-action="review" data-id="${r.id}" data-choice="hide">Ocultar / remover</button>`:''}`:''}${r.user_id?`<button class="ghost-btn" data-view="users" data-action="find-user" data-id="${r.user_id}">Ver na gestão de usuários</button>`:''}${r.post_id?`<a class="ghost-btn" href="/#post-${r.post_id}" target="_blank" rel="noopener">Abrir publicação ↗</a>`:''}</div></div>`;
}
async function reports(append=false){const d=await api('/admin/reports?'+new URLSearchParams({status:filter,page:String(page)}));
 if(!append)$('panel-content').innerHTML=frame(`<div class="section-actions"><h2>Fila de moderação</h2><select id="report-filter" class="filter-select"><option value="pending" ${filter==='pending'?'selected':''}>Pendentes</option><option value="resolved" ${filter==='resolved'?'selected':''}>Resolvidas</option><option value="dismissed" ${filter==='dismissed'?'selected':''}>Descartadas</option><option value="all" ${filter==='all'?'selected':''}>Todas</option></select></div><div id="report-rows" class="report-list"></div><div id="more-slot"></div>`);
 const holder=$('report-rows');if(!append)holder.innerHTML='';holder.insertAdjacentHTML('beforeend',d.items.length?d.items.map(reportCard).join(''):!append?empty('Nenhuma denúncia neste filtro.'):'' );$('more-slot').innerHTML=more(d.has_more);
}
async function users(append=false){const d=await api('/admin/users?'+new URLSearchParams({q:query,page:String(page)}));
 const rows=d.items.map(u=>`<tr><td><div class="cell-title">${escapeHTML(u.display_name||u.username)}</div><div class="cell-sub">@${escapeHTML(u.username)} · ID ${u.id}</div></td><td><span class="pill ${u.is_banned?'warn':'ok'}">${u.is_admin?'Admin':u.is_banned?'Suspenso':'Ativo'}</span></td><td>${escapeHTML(date(u.created_at))}</td><td><div class="table-actions">${u.is_admin?'<span class="muted">Protegido</span>':`<button class="ghost-btn ${u.is_banned?'':'danger'}" data-action="${u.is_banned?'unban':'ban'}" data-id="${u.id}">${u.is_banned?'Reativar':'Suspender'}</button>`}</div></td></tr>`);
 if(!append)$('panel-content').innerHTML=frame(`<div class="section-actions"><h2>Diretório de usuários</h2><form id="search-form"><input class="search-input" id="search-input" value="${escapeHTML(query)}" placeholder="Buscar por nome ou @..."><button class="ghost-btn" type="submit">Pesquisar</button></form></div><div id="table-slot">${table(['Conta','Situação','Cadastro','Ações'],[])}</div><div id="more-slot"></div>`);
 const tbody=$('table-slot')?.querySelector('tbody');
 if(tbody){if(!append)tbody.innerHTML='';tbody.insertAdjacentHTML('beforeend',rows.join(''));}
 if(!d.items.length&&!append)$('table-slot').innerHTML=empty('Nenhuma conta corresponde a esta busca.');
 $('more-slot').innerHTML=more(d.has_more);
}
async function posts(append=false){const d=await api('/admin/posts?'+new URLSearchParams({q:query,page:String(page)}));
 const rows=d.items.map(p=>`<tr><td><div class="cell-title">${escapeHTML(p.title)}</div><div class="cell-sub">#${p.id} · @${escapeHTML(p.author)}</div></td><td>${escapeHTML(p.kind)}</td><td>${fmt(p.views)}</td><td><span class="pill ${p.is_hidden?'warn':'ok'}">${p.is_hidden?'Oculto':'Público'}</span></td><td><div class="table-actions"><button class="ghost-btn ${p.is_hidden?'':'danger'}" data-action="visibility" data-id="${p.id}" data-hidden="${p.is_hidden?'false':'true'}">${p.is_hidden?'Restaurar':'Ocultar'}</button><a class="ghost-btn" href="/#post-${p.id}" target="_blank" rel="noopener">↗</a></div></td></tr>`);
 if(!append)$('panel-content').innerHTML=frame(`<div class="section-actions"><h2>Inventário de conteúdo</h2><form id="search-form"><input class="search-input" id="search-input" value="${escapeHTML(query)}" placeholder="Buscar título ou descrição..."><button class="ghost-btn" type="submit">Pesquisar</button></form></div><div id="table-slot">${table(['Publicação','Canal','Visualizações','Situação','Ações'],[])}</div><div id="more-slot"></div>`);
 const tbody=$('table-slot')?.querySelector('tbody');if(tbody){if(!append)tbody.innerHTML='';tbody.insertAdjacentHTML('beforeend',rows.join(''));}
 if(!d.items.length&&!append)$('table-slot').innerHTML=empty('Nenhuma publicação corresponde a esta busca.');
 $('more-slot').innerHTML=more(d.has_more);
}
async function audit(append=false){const d=await api('/admin/audit?page='+page);
 const rows=d.items.map(r=>`<tr><td><strong>#${r.id}</strong></td><td>${escapeHTML(r.admin)}</td><td><span class="pill">${escapeHTML(r.action)}</span></td><td>${escapeHTML(r.target_type)} #${r.target_id}</td><td>${escapeHTML(r.details)}</td><td>${escapeHTML(date(r.created_at))}</td></tr>`);
 if(!append)$('panel-content').innerHTML=frame(`<div class="section-actions"><h2>Trilha de auditoria</h2><span class="pill ok">Registros persistentes</span></div><div id="table-slot">${table(['ID','Administrador','Ação','Alvo','Justificativa','Data'],[])}</div><div id="more-slot"></div>`);
 const tbody=$('table-slot')?.querySelector('tbody');if(tbody){if(!append)tbody.innerHTML='';tbody.insertAdjacentHTML('beforeend',rows.join(''));}
 if(!d.items.length&&!append)$('table-slot').innerHTML=empty('Nenhuma ação administrativa registrada.');
 $('more-slot').innerHTML=more(d.has_more);
}
function confirmAction(title,copy){if(modalResolver)finishDialog(null);previousFocus=document.activeElement;$('dialog-title').textContent=title;$('dialog-copy').textContent=copy;$('dialog-reason').value='';$('admin-dialog').hidden=false;$('dialog-reason').focus();return new Promise(resolve=>modalResolver=resolve);}
function finishDialog(value){$('admin-dialog').hidden=true;const resolve=modalResolver;modalResolver=null;resolve?.(value);previousFocus?.focus?.();}
$('dialog-cancel').addEventListener('click',()=>finishDialog(null));
$('admin-dialog-form').addEventListener('submit',e=>{e.preventDefault();const value=$('dialog-reason').value.trim();if(value.length<5)return toast('Explique o motivo (mínimo 5 caracteres).',true);finishDialog(value);});
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&modalResolver)finishDialog(null);});
$('admin-dialog').addEventListener('click',e=>{if(e.target===$('admin-dialog'))finishDialog(null);});
$('panel-content').addEventListener('change',e=>{if(e.target.id==='report-filter'){filter=e.target.value;page=1;reports();}});
$('panel-content').addEventListener('submit',e=>{if(e.target.id==='search-form'){e.preventDefault();query=$('search-input').value.trim();page=1;navigateSearch();}});
async function navigateSearch(){if(busy)return;busy=true;try{if(view==='users')await users();if(view==='posts')await posts();}catch(e){toast(e.message,true);}finally{busy=false;}}
$('panel-content').addEventListener('click',async e=>{
 const button=e.target.closest('[data-action]');if(!button||busy)return;
 const action=button.dataset.action,id=Number(button.dataset.id);
 if(action==='more'){page++;busy=true;try{if(view==='reports')await reports(true);if(view==='users')await users(true);if(view==='posts')await posts(true);if(view==='audit')await audit(true);}catch(err){page--;toast(err.message,true);}finally{busy=false;}return;}
 if(action==='find-user'){await navigate('users');return;}
 let title='',copy='',path='',body={};
 if(action==='review'){const choice=button.dataset.choice;title={dismiss:'Descartar denúncia?',resolve:'Marcar como resolvida?',hide:'Remover conteúdo denunciado?'}[choice];copy='A decisão será registrada no histórico de auditoria.';path='/admin/reports/'+id;body={action:choice};}
 if(action==='ban'||action==='unban'){title=action==='ban'?'Suspender conta?':'Reativar conta?';copy=action==='ban'?'A conta perderá acesso imediatamente, inclusive sessões abertas.':'O usuário poderá voltar a entrar na plataforma.';path='/admin/users/'+id+'/'+action;}
 if(action==='visibility'){const hidden=button.dataset.hidden==='true';title=hidden?'Ocultar publicação?':'Restaurar publicação?';copy=hidden?'O conteúdo deixará de aparecer no feed público.':'O conteúdo voltará ao feed público.';path='/admin/posts/'+id+'/visibility';body={hidden};}
 if(!path)return;
 const reason=await confirmAction(title,copy);if(!reason)return;body.reason=reason;
 busy=true;button.disabled=true;
 try{await api(path,{method:'POST',body});toast('Ação registrada com sucesso.');busy=false;await navigate(view);}
 catch(err){toast(err.message,true);}finally{busy=false;button.disabled=false;}
});
setup().catch(e=>{$('gate-error').textContent=e.message;$('gate-error').hidden=false;});
