'use strict';
const $ = (id) => document.getElementById(id);
const state = {chatHistoryVersion:0,chatCaveatShown:false,contextFetchVersion:0,demo:false, language:'English', topic:'All topics', region:'All India', q:'', articles:[], selected:null, research:null, busy:false, metadata:null, lastFeedSuccess:null};
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
  const provenance = a.is_demo ? '' : a.feed_origin==='direct_publisher_rss' ? ' · Direct publisher RSS' :
    a.feed_origin==='google_news_rss' ? ' · Google News RSS' : a.feed_origin==='bbc_publisher_rss' ? ' · BBC RSS' : '';
  const read = allowedLink(a.url)?`<a href="${escapeHTML(a.url)}" target="_blank" rel="noopener noreferrer">Source ↗</a>`:'';
  const categoryThumb=state.demo ? (/farm|agricultur/i.test(a.topic+' '+a.title) ? 'news-farm-illustration.jpg' : /dam|water|metro|transport|infra/i.test(a.topic+' '+a.title) ? 'news-dam-illustration.jpg' : 'news-coast-illustration.jpg') : '';
  const thumbnail=categoryThumb?`<div class="news-card-thumb"><img src="/static/assets/${categoryThumb}" alt="Decorative illustration, not documentary evidence"/><span>Illustrative</span></div>`:`<div class="news-card-thumb source-thumbnail" aria-label="Source-linked news article, no source photograph provided"><span>◈</span><small>RSS</small></div>`;
  return `<article class="news-card">${thumbnail}<div class="card-top"><span class="category">${escapeHTML(a.topic)}</span><span class="card-age">${escapeHTML(relativeDate(a.published_at))}</span></div><h3>${escapeHTML(a.title)}</h3><div class="excerpt-label">${escapeHTML(excerptLabel)}</div><p>${escapeHTML(desc)}</p><div class="card-footer"><div class="card-source"><span class="source-pin"></span>${escapeHTML(a.region)} <span>·</span> ${escapeHTML(source)}${escapeHTML(provenance)}</div><div class="card-actions"><button type="button" data-research="${escapeHTML(a.id)}">Research ↗</button><button type="button" data-chat="${escapeHTML(a.id)}">Ask AI ↗</button>${read}</div></div></article>`;
}
function renderEvidenceInventory(items){
  const box = $('newsEvidencePanel');if(!box)return;
  if(!items.length){box.innerHTML='<p class="insight-empty">No indexed entries match the current filters. Refresh RSS or choose another region.</p>';return;}
  const outlets=new Set(items.map(a=>a.publisher).filter(Boolean));
  const topicCounts={};for(const item of items){const topic=item.topic||'Other';topicCounts[topic]=(topicCounts[topic]||0)+1;}
  const popular=Object.entries(topicCounts).sort((a,b)=>b[1]-a[1]).slice(0,3);
  box.innerHTML=`<div class="source-stat"><span>Indexed entries</span><strong>${items.length}</strong></div><div class="source-stat"><span>Publisher labels</span><strong>${outlets.size}</strong></div><h4>Most represented topics</h4>${popular.map(([topic,count])=>`<div class="insight-topic"><span>${escapeHTML(topic)}</span><b>${count} stories</b></div>`).join('')}<p class="insight-caveat">Counts reflect currently displayed feed entries, not a complete or verified survey of events.</p>`;
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
  renderEvidenceInventory(data.items);
  const filtersActive=Boolean(state.q)||state.topic!=='All topics';
  $('newsGrid').innerHTML=data.count?data.items.map(createArticleCard).join(''):
    `<div class="empty-state"><h3>${filtersActive?'No articles match your filters':state.demo?'No matching examples':'No matching live stories yet'}</h3><p>${filtersActive?'Try clearing your keywords or category. An empty result does not mean no event occurred.':state.demo?'Try choosing All India or clearing your search.':'BharatPulse checks for new RSS stories when you open the app and every five minutes. If the source has no relevant articles, try another region or inspect the feed status.'}</p>${filtersActive?'<button type="button" class="clear-filters-btn" id="clearEmptyFilters">Clear search & filters</button>':''}</div>`;
}
let searchTimer=null;
let newsRequestVersion=0;
let lastRenderedFilterKey='';
function resetNewsFilters(){
  clearTimeout(searchTimer);
  state.q='';state.topic='All topics';
  $('searchInput').value='';
  renderTopics(state.metadata?.topics||['All topics']);
  loadNews();
}
async function loadNews(silent=false){
  if(!silent)$('newsGrid').innerHTML='<div class="loading-view">Loading indexed stories…</div>';
  const qs=new URLSearchParams({region:state.region,topic:state.topic,q:state.q,demo:String(state.demo),limit:'60'});
  const filterKey=qs.toString();
  const requestVersion=++newsRequestVersion;
  try{
    const result=await request(`/api/news?${qs}`);
    if(requestVersion!==newsRequestVersion)return; // Ignore outdated fetches when filters change rapidly.
    const current=JSON.stringify(state.articles.map(a=>[a.id,a.published_at,a.description]));
    const incoming=JSON.stringify(result.items.map(a=>[a.id,a.published_at,a.description]));
    if(!silent || current!==incoming || lastRenderedFilterKey!==filterKey){
      renderNews(result);lastRenderedFilterKey=filterKey;
    }
  }catch(err){if(requestVersion===newsRequestVersion&&!silent){showNotice(err.message);$('newsGrid').innerHTML='<div class="empty-state"><h3>Could not load stories</h3><p>Check that the FastAPI server is running.</p></div>';}}
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
  $('topicRow').innerHTML=topics.map(t=>`<button type="button" class="topic-btn ${state.topic===t?'active':''}" data-topic="${escapeHTML(t)}">${escapeHTML(t==='All topics'?'All News':t)}</button>`).join('');
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
  state.selected=a;state.research=null;state.chatCaveatShown=false;
  $('researchQuestion').value='';
  $('drawerBackdrop').hidden=false;$('drawer').hidden=false;document.body.style.overflow='hidden';
  $('drawerTitle').textContent=a.title;
  $('drawerSub').textContent=`${a.publisher} · ${a.region} · Original language: ${a.language||'Unknown'} · Responses: ${state.language} · ${relativeDate(a.published_at)}`;
  $('researchOutput').textContent=a.is_demo?'This is an invented learning scenario. Real research is only available for live RSS articles.':'Select “Start research” to search for related coverage and build an evidence index. The configured Groq or Ollama model can generate a cited brief.';
  $('sourceList').innerHTML='';
  $('chatMessages').innerHTML='<div class="assistant-bubble">Hi! What would you like to know about this article?</div>';
  selectDrawerTab(which);
  loadArticleChatHistory(a.id, ++state.chatHistoryVersion);
}

function closeDrawer(){state.contextFetchVersion++;$('drawer').hidden=true;$('drawerBackdrop').hidden=true;document.body.style.overflow='';}
function selectDrawerTab(which){
  const research=which==='research';
  $('researchPanel').hidden=!research;$('chatPanel').hidden=research;
  $('researchTab').classList.toggle('active',research);$('chatTab').classList.toggle('active',!research);
  $('drawerTopic').textContent=research?'RESEARCH REPORT':'ARTICLE CHAT';
  if(!research){$('chatInput').focus();if(state.selected)beginArticlePreparation(state.selected.id);}
}
function locationLabel(item){
  return item.region==='All India' && item.region_confidence==='not_verified'
    ? 'Geographic location not verified'
    : (item.region||'Region not labelled');
}
function renderSources(sources){
  if(!sources?.length)return '<p class="drawer-sub">No additional live sources were available for verification.</p>';
  return `<div class="source-heading">EVIDENCE SOURCES / ${sources.length}</div>${sources.map(s=>`<article class="source-row" id="evidence-src-${Number(s.index)}"><strong>[${s.index}] ${escapeHTML(s.title)}</strong><p>${escapeHTML(s.publisher)} · ${escapeHTML(locationLabel(s))} (${escapeHTML(s.region_confidence||"unverified")}) · ${escapeHTML(relativeDate(s.published_at))} · ${escapeHTML(s.feed_origin==='direct_publisher_rss'?'Direct publisher RSS':s.feed_origin==='google_news_rss'?'Google News RSS':s.feed_origin==='bbc_publisher_rss'?'BBC RSS':'Feed origin unclassified')}</p>${allowedLink(s.url)?`<a href="${escapeHTML(s.url)}" target="_blank" rel="noopener noreferrer">Inspect publisher/source ↗</a>`:'Demo source — no external link'}</article>`).join('')}`;
}
function renderResearchReport(data){
  const report = data.report || {};
  const items = (Array.isArray(report.findings)?report.findings:[]);
  const findings = items.length ? items.map((finding, idx)=>{
    const links = (finding.evidence||[]).map(e=>`<a class="evidence-tag" href="#evidence-src-${Number(e.source)}">[${Number(e.source)}]</a>`).join(' ');
    const quotes = (finding.evidence||[]).map(e=>`<blockquote class="quote-evidence">“${escapeHTML(e.quote)}” <span>Source ${Number(e.source)} · ${data.sources?.[Number(e.source)-1]?.evidence_origin==='publisher_article'?'accessible publisher text':'RSS excerpt/headline'}</span></blockquote>`).join('');
    return `<div class="research-finding"><strong>Finding ${idx+1} · ${escapeHTML(String(finding.status||"attributed RSS report").replaceAll("_", " "))}</strong><p>${escapeHTML(finding.claim)} ${links}</p>${quotes}</div>`;
  }).join('') : '<p class="research-empty">Not enough excerpt-backed evidence to produce a supported research finding. Review the source headlines below.</p>';
  const timeline = (report.publication_timeline||[]).map(item=>`<li><a href="#evidence-src-${Number(item.source)}">[${Number(item.source)}]</a> ${escapeHTML(item.published_at)}</li>`).join('');
  const limitations = (report.not_verified||[]).map(item=>`<li>${escapeHTML(item)}</li>`).join('');
  const questions = (report.open_questions||[]).map(item=>`<li>${escapeHTML(item)}</li>`).join('');
  const badge = ['groq','ollama'].includes(data.generated_by) ? `AI DRAFT · ${escapeHTML(data.generated_by.toUpperCase())} · SOURCE-ANCHORED` : 'EVIDENCE INDEX · NO APPROVED AI FINDINGS';
  const dropNote = Number(report.rejected_claims||0)>0 ? `<p class="research-muted">${Number(report.rejected_claims)} draft claim(s) excluded by quotation, numeric or semantic review checks.</p>` : '';
  const disputes = (report.reported_disputes||[]).map(item=>`<blockquote>${escapeHTML(item.quote)} [${Number(item.source)}]</blockquote>`).join('');
  const summary = (disputes?`<section><h3>Disputed statements in the sources</h3>${disputes}</section>`:'') + (report.key_takeaway ? `<div class="report-section"><h3>Evidence-based research summary</h3><p>${escapeHTML(report.key_takeaway)}</p><p class="research-muted">Source statements below are attributed publisher reporting, not independent confirmation.</p></div>` : '');
  const focus = (Array.isArray(report.research_focus)?report.research_focus:[]);
  const researchFocus = focus.length ? `<div class="report-section"><h3>Answers to the requested research topics</h3><p class="research-muted">A relevant phrase in a source is not, by itself, proof that the question is fully answered.</p><ul>${focus.map(item => `<li><strong>${escapeHTML(item.label)}:</strong> ${item.status==='mentioned_in_rss' ? `Mentioned in source(s) ${(item.sources||[]).map(n=>`<a href="#evidence-src-${Number(n)}">[${Number(n)}]</a>`).join(' ')}` : 'Not established by indexed reporting'}<span class="research-muted"> — ${escapeHTML(item.note||'')}</span></li>`).join('')}</ul></div>` : '';
  const highlights = (Array.isArray(report.source_highlights)?report.source_highlights:[]);
  const additionalReporting = highlights.length ? `<div class="report-section"><h3>Additional potentially matching reporting</h3><p class="research-muted">Statements attributed to the indexed publishers.</p>${highlights.map(s=>`<div class="comparison-item"><strong><a href="#evidence-src-${Number(s.source)}">[${Number(s.source)}]</a> ${escapeHTML(s.publisher)}</strong><p>“${escapeHTML(s.headline)}”</p>${s.excerpt?`<blockquote>${escapeHTML(s.excerpt)}</blockquote>`:''}<small>Relationship: ${escapeHTML(s.relationship)}</small></div>`).join('')}</div>` : '';
  const comparisons=(Array.isArray(report.source_comparison)?report.source_comparison:[]);
  const detailCount=comparisons.filter(x=>x.detail_level==='excerpt_available').length;
  const articleCount=comparisons.filter(x=>x.detail_level==='publisher_article').length;
  const sourceComparison = comparisons.length ? `<div class="report-section source-comparison"><h3>Source-by-source reporting index</h3>
    <p class="research-muted">${comparisons.length} indexed sources; ${articleCount} include accessible publisher text; ${detailCount} contain RSS excerpt context. Publisher reporting is not independent verification.</p>
    ${comparisons.map(item=>`<div class="comparison-item"><div class="comparison-head"><strong><a href="#evidence-src-${Number(item.index)}">[${Number(item.index)}]</a> ${escapeHTML(item.publisher)}</strong><small>${item.detail_level==='publisher_article'?'Accessible publisher article':item.detail_level==='headline_only'?'Headline only':'Headline + RSS excerpt'} · ${escapeHTML(item.relationship==='selected_story'?'Selected story':item.relationship==='possible_same_story'?'Possible same story · not verified':'Related topic · same incident not established')}</small></div><p>${escapeHTML(item.headline)}</p>${item.excerpt?`<blockquote>${escapeHTML(item.excerpt)}</blockquote>`:'<small>No additional detail supplied by the indexed RSS entry.</small>'}</div>`).join('')}</div>` : '';
  const workflow = data.workflow || {};
  const nodes = (Array.isArray(workflow.trace) ? workflow.trace : []).map(step =>
    `<li class="agent-step"><span class="agent-dot ${step.status==='completed'?'ok':step.status==='degraded'?'warn':'skip'}"></span><div><strong>${escapeHTML(step.agent)}</strong><small>${escapeHTML(step.status)} · ${escapeHTML(step.detail)}</small></div></li>`).join('');
  const agentTrace = nodes ? `<div class="report-section"><h3>LangGraph agent execution trace</h3><p class="research-muted">${escapeHTML(workflow.engine||'')} · ${Number(workflow.source_count||0)} indexed sources · review: ${escapeHTML(workflow.review_status||'not_run')}</p><ol class="agent-trace">${nodes}</ol></div>` : '';
  // Literal RSS metadata signals; amounts and similar titles are not fact checks.
  const coverage=report.coverage||{};
  const headlineGroups=(coverage.headline_overlap_groups||[]).map(group=>
    `<li>Sources ${group.sources.map(n=>`<a href="#evidence-src-${Number(n)}">[${Number(n)}]</a>`).join(', ')}: similar wording; possible repeated reporting, not proven syndication.</li>`).join('');
  const amounts=(coverage.reported_numbers||[]).map(entry=>
    `<li><a href="#evidence-src-${Number(entry.source)}">[${Number(entry.source)}]</a> <strong>${escapeHTML(entry.value)}</strong> <span>— ${escapeHTML(entry.context)}</span></li>`).join('');
  const coveragePanel=(coverage.source_count!==undefined) ? `<div class="report-section coverage-panel">
    <h3>Coverage and reported figures · indexed source evidence</h3>
    <p class="research-muted">${Number(coverage.source_count||0)} indexed entries · ${Number(coverage.publisher_label_count||0)} publisher labels. Distinct labels do not prove independent reporting.</p>
    <h4>Possible headline overlap</h4>${headlineGroups?`<ul>${headlineGroups}</ul>`:'<p class="research-muted">No strong headline overlap found in this limited evidence set; syndication remains possible.</p>'}
    <h4>Numerical details appearing in sources</h4>${amounts?`<ul class="quantity-list">${amounts}</ul>`:'<p class="research-muted">No qualifying numeric figures with supported units in the indexed RSS text.</p>'}
    <p class="research-muted">Figures are quoted from source text and have not been verified or reconciled against primary documents.</p>
  </div>` : '';


  return `<div class="research-badge">${badge}</div>
    ${agentTrace}${summary}${researchFocus}<div class="report-section"><h3>AI-reviewed findings</h3>${findings}${dropNote}</div>${additionalReporting}${sourceComparison}${coveragePanel}
    <div class="report-section"><h3>Publication timeline (UTC)</h3><p class="research-muted">These are reported feed publication timestamps, <strong>not the dates or times of the underlying events.</strong></p><ol>${timeline}</ol></div>
    <div class="report-section"><h3>What is not verified</h3><ul>${limitations}</ul></div>
    <div class="report-section"><h3>Questions for further reporting</h3><ul>${questions}</ul></div>
    <div class="report-section research-caveat"><h3>Evidence limitations</h3><p>${escapeHTML(data.caveat||'')}</p>${data.warning?`<p>${escapeHTML(data.warning)}</p>`:''}<p>Source labels may represent syndicated material, not independent confirmation. This report requires editorial review.</p></div>`;
}
async function runResearch(){
  if(!state.selected)return;
  const article={...state.selected};
  $('researchRun').disabled=true;
  $('researchOutput').classList.remove('report-structured');
  $('researchOutput').textContent='Running LangGraph: planning, RSS discovery, retrieval, source-quoted synthesis and semantic review…';
  try{
    const result=await request(`/api/research/${encodeURIComponent(article.id)}`,{method:'POST',body:JSON.stringify({language:state.language,question:$('researchQuestion').value.trim()})});
    if(!state.selected || state.selected.id!==article.id)return;
    $('sourceList').innerHTML=renderSources(result.sources);
    $('researchOutput').classList.add('report-structured');
    $('researchOutput').innerHTML=renderResearchReport(result);
    const destination=$('researchShowcaseResult');
    if(destination){destination.innerHTML=renderResearchReport(result);const status=$('researchShowcaseStatus');status.textContent=`Research completed for: ${article.title}. Review source quotations and limitations below.`;}
    const ref=$('reportReference'),head=$('reportHeadline'),sub=$('reportSubtitle');
    if(ref)ref.textContent=`Article ${article.id}`;
    if(head)head.textContent=article.title;
    if(sub)sub.textContent=`${article.publisher} · ${locationLabel(article)} · ${relativeDate(article.published_at)} · ${result.report?.evidence_depth?.publisher_articles?'Includes publisher passages':'RSS evidence only'}`;
    const evidence=$('reportEvidenceSources');if(evidence)evidence.innerHTML=renderSources(result.sources);
    const evidenceHead=$('reportEvidenceHeading');if(evidenceHead)evidenceHead.textContent=`Cited evidence sources (${(result.sources||[]).length})`;
    const print=$('printReport');if(print)print.disabled=false;
    closeDrawer();setActiveScreen('research-showcase');

  }catch(err){
    $('researchOutput').classList.remove('report-structured');
    $('researchOutput').textContent='Research could not complete: '+err.message;
  }finally{$('researchRun').disabled=false;}
}

async function loadArticleChatHistory(articleId,version){
  // The server reads a first-party, HttpOnly session cookie. No session token
  // is exposed to JavaScript, localStorage, or the rendered answer.
  try{
    const result=await request(`/api/chat/history?article_id=${encodeURIComponent(articleId)}`);
    if(version!==state.chatHistoryVersion || state.selected?.id!==articleId)return;
    // Do not interleave delayed saved-history fetches with new messages.
    if($('chatMessages').querySelector('.user-bubble'))return;
    for(const turn of result.turns||[]){
      appendChat(turn.question,'user');
      appendChat(turn.answer,'assistant');
    }
    const action=document.createElement('button');
    action.type='button';action.className='chat-clear-history';
    action.textContent='Clear this article conversation';
    action.addEventListener('click',async()=>{
      try{
        await request('/api/chat/clear',{method:'POST',body:JSON.stringify({article_id:articleId})});
        if(state.selected?.id===articleId){
          state.chatHistoryVersion++;
          $('chatMessages').innerHTML='<div class="assistant-bubble">Conversation cleared for this article. Ask a new question.</div>';
          $('chatMessages').append(action);
        }
      }catch(err){showNotice(`Unable to clear chat: ${err.message}`);}
    });
    $('chatMessages').append(action);
  }catch(err){
    // News Q&A remains usable even if the optional history endpoint fails.
  }
}

function articleEvidenceStatusLabel(payload){
  if(payload?.status==='ready')return payload.provenance==='publisher_syndicated_feed'?'Article evidence ready · publisher feed':'Article evidence ready · publisher page';
  const reason=String(payload?.failure_code||'');
  const labels={
    publisher_dns_unavailable:'RSS evidence only · publisher DNS unavailable',
    robots_policy_unavailable:'RSS evidence only · publisher reading policy unavailable',
    publisher_url_not_resolved:'RSS evidence only · original publisher link not resolved',
    publisher_access_not_permitted:'RSS evidence only · publisher does not permit automated reading',
    publisher_access_restricted:'RSS evidence only · publisher access restricted',
    insufficient_accessible_text:'RSS evidence only · readable article body unavailable',
    publisher_story_mismatch:'RSS evidence only · retrieved page did not match article',
    publisher_domain_mismatch:'RSS evidence only · destination was a different publisher',
    source_url_not_permitted:'RSS evidence only · source URL not approved',
  };
  return labels[reason]||(reason?'RSS evidence only · '+reason.replaceAll('_',' '):'RSS evidence only');
}
async function beginArticlePreparation(articleId){
  const version=++state.contextFetchVersion;
  if(!state.selected || state.selected.id!==articleId || state.selected.is_demo)return;
  const initial=$('chatContextStatus');
  if(initial)initial.textContent='Reading source in the background…';
  try{
    const first=await request(`/api/article-context/${encodeURIComponent(articleId)}/prepare`,{method:'POST'});
    if(version!==state.contextFetchVersion || state.selected?.id!==articleId)return;
    if(first.status==='ready' || first.status==='limited'){
      if(initial)initial.textContent=articleEvidenceStatusLabel(first);
      return;
    }
    for(let i=0;i<18;i++){
      await new Promise(resolve=>setTimeout(resolve,1500));
      if(version!==state.contextFetchVersion || state.selected?.id!==articleId)return;
      const data=await request(`/api/article-context/${encodeURIComponent(articleId)}`);
      if(data.status!=='loading' && data.status!=='not_started'){
        if(initial)initial.textContent=articleEvidenceStatusLabel(data);
        return;
      }
    }
    if(initial)initial.textContent='Preparing article evidence; questions can still be submitted';
  }catch(err){
    if(version===state.contextFetchVersion && initial)initial.textContent='Article preload unavailable · RSS fallback';
  }
}
function appendChat(text,type){const div=document.createElement('div');div.className=type==='user'?'user-bubble':'assistant-bubble';div.textContent=text;$('chatMessages').append(div);$('chatMessages').scrollTop=$('chatMessages').scrollHeight;return div;}
async function submitChat(event){
  event.preventDefault();if(!state.selected)return;
  const input=$('chatInput'),question=input.value.trim();if(question.length<2)return;
  const articleId=state.selected.id;
  input.value='';appendChat(question,'user');const bubble=appendChat('Checking prepared article evidence…','assistant');
  const submit=$('chatForm').querySelector('button');submit.disabled=true;
  try{
    const data=await request('/api/chat',{method:'POST',body:JSON.stringify({article_id:articleId,question,language:state.language})});
    if(!state.selected || state.selected.id!==articleId){bubble.remove();return;}
    const hasReviewedClaims=Array.isArray(data.claims)&&data.claims.length>0;
    const titles={source_passage:'RELEVANT SOURCE PASSAGE',source_metadata:'PUBLICATION DETAILS',general_ai:'GENERAL KNOWLEDGE · AI EXPLANATION',general_reference:'GENERAL KNOWLEDGE · DEFINITION',mixed_ai:'GENERAL BACKGROUND + ARTICLE EVIDENCE',
      source_summary:'RSS-LEVEL SUMMARY · NOT FULL ARTICLE',source_evidence:'WHAT INDEXED RSS SOURCES ACTUALLY SAY',
      source_overview:'MULTI-SOURCE RSS REPORTING · NOT INDEPENDENT VERIFICATION',
      source_source_list:'INDEXED PUBLISHERS · SOURCE ATTRIBUTION',source_later_events:'LATER DEVELOPMENTS · NOT ESTABLISHED',
      insufficient_evidence:'AVAILABLE EVIDENCE · ANSWER NOT ESTABLISHED',
      source_index:'SOURCE INDEX · AI PROVIDER NOT CONFIGURED',
      ai_unavailable:'AI PROVIDER UNAVAILABLE · SOURCE DETAILS ONLY',
      groq:'ARTICLE AI DRAFT · CLAIMS REVIEWED',ollama:'ARTICLE AI DRAFT · CLAIMS REVIEWED'};
    const title=data.evidence_status==='publisher_article'?'PUBLISHER ARTICLE EVIDENCE':titles[data.generated_by]||'SOURCE-LIMITED ANSWER';
    bubble.textContent=`${title}\n\n${data.answer}`;
    if(hasReviewedClaims){
      for(const claim of data.claims){
        const detail=document.createElement('div');detail.className='chat-evidence';
        const heading=document.createElement('strong');heading.textContent=`Source [${claim.source}] · exact supporting ${data.sources?.find(s=>Number(s.index)===Number(claim.source))?.evidence_origin==='publisher_article'?'publisher article passage':'RSS excerpt'}`;
        const excerpt=document.createElement('blockquote');excerpt.textContent=claim.quote;
        detail.append(heading,excerpt);bubble.append(detail);
      }
    }
    if(data.sources?.length){
      const heading=document.createElement('p');heading.className='chat-evidence-note';
      heading.textContent=(hasReviewedClaims||['source_summary','source_evidence','source_overview','source_source_list','source_later_events','general_reference','mixed_ai'].includes(data.generated_by))?
        'Indexed reporting links (not independent verification):':'Related reporting links (not proof of the requested answer):';bubble.append(heading);
      for(const src of data.sources){
        if(!allowedLink(src.url))continue;
        const link=document.createElement('a');link.href=src.url;link.target='_blank';link.rel='noopener noreferrer';
        const throughGoogle=/^https:\/\/news\.google\.com\//i.test(src.url);
        link.className='chat-evidence-link';
        link.textContent=`[${src.index}] ${src.publisher} · ${throughGoogle?'Open Google News RSS link':'Open publisher/source link'} ↗`;
        bubble.append(link);
      }
    }
    // One disclaimer per open article conversation, not repeated under every reply.
    if(!state.chatCaveatShown && data.caveat){
      const note=document.createElement('p');note.className='chat-evidence-note';
      note.textContent=data.caveat;bubble.append(note);state.chatCaveatShown=true;
    }
  }catch(err){bubble.textContent='Request failed: '+err.message;}
  finally{submit.disabled=false;$('chatMessages').scrollTop=$('chatMessages').scrollHeight;}
}
// v0.8 Weather Intelligence. No fake weather values: empty provider responses stay empty.
const weatherState={city:'Bengaluru',forecast:null,cities:[],map:null,markers:[],markerByCity:new Map(),selectedLocationMarker:null,mapLoaded:false,loading:false,requestId:0};
function weatherNumber(value,suffix='',digits=0){return typeof value==='number'&&Number.isFinite(value)?`${value.toFixed(digits)}${suffix}`:'Unavailable';}
function mapTemperature(value){return typeof value==='number'?`${Math.round(value)}°C`:'No data';}
function weatherMapIcon(city,temperature){
  const label=`${escapeHTML(city)} · ${escapeHTML(mapTemperature(temperature))}`;
  return window.L.divIcon({html:`<span class="weather-temp-marker">${label}</span>`,className:'',iconSize:[150,25],iconAnchor:[60,15]});
}
// Keep the selected city, forecast and map in sync. Works even for cities not
// included among the 12 sampled temperature markers on the overview map.
function syncWeatherMapToCity({focus=true}={}){
  const place=weatherState.cities.find(item=>item.city===weatherState.city);
  if(!place)return;
  const status=$('weatherMapSelection');
  if(status)status.textContent=`Selected: ${place.city} · ${place.region}`;
  const fallbackMarker=$('fallbackCityMarker');
  if(fallbackMarker){
    const temp=weatherState.forecast?.city===place.city?weatherState.forecast.current?.temperature_c:null;
    fallbackMarker.textContent=`${place.city} · ${mapTemperature(temp)}`;
    fallbackMarker.style.left=`${Math.max(5,Math.min(91,(Number(place.longitude)-66)/34*100))}%`;
    fallbackMarker.style.top=`${Math.max(12,Math.min(78,(39-Number(place.latitude))/34*100))}%`;
  }
  const map=weatherState.map;
  if(!map)return; // A lazy-loaded map will catch up when it initializes.
  const coords=[place.latitude,place.longitude];
  const hasForecast=weatherState.forecast?.city===place.city;
  const temperature=hasForecast?weatherState.forecast.current?.temperature_c:null;
  const popup=`<strong>${escapeHTML(place.city)}, ${escapeHTML(place.region)}</strong><br>${escapeHTML(mapTemperature(temperature))} · Selected location`;
  if(!weatherState.selectedLocationMarker){
    weatherState.selectedLocationMarker=window.L.circleMarker(coords,{
      radius:15,color:'#397b3a',weight:3,fillColor:'#b2ed70',fillOpacity:0.28
    }).addTo(map);
  }else{
    weatherState.selectedLocationMarker.setLatLng(coords);
  }
  weatherState.selectedLocationMarker.bindPopup(popup);
  for(const [name,marker] of weatherState.markerByCity){
    const element=marker.getElement();
    element?.querySelector('.weather-temp-marker')?.classList.toggle('is-selected',name===place.city);
    marker.setZIndexOffset(name===place.city?1000:0);
  }
  if(hasForecast&&typeof temperature==='number'){
    const marker=weatherState.markerByCity.get(place.city);
    if(marker){
      marker.setIcon(weatherMapIcon(place.city,temperature));
      marker.getElement()?.querySelector('.weather-temp-marker')?.classList.add('is-selected');
    }
  }
  if(focus){
    map.invalidateSize();
    map.setView(coords,Math.max(map.getZoom(),7),{animate:true});
    const labelled=weatherState.markerByCity.get(place.city);
    (labelled||weatherState.selectedLocationMarker).openPopup();
  }
}
function chooseWeatherCity(city){
  if(!weatherState.cities.some(item=>item.city===city))return;
  const changed=weatherState.city!==city;
  weatherState.city=city;$('weatherCitySelect').value=city;
  if(changed){
    weatherState.forecast=null; // Do not display a previous city's values as the new city's values.
    $('weatherAnswer').textContent=`Location changed to ${city}. Ask Weather AI for this city's forecast.`;
  }
  syncWeatherMapToCity(); // Recenter immediately, without waiting for an API response.
  loadWeather();
}
async function loadWeather(){
  const requestId=++weatherState.requestId;
  weatherState.loading=true;
  const selected=weatherState.city;
  $('weatherUpdated').textContent='Checking Open-Meteo forecast…';
  $('weatherCityTitle').textContent=selected;
  $('weatherTemp').textContent='—';
  $('weatherDaily').innerHTML='<p class="weather-empty">Fetching seven-day forecast…</p>';
  try{
    const forecast=await request(`/api/weather/forecast?${new URLSearchParams({city:selected})}`);
    if(selected!==weatherState.city)return;
    weatherState.forecast=forecast;
    const current=forecast.current||{};
    $('weatherTemp').textContent=weatherNumber(current.temperature_c,'°C',1);
    $('weatherCurrent').textContent=current.description||'Condition not available';
    $('weatherHumidity').textContent=`Humidity ${weatherNumber(current.humidity_percent,'%')}`;
    $('weatherWind').textContent=`Wind ${weatherNumber(current.wind_kmh,' km/h',1)}`;
    $('weatherUpdated').textContent=`Weather provider: ${forecast.provider} · Retrieved ${new Date(forecast.fetched_at).toLocaleString('en-IN')} · City-specific model forecast`;
    syncWeatherMapToCity({focus:false}); // Reflect the selected city's latest temperature in its map marker.
    $('weatherDaily').innerHTML=forecast.daily.map(day=>`<div class="weather-day"><strong>${escapeHTML(new Date(day.date+'T12:00:00').toLocaleDateString('en-IN',{weekday:'short',day:'numeric',month:'short'}))}</strong><span class="day-condition">${escapeHTML(day.description)}</span><span class="day-temps">${weatherNumber(day.temperature_2m_min,'°')}–${weatherNumber(day.temperature_2m_max,'°')}</span><span class="day-rain">Rain chance ${weatherNumber(day.precipitation_probability_max,'%')}<br>Precip. ${weatherNumber(day.precipitation_sum,' mm',1)}</span></div>`).join('');
  }catch(err){
    weatherState.forecast=null;$('weatherCurrent').textContent='Forecast unavailable';
    $('weatherUpdated').textContent='Open-Meteo is unavailable. No forecast has been invented.';
    $('weatherDaily').innerHTML=`<div class="weather-empty">${escapeHTML(err.message)}. Try again later.</div>`;
  }finally{if(requestId===weatherState.requestId)weatherState.loading=false;}
  if(requestId!==weatherState.requestId)return;
  try{
    const place=weatherState.cities.find(c=>c.city===selected);
    if(place){
      await request('/api/news/watch',{method:'POST',body:JSON.stringify({region:place.region})});
      await loadWeatherNews(place.region);
    }
  }catch{ /* Weather news is supplementary and must not block forecast viewing. */ }
}
async function loadWeatherNews(region){
  try{
    const news=await request(`/api/weather/news?${new URLSearchParams({region})}`);
    $('weatherNews').innerHTML=news.items.length ? news.items.map(item=>`<article class="weather-news-item">${allowedLink(item.url)?`<a href="${escapeHTML(item.url)}" target="_blank" rel="noopener noreferrer">${escapeHTML(item.title)}</a>`:`<strong>${escapeHTML(item.title)}</strong>`}<small>${escapeHTML(item.publisher)} · ${escapeHTML(relativeDate(item.published_at))}</small><div class="weather-news-actions"><button type="button" data-weather-research="${escapeHTML(item.id)}">Research ↗</button><button type="button" data-weather-chat="${escapeHTML(item.id)}">Ask AI ↗</button></div></article>`).join('') : '<p class="weather-empty">No matching weather-related reports in the indexed regional RSS headlines. This does not mean no weather events have occurred.</p>';
  }catch(err){$('weatherNews').textContent='Could not load weather news: '+err.message;}
}
async function showWeatherMap(){
  if(weatherState.mapLoaded)return;
  weatherState.mapLoaded=true;
  if(typeof window.L==='undefined'){$('weatherMapFallback').hidden=false;$('weatherMap').closest('.weather-map-panel')?.classList.add('offline-map');syncWeatherMapToCity({focus:false});return;}
  const L=window.L;
  weatherState.map=L.map('weatherMap',{scrollWheelZoom:false}).setView([22.5,79.0],5);
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{
    attribution:'© OpenStreetMap contributors',maxZoom:18
  }).addTo(weatherState.map);
  syncWeatherMapToCity(); // Focus the initial city even before sample markers are fetched.
  try{
    const data=await request('/api/weather/map');
    for(const city of data.points){
      const liveTemperature=weatherState.forecast?.city===city.city
        ?weatherState.forecast.current?.temperature_c:city.temperature_c;
      const label=`${escapeHTML(city.city)} · ${escapeHTML(mapTemperature(liveTemperature))}`;
      const marker=L.marker([city.latitude,city.longitude],{
        icon:weatherMapIcon(city.city,liveTemperature)
      }).addTo(weatherState.map);
      marker.bindPopup(`${label}<p>Click the marker for the city forecast.</p>`);
      marker.on('click',()=>chooseWeatherCity(city.city));
      weatherState.markers.push(marker);
      weatherState.markerByCity.set(city.city,marker);
    }
    syncWeatherMapToCity({focus:false}); // Highlight the current selection after async markers load.
  }catch{
    $('weatherMapFallback').hidden=false;
    $('weatherMap').closest('.weather-map-panel')?.classList.add('offline-map');
    $('weatherMapFallback').textContent='City temperature measurements unavailable; choose a city from the dropdown.';
  }
  setTimeout(()=>weatherState.map?.invalidateSize(),150);
}
async function sendWeatherChat(event){
  event.preventDefault();
  const input=$('weatherQuestion'),question=input.value.trim();if(question.length<2)return;
  const button=$('weatherChatForm').querySelector('button');button.disabled=true;
  const requestedCity=weatherState.city;
  $('weatherAnswer').textContent='Checking forecast measurements and preparing an evidence-constrained response…';
  try{
    const data=await request('/api/weather/chat',{method:'POST',body:JSON.stringify({city:requestedCity,question,language:state.language})});
    if(requestedCity===weatherState.city)$('weatherAnswer').textContent=`${data.answer}\n\nSource: ${data.source} · ${data.generated_by}\n${data.caveat}`;
  }catch(err){if(requestedCity===weatherState.city)$('weatherAnswer').textContent='Weather assistant unavailable: '+err.message;}
  finally{button.disabled=false;}
}
async function initWeather(){
  try{
    const info=await request('/api/weather/cities');weatherState.cities=info.items;
    $('weatherCitySelect').innerHTML=info.items.map(c=>`<option value="${escapeHTML(c.city)}">${escapeHTML(c.city)} · ${escapeHTML(c.region)}</option>`).join('');
    $('weatherCitySelect').value=weatherState.city;
    syncWeatherMapToCity({focus:false});
    await loadWeather();
  }catch(err){$('weatherUpdated').textContent='Weather module unavailable: '+err.message;}
  $('weatherCitySelect').addEventListener('change',e=>chooseWeatherCity(e.target.value));
  $('weatherRefresh').addEventListener('click',loadWeather);
  $('weatherChatForm').addEventListener('submit',sendWeatherChat);
  $('weatherNews').addEventListener('click',async event=>{
    const button=event.target.closest('[data-weather-research],[data-weather-chat]');
    if(!button)return;
    const id=button.dataset.weatherResearch||button.dataset.weatherChat;
    try{
      if(!state.articles.some(a=>a.id===id)){
        const item=await request(`/api/news/${encodeURIComponent(id)}`);
        if(item.is_demo)return;
        state.articles.push(item);
      }
      openDrawer(id,button.hasAttribute('data-weather-chat')?'chat':'research');
    }catch(err){$('weatherNews').insertAdjacentText('beforeend',' · Could not load selected story: '+err.message);}
  });
  if('IntersectionObserver' in window){
    const observer=new IntersectionObserver(entries=>{if(entries.some(entry=>entry.isIntersecting)){observer.disconnect();showWeatherMap();}},{rootMargin:'200px'});
    observer.observe($('weather'));
  }else{showWeatherMap();}
  document.querySelector('[data-nav="weather"]')?.addEventListener('click',showWeatherMap);
  // Forecast cache TTL is ten minutes; don't repeatedly load upstream when a tab is hidden.
  window.setInterval(()=>{if(!document.hidden&&weatherState.forecast&&Date.now()-new Date(weatherState.forecast.fetched_at).getTime()>600000)loadWeather();},60000);
}
async function init(){
  try{
    state.metadata=await request('/api/meta');
    $('regionSelect').innerHTML=state.metadata.regions.map(r=>`<option value="${escapeHTML(r)}">${escapeHTML(r)}</option>`).join('');
    renderTopics(state.metadata.topics);
    $('languageSelect').innerHTML=state.metadata.response_languages.map(l=>`<option value="${escapeHTML(l)}">${escapeHTML(l)}</option>`).join('');
    $('languageSelect').value=state.language;
    $('statAI').textContent=state.metadata.llm_configured?`${state.metadata.llm_provider.toUpperCase()} SETUP`:'SOURCE MODE';
    const headerAi=$('headerAiCheckBtn');
    const publicOff=state.metadata.public_demo&&!state.metadata.public_ai_enabled;
    headerAi.textContent=publicOff?'AI OFF · PUBLIC DEMO':state.metadata.llm_configured?'Test AI connection':'AI NOT CONFIGURED';
    headerAi.disabled=publicOff||!state.metadata.llm_configured;
    $('aiNote').textContent=state.metadata.llm_configured?`Model: ${state.metadata.llm_model} (check connection via /api/ai/check)`:'Configure Groq or Ollama to enable AI';
  }catch(err){showNotice('Backend not responding: '+err.message);}
  $('aiCheckBtn').addEventListener('click',async()=>{
    const btn=$('aiCheckBtn');btn.disabled=true;btn.textContent='Checking…';
    try{
      const result=await request('/api/ai/check',{method:'POST'});
      $('statAI').textContent=`${result.provider.toUpperCase()} READY`;
      $('headerAiCheckBtn').textContent=`${result.provider.toUpperCase()} READY`;
      $('aiNote').textContent=`Connected to ${result.model}`;
    }catch(err){
      $('statAI').textContent='AI UNAVAILABLE';
      $('headerAiCheckBtn').textContent='AI UNAVAILABLE';
      $('aiNote').textContent=err.message;
    }finally{btn.disabled=false;btn.textContent='Test AI connection';}
  });
  $('headerAiCheckBtn').addEventListener('click',()=>$('aiCheckBtn').click());
  $('regionSelect').addEventListener('change',e=>{state.region=e.target.value;state.lastFeedSuccess=null;loadNews();if(!state.demo){watchRegion();checkLiveUpdates();}});
  $('languageSelect').addEventListener('change',e=>{state.language=e.target.value;if(state.selected){$('drawerSub').textContent=`${state.selected.publisher} · ${state.selected.region} · Original language: ${state.selected.language||'Unknown'} · Responses: ${state.language}`;}});
  $('searchInput').addEventListener('input',e=>{clearTimeout(searchTimer);searchTimer=setTimeout(()=>{state.q=e.target.value.trim();loadNews();},230);});
  $('topicRow').addEventListener('click',e=>{const b=e.target.closest('[data-topic]');if(!b)return;state.topic=b.dataset.topic;renderTopics(state.metadata?.topics||['All topics']);loadNews();});
  $('clearFiltersBtn').addEventListener('click',resetNewsFilters);
  $('newsGrid').addEventListener('click',e=>{if(e.target.closest('#clearEmptyFilters'))resetNewsFilters();});
  $('liveBtn').addEventListener('click',()=>setMode(false));$('demoBtn').addEventListener('click',()=>setMode(true));
  $('refreshBtn').addEventListener('click',refresh);
  $('newsGrid').addEventListener('click',e=>{const b=e.target.closest('[data-research],[data-chat]');if(!b)return;openDrawer(b.dataset.research||b.dataset.chat,b.hasAttribute('data-chat')?'chat':'research');});
  $('drawerClose').addEventListener('click',closeDrawer);$('drawerBackdrop').addEventListener('click',closeDrawer);
  document.addEventListener('keydown',e=>{if(e.key==='Escape')closeDrawer();});
  $('researchTab').addEventListener('click',()=>selectDrawerTab('research'));
  $('chatTab').addEventListener('click',()=>selectDrawerTab('chat'));
  $('researchRun').addEventListener('click',runResearch);$('chatForm').addEventListener('submit',submitChat);
  document.querySelectorAll('[data-nav]').forEach(a=>a.addEventListener('click',()=>setActiveScreen(a.dataset.nav)));
  window.addEventListener('hashchange',()=>setActiveScreen(screenFromHash(),false));
  $('printReport')?.addEventListener('click',()=>window.print());
  setActiveScreen(screenFromHash(),false);
  // Opening the page immediately asks the server to check freshness and,
  // if due, start a non-blocking RSS retrieval. Cached items appear at once.
  setMode(false);
  initWeather();
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)checkLiveUpdates();});
  window.setInterval(checkLiveUpdates,20000); // UI sync, distinct from 5-minute RSS polling.
}
function screenFromHash(){
  const id=(location.hash||'#explorer').slice(1);
  return ['explorer','research-showcase','weather','regional-coverage'].includes(id) ? id : 'explorer';
}
function setActiveScreen(screen, updateHash=true){
  if(!['explorer','research-showcase','weather','regional-coverage'].includes(screen))screen='explorer';
  document.body.dataset.screen=screen;
  document.querySelectorAll('[data-nav]').forEach(a=>a.classList.toggle('active',a.dataset.nav===screen));
  if(updateHash&&location.hash!==`#${screen}`)history.replaceState(null,'',`#${screen}`);
  window.scrollTo(0,0);
  if(screen==='weather'){
    if(typeof showWeatherMap==='function')showWeatherMap();
    setTimeout(()=>weatherState.map?.invalidateSize(),200);
  }
}
window.addEventListener('DOMContentLoaded',init);
