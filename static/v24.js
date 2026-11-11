/* TWYS 2.4: research-centric watchlists, actual macro series, movable panels. */
'use strict';
function v24WatchChart(sym,info) {
  v22Selected=sym;
  const title=q22('v24-watch-title');if(title)title.textContent=sym+' · '+(info.name||'Financial instrument');
  v22TvChart(sym,info);
  const pos=q22('v22-positioning'),social=q22('v22-social');
  if(pos)pos.innerHTML=no22('Checking reported positions...');
  if(social)social.innerHTML=no22('Checking public discussion...');
  v22LoadPositioning(sym);v22LoadSocial(sym);
  if(q22('v22-mini-calendar'))v22LoadMiniNews(sym);
}
async function v24LoadWatchlist(){
 let d;try{d=await api('/api/v2/favorites')}catch(e){d={symbols:[]}};
 const list=d.symbols||[];
 const active=list.includes(localStorage.getItem('twys_watch_selected'))?localStorage.getItem('twys_watch_selected'):list[0];
 const box=q22('workspace');
 box.innerHTML=`<div class="v22-full-head"><div><h1>Watchlist</h1><span class="v22-subtitle">All your tracked markets in one research workspace</span></div><button class="v22-btn" id="v24-watch-explore">+ Add instruments</button></div>${!list.length?`<section class="v22-panel">${no22('No favorites yet. Add an instrument from Markets to see its chart, reported sentiment and related news here.')}</section>`:`<div class="v24-watch-layout"><aside class="v24-watch-list v22-panel">${title22('Saved instruments',list.length+' tracked')}${list.map(s=>`<div class="v24-watch-symbol ${s===active?'active':''}" data-v24-row="${h22(s)}"><button type="button" data-v24-watch="${h22(s)}" class="v24-watch-open" aria-label="Show ${h22(s)} market details"><b>${h22(s)}</b><span>View details ↗</span></button><button type="button" data-v24-remove="${h22(s)}" class="v24-watch-remove" title="Remove ${h22(s)} from watchlist" aria-label="Remove ${h22(s)} from watchlist">★</button></div>`).join('')}</aside><section class="v24-watch-work"><div class="v24-watch-title"><h2 id="v24-watch-title">${h22(active)}</h2><button class="v22-btn" id="v24-full-market">Full market view ↗</button></div><section class="v22-panel"><div id="v22-chart" class="v22-chart">Connecting to market chart...</div><div class="v22-chart-bottom">Provider-supplied prices and chart ranges · real-time or delayed according to the venue</div></section><div class="v24-watch-research"><section class="v22-panel">${title22('Reported market positioning','Verified sources only')}<div id="v22-positioning"></div></section><section class="v22-panel">${title22('Public discussions','Instrument-matched posts')}<div id="v22-social"></div></section></div><section class="v22-panel v24-watch-news">${title22('Relevant scheduled events','Local computer time')}<div id="v22-mini-calendar">${no22('Fetching upcoming economic events...')}</div></section></section></div>`}`;
 q22('v24-watch-explore').onclick=()=>navigate('marketdesk');
 if(!list.length)return;
 const select=async(sym)=>{
  if(state.page!=='watchlist')return;
  localStorage.setItem('twys_watch_selected',sym);
  box.querySelectorAll('[data-v24-row]').forEach(el=>el.classList.toggle('active',el.dataset.v24Row===sym));
  let info;try{info=await api('/api/v2/markets/'+encodeURIComponent(sym))}catch(e){info={name:sym,asset_class:'Unknown'}};
  if(state.page!=='watchlist'||localStorage.getItem('twys_watch_selected')!==sym)return;
  v24WatchChart(sym,info);
  q22('v24-full-market').onclick=()=>{v22Selected=sym;navigate('marketdesk')};
 };
 box.querySelectorAll('[data-v24-watch]').forEach(el=>el.onclick=()=>select(el.dataset.v24Watch));
 box.querySelectorAll('[data-v24-remove]').forEach(el=>el.onclick=async()=>{const sym=el.dataset.v24Remove;el.disabled=true;try{await api('/api/v2/favorites',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({symbol:sym,favorite:false})});if(localStorage.getItem('twys_watch_selected')===sym)localStorage.removeItem('twys_watch_selected');if(state.page==='watchlist')await v24LoadWatchlist()}catch(error){el.disabled=false;toast('Could not remove '+sym+': '+error.message)}});
 await select(active);
}
function v24Sparkline(points){
 if(points.length<2)return '<span class="v24-nohistory">Not enough observations to chart</span>';
 const nums=points.map(p=>p.value),lo=Math.min(...nums),hi=Math.max(...nums),range=hi-lo||1;
 const coords=nums.map((v,i)=>`${(i/(nums.length-1)*100).toFixed(2)},${(42-(v-lo)/range*38).toFixed(2)}`).join(' ');
 const up=nums[nums.length-1]>=nums[0];
 return `<svg class="v24-spark" viewBox="0 0 100 46" preserveAspectRatio="none" aria-label="Historical observation chart"><polyline points="${coords}" stroke="${up?'#39cba1':'#ee6573'}" fill="none" stroke-width="1.7" vector-effect="non-scaling-stroke"/></svg>`;
}
async function v24LoadMacro(){
 const root=q22('workspace');
 root.innerHTML=`<div class="v22-banner"><div><h1>Macro Desk</h1><p>Interest rates, bonds, inflation, the US dollar and cross-market relationships</p></div><button class="v22-btn" id="v24-macro-refresh">↻ Refresh</button></div><div class="v24-macro-explain">Financial-market moves depend on expectations, surprises, relative policies and positioning, not one guaranteed cause. Values below are the latest <strong>published observations</strong>, not streaming market quotes.</div><div class="v24-macro-grid" id="v24-macro-data">${no22('Loading official Federal Reserve economic series...')}</div><section class="v22-panel v24-macro-relations">${title22('Macro releases and related news','Latest reported values and official headlines')}<div id="v26-macro-news" class="v26-macro-news">${no22('Checking economic releases and financial headlines...')}</div></section><section class="v22-panel v24-macro-relations">${title22('How macro forces interact','Conditional mechanisms, not predictions')}<div id="v24-macro-theories"></div></section>`;
 q22('v24-macro-refresh').onclick=()=>v24LoadMacro();
 v26LoadMacroNews();
 try{
  const result=await api('/api/v2/macro');if(state.page!=='macro')return;
  q22('v24-macro-data').innerHTML=(result.series||[]).map(s=>{
    const latest=s.latest,delta=s.change;
    return `<article class="v22-panel v24-macro-card"><header><b>${h22(s.name)}</b><a href="${h22(s.url)}" target="_blank" rel="noopener noreferrer">FRED ↗</a></header>${latest?`<div class="v24-macro-value">${Number(latest.value).toLocaleString(undefined,{maximumFractionDigits:3})} <small>${h22(s.unit)}</small></div><div class="v24-macro-meta">${delta!==null?(delta>=0?'+':'')+Number(delta).toFixed(3)+' vs prior observation · ':''}As of ${h22(latest.date)} · ${h22(s.frequency)}</div>${s.yoy_percent!=null?`<div class="v24-macro-meta">CPI year-over-year: ${s.yoy_percent}% (calculated from monthly index)</div>`:''}${v24Sparkline((s.history||[]).slice(-90))}`:`<div class="v24-nohistory">Data source unavailable. ${h22(s.error||'')}</div>`}</article>`;
  }).join('');
  q22('v24-macro-theories').innerHTML=(result.scenarios||[]).map(o=>`<div class="v24-macro-theory"><b>${h22(o.title)}</b><p>${h22(o.mechanism)}</p></div>`).join('')+`<p class="v24-macro-caveat">${h22(result.methodology)}</p>`;
 }catch(e){q22('v24-macro-data').innerHTML=no22('Could not retrieve macro observations: '+e.message)}
}
function v24EnablePanels(){
 // Workspaces allow right-hand research panels to be reordered, without displacing the price chart.
 const rail=q22('v22-desk')?.querySelector('.v22-rail')||document.querySelector('.v22-desk .v22-rail');
 if(!rail)return;
 const panels=[...rail.querySelectorAll(':scope > .v22-panel')];
 panels.forEach((p,i)=>{
  const title=p.querySelector('.v22-phead h2')?.textContent||'Research '+i;
  p.dataset.panelId=title.trim().toLowerCase().replace(/[^a-z0-9]+/g,'-');
  p.draggable=true;p.classList.add('v24-draggable-panel');
  const head=p.querySelector('.v22-phead');if(head&&!head.querySelector('.v24-grab'))head.insertAdjacentHTML('afterbegin','<span class="v24-grab" title="Drag to reorder">⠿</span>');
  p.addEventListener('dragstart',event=>{event.dataTransfer.setData('text/plain',p.dataset.panelId);p.classList.add('v24-dragging')});
  p.addEventListener('dragend',()=>p.classList.remove('v24-dragging'));
  p.addEventListener('dragover',event=>event.preventDefault());
  p.addEventListener('drop',event=>{event.preventDefault();const source=rail.querySelector('.v24-dragging');if(!source||source===p)return;const rect=p.getBoundingClientRect();rail.insertBefore(source,event.clientY<rect.top+rect.height/2?p:p.nextSibling);localStorage.setItem('twys_rail_order',[...rail.querySelectorAll('[data-panel-id]')].map(e=>e.dataset.panelId).join(','))});
 });
 const order=(localStorage.getItem('twys_rail_order')||'').split(',');order.forEach(id=>{const p=panels.find(n=>n.dataset.panelId===id);if(p)rail.append(p)});
 if(!rail.querySelector('.v24-rail-resizer')){
   const grab=document.createElement('div');grab.className='v24-rail-resizer';grab.title='Drag to resize research column';rail.prepend(grab);
   grab.addEventListener('pointerdown',event=>{event.preventDefault();grab.setPointerCapture(event.pointerId);const start=event.clientX,initial=parseInt(getComputedStyle(document.documentElement).getPropertyValue('--rail-w'))||325;const move=e=>{const width=Math.max(250,Math.min(570,initial+start-e.clientX));document.documentElement.style.setProperty('--rail-w',width+'px');localStorage.setItem('twys_rail_width',String(width))};grab.addEventListener('pointermove',move);grab.addEventListener('pointerup',()=>{grab.removeEventListener('pointermove',move)},{once:true})});
 }
}
function v24InitSidebarResize(){
 const saved=Number(localStorage.getItem('twys_sidebar_width'));if(saved>=160&&saved<=370)document.documentElement.style.setProperty('--sidebar-w',saved+'px');
 const rail=Number(localStorage.getItem('twys_rail_width'));if(rail>=250&&rail<=570)document.documentElement.style.setProperty('--rail-w',rail+'px');
 const el=document.querySelector('.sidebar');if(!el||document.getElementById('v24-sidebar-grab'))return;
 const grab=document.createElement('div');grab.id='v24-sidebar-grab';grab.title='Drag to resize navigation';el.append(grab);
 grab.addEventListener('pointerdown',event=>{event.preventDefault();grab.setPointerCapture(event.pointerId);const move=e=>{const px=Math.max(160,Math.min(370,e.clientX));document.documentElement.style.setProperty('--sidebar-w',px+'px');localStorage.setItem('twys_sidebar_width',String(px))};grab.addEventListener('pointermove',move);grab.addEventListener('pointerup',()=>grab.removeEventListener('pointermove',move),{once:true})});
}
setTimeout(v24InitSidebarResize,300);

async function v26LoadMacroNews(){
 const box=q22('v26-macro-news');if(!box)return;
 try{const d=await api('/api/v2/macro/news');if(state.page!=='macro'||!q22('v26-macro-news'))return;
 const release=(d.events||[]).slice(0,15).map(e=>`<div class="v26-news-row"><div class="v26-news-meta">${h22((e.currency||'').toUpperCase())} · ${date22(e.datetime)} · ${h22(e.source||'')}</div><b>${h22(e.event)}</b><div class="v26-news-values">Actual: ${h22(e.actual??'Not reported')} · Forecast: ${h22(e.forecast??'—')} · Previous: ${h22(e.previous??'—')}</div></div>`).join('');
 const headlines=(d.headlines||[]).slice(0,16).map(h=>`<div class="v26-news-row"><div class="v26-news-meta">${h22(h.source||'')} · ${date22(h.published)}</div><a href="${h22(h.url)}" target="_blank" rel="noopener noreferrer">${h22(h.title)}</a></div>`).join('');
 q22('v26-macro-news').innerHTML=`<div class="v26-macro-columns"><section><h3>Economic releases</h3>${release||no22('No matching releases returned by the connected date-range feed. '+(d.calendar_message||''))}</section><section><h3>Official macro headlines</h3>${headlines||no22('Official headline sources are currently unavailable.')}</section></div><p class="v24-macro-caveat">${h22(d.note)}</p>`;
 }catch(e){if(q22('v26-macro-news'))q22('v26-macro-news').innerHTML=no22('Macro news source could not update: '+e.message)}
}
