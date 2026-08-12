# ruff: noqa: E501

RUNTIME_DASHBOARD = """<!doctype html>
<html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>DGX MoA Runtime</title><style>
:root{color-scheme:dark;--bg:#070a12;--card:#111827;--line:#293248;--text:#eef2ff;
--muted:#98a2b8;--accent:#83a3ff;--ok:#54deb0;--bad:#ff7892}*{box-sizing:border-box}
body{margin:0;background:radial-gradient(circle at 15% 0,#332767,transparent 35%),var(--bg);
color:var(--text);font:14px/1.45 system-ui,sans-serif}main{max-width:1500px;margin:auto;padding:24px}
header,.nav,.lanes{display:flex;gap:10px}header{align-items:center;justify-content:space-between}
h1{margin:0;font-size:28px}.muted{color:var(--muted)}button,input{border:1px solid var(--line);
border-radius:10px;padding:10px 12px;background:#0b1020;color:var(--text)}button{cursor:pointer}
.nav{margin:20px 0;overflow:auto}.nav button:first-child{border-color:var(--accent)}
.card{border:1px solid var(--line);border-radius:18px;background:#111827d9;padding:18px}
#login{max-width:600px;margin:12vh auto}.lanes{overflow:auto}.lane{min-width:150px;flex:1;min-height:220px;
border:1px solid var(--line);border-radius:12px;padding:10px;background:#ffffff05}.lane h2{font-size:12px;
letter-spacing:.08em;color:var(--muted)}.node{margin:8px 0;padding:8px;border-left:3px solid var(--accent);
background:#ffffff08;word-break:break-word}.timeline{margin-top:16px;max-height:42vh;overflow:auto}
.event{display:grid;grid-template-columns:180px 190px 1fr;gap:10px;padding:8px;border-bottom:1px solid var(--line)}
.ok{color:var(--ok)}.bad{color:var(--bad)}@media(max-width:700px){main{padding:12px}.event{grid-template-columns:1fr}}
</style><main><section id="login" class="card"><h1>DGX MoA Runtime</h1>
<p class="muted">API key를 1일 HttpOnly dashboard session으로 교환합니다.</p><form id="login-form">
<input id="token" type="password" autocomplete="off" size="48" placeholder="API key" required>
<button>연결</button></form><p id="login-state" class="bad"></p></section><div id="app" hidden>
<header><div><h1>Dynamic MoA</h1><span id="identity" class="muted"></span></div>
<div><span id="socket" class="muted">연결 중</span> <button id="logout">로그아웃</button></div></header>
<nav class="nav"><button data-view="live">LIVE</button><button data-view="requests">REQUESTS</button>
<button data-view="models">MODELS</button><button data-view="system">SYSTEM</button>
<button data-view="incidents">INCIDENTS</button><button data-view="evaluation">EVALUATION</button>
<button data-view="audit">AUDIT</button></nav>
<section class="card"><div class="lanes" id="lanes"></div>
<div class="timeline" id="timeline" aria-live="polite"></div></section></div></main><script>
const $=id=>document.getElementById(id),roles=["Reasoner","Planner","Frontier A","Executor","Tools","Reviewer","Judge","Frontier B"];
let socket,retry=1000,lastSeq=0;const api=async(path,options={})=>{const response=await fetch(path,{...options,
headers:{"Content-Type":"application/json",...(options.headers||{})}});if(!response.ok)throw new Error(
(await response.json()).error?.message||response.statusText);return response.status===204?null:response.json()};
const build=()=>{$("lanes").replaceChildren();roles.forEach(role=>{const lane=document.createElement("div");
lane.className="lane";lane.dataset.role=role.toLowerCase();const title=document.createElement("h2");
title.textContent=role;lane.append(title);$("lanes").append(lane)})};
const graphRole=node=>{const type=(node.node_type||"").toUpperCase();if(type==="FRONTIER_B")return"Frontier B";
if(type==="FRONTIER_A")return"Frontier A";if(["TOOL","TEST"].includes(type))return"Tools";
return roles.find(role=>type.includes(role.toUpperCase().split(" ")[0]))||"Executor"};
const laneFor=role=>[...$("lanes").children].find(item=>item.dataset.role===role.toLowerCase());
const renderGraph=event=>{const payload=event.payload||{};if(event.event_type==="graph_saved"){
(payload.nodes||[]).forEach(node=>{const lane=laneFor(graphRole(node));if(!lane)return;const card=document.createElement("div");
card.className="node";card.dataset.nodeId=node.node_id;const outgoing=(payload.edges||[]).filter(edge=>edge.from_node===node.node_id);
card.textContent=[node.node_id,node.node_type,node.provider,node.parallel_group_id,outgoing.map(edge=>edge.edge_type+"→"+edge.to_node).join(",")].filter(Boolean).join(" · ");lane.append(card)})}
if(event.event_type==="node_attempt"){const card=document.querySelector('[data-node-id="'+payload.node_id+'"]');
if(card)card.textContent=[payload.node_id,payload.node_type,payload.state,payload.provider,payload.latency_ms==null?null:payload.latency_ms+"ms"].filter(value=>value!=null).join(" · ")}
if(event.event_type==="graph_checkpoint")Object.entries(payload.node_states||{}).forEach(([id,state])=>{const card=document.querySelector('[data-node-id="'+id+'"]');if(card)card.dataset.state=state})};
const roleFor=event=>{const text=(event.payload?.role||event.payload?.node_type||event.event_type||"").toLowerCase();
return roles.find(role=>text.includes(role.toLowerCase().split(" ")[0]))||"Executor"};
const render=event=>{if(!["runtime_event","execution_graph"].includes(event.type))return;if(event.gap){const gap=document.createElement("p");
gap.className="bad";gap.textContent="이전 live event 일부가 bounded queue에서 생략되었습니다.";$("timeline").prepend(gap)}
if(event.seq)lastSeq=Math.max(lastSeq,event.seq);
const row=document.createElement("div");row.className="event";[event.created_at,event.event_type,
JSON.stringify(event.payload||{})].forEach(text=>{const item=document.createElement("span");item.textContent=text||"";row.append(item)});
$("timeline").prepend(row);if(event.type==="execution_graph"){renderGraph(event);return}const lane=laneFor(roleFor(event));
if(lane){const node=document.createElement("div");node.className="node";node.textContent=event.event_type;
lane.append(node);while(lane.children.length>7)lane.children[1].remove()}};
const showView=async view=>{[...document.querySelectorAll(".nav button")].forEach(button=>
button.style.borderColor=button.dataset.view===view?"var(--accent)":"var(--line)");
$("lanes").hidden=view!=="live";$("timeline").replaceChildren();if(view==="live")return;
const title=document.createElement("h2");title.textContent=view.toUpperCase();$("timeline").append(title);
if(view==="requests"){const data=await api("/v1/dashboard/requests");const pre=document.createElement("pre");
pre.textContent=JSON.stringify(data,null,2);$("timeline").append(pre)}else{const note=document.createElement("p");
note.className="muted";note.textContent="이 화면은 persisted ExecutionGraph와 검증 artifact projection으로 채워집니다.";
$("timeline").append(note)}};
const loadSnapshot=async()=>{const snapshot=await api("/v1/dashboard/snapshot");if(snapshot.scope!=="private")return;
snapshot.execution_graphs.forEach(item=>{const graph=item.graph||{};render({type:"execution_graph",event_type:"graph_saved",
created_at:graph.created_at,payload:graph});(item.attempts||[]).forEach(attempt=>render({type:"execution_graph",
event_type:"node_attempt",created_at:attempt.ended_at||attempt.started_at,payload:attempt}));if(item.checkpoint)
render({type:"execution_graph",event_type:"graph_checkpoint",created_at:item.checkpoint.created_at,payload:item.checkpoint})})};
const connect=()=>{const replay=lastSeq?"?last_seq="+lastSeq:"";socket=new WebSocket((location.protocol==="https:"?"wss://":"ws://")+location.host+"/v1/dashboard/live"+replay);
socket.onopen=()=>{$("socket").textContent="LIVE";$("socket").className="ok";retry=1000};
socket.onmessage=async message=>{const event=JSON.parse(message.data);if(event.type==="RESYNC_REQUIRED"){
lastSeq=0;await loadSnapshot();return}render(event)};socket.onclose=()=>{$("socket").textContent="재연결 중";
$("socket").className="bad";setTimeout(connect,retry);retry=Math.min(retry*2,10000)}};
async function load(){const me=await api("/v1/dashboard/me");$("identity").textContent=me.api_key_id+(me.operator?" · operator aggregate":" · private scope");
$("login").hidden=true;$("app").hidden=false;build();await loadSnapshot();connect()}
$("login-form").onsubmit=async event=>{event.preventDefault();try{await api("/v1/dashboard/session",{method:"POST",
headers:{Authorization:"Bearer "+$("token").value}});$("token").value="";await load()}catch(error){$("login-state").textContent=error.message}};
$("logout").onclick=async()=>{if(socket)socket.close();await api("/v1/dashboard/session",{method:"DELETE"});location.reload()};
document.querySelectorAll(".nav button").forEach(button=>button.onclick=()=>showView(button.dataset.view));
load().catch(()=>$("login").hidden=false);
</script></html>"""
