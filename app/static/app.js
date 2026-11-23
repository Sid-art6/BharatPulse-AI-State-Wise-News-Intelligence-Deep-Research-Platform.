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
  $('researchQuestion').value='';
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
  const dropNote = Number(report.rejected_claims||0)>0 ? `<p class="research-muted">${Number(report.rejected_claims)} draft claim(s) excluded by quotation, numeric or semantic review checks.</p>` : '';
  const workflow = data.workflow || {};
  const nodes = (Array.isArray(workflow.trace) ? workflow.trace : []).map(step =>
    `<li class="agent-step"><span class="agent-dot ${step.status==='completed'?'ok':step.status==='degraded'?'warn':'skip'}"></span><div><strong>${escapeHTML(step.agent)}</strong><small>${escapeHTML(step.status)} · ${escapeHTML(step.detail)}</small></div></li>`).join('');
  const agentTrace = nodes ? `<div class="report-section"><h3>LangGraph agent execution trace</h3><p class="research-muted">${escapeHTML(workflow.engine||'')} · ${Number(workflow.source_count||0)} indexed sources · review: ${escapeHTML(workflow.review_status||'not_run')}</p><ol class="agent-trace">${nodes}</ol></div>` : '';

  return `<div class="research-badge">${badge}</div>
    ${agentTrace}<div class="report-section"><h3>What available sources report</h3>${findings}${dropNote}</div>
    <div class="report-section"><h3>Publication timeline (UTC)</h3><p class="research-muted">These are reported feed publication timestamps, <strong>not the dates or times of the underlying events.</strong></p><ol>${timeline}</ol></div>
    <div class="report-section"><h3>What is not verified</h3><ul>${limitations}</ul></div>
    <div class="report-section"><h3>Questions for further reporting</h3><ul>${questions}</ul></div>
    <div class="report-section research-caveat"><h3>Evidence limitations</h3><p>${escapeHTML(data.caveat||'')}</p>${data.warning?`<p>${escapeHTML(data.warning)}</p>`:''}<p>Source labels may represent syndicated material, not independent confirmation. This report requires editorial review.</p></div>`;
}
async function runResearch(){
  if(!state.selected)return;
  $('researchRun').disabled=true;
  $('researchOutput').classList.remove('report-structured');
  $('researchOutput').textContent='Running LangGraph: planning, RSS discovery, retrieval, source-quoted synthesis and semantic review…';
  try{
    const result=await request(`/api/research/${encodeURIComponent(state.selected.id)}`,{method:'POST',body:JSON.stringify({language:state.language,question:$('researchQuestion').value.trim()})});
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
    const isDraft=['groq','ollama'].includes(data.generated_by) && data.claims?.length;
    bubble.textContent=(isDraft?'AI DRAFT · CLAIMS REVIEWED AGAINST RSS EXCERPTS\n\n':'INSUFFICIENT SOURCE EVIDENCE / AI UNAVAILABLE\n\n')+data.answer;
    if(isDraft){
      for(const claim of data.claims){
        const detail=document.createElement('div');detail.className='chat-evidence';
        const heading=document.createElement('strong');heading.textContent=`RSS source [${claim.source}] · exact supporting excerpt`;
        const excerpt=document.createElement('blockquote');excerpt.textContent=claim.quote;
        detail.append(heading,excerpt);bubble.append(detail);
      }
    }
    if(data.sources?.length){
      const heading=document.createElement('p');heading.className='chat-evidence-note';
      heading.textContent=isDraft?'Cited source links:':'Related source links (not proof of the requested answer):';bubble.append(heading);
      for(const src of data.sources){
        if(!allowedLink(src.url))continue;
        const link=document.createElement('a');link.href=src.url;link.target='_blank';link.rel='noopener noreferrer';
        link.className='chat-evidence-link';link.textContent=`[${src.index}] ${src.publisher} · Open original source ↗`;
        bubble.append(link);
      }
    }
    const note=document.createElement('p');note.className='chat-evidence-note';
    note.textContent=data.caveat||'RSS excerpts are not independently fact checked. Check publisher articles.';
    bubble.append(note);
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
  if(typeof window.L==='undefined'){$('weatherMapFallback').hidden=false;return;}
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
      openDrawer(id,button.hasAttribute('data-weatherChat')?'chat':'research');
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
  initWeather();
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)checkLiveUpdates();});
  window.setInterval(checkLiveUpdates,20000); // UI sync, distinct from 5-minute RSS polling.
}
window.addEventListener('DOMContentLoaded',init);
