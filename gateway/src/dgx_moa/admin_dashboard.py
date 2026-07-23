# ruff: noqa: E501

ADMIN_DASHBOARD = """<!doctype html>
<html lang="ko">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MoA Admin</title>
<style>
:root{color-scheme:dark;--bg:#0b1020;--card:#151c31;--line:#29334f;--text:#edf2ff;
--muted:#98a5c5;--accent:#70a5ff;--ok:#55d6a5;--bad:#ff718c}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);
font:14px system-ui,sans-serif}main{max-width:1100px;margin:auto;padding:28px}
h1{margin:0 0 6px;font-size:26px}h2{font-size:16px}.muted{color:var(--muted)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px}
a{color:var(--accent)}input,select,textarea,button{border:1px solid var(--line);border-radius:8px;
padding:9px 11px;background:#0e1528;color:var(--text)}button{cursor:pointer}
button.primary{background:var(--accent);color:#071022}form{display:flex;gap:8px;flex-wrap:wrap}
textarea{width:100%;min-height:90px;resize:vertical}.chat{margin-top:16px}.messages{min-height:260px;
max-height:540px;overflow:auto;display:grid;gap:10px;margin:14px 0}.message{white-space:pre-wrap;
word-break:break-word;border-radius:10px;padding:11px}.user{background:#20304f}.assistant{background:#12283a}
.event{color:var(--muted);font:12px ui-monospace,monospace}.usage{color:var(--ok)}
#workspace{min-width:270px}.composer{display:grid;grid-template-columns:1fr auto;gap:8px}
@media(max-width:600px){main{padding:16px}.composer{grid-template-columns:1fr}}
</style>
<main>
  <h1>MoA Admin</h1>
  <p class="muted">관리 라우팅 · 채팅 · 제한된 Codex 작업</p>
  <section class="card" id="login">
    <h2>Operator 인증</h2>
    <form id="login-form"><input id="token" type="password" autocomplete="off"
      placeholder="operator API key" size="48" required><button class="primary">연결</button></form>
    <span id="auth-state" class="muted">30일 HttpOnly 세션으로 교환됩니다.</span>
  </section>
  <div id="content" hidden>
    <div class="grid">
      <section class="card"><h2>API Key Control</h2>
        <p class="muted">키·한도·사용량·Frontier OAuth를 관리합니다.</p>
        <a href="/admin/api-keys">키 대시보드 열기</a></section>
      <section class="card"><h2>Runtime</h2>
        <p class="muted">인증된 런타임 상태 JSON을 확인합니다.</p>
        <button id="runtime">상태 조회</button></section>
    </div>
    <section class="card chat">
      <h2>Codex CLI · DGX MoA custom provider</h2>
      <form id="mode-form">
        <label>모드 <select id="mode"><option value="chat">채팅 · 읽기 전용</option>
          <option value="agent">에이전트 작업 · workspace-write</option></select></label>
        <label id="workspace-label" hidden>작업 폴더
          <select id="workspace"></select></label>
        <button id="new-session" type="button">새 대화</button>
      </form>
      <div id="messages" class="messages"></div>
      <form id="composer" class="composer">
        <textarea id="prompt" maxlength="20000" placeholder="메시지 또는 작업을 입력하세요."
          required></textarea>
        <button class="primary" id="send">전송</button>
      </form>
      <p id="codex-state" class="muted">독립된 Codex CLI 세션을 사용합니다.</p>
    </section>
    <button id="logout">로그아웃</button>
  </div>
</main>
<script>
const $=id=>document.getElementById(id);
let sessionId=null,busy=false;
const api=async(path,options={})=>{
  const response=await fetch(path,{...options,headers:{"Content-Type":"application/json",
    ...(options.headers||{})}});
  if(!response.ok){const text=await response.text();let payload={};
    try{payload=JSON.parse(text)}catch{}throw new Error(payload.detail||payload.error?.message||
      response.status+" "+response.statusText)}
  return response.status===204?null:response.json();
};
const addMessage=(text,kind)=>{const item=document.createElement("div");
  item.className="message "+kind;item.textContent=text;$("messages").append(item);
  $("messages").scrollTop=$("messages").scrollHeight;return item};
async function load(){
  const data=await api("/v1/admin/codex/workspaces");
  $("login").hidden=true;$("content").hidden=false;$("workspace").replaceChildren();
  data.workspaces.forEach(name=>{const option=document.createElement("option");
    option.value=name;option.textContent=name;$("workspace").append(option)});
}
function reset(){sessionId=null;$("messages").replaceChildren();
  $("codex-state").textContent="새 독립 Codex CLI 세션입니다."}
function render(event,assistant){
  if(event.type==="thread.started")sessionId=event.thread_id;
  if(event.type==="message"){assistant.textContent+=event.text;
    $("messages").scrollTop=$("messages").scrollHeight}
  if(event.type==="command")addMessage("$ "+event.command+" · "+event.status,"event");
  if(event.type==="file_change")addMessage("파일 변경 · "+event.status,"event");
  if(event.type==="turn.completed")$("codex-state").textContent="완료 · input "+
    (event.usage.input_tokens||0).toLocaleString()+" / output "+
    (event.usage.output_tokens||0).toLocaleString()+" tokens";
  if(event.type==="error")addMessage(event.message,"event");
}
async function send(event){
  event.preventDefault();if(busy)return;busy=true;$("send").disabled=true;
  const prompt=$("prompt").value.trim();if(!prompt){busy=false;$("send").disabled=false;return}
  addMessage(prompt,"user");const assistant=addMessage("","assistant");$("prompt").value="";
  $("codex-state").textContent="Codex CLI 실행 중...";
  try{const response=await fetch("/v1/admin/codex",{method:"POST",
    headers:{"Content-Type":"application/json"},body:JSON.stringify({prompt,session_id:sessionId,
      mode:$("mode").value,workspace:$("mode").value==="agent"?$("workspace").value:""})});
    if(!response.ok){const text=await response.text();let payload={};
      try{payload=JSON.parse(text)}catch{}throw new Error(payload.detail||response.statusText)}
    const reader=response.body.getReader(),decoder=new TextDecoder();let buffer="";
    for(;;){const {done,value}=await reader.read();buffer+=decoder.decode(value||new Uint8Array(),
      {stream:!done});const lines=buffer.split("\\n");buffer=lines.pop();
      lines.filter(Boolean).forEach(line=>render(JSON.parse(line),assistant));if(done)break}}
  catch(error){addMessage(error.message,"event");$("codex-state").textContent="실패"}
  finally{busy=false;$("send").disabled=false}
}
$("login-form").onsubmit=async event=>{event.preventDefault();try{
  await api("/v1/admin/session",{method:"POST",headers:{"Authorization":"Bearer "+$("token").value}});
  $("token").value="";await load()}catch(error){$("auth-state").textContent=error.message}};
$("mode").onchange=()=>{$("workspace-label").hidden=$("mode").value!=="agent";reset()};
$("workspace").onchange=reset;$("new-session").onclick=reset;$("composer").onsubmit=send;
$("runtime").onclick=async()=>addMessage(JSON.stringify(
  await api("/v1/admin/runtime-status"),null,2),"event");
$("logout").onclick=async()=>{await api("/v1/admin/session",{method:"DELETE"});
  $("content").hidden=true;$("login").hidden=false;reset()};
load().catch(()=>$("login").hidden=false);
</script>
</html>"""
