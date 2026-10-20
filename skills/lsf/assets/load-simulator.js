/* load-simulator:begin */
(function(root){
"use strict";
function validate(m){
 if(!m||!Array.isArray(m.nodes)||!Array.isArray(m.edges)||!m.nodes.length||m.nodes.length>40||m.edges.length>120){throw Error("Use 1–40 services and at most 120 paths.");}
 var ids=new Set();
 m.nodes.forEach(function(n){if(!n||typeof n.id!=="string"||!n.id||ids.has(n.id)||!Number.isFinite(n.capacity_rps)||n.capacity_rps<0){throw Error("Services need unique string ids and nonnegative finite capacity_rps.");}ids.add(n.id);});
 if(!ids.has(m.entry)){throw Error("entry must identify a service.");}
 var degree=Object.create(null),next=Object.create(null);ids.forEach(function(id){degree[id]=0;next[id]=[];});
 m.edges.forEach(function(e){if(!e||!ids.has(e.from)||!ids.has(e.to)||!Number.isFinite(e.factor)||e.factor<0||e.factor>100){throw Error("Each path needs known endpoints and a factor from 0 to 100 (calls per upstream request).");}degree[e.to]++;next[e.from].push(e.to);});
 var queue=Array.from(ids).filter(function(id){return degree[id]===0;}),order=[];
 while(queue.length){var id=queue.shift();order.push(id);next[id].forEach(function(to){if(--degree[to]===0){queue.push(to);}});}
 if(order.length!==m.nodes.length){throw Error("Cycles need a bounded retry/visit factor or an unrolled topology; cyclic graphs are not supported.");}
 return order;
}
function simulate(m,users,rate,burst,failed){
 var order=validate(m);
 [users,rate,burst].forEach(function(v){if(!Number.isFinite(v)||v<0||v>1e9){throw Error("Users, requests/user/s and burst must be finite, nonnegative, and at most 1 billion.");}});
 failed=new Set(failed||[]);
 var visits=Object.create(null),affected=Object.create(null),incoming=Object.create(null),rows=Object.create(null),limit=Infinity,critical=null;
 m.nodes.forEach(function(n){visits[n.id]=0;affected[n.id]=false;incoming[n.id]=[];});visits[m.entry]=1;
 m.edges.forEach(function(e){incoming[e.to].push(e);});
 order.forEach(function(id){
  incoming[id].forEach(function(e){visits[id]+=visits[e.from]*e.factor;if(e.factor>0&&affected[e.from]){affected[id]=true;}});
  var n=m.nodes.find(function(x){return x.id===id;}),demand=visits[id]*users*rate*burst,cap=failed.has(id)?0:n.capacity_rps;
  if(!Number.isFinite(demand)||!Number.isFinite(visits[id])){throw Error("Demand overflow; reduce fan-out or traffic assumptions.");}
  var saturated=demand>0&&demand>=cap;
  if(visits[id]>0&&rate*burst>0){var supported=cap/(visits[id]*rate*burst);if(supported<limit){limit=supported;critical=id;}}
  rows[id]={id:id,label:n.label||id,demand:demand,capacity:cap,utilization:cap>0?demand/cap:null,failed:failed.has(id),saturated:saturated,affected:affected[id],visits:visits[id],source:n.source||"Assumed capacity; not measured"};
  affected[id]=affected[id]||saturated||failed.has(id);
 });
 return {nodes:m.nodes.map(function(n){return rows[n.id];}),edges:m.edges.map(function(e){return {from:e.from,to:e.to,factor:e.factor,demand:rows[e.from].demand*e.factor,affected:e.factor>0&&affected[e.from]};}),order:order,maxUsers:Number.isFinite(limit)?limit:null,bottleneck:critical};
}
var EXAMPLE={title:"Illustrative web service — replace with this repo's topology",entry:"gateway",nodes:[{id:"gateway",label:"API gateway",capacity_rps:12000},{id:"api",label:"Application API",capacity_rps:4000},{id:"cache",label:"Cache",capacity_rps:20000},{id:"db",label:"Database",capacity_rps:800},{id:"queue",label:"Work queue",capacity_rps:2000},{id:"worker",label:"Workers",capacity_rps:300},{id:"provider",label:"External provider",capacity_rps:100}],edges:[{from:"gateway",to:"api",factor:1},{from:"api",to:"cache",factor:0.8},{from:"cache",to:"db",factor:0.1},{from:"api",to:"db",factor:0.2},{from:"api",to:"queue",factor:0.1},{from:"queue",to:"worker",factor:1},{from:"worker",to:"provider",factor:0.5}]};
var scenarios=new Map();
function render(model,key){
 var example=!model,initial=model||EXAMPLE,signature=key+JSON.stringify(initial),state=scenarios.get(signature);
 if(!state){state={model:initial,users:1000,rate:0.2,burst:1,failed:[]};scenarios.set(signature,state);}
 function el(tag,text,attrs){var n=document.createElement(tag);if(text!==null&&text!==undefined){n.textContent=text;}Object.keys(attrs||{}).forEach(function(k){n.setAttribute(k,attrs[k]);});return n;}
 var wrap=el("section"),title=el("h2","System design · Load simulator");wrap.appendChild(title);
 wrap.appendChild(el("p","SIMULATED ESTIMATES ONLY · Pure browser arithmetic. No traffic is sent to services. No external calls or infrastructure is created.",{class:"chip v-wait"}));
 wrap.appendChild(el("p",example?"Illustrative example, not a discovered architecture for this repo. Add docs/load-model.json to use your system graph.":"Repository topology: docs/load-model.json. Capacities and routing factors are assumptions unless their sources provide measurements.",{class:"mute"}));
 var controls=el("div",null,{class:"row",style:"gap:1.2rem;align-items:center"}),output=el("div"),error=el("p",null,{role:"alert",class:"err"});wrap.appendChild(controls);wrap.appendChild(error);
 function input(label,key,min,max,step,type){var l=el("label",label+" ",{style:"display:flex;gap:.6rem;align-items:center"}),i=el("input",null,{type:type||"number",min:min,max:max,step:step,value:state[key],"aria-label":label}),v=el("span",String(state[key]));i.addEventListener("input",function(){state[key]=Number(i.value);v.textContent=i.value;draw();});l.appendChild(i);if(type==="range"){l.appendChild(v);}controls.appendChild(l);}
 input("Active users","users",0,100000,100,"range");input("Requests / user / second","rate",0,10000,0.01);input("Burst multiplier","burst",0,1000,0.1);
 var failures=el("details"),summary=el("summary","Simulate service outages"),checks=el("div",null,{class:"row"});failures.appendChild(summary);failures.appendChild(checks);wrap.appendChild(failures);
 function failureControls(){checks.textContent="";state.model.nodes.forEach(function(n){var l=el("label",n.label||n.id),c=el("input",null,{type:"checkbox","aria-label":"Fail "+n.id});c.checked=state.failed.indexOf(n.id)>=0;c.addEventListener("change",function(){state.failed=state.failed.filter(function(id){return id!==n.id;});if(c.checked){state.failed.push(n.id);}draw();});l.prepend(c);checks.appendChild(l);});}
 wrap.appendChild(output);
 var edit=el("details"),json=el("textarea",JSON.stringify(state.model,null,2),{rows:14,style:"width:100%;font-family:monospace","aria-label":"Topology JSON"}),apply=el("button","Apply topology",{type:"button"});
 edit.appendChild(el("summary","Topology and capacity assumptions"));edit.appendChild(el("p","Each edge factor is downstream calls per upstream request: cache miss 10% = 0.1; fan-out to three shards = 3. Parallel edges and converging paths add demand. Model retries with a bounded factor; cycles are rejected. Set capacity_rps per component and source to the evidence or assumption. No latency or correctness guarantee is inferred."));edit.appendChild(json);edit.appendChild(apply);wrap.appendChild(edit);
 apply.addEventListener("click",function(){try{var m=JSON.parse(json.value);validate(m);state.model=m;state.failed=[];failureControls();draw();}catch(e){error.textContent=e.message;}});
 wrap.appendChild(el("p","Model limits: steady-state offered demand, linear fan-out, fixed capacities. Edge rates show demand assuming upstream work can proceed, not achieved throughput. Red means at/over assumed capacity or unavailable; amber means ≥80% capacity or dependent on an overloaded path. Downstream impact is a warning, not a prediction of exact failures. Queues, backpressure, autoscaling, latency distributions and recovery are not simulated.",{class:"small mute"}));
 function fmt(v){return Number.isFinite(v)?v.toLocaleString(undefined,{maximumFractionDigits:1}):"—";}
 function draw(){
  output.textContent="";error.textContent="";var result;
  try{result=simulate(state.model,state.users,state.rate,state.burst,state.failed);}catch(e){error.textContent=e.message;return;}
  output.appendChild(el("h3",String(state.model.title||"System topology")));
  output.appendChild(el("p","Offered entry load: "+fmt(state.users*state.rate*state.burst)+" req/s · First capacity constraint: "+(result.bottleneck||"none at this request rate")+" · Estimated user ceiling: "+(result.maxUsers===null?"not applicable":fmt(result.maxUsers))));
  var ns=["http:","","www.w3.org","2000","svg"].join("/"),svg=document.createElementNS(ns,"svg"),layers=Object.create(null),positions=Object.create(null),counts={};
  result.order.forEach(function(id){var parents=state.model.edges.filter(function(e){return e.to===id;});layers[id]=parents.length?Math.max.apply(null,parents.map(function(e){return layers[e.from]+1;})):0;counts[layers[id]]=(counts[layers[id]]||0)+1;});
  var depth=Math.max.apply(null,Object.values(layers))+1,height=Math.max.apply(null,Object.values(counts))*125+120,width=depth*250+40,used={};
  svg.setAttribute("viewBox","0 0 "+width+" "+height);svg.setAttribute("role","img");svg.setAttribute("aria-label","System topology with simulated request rates and capacity warnings");svg.style.cssText="width:100%;min-width:850px;max-height:650px";
  function shape(tag,attrs,text){var e=document.createElementNS(ns,tag);Object.keys(attrs).forEach(function(k){e.setAttribute(k,attrs[k]);});if(text!==undefined){e.textContent=text;}svg.appendChild(e);return e;}
  result.order.forEach(function(id){var layer=layers[id],index=used[layer]||0;used[layer]=index+1;positions[id]={x:20+layer*250,y:60+index*125};});
  result.edges.forEach(function(e,index){var a=positions[e.from],b=positions[e.to],color=e.affected?"#f59e0b":"#64748b";var far=b.x-a.x>260,route=Math.min(a.y,b.y)-22-(index%2)*12;
   var path=far?"M "+(a.x+190)+" "+a.y+" L "+(a.x+215)+" "+route+" L "+(b.x-15)+" "+route+" L "+(b.x+10)+" "+b.y:"M "+(a.x+200)+" "+(a.y+36)+" C "+(a.x+225)+" "+(a.y+36)+", "+(b.x-25)+" "+(b.y+36)+", "+b.x+" "+(b.y+36);
   shape("path",{d:path,fill:"none",stroke:color,"stroke-width":2});shape("text",{x:(a.x+200+b.x)/2,y:far?route-5:(a.y+b.y)/2+25,fill:color,"font-size":10,"text-anchor":"middle"},fmt(e.demand)+"/s →");});
  result.nodes.forEach(function(n){var p=positions[n.id],color=n.failed||n.saturated?"#f87171":n.affected||n.utilization>=0.8?"#fbbf24":"#34d399";shape("rect",{x:p.x,y:p.y,width:200,height:78,rx:10,fill:"#151d2b",stroke:color,"stroke-width":2});shape("text",{x:p.x+10,y:p.y+21,fill:"#e2e8f0","font-size":13},String(n.label).slice(0,25));shape("text",{x:p.x+10,y:p.y+42,fill:color,"font-size":12},fmt(n.demand)+" / "+fmt(n.capacity)+" req/s");shape("text",{x:p.x+10,y:p.y+62,fill:color,"font-size":11},n.failed?"UNAVAILABLE":n.saturated?"CAPACITY EXCEEDED":n.affected?"UPSTREAM AT RISK":fmt((n.utilization||0)*100)+"% utilization");});
  var graph=el("div",null,{style:"overflow-x:auto"});graph.appendChild(svg);output.appendChild(graph);
  var table=el("table",null,{style:"width:100%;border-spacing:10px;text-align:left"}),head=el("tr");["Service","Demand req/s","Capacity req/s","Utilization","Capacity basis"].forEach(function(s){head.appendChild(el("th",s));});table.appendChild(head);
  result.nodes.forEach(function(n){var row=el("tr");[n.label,fmt(n.demand),fmt(n.capacity),n.utilization===null?"unavailable":fmt(n.utilization*100)+"%",n.source].forEach(function(v){row.appendChild(el("td",String(v)));});table.appendChild(row);});output.appendChild(table);
 }
 failureControls();draw();return wrap;
}
var api={validate:validate,simulate:simulate,example:EXAMPLE,render:render};
if(typeof module!=="undefined"&&module.exports){module.exports=api;}else{root.LSFLoad=api;}
})(typeof window!=="undefined"?window:globalThis);
/* load-simulator:end */
