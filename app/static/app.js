'use strict';
const $ = (id) => document.getElementById(id);
const state = {demo:false, language:'English', topic:'All topics', region:'All India', q:'', articles:[], selected:null, research:null, busy:false, metadata:null, lastFeedSuccess:null};
const escapeHTML = (input) => String(input ?? '').replace(/[&<>"']/g, (char) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const allowedLink = (url) => /^https:\/\//i.test(String(url||''));
async function request(url, options={}){
  const response = await fetch(url,{headers:{'Accept':'application/json','Content-Type':'application/json'},...options});
  let data;
  try { data = await response.json(); } catch { throw new Error('Unable to parse server response'); }
  if(!response.ok){throw new Error(typeof data.detail==='string' ? data.detail : `Request failed (${response.status})`);}
  return data;
}
function relativeDate(value){
  const time = new Date(value).getTime(); if(!Number.isFinite(time)) return 'Date unknown';
  const hours = Math.max(0, Math.floor((Date.now()-time)/3600000));
  if(hours<1) return 'Just now'; if(hours<24) return `${hours}h ago`;
  const days = Math.floor(hours/24); if(days<30) return `${days}d ago`;
  return new Date(time).toLocaleDateString('en-IN',{day:'numeric',month:'short'});
}
function showNotice(message='',ok=false){$('notice').innerHTML=message?`<div class="notice ${ok?'ok':''}">${escapeHTML(message)}</div>`:'';}
function setMode(demo){
  state.demo=demo;
  $('liveBtn').classList.toggle('active',!demo);
  $('demoBtn').classList.toggle('active',demo);
  $('dataBanner').className=`data-banner ${demo?'demo-banner':'live-banner'}`;
  $('dataBanner').innerHTML=demo
    ? '<div class="banner-icon">i</div><div><strong>Illustrative demo mode</strong><span>These are invented learning scenarios, NOT real news. Switch to Live RSS and refresh to load actual feed headlines.</span></div>'
    : '<div class="banner-icon">i</div><div><strong>Live RSS metadata mode</strong><span>Feed headlines and excerpts are real provider entries, but have NOT been independently verified. Publisher source links are available on each card.</span></div>';
  showNotice(); loadNews();
  if(!demo){watchRegion();checkLiveUpdates();}
  else $('feedStatus').textContent='Automatic feed updates are available in Live RSS mode.';
}
function createArticleCard(a){
  const source = a.is_demo ? 'Illustrative fixture' : a.publisher;
  const hasEnglishPreview = Boolean(a.summary_en);
  const lang = a.language || 'Unknown';
  const desc = (state.demo ? a.description : (a.summary_en || a.description)) || 'No excerpt supplied by this feed. Inspect the publisher link for details.';
  const excerptLabel = state.demo ? 'ILLUSTRATIVE SCENARIO' : hasEnglishPreview ? (lang==='English' ? 'RSS EXCERPT · ENGLISH' : 'ENGLISH PREVIEW · AI TRANSLATION') : `ORIGINAL ${lang.toUpperCase()} EXCERPT · NO ENGLISH PREVIEW`;
  const read = allowedLink(a.url)?`<a href="${escapeHTML(a.url)}" target="_blank" rel="noopener noreferrer">Source ↗</a>`:'';
  return `<article class="news-card"><div class="card-top"><span class="category">${escapeHTML(a.topic)}</span><span class="card-age">${escapeHTML(relativeDate(a.published_at))}</span></div><h3>${escapeHTML(a.title)}</h3><div class="excerpt-label">${escapeHTML(excerptLabel)}</div><p>${escapeHTML(desc)}</p><div class="card-footer"><div class="card-source"><span class="source-pin"></span>${escapeHTML(a.region)} <span>·</span> ${escapeHTML(source)}</div><div class="card-actions"><button type="button" data-research="${escapeHTML(a.id)}">Research ↗</button><button type="button" data-chat="${escapeHTML(a.id)}">Ask AI ↗</button>${read}</div></div></article>`;
}
function updateStats(stats){
  $('statStories').textContent=Number(stats.total_articles||0).toLocaleString('en-IN');
  $('statRegions').innerHTML=`${Number(stats.regions_covered||0)}<span class="metric-suffix">/ 36</span>`;
  $('statTopics').textContent=Object.keys(stats.topic_counts||{}).length;
}
function renderNews(data){
  state.articles=data.items;
  $('resultCount').textContent=`${data.count} ${data.count===1?'STORY':'STORIES'}`;
  $('resultLabel').textContent=state.region==='All India'?'across India':`in ${state.region}`;
  updateStats(data.stats);
  $('newsGrid').innerHTML=data.count?data.items.map(createArticleCard).join(''):
    `<div class="empty-state"><h3>${state.demo?'No matching examples':'No matching live stories yet'}</h3><p>${state.demo?'Try choosing All India or clearing your search.':'BharatPulse checks for new RSS stories when you open the app and every five minutes. If the source has no relevant articles, try another region or inspect the feed status.'}</p></div>`;
}
let searchTimer=null;
async function loadNews(silent=false){
  if(!silent)$('newsGrid').innerHTML='<div class="loading-view">Loading indexed stories…</div>';
  const qs=new URLSearchParams({region:state.region,topic:state.topic,q:state.q,demo:String(state.demo),limit:'60'});
  try{
    const result=await request(`/api/news?${qs}`);
    const current=JSON.stringify(state.articles.map(a=>[a.id,a.published_at]));
    const incoming=JSON.stringify(result.items.map(a=>[a.id,a.published_at]));
    if(!silent || current!==incoming)renderNews(result);
  }catch(err){if(!silent){showNotice(err.message);$('newsGrid').innerHTML='<div class="empty-state"><h3>Could not load stories</h3><p>Check that the FastAPI server is running.</p></div>';}}
}
async function watchRegion(){
  if(state.demo)return;
  try{await request('/api/news/watch',{method:'POST',body:JSON.stringify({region:state.region})});}
  catch(err){$('feedStatus').textContent='Automatic feed watch unavailable: '+err.message;}
}
async function checkLiveUpdates(){
  if(state.demo || state.busy || document.hidden)return;
  try{
    await watchRegion();
    const status=await request(`/api/news/status?${new URLSearchParams({region:state.region})}`);
    const success=status.last_success;
    const checked=success?new Date(success).toLocaleString('en-IN'):'Not yet';
    const attempt=status.last_attempt?new Date(status.last_attempt).toLocaleString('en-IN'):'Awaiting first check';
    $('feedStatus').textContent=`Auto-check on opening + every ${Math.round(status.poll_seconds/60)} min · Last success: ${checked} · Last attempt: ${attempt}${status.refreshing?' · Checking sources…':''}${status.last_error?' · Latest attempt failed; cached news remains available':''}`;
    if(success && success!==state.lastFeedSuccess){state.lastFeedSuccess=success;await loadNews(true);}
  }catch(err){$('feedStatus').textContent='Feed status unavailable. Check backend connection.';}
}
function renderTopics(topics){
  $('topicRow').innerHTML=topics.map(t=>`<button type="button" class="topic-btn ${state.topic===t?'active':''}" data-topic="${escapeHTML(t)}">${escapeHTML(t)}</button>`).join('');
}
function setBusy(busy){state.busy=busy;$('refreshBtn').disabled=busy;$('refreshBtn').querySelector('span').textContent=busy?'Fetching RSS…':'Fetch live news';}
async function refresh(){
  if(state.busy)return;
  setBusy(true);showNotice('Contacting Google News RSS. The provider may be temporarily unavailable.');
  try{
    const data=await request('/api/news/refresh',{method:'POST',body:JSON.stringify({region:state.region})});
    setMode(false);
    showNotice(`Fetched ${data.fetched} RSS entries; ${data.added} new unique headlines indexed. Automatic refresh remains enabled every five minutes. Filtering: ${data.filter_mode}.`,true);
  }catch(err){showNotice(err.message);}
  finally{setBusy(false);}
}
function openDrawer(id,which){
  const a=state.articles.find(item=>item.id===id);
  if(!a)return;
  state.selected=a;state.research=null;
  $('drawerBackdrop').hidden=false;$('drawer').hidden=false;document.body.style.overflow='hidden';
  $('drawerTitle').textContent=a.title;
  $('drawerSub').textContent=`${a.publisher} · ${a.region} · Original language: ${a.language||'Unknown'} · Responses: ${state.language} · ${relativeDate(a.published_at)}`;
  $('researchOutput').textContent=a.is_demo?'This is an invented learning scenario. Real research is only available for live RSS articles.':'Select “Start research” to search for related coverage and build an evidence index. The configured Groq or Ollama model can generate a cited brief.';
  $('sourceList').innerHTML='';
  $('chatMessages').innerHTML='<div class="assistant-bubble">Ask a question about this headline. Without an AI provider, I can show relevant source references; I will not invent an answer from incomplete RSS snippets.</div>';
  selectDrawerTab(which);
}
function closeDrawer(){$('drawer').hidden=true;$('drawerBackdrop').hidden=true;document.body.style.overflow='';}
function selectDrawerTab(which){
  const research=which==='research';
  $('researchPanel').hidden=!research;$('chatPanel').hidden=research;
  $('researchTab').classList.toggle('active',research);$('chatTab').classList.toggle('active',!research);
  $('drawerTopic').textContent=research?'RESEARCH REPORT':'ARTICLE CHAT';
  if(!research)$('chatInput').focus();
}
function renderSources(sources){
  if(!sources?.length)return '<p class="drawer-sub">No additional live sources were available for verification.</p>';
  return `<div class="source-heading">EVIDENCE SOURCES / ${sources.length}</div>${sources.map(s=>`<article class="source-row" id="evidence-src-${Number(s.index)}"><strong>[${s.index}] ${escapeHTML(s.title)}</strong><p>${escapeHTML(s.publisher)} · ${escapeHTML(s.region)} · ${escapeHTML(relativeDate(s.published_at))}</p>${allowedLink(s.url)?`<a href="${escapeHTML(s.url)}" target="_blank" rel="noopener noreferrer">Inspect publisher/source ↗</a>`:'Demo source — no external link'}</article>`).join('')}`;
}
function renderResearchReport(data){
  const report = data.report || {};
  const items = (Array.isArray(report.findings)?report.findings:[]);
  const findings = items.length ? items.map((finding, idx)=>{
    const links = (finding.evidence||[]).map(e=>`<a class="evidence-tag" href="#evidence-src-${Number(e.source)}">[${Number(e.source)}]</a>`).join(' ');
    const quotes = (finding.evidence||[]).map(e=>`<blockquote class="quote-evidence">“${escapeHTML(e.quote)}” <span>Source ${Number(e.source)} · RSS excerpt/headline</span></blockquote>`).join('');
    return `<div class="research-finding"><strong>Finding ${idx+1}</strong><p>${escapeHTML(finding.claim)} ${links}</p>${quotes}</div>`;
  }).join('') : '<p class="research-empty">Not enough excerpt-backed evidence to produce a supported research finding. Review the source headlines below.</p>';
  const timeline = (report.publication_timeline||[]).map(item=>`<li><a href="#evidence-src-${Number(item.source)}">[${Number(item.source)}]</a> ${escapeHTML(item.published_at)}</li>`).join('');
  const limitations = (report.not_verified||[]).map(item=>`<li>${escapeHTML(item)}</li>`).join('');
  const questions = (report.open_questions||[]).map(item=>`<li>${escapeHTML(item)}</li>`).join('');
  const badge = ['groq','ollama'].includes(data.generated_by) ? `AI DRAFT · ${escapeHTML(data.generated_by.toUpperCase())} · EXCERPT-ANCHORED` : 'EVIDENCE INDEX · NO APPROVED AI FINDINGS';
  const dropNote = Number(report.rejected_claims||0)>0 ? `<p class="research-muted">${Number(report.rejected_claims)} model claim(s) excluded because their quoted evidence or numeric details did not pass the automated checks.</p>` : '';
  return `<div class="research-badge">${badge}</div>
    <div class="report-section"><h3>What available sources report</h3>${findings}${dropNote}</div>
    <div class="report-section"><h3>Publication timeline (UTC)</h3><p class="research-muted">These are reported feed publication timestamps, <strong>not the dates or times of the underlying events.</strong></p><ol>${timeline}</ol></div>
    <div class="report-section"><h3>What is not verified</h3><ul>${limitations}</ul></div>
    <div class="report-section"><h3>Questions for further reporting</h3><ul>${questions}</ul></div>
    <div class="report-section research-caveat"><h3>Evidence limitations</h3><p>${escapeHTML(data.caveat||'')}</p>${data.warning?`<p>${escapeHTML(data.warning)}</p>`:''}<p>Source labels may represent syndicated material, not independent confirmation. This report requires editorial review.</p></div>`;
}
async function runResearch(){
  if(!state.selected)return;
  $('researchRun').disabled=true;
  $('researchOutput').classList.remove('report-structured');
  $('researchOutput').textContent='Discovering related RSS coverage, checking excerpt quotations, and building a structured report…';
  try{
    const result=await request(`/api/research/${encodeURIComponent(state.selected.id)}`,{method:'POST',body:JSON.stringify({language:state.language})});
    $('sourceList').innerHTML=renderSources(result.sources);
    $('researchOutput').classList.add('report-structured');
    $('researchOutput').innerHTML=renderResearchReport(result);
  }catch(err){
    $('researchOutput').classList.remove('report-structured');
    $('researchOutput').textContent='Research could not complete: '+err.message;
  }finally{$('researchRun').disabled=false;}
}

function appendChat(text,type){const div=document.createElement('div');div.className=type==='user'?'user-bubble':'assistant-bubble';div.textContent=text;$('chatMessages').append(div);$('chatMessages').scrollTop=$('chatMessages').scrollHeight;return div;}
async function submitChat(event){
  event.preventDefault();if(!state.selected)return;
  const input=$('chatInput'),question=input.value.trim();if(question.length<2)return;
  input.value='';appendChat(question,'user');const bubble=appendChat('Checking available sources…','assistant');
  const submit=$('chatForm').querySelector('button');submit.disabled=true;
  try{
    const data=await request('/api/chat',{method:'POST',body:JSON.stringify({article_id:state.selected.id,question,language:state.language})});
    bubble.textContent=(['groq','ollama'].includes(data.generated_by)?'':'SOURCE REFERENCE MODE — No AI synthesis\n\n')+data.answer;
    if(data.sources?.length){const links=data.sources.filter(s=>allowedLink(s.url)).map(s=>`[${s.index}] ${s.publisher}: ${s.url}`).join('\n');if(links)bubble.textContent+='\n\nLinks:\n'+links;}
  }catch(err){bubble.textContent='Request failed: '+err.message;}
  finally{submit.disabled=false;$('chatMessages').scrollTop=$('chatMessages').scrollHeight;}
}
async function init(){
  try{
    state.metadata=await request('/api/meta');
    $('regionSelect').innerHTML=state.metadata.regions.map(r=>`<option value="${escapeHTML(r)}">${escapeHTML(r)}</option>`).join('');
    renderTopics(state.metadata.topics);
    $('languageSelect').innerHTML=state.metadata.response_languages.map(l=>`<option value="${escapeHTML(l)}">${escapeHTML(l)}</option>`).join('');
    $('languageSelect').value=state.language;
    $('statAI').textContent=state.metadata.llm_configured?`${state.metadata.llm_provider.toUpperCase()} SETUP`:'SOURCE MODE';
    $('aiNote').textContent=state.metadata.llm_configured?`Model: ${state.metadata.llm_model} (check connection via /api/ai/check)`:'Configure Groq or Ollama to enable AI';
  }catch(err){showNotice('Backend not responding: '+err.message);}
  $('aiCheckBtn').addEventListener('click',async()=>{
    const btn=$('aiCheckBtn');btn.disabled=true;btn.textContent='Checking…';
    try{
      const result=await request('/api/ai/check',{method:'POST'});
      $('statAI').textContent=`${result.provider.toUpperCase()} READY`;
      $('aiNote').textContent=`Connected to ${result.model}`;
    }catch(err){
      $('statAI').textContent='AI UNAVAILABLE';
      $('aiNote').textContent=err.message;
    }finally{btn.disabled=false;btn.textContent='Test AI connection';}
  });
  $('regionSelect').addEventListener('change',e=>{state.region=e.target.value;state.lastFeedSuccess=null;loadNews();if(!state.demo){watchRegion();checkLiveUpdates();}});
  $('languageSelect').addEventListener('change',e=>{state.language=e.target.value;if(state.selected){$('drawerSub').textContent=`${state.selected.publisher} · ${state.selected.region} · Original language: ${state.selected.language||'Unknown'} · Responses: ${state.language}`;}});
  $('searchInput').addEventListener('input',e=>{clearTimeout(searchTimer);searchTimer=setTimeout(()=>{state.q=e.target.value.trim();loadNews();},230);});
  $('topicRow').addEventListener('click',e=>{const b=e.target.closest('[data-topic]');if(!b)return;state.topic=b.dataset.topic;renderTopics(state.metadata.topics);loadNews();});
  $('liveBtn').addEventListener('click',()=>setMode(false));$('demoBtn').addEventListener('click',()=>setMode(true));
  $('refreshBtn').addEventListener('click',refresh);
  $('newsGrid').addEventListener('click',e=>{const b=e.target.closest('[data-research],[data-chat]');if(!b)return;openDrawer(b.dataset.research||b.dataset.chat,b.hasAttribute('data-chat')?'chat':'research');});
  $('drawerClose').addEventListener('click',closeDrawer);$('drawerBackdrop').addEventListener('click',closeDrawer);
  document.addEventListener('keydown',e=>{if(e.key==='Escape')closeDrawer();});
  $('researchTab').addEventListener('click',()=>selectDrawerTab('research'));
  $('chatTab').addEventListener('click',()=>selectDrawerTab('chat'));
  $('researchRun').addEventListener('click',runResearch);$('chatForm').addEventListener('submit',submitChat);
  document.querySelectorAll('[data-nav]').forEach(a=>a.addEventListener('click',()=>{document.querySelectorAll('[data-nav]').forEach(n=>n.classList.remove('active'));a.classList.add('active');}));
  // Opening the page immediately asks the server to check freshness and,
  // if due, start a non-blocking RSS retrieval. Cached items appear at once.
  setMode(false);
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)checkLiveUpdates();});
  window.setInterval(checkLiveUpdates,20000); // UI sync, distinct from 5-minute RSS polling.
}
window.addEventListener('DOMContentLoaded',init);
