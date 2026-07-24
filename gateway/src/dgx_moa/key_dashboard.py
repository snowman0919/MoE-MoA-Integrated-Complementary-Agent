# ruff: noqa: E501

API_KEY_DASHBOARD = """<!doctype html>
<html lang="ko">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MoA API Keys</title>
<style>
:root{color-scheme:dark;--bg:#070a12;--glass:#111827b8;--glass-strong:#172033db;
--line:#ffffff17;--line-strong:#ffffff29;--text:#f7f8ff;--muted:#98a2b8;
--accent:#7c9cff;--accent-2:#9e73ff;--ok:#5ee6b5;--bad:#ff7892;--warn:#ffc66d}
*{box-sizing:border-box}[hidden]{display:none!important}html,body{overflow-x:hidden}
body{min-height:100vh;margin:0;color:var(--text);
font:14px/1.45 Inter,ui-sans-serif,system-ui,sans-serif;background:
radial-gradient(circle at 15% -5%,#41347b70 0,transparent 34%),
radial-gradient(circle at 88% 8%,#174c7770 0,transparent 30%),var(--bg)}
body:before{content:"";position:fixed;inset:0;pointer-events:none;opacity:.18;
background-image:linear-gradient(#fff1 1px,transparent 1px),linear-gradient(90deg,#fff1 1px,transparent 1px);
background-size:42px 42px;mask-image:linear-gradient(to bottom,#000,transparent 75%)}
main{position:relative;max-width:1440px;margin:auto;padding:clamp(20px,4vw,56px)}
a{color:#b7c8ff;text-decoration:none}.topbar,.section-head,.content-actions{display:flex;
align-items:center;justify-content:space-between;gap:16px}.topbar{margin-bottom:24px}.back{display:inline-flex;
align-items:center;justify-content:center;width:42px;height:42px;border:1px solid var(--line);
border-radius:14px;background:#ffffff0b}.brand{flex:1}.eyebrow{margin:0;color:#91a2c6;
font-size:11px;font-weight:750;letter-spacing:.16em;text-transform:uppercase}h1{margin:2px 0 0;
font-size:clamp(26px,3vw,38px);letter-spacing:-.04em}h2{margin:0;font-size:16px;letter-spacing:-.01em}
.muted{color:var(--muted)}#content{display:grid;min-width:0;gap:18px}.content-actions{justify-content:flex-end}
.card{padding:clamp(18px,2.4vw,28px);border:1px solid var(--line);border-radius:22px;
background:linear-gradient(145deg,#ffffff10,#ffffff05),var(--glass);box-shadow:0 18px 55px #0007;
backdrop-filter:blur(22px);-webkit-backdrop-filter:blur(22px);min-width:0}
input,select,button{min-height:42px;border:1px solid var(--line);border-radius:12px;padding:10px 13px;
background:#090e1bd9;color:var(--text);font:inherit;outline:none;transition:.18s ease;min-width:0;
max-width:100%}
input:focus,select:focus,button:focus-visible{border-color:#89a5ff;box-shadow:0 0 0 3px #7898ff2d}
button{cursor:pointer}button:hover{transform:translateY(-1px);border-color:var(--line-strong)}
button.primary{border:0;background:linear-gradient(135deg,var(--accent),var(--accent-2));
color:#090b15;font-weight:750;box-shadow:0 9px 24px #725fff38}button.danger{color:var(--bad)}
form{margin:0}.form-grid{display:grid;grid-template-columns:minmax(170px,1.2fr) repeat(4,minmax(120px,1fr)) auto;
gap:10px;align-items:end}.form-grid .section-head{grid-column:1/-1;margin-bottom:8px}
.field{display:grid;min-width:0;gap:6px}.field span{color:var(--muted);font-size:12px}
#secret{grid-column:1/-1;min-height:20px;color:var(--ok)}.keys{padding:0;overflow:hidden}
.keys .section-head{padding:22px 24px 10px}.table-wrap{overflow:auto}table{width:100%;border-collapse:collapse;
min-width:1050px}th,td{padding:14px 12px;border-bottom:1px solid var(--line);text-align:left;
white-space:nowrap}th{color:var(--muted);font-size:11px;letter-spacing:.08em;text-transform:uppercase}
tbody tr{transition:.15s}tbody tr:hover{background:#ffffff09}.status-active{color:var(--ok)}
.status-expired,.status-revoked{color:var(--bad)}.key-value{display:flex;align-items:center;gap:6px}
.key-value code{display:inline-block;max-width:300px;overflow:hidden;text-overflow:ellipsis;color:#cbd6f2}
.key-value button,td button{min-height:34px;padding:6px 9px;border-radius:9px}.toolbar{display:flex;
align-items:end;gap:10px;flex-wrap:wrap}.toolbar .section-head{margin-right:auto}.kpis{display:grid;
grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:18px 0}.kpi{padding:16px;border:1px solid var(--line);
border-radius:17px;background:#ffffff08}.kpi span{display:block;color:var(--muted);font-size:12px}
.kpi strong{display:block;margin-top:6px;font-size:25px;letter-spacing:-.04em}.kpi.fallback strong{color:var(--warn)}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}.chart{display:grid;gap:11px;
margin-top:18px}.bar-row{display:grid;grid-template-columns:minmax(115px,170px) 1fr auto;gap:10px;
align-items:center}.bar-row>span:first-child{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
color:#cad3e7}.track{height:10px;background:#060913;border:1px solid #ffffff0d;border-radius:99px;
overflow:hidden}.bar{height:100%;background:linear-gradient(90deg,var(--accent),var(--accent-2));
border-radius:99px}.bar-row>span:last-child{min-width:42px;text-align:right;font-variant-numeric:tabular-nums}
.stacked-wrap{margin-top:16px;overflow-x:auto}.stacked-plot{height:310px;min-width:760px;padding:10px 8px 0;
display:grid;grid-auto-flow:column;grid-auto-columns:minmax(18px,1fr);gap:5px;align-items:end;
background:repeating-linear-gradient(to top,transparent 0,transparent 59px,#ffffff10 60px)}
.stacked-column{height:100%;display:flex;flex-direction:column;justify-content:flex-end;gap:7px}
.stack{display:flex;flex-direction:column-reverse;min-height:1px;border-radius:6px 6px 2px 2px;overflow:hidden}
.segment{min-height:2px;border-top:1px solid #ffffff24;transition:filter .15s}.segment:hover{filter:brightness(1.3)}
.day-label{font-size:10px;color:var(--muted);text-align:center;white-space:nowrap}.legend{display:flex;
gap:10px 16px;flex-wrap:wrap;margin-top:16px}.legend-item{display:flex;align-items:center;gap:7px;
color:#cbd3e8;font-size:12px}.swatch{width:10px;height:10px;border-radius:3px}
.model-strip{display:flex;gap:8px;flex-wrap:wrap}.model-strip span{padding:8px 11px;border:1px solid var(--line);
border-radius:99px;background:#ffffff07;color:#cbd3e8}#frontier-output{white-space:pre-wrap;word-break:break-word;
color:var(--muted);max-height:180px;overflow:auto}.tooltip{position:fixed;z-index:30;max-width:280px;
padding:10px 12px;border:1px solid var(--line-strong);border-radius:12px;background:#090e19ee;
box-shadow:0 12px 34px #000b;white-space:pre-line;pointer-events:none;transform:translate(12px,12px)}
@media(max-width:980px){.form-grid{grid-template-columns:repeat(2,minmax(0,1fr))}
.form-grid button{grid-column:1/-1}.kpis{grid-template-columns:repeat(2,1fr)}}
@media(max-width:700px){main{padding:18px}.grid{grid-template-columns:1fr}.card{border-radius:18px}
.form-grid{grid-template-columns:1fr}.kpis{grid-template-columns:1fr 1fr}.toolbar{align-items:stretch}
.toolbar .section-head,.toolbar .field{width:100%}.toolbar input,.toolbar select,.toolbar button{width:100%}
.bar-row{grid-template-columns:105px 1fr 42px}}
</style>
<main>
  <header class="topbar">
    <a class="back" href="/admin" aria-label="관리 화면으로 돌아가기">←</a>
    <div class="brand"><p class="eyebrow">MoA Control</p><h1>API Keys</h1></div>
  </header>
  <section class="card" id="login">
    <form id="login-form" class="toolbar"><input id="token" type="password" autocomplete="off"
      placeholder="Operator API key" size="48" required><button class="primary">로그인</button>
      <span id="auth-state" class="muted"></span></form>
  </section>
  <div id="content" hidden>
    <div class="content-actions"><button id="logout" class="danger">로그아웃</button></div>
    <form id="create-form" class="card form-grid">
      <div class="section-head"><h2>새 키</h2></div>
      <label class="field"><span>이름</span><input id="name" pattern="[a-z][a-z0-9_-]{0,31}"
        placeholder="key-name" autocapitalize="none" spellcheck="false" required></label>
      <label class="field"><span>권한</span><select id="kind"><option value="general">일반</option>
        <option value="admin">관리자</option></select></label>
      <label class="field"><span>유효일</span><input id="days" type="number" min="1" max="365"
        value="90" required></label>
      <label class="field"><span>요청 한도</span><input id="request-limit" type="number" min="1"
        placeholder="무제한"></label>
      <label class="field"><span>토큰 한도</span><input id="token-limit" type="number" min="1"
        placeholder="무제한"></label>
      <button class="primary">생성</button>
      <span id="secret"></span>
    </form>
    <section class="card keys"><div class="section-head"><h2>키</h2></div><div class="table-wrap"><table>
      <thead><tr><th>이름</th><th>권한</th><th>API key 원문</th><th>상태</th><th>만료</th>
      <th>요청/한도</th><th>토큰/한도</th><th>관리</th></tr></thead>
      <tbody id="keys"></tbody></table></div></section>
    <section class="card">
      <form id="graph-filter" class="toolbar">
        <div class="section-head"><h2>사용량</h2></div>
        <label class="field"><span>키</span><select id="graph-key"></select></label>
        <label class="field"><span>시작</span><input id="graph-start" type="date" required></label>
        <label class="field"><span>종료</span><input id="graph-end" type="date" required></label>
        <button class="primary">조회</button>
      </form>
      <div class="kpis">
        <div class="kpi"><span>요청</span><strong id="kpi-requests">0</strong></div>
        <div class="kpi"><span>토큰</span><strong id="kpi-tokens">0</strong></div>
        <div class="kpi fallback"><span>Fallback</span><strong id="kpi-fallback">0%</strong></div>
        <div class="kpi"><span>실패</span><strong id="kpi-failed">0</strong></div>
      </div>
      <div class="section-head"><h2>일일 토큰</h2><span id="token-summary" class="muted"></span></div>
      <div class="stacked-wrap"><div id="daily-models" class="stacked-plot"></div></div>
      <div id="model-legend" class="legend"></div>
    </section>
    <div class="grid">
      <section class="card"><h2>작업 · 요청 모델</h2><div id="tasks" class="chart"></div></section>
      <section class="card"><h2>실제 역할 · 모델 호출</h2><div id="models" class="chart"></div></section>
      <section class="card"><h2>Fallback 경로</h2><div id="fallbacks" class="chart"></div></section>
      <section class="card"><h2>일별 요청량</h2><div id="daily" class="chart"></div></section>
    </div>
    <section class="card"><div class="section-head"><h2>모델</h2>
      <div id="model-catalog" class="model-strip"></div></div></section>
    <section class="card" id="frontier-card" hidden>
      <div class="section-head"><h2>Frontier OAuth</h2><a href="https://auth.openai.com/codex/device"
        target="_blank" rel="noopener noreferrer">인증 열기 ↗</a></div>
      <div id="frontier-auth" class="chart"></div><pre id="frontier-output"></pre>
    </section>
  </div>
</main>
<div id="tooltip" class="tooltip" hidden></div>
<script>
const $=id=>document.getElementById(id);
const fmtTime=value=>value?new Date(value*1000).toLocaleString():"없음";
const optional=id=>$(id).value?Number($(id).value):null;
let modelCatalog=new Map();
const modelNames=new Map([["dgx-moa-executor","Qwen3-Next"],
  ["dgx-moa-planner","Nemotron-30B"],["dgx-moa-reviewer","North-Mini-30B"]]);
const modelLabel=model=>modelNames.get(model)||model;
const reasonNames=new Map([["local_busy","로컬 Busy"],["local_context_exceeded","컨텍스트 초과"],
  ["executor_remote","Executor 원격"],["remote_faster","원격 우선"],
  ["local_readiness_race","준비 상태 변경"],["provider_failed","Provider 실패"]]);
const reasonLabel=reason=>reasonNames.get(reason)||String(reason||"원격 전환").replaceAll("_"," ");
const tooltip=$("tooltip");
const moveTip=event=>{tooltip.style.left=Math.min(event.clientX,innerWidth-300)+"px";
  tooltip.style.top=Math.min(event.clientY,innerHeight-150)+"px"};
const tip=(node,text)=>{
  const show=event=>{tooltip.textContent=text;tooltip.hidden=false;
    if(event.clientX!==undefined)moveTip(event);else{const box=node.getBoundingClientRect();
      tooltip.style.left=box.left+"px";tooltip.style.top=box.bottom+"px"}};
  node.tabIndex=0;node.setAttribute("aria-label",text.replaceAll("\\n",", "));
  node.onpointerenter=show;node.onpointermove=moveTip;node.onpointerleave=()=>tooltip.hidden=true;
  node.onfocus=show;node.onblur=()=>tooltip.hidden=true};
const api=async(path,options={})=>{
  const response=await fetch(path,{...options,headers:{
    "Content-Type":"application/json",...(options.headers||{})}});
  if(!response.ok){const text=await response.text();let payload={};
    try{payload=JSON.parse(text)}catch{}
    throw new Error(payload.detail||payload.error?.message||
      response.status+" "+response.statusText)}
  return response.status===204?null:response.json();
};
const cell=(row,text,cls="")=>{const value=document.createElement("td");value.textContent=text;
  value.className=cls;row.append(value)};
const copy=async text=>{
  if(navigator.clipboard)await navigator.clipboard.writeText(text);
  else{const area=document.createElement("textarea");area.value=text;document.body.append(area);
    area.select();document.execCommand("copy");area.remove()}
};
const keyCell=(row,key)=>{
  const cell=document.createElement("td");const wrap=document.createElement("div");
  wrap.className="key-value";const value=document.createElement("code");value.textContent=key.masked_key;
  const reveal=document.createElement("button");reveal.textContent="👁";reveal.ariaLabel="키 원문 보기";
  let visible=false,raw="";const getRaw=async()=>raw||(raw=(await api(
    "/v1/admin/api-keys/"+key.name+"/reveal")).api_key);
  reveal.onclick=async()=>{visible=!visible;value.textContent=visible?await getRaw():key.masked_key;
    reveal.ariaLabel=visible?"키 숨기기":"키 원문 보기"};
  const copier=document.createElement("button");copier.textContent="복사";copier.onclick=async()=>{
    await copy(await getRaw());copier.textContent="복사됨";setTimeout(()=>copier.textContent="복사",1200)};
  wrap.append(value,reveal,copier);cell.append(wrap);row.append(cell);
};
const bars=(id,rows,label,value,details)=>{
  const root=$(id);root.replaceChildren();const max=Math.max(1,...rows.map(value));
  rows.slice(0,14).forEach(item=>{const line=document.createElement("div");line.className="bar-row";
    const title=document.createElement("span");title.textContent=label(item);
    const track=document.createElement("div");track.className="track";const bar=document.createElement("div");
    bar.className="bar";bar.style.width=(value(item)/max*100)+"%";track.append(bar);
    const count=document.createElement("span");count.textContent=value(item).toLocaleString();
    line.append(title,track,count);tip(line,details(item));root.append(line)});
};
const palette=["#7f8c3a","#70508e","#9a5e4d","#397c8f","#a37a2c","#4f75a8","#8d456f","#4f8b62"];
const stacked=(rows,start,end)=>{
  const root=$("daily-models"),legend=$("model-legend");root.replaceChildren();legend.replaceChildren();
  const models=[...new Set(rows.map(item=>item.model))];
  const modelTotals=new Map(models.map(model=>[model,rows.filter(item=>item.model===model)
    .reduce((sum,item)=>sum+item.total_tokens,0)]));
  const total=[...modelTotals.values()].reduce((sum,value)=>sum+value,0);
  $("token-summary").textContent="선택 기간 합계 "+total.toLocaleString()+" tokens";
  models.forEach((model,index)=>{const item=document.createElement("span");item.className="legend-item";
    const swatch=document.createElement("span");swatch.className="swatch";
    swatch.style.backgroundColor=palette[index%palette.length];
    item.append(swatch,modelLabel(model)+" · "+modelTotals.get(model).toLocaleString()+" tokens");
    legend.append(item)});
  const values=new Map(rows.map(item=>[item.day+"\\0"+item.model,item]));
  const days=[];for(let day=new Date(start+"T00:00:00Z"),last=new Date(end+"T00:00:00Z");
    day<=last;day.setUTCDate(day.getUTCDate()+1))days.push(day.toISOString().slice(0,10));
  const totals=days.map(day=>models.reduce((sum,model)=>
    sum+(values.get(day+"\\0"+model)?.total_tokens||0),0));const max=Math.max(1,...totals);
  days.forEach((day,dayIndex)=>{const column=document.createElement("div");column.className="stacked-column";
    const stack=document.createElement("div");stack.className="stack";
    stack.style.height=(totals[dayIndex]/max*260)+"px";
    models.forEach((model,index)=>{const data=values.get(day+"\\0"+model);if(!data)return;
      const segment=document.createElement("div");segment.className="segment";
      segment.style.height=(data.total_tokens/Math.max(1,totals[dayIndex])*100)+"%";
      segment.style.backgroundColor=palette[index%palette.length];
      tip(segment,day+"\\n"+modelLabel(model)+"\\n입력 "+data.prompt_tokens.toLocaleString()+
        " · 출력 "+data.completion_tokens.toLocaleString()+"\\n정확한 토큰 "+
        data.total_tokens.toLocaleString()+" · 호출 "+data.invocations.toLocaleString()+"회");
      stack.append(segment)});
    const label=document.createElement("span");label.className="day-label";label.textContent=day.slice(5);
    column.append(stack,label);root.append(column)});
};
async function load(){
  const data=await api("/v1/admin/api-keys");$("content").hidden=false;$("login").hidden=true;
  modelCatalog=new Map(data.model_catalog.map(item=>[item.served_name,item.repository]));
  $("model-catalog").replaceChildren();
  data.model_catalog.forEach(item=>{const line=document.createElement("span");
    line.textContent=modelLabel(item.served_name);
    tip(line,item.served_name+"\\n"+item.repository);$("model-catalog").append(line)});
  const usage=new Map(data.usage.summary.map(item=>[item.name,item]));$("keys").replaceChildren();
  const selected=$("graph-key").value;$("graph-key").replaceChildren();
  data.keys.forEach(key=>{const row=document.createElement("tr");const stats=usage.get(key.name)||{};
    cell(row,key.name);cell(row,key.kind);keyCell(row,key);cell(row,key.status,"status-"+key.status);
    cell(row,fmtTime(key.expires_at));cell(row,(stats.requests||0)+"/"+(key.request_limit||"∞"));
    cell(row,(stats.total_tokens||0).toLocaleString()+"/"+(key.token_limit||"∞"));
    const actions=document.createElement("td");
    const available=key.status==="revoked"
      ?(key.source==="managed"?[["삭제","delete","danger"]]:[]):[
        ["회전","rotate",""],["한도","update",""],["폐기","revoke","danger"]];
    available.unshift(["그래프","graph",""]);
    for(const [title,action,cls] of available){
      const button=document.createElement("button");button.textContent=title;button.className=cls;
      button.onclick=()=>action==="graph"?selectGraph(key.name):change(key,action);
      actions.append(button)}row.append(actions);$("keys").append(row);
    const option=document.createElement("option");option.value=key.name;option.textContent=key.name;
    $("graph-key").append(option)});
  $("graph-key").value=selected&&data.keys.some(key=>key.name===selected)?selected:data.keys[0]?.name||"";
  await loadFrontierAuth();
  await loadCharts();
}
async function loadCharts(){
  const query=new URLSearchParams({start:$("graph-start").value,end:$("graph-end").value});
  const data=await api("/v1/admin/api-keys/"+$("graph-key").value+"/usage?"+query);
  const summary=data.summary[0]||{},fallback=data.fallback_summary[0]||{};
  $("kpi-requests").textContent=(summary.requests||0).toLocaleString();
  $("kpi-tokens").textContent=(summary.total_tokens||0).toLocaleString();
  $("kpi-fallback").textContent=(fallback.rate||0).toFixed(1)+"%";
  $("kpi-failed").textContent=(summary.failed||0).toLocaleString();
  bars("tasks",data.tasks,item=>item.request_class+" · "+item.model_alias,item=>item.requests,
    item=>"요청 "+item.requests.toLocaleString()+"회\\n토큰 "+item.total_tokens.toLocaleString());
  bars("models",data.models,item=>item.role+" · "+modelLabel(item.model),item=>item.invocations,
    item=>modelLabel(item.model)+"\\n"+item.provider+" · "+item.invocations.toLocaleString()+
      "회\\n토큰 "+item.total_tokens.toLocaleString());
  bars("fallbacks",data.fallbacks,item=>item.role+" · "+reasonLabel(item.reason),
    item=>item.invocations,item=>modelLabel(item.model)+"\\n"+reasonLabel(item.reason)+" · "+
      item.provider+"\\n"+item.invocations.toLocaleString()+"회 · 토큰 "+
      item.total_tokens.toLocaleString());
  bars("daily",data.daily,item=>item.day,item=>item.requests,
    item=>item.day+"\\n요청 "+item.requests.toLocaleString()+"회");
  stacked(data.daily_models,$("graph-start").value,$("graph-end").value);
}
async function loadFrontierAuth(){
  const data=await api("/v1/admin/frontier-auth");
  $("frontier-card").hidden=!data.enabled;
  if(!data.enabled)return;
  $("frontier-auth").replaceChildren();
  data.profiles.forEach(profile=>{const line=document.createElement("div");
    const state=document.createElement("span");state.textContent=profile.profile+" · "+
      (profile.authenticated==="yes"?"자격증명 저장됨 (유효성 미검증)":"인증 필요");
    const button=document.createElement("button");button.textContent="재인증";
    button.onclick=()=>startFrontierAuth(profile.profile,button);
    line.append(state,button);$("frontier-auth").append(line)});
}
async function startFrontierAuth(profile,button){
  button.disabled=true;$("frontier-output").textContent="인증 요청을 시작합니다...\\n";
  try{const response=await fetch("/v1/admin/frontier-auth/"+profile,{method:"POST"});
    if(!response.ok)throw new Error(response.status+" "+response.statusText);
    const reader=response.body.getReader(),decoder=new TextDecoder();
    for(;;){const {done,value}=await reader.read();if(done)break;
      $("frontier-output").textContent+=decoder.decode(value,{stream:true});
      $("frontier-output").scrollTop=$("frontier-output").scrollHeight}
    await loadFrontierAuth()}
  catch(error){$("frontier-output").textContent+=error.message}
  finally{button.disabled=false}
}
async function selectGraph(name){$("graph-key").value=name;await loadCharts();
  $("graph-filter").scrollIntoView({behavior:"smooth"})}
async function change(key,action){
  if(action==="revoke"&&!confirm(key.name+" 키를 폐기할까요?"))return;
  if(action==="delete"&&!confirm(key.name+" 키를 영구 삭제할까요? 사용 기록은 유지됩니다."))return;
  try{let body;
    if(action==="rotate")body={name:key.name,kind:key.kind,expires_in_days:Number($("days").value),
      request_limit:key.request_limit,token_limit:key.token_limit};
    if(action==="update"){const requests=prompt("새 요청 한도",key.request_limit||"");
      const tokens=prompt("새 토큰 한도",key.token_limit||"");
      if(requests===null||tokens===null)return;
      body={request_limit:requests?Number(requests):null,
        token_limit:tokens?Number(tokens):null}};
    const path=action==="delete"?"/v1/admin/api-keys/"+key.name:
      "/v1/admin/api-keys/"+key.name+"/"+action;
    const result=await api(path,
      {method:action==="delete"?"DELETE":"POST",body:body?JSON.stringify(body):undefined});
    $("secret").textContent=result&&result.api_key?"키가 회전되었습니다. 목록에서 확인하세요.":"";
    await load()}
  catch(error){alert(error.message)}
}
$("login-form").onsubmit=async event=>{event.preventDefault();
  try{const token=$("token").value;await api("/v1/admin/session",
    {method:"POST",headers:{"Authorization":"Bearer "+token}});$("token").value="";await load()}
  catch(error){$("auth-state").textContent=error.message}};
$("create-form").onsubmit=async event=>{event.preventDefault();try{
  const result=await api("/v1/admin/api-keys",{method:"POST",body:JSON.stringify({
    name:$("name").value.trim().toLowerCase(),kind:$("kind").value,
    expires_in_days:Number($("days").value),
    request_limit:optional("request-limit"),token_limit:optional("token-limit")})});
  $("secret").textContent="키가 생성되었습니다. 목록에서 확인하세요.";
  $("name").value="";await load()}
  catch(error){alert(error.message)}};
$("name").oninput=event=>event.target.value=event.target.value.toLowerCase();
$("graph-filter").onsubmit=async event=>{event.preventDefault();try{await loadCharts()}
  catch(error){alert(error.message)}};
$("logout").onclick=async()=>{await api("/v1/admin/session",{method:"DELETE"});
  $("content").hidden=true;$("login").hidden=false};
const localDate=date=>new Date(date-date.getTimezoneOffset()*60000)
  .toISOString().slice(0,10);
const today=new Date();const start=new Date(today);start.setDate(start.getDate()-29);
$("graph-start").value=localDate(start);$("graph-end").value=localDate(today);
load().catch(()=>$("login").hidden=false);
</script>
</html>"""
