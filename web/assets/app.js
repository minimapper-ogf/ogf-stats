(function(){
'use strict';
var META=window.OGF_META||{version:'',history:[]};
var OGF=window.OGF={meta:META};
OGF.esc=function(s){return String(s==null?'':s).replace(/[&<>"']/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]})};
OGF.num=function(n){return(Number(n)||0).toLocaleString('en-US')};
OGF.getJSON=function(u){return fetch(u,{cache:'no-store'}).then(function(r){if(!r.ok)throw new Error(u+' '+r.status);return r.json()})};
OGF.ago=function(iso){var m=Math.round((Date.now()-Date.parse(iso))/60000);if(isNaN(m))return'unknown';if(m<1)return'just now';if(m<60)return m+' min ago';if(m<1440)return Math.round(m/60)+' h ago';return Math.round(m/1440)+' d ago'};
OGF.userLink=function(uid,name){return uid&&uid!=='unknown'?'<a class="ulink" href="/users/'+encodeURIComponent(uid)+'.html">'+OGF.esc(name)+'</a>':OGF.esc(name)};
OGF.seg=function(el,cb){el.addEventListener('click',function(e){var b=e.target.closest('button');if(!b)return;el.querySelectorAll('button').forEach(function(x){x.classList.toggle('on',x===b)});cb(b.dataset.v)})};
OGF.bar=function(v,max){return'<div class="bar">'+OGF.num(v)+'<i style="width:'+(max?Math.max(2,100*v/max):0)+'%"></i></div>'};

// table with sortable columns: opt={columns:[{key,label,num,render,sort}],rows,sort:{key,dir}}
OGF.table=function(host,opt){
  var cols=opt.columns,rows=opt.rows,sort=opt.sort;
  function val(c,r){return c.sort?c.sort(r):r[c.key]}
  function draw(){
    var list=rows.slice();
    if(sort){var c=cols.filter(function(c){return c.key===sort.key})[0];list.sort(function(a,b){var x=val(c,a),y=val(c,b);return(typeof x==='number'&&typeof y==='number'?x-y:String(x).localeCompare(String(y)))*sort.dir})}
    host.innerHTML='<div class="tbl-wrap"><table class="tbl"><thead><tr>'+cols.map(function(c){return'<th data-k="'+c.key+'" class="'+(c.num?'num ':'')+(c.nosort?'':'sortable ')+(sort&&sort.key===c.key?(sort.dir>0?'asc':'desc'):'')+'">'+c.label+'</th>'}).join('')+'</tr></thead><tbody>'+
      (list.length?list.map(function(r,i){return'<tr>'+cols.map(function(c){return'<td class="'+(c.num?'num':'')+(c.key==='_rank'?' rk':'')+'">'+(c.render?c.render(r,i):OGF.esc(r[c.key]))+'</td>'}).join('')+'</tr>'}).join(''):'<tr><td class="empty" colspan="'+cols.length+'">'+(opt.empty||'No activity yet')+'</td></tr>')+'</tbody></table></div>';
    host.querySelectorAll('th.sortable').forEach(function(th){th.onclick=function(){var k=th.dataset.k,c=cols.filter(function(c){return c.key===k})[0];sort=sort&&sort.key===k?{key:k,dir:-sort.dir}:{key:k,dir:c.num?-1:1};draw()}});
  }
  draw();
};

// ---- theme
function cssv(n){return getComputedStyle(document.documentElement).getPropertyValue(n).trim()}
OGF.palette=['#14b8a6','#6366f1','#f59e0b','#ef4444','#a855f7','#0ea5e9','#ec4899','#84cc16','#f97316','#64748b'];
function chartTheme(){
  var t=cssv('--muted'),g=cssv('--border'),s=cssv('--surface'),x=cssv('--text');
  var ax={labels:{style:{color:t}},lineColor:g,tickColor:g,gridLineColor:g,title:{style:{color:t}}};
  return{colors:OGF.palette,chart:{backgroundColor:'transparent',style:{fontFamily:'inherit'}},title:{text:''},credits:{enabled:false},
    xAxis:ax,yAxis:ax,legend:{itemStyle:{color:x},itemHoverStyle:{color:cssv('--accent')},itemHiddenStyle:{color:t}},
    tooltip:{backgroundColor:s,borderColor:g,style:{color:x},shadow:false,borderRadius:8},
    plotOptions:{series:{borderWidth:0,animation:false},column:{borderRadius:3},pie:{borderColor:s}}};
}
OGF.refreshCharts=function(){
  if(!window.Highcharts)return;var o=chartTheme();Highcharts.setOptions(o);
  Highcharts.charts.forEach(function(c){if(!c)return;var u={chart:o.chart,legend:o.legend,tooltip:o.tooltip};
    if(c.xAxis&&c.xAxis.length)u.xAxis=o.xAxis;if(c.yAxis&&c.yAxis.length)u.yAxis=o.yAxis;c.update(u,true)});
};
function isDark(){var t=document.documentElement.dataset.theme;return t?t==='dark':matchMedia('(prefers-color-scheme: dark)').matches}
if(window.Highcharts){Highcharts.setOptions({lang:{thousandsSep:','}});OGF.refreshCharts()}
matchMedia('(prefers-color-scheme: dark)').addEventListener('change',function(){OGF.refreshCharts()});

// ---- analytics
(function(){var s=document.createElement('script');s.async=true;s.src='https://www.googletagmanager.com/gtag/js?id=G-7BV9Y2QVPZ';document.head.appendChild(s);
window.dataLayer=window.dataLayer||[];window.gtag=function(){dataLayer.push(arguments)};gtag('js',new Date());gtag('config','G-7BV9Y2QVPZ')})();

// ---- header + search
document.addEventListener('DOMContentLoaded',function(){
  var page=document.body.dataset.page||'';
  var links=[['charts','/index.html','Charts'],['leaderboards','/leaderboards.html','Leaderboards'],['territory','/territory.html','Territory Stats'],['version','/version.html','v'+META.version]];
  var h=document.createElement('header');h.className='site-header';
  h.innerHTML='<div class="hdr-inner"><a class="brand" href="/index.html"><img src="/assets/favicon.svg" alt="">OGF<b>Stats</b></a><nav class="nav-links">'+
    links.map(function(l){return'<a href="'+l[1]+'"'+(l[0]===page?' class="active"':'')+'>'+l[2]+'</a>'}).join('')+
    '</nav><div class="hdr-tools"><div class="search"><input id="siteSearch" placeholder="Search users…  ( / )" autocomplete="off" aria-label="Search users"><div class="suggest" id="suggest"></div></div><button class="icon-btn" id="themeBtn" title="Toggle theme" aria-label="Toggle theme"></button></div></div>';
  document.body.prepend(h);
  var f=document.createElement('div');f.className='footer';f.textContent='OGFStats v'+META.version+' by minimapper :)';document.body.appendChild(f);

  var tb=document.getElementById('themeBtn');function icon(){tb.textContent=isDark()?'☀':'☾'}icon();
  tb.onclick=function(){var d=isDark()?'light':'dark';document.documentElement.dataset.theme=d;try{localStorage.setItem('ogf-theme',d)}catch(e){}icon();OGF.refreshCharts()};

  var input=document.getElementById('siteSearch'),box=document.getElementById('suggest'),idx=null,res=[],act=-1;
  function load(){if(idx)return Promise.resolve(idx);return fetch('/users/index.json').then(function(r){return r.ok?r.json():[]}).catch(function(){return[]}).then(function(a){return idx=a})}
  function go(u){location.href='/users/'+encodeURIComponent(u.uid)+'.html'}
  function show(){box.innerHTML=res.map(function(u,i){return'<div class="'+(i===act?'on':'')+'" data-i="'+i+'"><span>'+OGF.esc(u.user)+'</span><small>#'+OGF.esc(u.uid)+'</small></div>'}).join('');box.style.display=res.length?'block':'none'}
  input.addEventListener('input',function(){var q=input.value.trim().toLowerCase();if(!q){res=[];show();return}
    load().then(function(a){res=a.filter(function(u){return(u.user||'').toLowerCase().indexOf(q)>-1}).sort(function(x,y){var a=(x.user||'').toLowerCase(),b=(y.user||'').toLowerCase();return(b.indexOf(q)===0)-(a.indexOf(q)===0)||a.localeCompare(b)}).slice(0,8);act=-1;show()})});
  input.addEventListener('keydown',function(e){
    if(e.key==='ArrowDown'){act=Math.min(act+1,res.length-1);show();e.preventDefault()}
    else if(e.key==='ArrowUp'){act=Math.max(act-1,0);show();e.preventDefault()}
    else if(e.key==='Enter'&&res.length){go(res[act>=0?act:0])}
    else if(e.key==='Escape'){box.style.display='none'}});
  box.addEventListener('click',function(e){var d=e.target.closest('[data-i]');if(d)go(res[+d.dataset.i])});
  document.addEventListener('click',function(e){if(!e.target.closest('.search'))box.style.display='none'});
  document.addEventListener('keydown',function(e){if(e.key==='/'&&!/INPUT|TEXTAREA/.test(document.activeElement.tagName)){e.preventDefault();input.focus()}});
});
})();
