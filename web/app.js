'use strict';
const $ = s => document.querySelector(s);
const $$ = s => Array.from(document.querySelectorAll(s));
let draftText = '';
let toastHandle;
const pages = {overview:'Tổng quan', assistant:'RAG Assistant', support:'Support Ticket Triage', agent:'Agent Workbench', campaign:'Campaign Studio', quality:'Quality & Evaluation'};
function toast(msg){const el=$('#toast');el.textContent=msg;el.classList.add('visible');clearTimeout(toastHandle);toastHandle=setTimeout(()=>el.classList.remove('visible'),4200)}
function showPage(page){if(!pages[page]) return;$$('.page').forEach(el=>el.classList.toggle('hidden',el.id!=='page-'+page));$$('.nav').forEach(el=>el.classList.toggle('active',el.dataset.page===page));$('#crumb').textContent=pages[page];history.replaceState(null,'','#'+page);if(page==='quality')loadMetrics();window.scrollTo({top:0,behavior:'smooth'})}
$$('.nav').forEach(el=>el.addEventListener('click',()=>showPage(el.dataset.page)));
$$('.jump').forEach(el=>el.addEventListener('click',()=>showPage(el.dataset.to)));
if(pages[location.hash.slice(1)])showPage(location.hash.slice(1));
async function api(path,options={}){const res=await fetch(path,{headers:{'Content-Type':'application/json'},...options});let data;try{data=await res.json()}catch{throw new Error('Không đọc được dữ liệu API')}if(!res.ok)throw new Error(typeof data.detail==='string'?data.detail:`HTTP ${res.status}`);return data}
const fmt=n=>new Intl.NumberFormat('vi-VN').format(n);
async function init(){try{const [health,products]=await Promise.all([api('/api/health'),api('/api/products')]);$('#status-dot').classList.add('connected');$('#backend-status').textContent='Local API online';$('#stat-docs').textContent=fmt(health.documents);$('#stat-mode').textContent=health.llm_provider==='ollama'?'Ollama configured':'Extractive demo';$('#stat-embedding').textContent=`Retriever: ${health.embedding_provider==='ollama'?'Ollama configured (check index)':'Lexical BM25'}`;$('#chat-mode').textContent=`${health.llm_provider==='ollama'?'LLM: Ollama':'LLM: OFF'} · ${health.embedding_provider==='ollama'?'Vector + BM25':'BM25'}`;const select=$('#product');select.replaceChildren();for(const p of products){const o=document.createElement('option');o.value=p.id;o.textContent=p.title;select.appendChild(o)}await loadMetrics()}catch(e){$('#backend-status').textContent='API offline';toast('Không kết nối được backend: '+e.message)}}
async function loadMetrics(){try{const m=await api('/api/metrics');$('#stat-calls').textContent=fmt(m.calls);$('#stat-latency').textContent=Math.round(m.avg_ms)+' ms';$('#metric-calls').textContent=fmt(m.calls);$('#metric-latency').textContent=Math.round(m.avg_ms)+' ms';$('#metric-in').textContent=fmt(m.tokens_in);$('#metric-out').textContent=fmt(m.tokens_out)}catch(e){toast(e.message)}}
function elem(tag,klass,text){const el=document.createElement(tag);if(klass)el.className=klass;if(text!==undefined)el.textContent=text;return el}
function message(role,text){const wrap=elem('div','msg '+role);wrap.append(elem('div','avatar',role==='user'?'●':'✳'));wrap.append(elem('div','bubble',text));$('#messages').appendChild(wrap);$('#messages').scrollTop=$('#messages').scrollHeight;return wrap}
function renderSources(items){const el=$('#sources');el.replaceChildren();$('#source-count').textContent=`${items.length} nguồn`;if(!items.length){el.append(elem('div','sources-empty','Không có tài liệu phù hợp.'));return}items.forEach((s,i)=>{const card=elem('div','source');const top=elem('div','source-top');top.append(elem('strong',null,'['+s.id+']'));top.append(elem('span',null,'rank '+(i+1)));card.append(top,elem('h4',null,s.title),elem('p',null,s.content.slice(0,260)+(s.content.length>260?'…':'')));el.append(card)})}
async function ask(q){q=q.trim();if(q.length<3)return;message('user',q);const pending=message('assistant','Đang tìm tài liệu…');$('#question').value='';$('#chat-form button').disabled=true;try{const d=await api('/api/chat',{method:'POST',body:JSON.stringify({question:q})});pending.querySelector('.bubble').textContent=d.answer;renderSources(d.sources);$('#diag-mode').textContent=d.mode;$('#diag-search').textContent=d.retrieval_mode;$('#diag-latency').textContent=d.latency_ms+' ms';$('#diag-in').textContent=fmt(d.tokens_in);$('#diag-out').textContent=fmt(d.tokens_out);$('#diag-note').textContent=d.token_note;loadMetrics()}catch(e){pending.querySelector('.bubble').textContent='Có lỗi: '+e.message;toast(e.message)}finally{$('#chat-form button').disabled=false;$('#question').focus()}}
$('#chat-form').addEventListener('submit',e=>{e.preventDefault();ask($('#question').value)});
$$('.prompt').forEach(btn=>btn.addEventListener('click',()=>{showPage('assistant');ask(btn.textContent)}));
$('#campaign-form').addEventListener('submit',async e=>{e.preventDefault();const btn=$('#generate');btn.disabled=true;btn.textContent='Đang xây dựng bản nháp…';try{const d=await api('/api/campaign',{method:'POST',body:JSON.stringify({sku:$('#product').value,audience:$('#audience').value})});const out=$('#campaign-output');out.replaceChildren();out.append(elem('span','eyebrow dark','DRAFT PREVIEW'),elem('h2','draft-title',d.headline),elem('p','draft-body',d.body),elem('span','draft-cta',d.cta),elem('div','draft-note',d.disclaimer));$('#draft-status').textContent='Human approval required';$('#campaign-meta').textContent=`${d.mode} · ${d.latency_ms} ms · source ${d.product_source}`;draftText=`${d.headline}\n\n${d.body}\n\n${d.cta}\n\n[Chưa duyệt — không phát hành]`;$('#copy-draft').disabled=false;loadMetrics()}catch(err){toast(err.message)}finally{btn.disabled=false;btn.innerHTML='Tạo bản nháp nội dung <span>✦</span>'}});
$('#copy-draft').addEventListener('click',async()=>{try{await navigator.clipboard.writeText(draftText);toast('Đã sao chép bản nháp')}catch{toast('Không sao chép được. Hãy chọn nội dung thủ công.')}});
$('#run-eval').addEventListener('click',async()=>{const btn=$('#run-eval');btn.disabled=true;btn.textContent='Đang đánh giá…';try{const d=await api('/api/evaluation');$('#eval-score').textContent=Math.round(d.score*100)+'%';$('#case-count').textContent=`${d.passed}/${d.total} đạt`;$('#negative-metric').textContent=`Ngoài phạm vi: ${d.negative_rejection.passed}/${d.negative_rejection.total} từ chối đúng`;const tbody=$('#cases');tbody.replaceChildren();d.cases.forEach(c=>{const tr=document.createElement('tr');tr.append(elem('td',null,c.question),elem('td',null,c.expected_source),elem('td',null,c.found.join(', ')||'—'),elem('td',c.hit?'pass':'fail',c.hit?'PASS':'REVIEW'));tbody.append(tr)});toast('Đã kiểm tra '+d.total+' câu hỏi. Đây chỉ là retrieval Hit@3.')}catch(e){toast(e.message)}finally{btn.disabled=false;btn.textContent='Chạy lại bộ đánh giá →'}});
init();

$('#agent-form').addEventListener('submit',async e=>{e.preventDefault();const btn=$('#run-agent');btn.disabled=true;btn.textContent='Đang chạy mô hình…';try{const d=await api('/api/agent',{method:'POST',body:JSON.stringify({task:$('#agent-task').value})});$('#agent-status').textContent=d.mode;const out=$('#agent-output');out.replaceChildren();out.append(elem('h3','agent-answer-title','Agent response'),elem('p','agent-answer',d.answer));if(d.steps.length){out.append(elem('h4','trace-title','Tool trace'));d.steps.forEach(s=>{const step=elem('div','trace-item');step.append(elem('strong',null,`${s.step}. ${s.tool}`),elem('pre',null,JSON.stringify(s.result,null,2)));out.append(step)})}out.append(elem('div','draft-note',`Review required · ${d.latency_ms} ms · ${d.tokens_in+d.tokens_out} model tokens`));loadMetrics();if(d.mode==='agent_disabled')toast('Chưa bật Ollama nên agent thật chưa thể chạy. Xem README mục 3.')}catch(err){toast(err.message)}finally{btn.disabled=false;btn.textContent='Chạy agent (cần Ollama) →'}});

// Business workflow demo: only factual routing & evidence supplied by the API.
$('#support-form').addEventListener('submit',async e=>{
  e.preventDefault();const btn=$('#triage-button');const output=$('#support-output');
  btn.disabled=true;btn.textContent='Đang phân tích…';
  try{
    const data=await api('/api/support/triage',{method:'POST',body:JSON.stringify({message:$('#support-message').value})});
    $('#support-state').textContent=data.status;
    output.replaceChildren();
    const detail=elem('div','routing-grid');
    for(const [label,value] of [['Intent',data.intent],['Priority',data.priority],['Assigned team',data.assigned_team],['Retriever',data.retrieval_mode]]){
      const item=elem('div','routing-field');item.append(elem('small',null,label),elem('strong',null,value));detail.append(item);
    }
    output.append(detail,elem('h3','agent-answer-title','Draft reply — needs human review'),elem('p','agent-answer',data.draft_reply));
    const sourceHead=elem('h4','trace-title','Evidence');output.append(sourceHead);
    if(!data.evidence.length)output.append(elem('p','muted','Không tìm thấy tài liệu liên quan; phải chuyển nhân viên xử lý.'));
    for(const evidence of data.evidence){const card=elem('div','trace-item');card.append(elem('strong',null,'['+evidence.id+'] '+evidence.title),elem('p','agent-answer',evidence.excerpt));output.append(card)}
    output.append(elem('div','draft-note','Không có hành động tự động · yêu cầu con người kiểm duyệt · '+data.latency_ms+' ms'));
    loadMetrics();
  }catch(error){toast(error.message);output.replaceChildren(elem('p','muted','Không xử lý được yêu cầu: '+error.message));}
  finally{btn.disabled=false;btn.innerHTML='Phân tích và định tuyến <span>→</span>';}
});
