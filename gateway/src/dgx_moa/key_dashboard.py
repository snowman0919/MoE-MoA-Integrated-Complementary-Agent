# ruff: noqa: E501

API_KEY_DASHBOARD = """<!doctype html>
<html lang="ko">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MoA API Keys</title>
<style>
:root{color-scheme:dark;--bg:#0b1020;--card:#151c31;--line:#29334f;--text:#edf2ff;
--muted:#98a5c5;--accent:#70a5ff;--ok:#55d6a5;--bad:#ff718c}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);
font:14px system-ui,sans-serif}main{max-width:1200px;margin:auto;padding:28px}
h1{margin:0 0 6px;font-size:26px}h2{font-size:16px}.muted{color:var(--muted)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px}
input,select,button{border:1px solid var(--line);border-radius:8px;padding:9px 11px;background:#0e1528;
color:var(--text)}button{cursor:pointer}button.primary{background:var(--accent);color:#071022}
button.danger{color:var(--bad)}form{display:flex;gap:8px;flex-wrap:wrap;margin:14px 0}
table{width:100%;border-collapse:collapse}th,td{padding:10px 7px;border-bottom:1px solid var(--line);
text-align:left}.status-active{color:var(--ok)}.status-expired,.status-revoked{color:var(--bad)}
.key-value{display:flex;align-items:center;gap:5px}.key-value code{min-width:245px}
.chart{display:grid;gap:9px}.bar-row{display:grid;grid-template-columns:145px 1fr 55px;gap:8px;
align-items:center}.track{height:12px;background:#0b1020;border-radius:8px;overflow:hidden}
.bar{height:100%;background:linear-gradient(90deg,var(--accent),#8d7dff);border-radius:8px}
#secret{word-break:break-all;color:var(--ok)}@media(max-width:600px){main{padding:16px}
.bar-row{grid-template-columns:100px 1fr 42px}.keys{overflow:auto}}
</style>
<main>
  <h1>API Key Control</h1>
  <p class="muted">Tailnet operator console · 원문은 눈동자 버튼을 누를 때만 표시됩니다.</p>
  <section class="card" id="login">
    <h2>Operator 인증</h2>
    <form id="login-form"><input id="token" type="password" autocomplete="off"
      placeholder="operator API key" size="48" required><button class="primary">연결</button></form>
    <span id="auth-state" class="muted">키는 브라우저 저장소에 보관하지 않습니다.</span>
  </section>
  <div id="content" hidden>
    <button id="logout" class="danger">로그아웃</button>
    <form id="create-form" class="card">
      <input id="name" pattern="[a-z][a-z0-9_-]{0,31}" placeholder="key-name"
        autocapitalize="none" spellcheck="false" required>
      <select id="kind"><option value="general">일반</option><option value="admin">관리자</option></select>
      <input id="days" type="number" min="1" max="365" value="90" required>
      <input id="request-limit" type="number" min="1" placeholder="요청 한도 (공란=무제한)">
      <input id="token-limit" type="number" min="1" placeholder="토큰 한도 (공란=무제한)">
      <button class="primary">새 키 생성</button>
      <span id="secret"></span>
    </form>
    <section class="card keys"><h2>키 상태와 사용량</h2><table>
      <thead><tr><th>이름</th><th>권한</th><th>API key 원문</th><th>상태</th><th>만료</th>
      <th>요청/한도</th><th>토큰/한도</th><th>관리</th></tr></thead>
      <tbody id="keys"></tbody></table></section>
    <form id="graph-filter" class="card">
      <label>키 <select id="graph-key"></select></label>
      <label>시작 <input id="graph-start" type="date" required></label>
      <label>종료 <input id="graph-end" type="date" required></label>
      <button class="primary">그래프 조회</button>
    </form>
    <div class="grid" style="margin-top:16px">
      <section class="card"><h2>작업 · 요청 모델</h2><div id="tasks" class="chart"></div></section>
      <section class="card"><h2>실제 역할 · 모델 호출</h2><div id="models" class="chart"></div></section>
      <section class="card"><h2>일별 요청량</h2><div id="daily" class="chart"></div></section>
    </div>
  </div>
</main>
<script>
const $=id=>document.getElementById(id);
const fmtTime=value=>value?new Date(value*1000).toLocaleString():"없음";
const optional=id=>$(id).value?Number($(id).value):null;
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
const bars=(id,rows,label,value)=>{
  const root=$(id);root.replaceChildren();const max=Math.max(1,...rows.map(value));
  rows.slice(0,14).forEach(item=>{const line=document.createElement("div");line.className="bar-row";
    const title=document.createElement("span");title.textContent=label(item);title.title=title.textContent;
    const track=document.createElement("div");track.className="track";const bar=document.createElement("div");
    bar.className="bar";bar.style.width=(value(item)/max*100)+"%";track.append(bar);
    const count=document.createElement("span");count.textContent=value(item).toLocaleString();
    line.append(title,track,count);root.append(line)});
};
async function load(){
  const data=await api("/v1/admin/api-keys");$("content").hidden=false;$("login").hidden=true;
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
  await loadCharts();
}
async function loadCharts(){
  const query=new URLSearchParams({start:$("graph-start").value,end:$("graph-end").value});
  const data=await api("/v1/admin/api-keys/"+$("graph-key").value+"/usage?"+query);
  bars("tasks",data.tasks,item=>item.request_class+" · "+item.model_alias,item=>item.requests);
  bars("models",data.models,item=>item.role+" · "+item.model,item=>item.invocations);
  bars("daily",data.daily,item=>item.day,item=>item.requests);
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
