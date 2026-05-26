const S = {
  videoPath:'', gpxPath:'', outputPath:'',
  widgets: new Set(['map','speed','elevation']),
  position:'top-left', theme:'dark', encoder:'cpu',
  mode:'burn', overlayFmt:'prores',
  opacity:82, accentColor:'',
  loadMapTiles:false, mapStyle:'voyager', zoom:15, offset:0,
  gpxData:null, videoFrame:null, jobId:null, lastLogCount:0,
};

const THEME_ACCENT_DEFAULTS = { dark:'#52d282', light:'#28a052' };

const THEMES = {
  dark:{
    bg:'rgba(15,17,20,0.88)', bg2:'#191c22', border:'#2d3245',
    accent:'#52d282', accent2:'#ffa03c', text:'#e6ebf5', muted:'#78839a',
    danger:'#e05050', dot:'#ffffff',
    trackDone:'#4ec87a', trackFuture:'#3c404b',
    chartFill:'rgba(50,160,90,0.22)',
  },
  light:{
    bg:'rgba(245,247,250,0.92)', bg2:'#ffffff', border:'#d2d7e1',
    accent:'#28a052', accent2:'#2864c8', text:'#1e2332', muted:'#828ca0',
    danger:'#d23232', dot:'#141414',
    trackDone:'#32aa5a', trackFuture:'#b4b9c3',
    chartFill:'rgba(40,160,80,0.14)',
  },
};

const W_DEFS = {
  map:       {h:290, w:290},
  speed:     {h:90,  w:290},
  elevation: {h:110, w:290},
  grade:     {h:70,  w:290},
  distance:  {h:70,  w:290},
};
const W_PAD = 12;
const SCALE = 960 / 1920;

// ── Canvas ────────────────────────────────────────────────────────────────────
const canvas = document.getElementById('previewCanvas');
const ctx = canvas.getContext('2d');

function drawPreview() {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  if (S.videoFrame) {
    ctx.drawImage(S.videoFrame, 0, 0, canvas.width, canvas.height);
  } else {
    const g = ctx.createLinearGradient(0, 0, canvas.width, canvas.height);
    g.addColorStop(0, '#1c2a3a'); g.addColorStop(1, '#0d1520');
    ctx.fillStyle = g; ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = 'rgba(255,255,255,0.03)';
    ctx.fillRect(0, canvas.height*0.6, canvas.width, canvas.height*0.4);
  }

  const T = Object.assign({}, THEMES[S.theme]);
  if (S.accentColor) {
    T.accent = S.accentColor;
    T.trackDone = S.accentColor;
    const hex = S.accentColor.replace('#','');
    const r = parseInt(hex.slice(0,2),16), g = parseInt(hex.slice(2,4),16), b = parseInt(hex.slice(4,6),16);
    T.chartFill = `rgba(${r},${g},${b},0.22)`;
  }
  const widgets = [...S.widgets];
  if (!widgets.length) return;

  const GAP = 8 * SCALE, MARGIN = 20 * SCALE;
  const totalH = widgets.reduce((s,w) => s + W_DEFS[w].h * SCALE, 0) + GAP*(widgets.length-1);
  const maxW = Math.max(...widgets.map(w => W_DEFS[w].w)) * SCALE;

  let ox, oy;
  if (S.position==='top-left')         { ox=MARGIN; oy=MARGIN; }
  else if (S.position==='top-right')   { ox=canvas.width-maxW-MARGIN; oy=MARGIN; }
  else if (S.position==='bottom-left') { ox=MARGIN; oy=canvas.height-totalH-MARGIN; }
  else                                  { ox=canvas.width-maxW-MARGIN; oy=canvas.height-totalH-MARGIN; }

  let cy = oy;
  for (const wid of widgets) {
    const ww = W_DEFS[wid].w * SCALE, wh = W_DEFS[wid].h * SCALE;
    drawWidget(wid, ox, cy, ww, wh, T);
    cy += wh + GAP;
  }
}

function drawWidget(type, x, y, w, h, T) {
  const pad = W_PAD * SCALE;
  const alpha = S.opacity / 100;
  const bgBase = T.bg.replace(/[\d.]+\)$/, `${alpha})`);
  ctx.fillStyle = bgBase; ctx.fillRect(x, y, w, h);
  ctx.fillStyle = T.accent; ctx.fillRect(x, y, 3*SCALE, h);

  if      (type==='map')       drawMap(x, y, w, h, pad, T);
  else if (type==='speed')     drawSpeed(x, y, w, h, pad, T);
  else if (type==='elevation') drawElevation(x, y, w, h, pad, T);
  else if (type==='grade')     drawGrade(x, y, w, h, pad, T);
  else if (type==='distance')  drawDistance(x, y, w, h, pad, T);
}

function lbl(text, x, y, T) {
  ctx.font = `${Math.round(10*SCALE)}px DM Mono,monospace`;
  ctx.fillStyle = T.muted; ctx.fillText(text, x, y);
}
function big(text, x, y, T, color) {
  ctx.font = `800 ${Math.round(30*SCALE)}px Syne,sans-serif`;
  ctx.fillStyle = color||T.accent; ctx.fillText(text, x, y);
}
function sm(text, x, y, T, color) {
  ctx.font = `${Math.round(12*SCALE)}px Syne,sans-serif`;
  ctx.fillStyle = color||T.text; ctx.fillText(text, x, y);
}

function drawMap(x, y, w, h, pad, T) {
  const mx=x+pad, my=y+pad, mw=w-pad*2, mh=h-pad*2;
  ctx.fillStyle = S.theme==='dark' ? '#18222e' : '#dce8f0';
  ctx.fillRect(mx, my, mw, mh);

  if (!S.gpxData) { lbl('No GPX data', mx+8, my+20, T); return; }
  const tr = S.gpxData.track;
  const split = Math.floor(tr.length*0.4);

  ctx.strokeStyle = T.trackFuture; ctx.lineWidth = 1.5*SCALE; ctx.beginPath();
  tr.forEach((p,i)=>{ const px=mx+p.x*mw,py=my+p.y*mh; i===0?ctx.moveTo(px,py):ctx.lineTo(px,py); });
  ctx.stroke();

  ctx.strokeStyle = T.trackDone; ctx.lineWidth = 3*SCALE; ctx.beginPath();
  tr.slice(0,split).forEach((p,i)=>{ const px=mx+p.x*mw,py=my+p.y*mh; i===0?ctx.moveTo(px,py):ctx.lineTo(px,py); });
  ctx.stroke();

  const cur=tr[split];
  if(cur){
    const cx2=mx+cur.x*mw, cy2=my+cur.y*mh;
    const prev=tr[Math.max(0,split-1)], next=tr[Math.min(tr.length-1,split+1)];
    const dx=(next.x-prev.x)*mw, dy=(next.y-prev.y)*mh;
    const angle=Math.atan2(dy,dx);
    const sz=8*SCALE;
    ctx.fillStyle='#fff'; ctx.beginPath(); ctx.arc(cx2,cy2,sz*1.4,0,Math.PI*2); ctx.fill();
    ctx.save(); ctx.translate(cx2,cy2); ctx.rotate(angle);
    ctx.fillStyle='#ff2222'; ctx.beginPath();
    ctx.moveTo(sz,0); ctx.lineTo(-sz*0.55,-sz*0.65); ctx.lineTo(-sz*0.55,sz*0.65);
    ctx.closePath(); ctx.fill(); ctx.restore();
  }
}

function drawSpeed(x, y, w, h, pad, T) {
  const spd = S.gpxData ? Math.round(S.gpxData.speed_max*0.6) : 34;
  lbl('SPEED', x+pad+4*SCALE, y+pad+12*SCALE, T);
  ctx.font = `800 ${Math.round(30*SCALE)}px Syne,sans-serif`;
  const spdW = ctx.measureText(String(spd)).width;
  big(String(spd), x+pad, y+h-14*SCALE, T, T.accent);
  sm('km/h', x+pad+spdW+6*SCALE, y+h-20*SCALE, T, T.muted);
  const bx=x+pad, by=y+h-5*SCALE, bw=w-pad*2;
  ctx.fillStyle=T.bg2||'#222'; ctx.fillRect(bx,by,bw,3*SCALE);
  ctx.fillStyle=T.accent; ctx.fillRect(bx,by,bw*0.6,3*SCALE);
}

function drawElevation(x, y, w, h, pad, T) {
  const eMin=S.gpxData?S.gpxData.ele_min:200, eMax=S.gpxData?S.gpxData.ele_max:800;
  const eCur=Math.round(eMin+(eMax-eMin)*0.4);
  lbl('ELEVATION', x+pad+4*SCALE, y+pad+12*SCALE, T);
  sm(`${eCur} m`, x+pad, y+42*SCALE, T, T.text);

  const cx0=x+pad, cy0=y+54*SCALE, cw=w-pad*2, ch=h-64*SCALE;
  const eRange=Math.max(eMax-eMin,1);
  const prof=S.gpxData?S.gpxData.ele_profile:[];
  const split=0.4;

  // ▲max / ▼min labels (right side)
  ctx.font=`${Math.round(10*SCALE)}px DM Mono,monospace`; ctx.fillStyle=T.muted;
  ctx.fillText(`▲${Math.round(eMax)}m`, x+w-52*SCALE, y+30*SCALE);
  ctx.fillText(`▼${Math.round(eMin)}m`, x+w-52*SCALE, y+46*SCALE);

  if(prof.length>1){
    ctx.fillStyle=T.chartFill; ctx.beginPath();
    ctx.moveTo(cx0,cy0+ch);
    prof.forEach(p=>{ ctx.lineTo(cx0+p.x*cw, cy0+ch-((p.y-eMin)/eRange)*ch); });
    ctx.lineTo(cx0+cw,cy0+ch); ctx.closePath(); ctx.fill();

    ctx.strokeStyle=T.trackFuture; ctx.lineWidth=1.5*SCALE; ctx.beginPath();
    let first=true;
    prof.filter(p=>p.x>=split).forEach(p=>{
      const px2=cx0+p.x*cw, py2=cy0+ch-((p.y-eMin)/eRange)*ch;
      first?(ctx.moveTo(px2,py2),first=false):ctx.lineTo(px2,py2);
    }); ctx.stroke();

    ctx.strokeStyle=T.accent; ctx.lineWidth=2*SCALE; ctx.beginPath(); first=true;
    prof.filter(p=>p.x<=split).forEach(p=>{
      const px2=cx0+p.x*cw, py2=cy0+ch-((p.y-eMin)/eRange)*ch;
      first?(ctx.moveTo(px2,py2),first=false):ctx.lineTo(px2,py2);
    }); ctx.stroke();

    // cursor line (T.dot) + cursor dot
    const curX2=cx0+split*cw;
    ctx.strokeStyle=T.dot; ctx.lineWidth=1*SCALE;
    ctx.beginPath(); ctx.moveTo(curX2,cy0); ctx.lineTo(curX2,cy0+ch); ctx.stroke();
    const closest=prof.reduce((a,b)=>Math.abs(b.x-split)<Math.abs(a.x-split)?b:a);
    const curY2=cy0+ch-((closest.y-eMin)/eRange)*ch;
    ctx.fillStyle=T.accent; ctx.beginPath(); ctx.arc(curX2,curY2,4*SCALE,0,Math.PI*2); ctx.fill();
  }
}

function drawGrade(x, y, w, h, pad, T) {
  const grade = 3.2; // static preview value
  const sign = grade > 0 ? '+' : '';
  const gradeColor = Math.abs(grade) > 8 ? T.danger : Math.abs(grade) > 3 ? T.accent : T.text;
  lbl('GRADE', x+pad+4*SCALE, y+pad+12*SCALE, T);
  big(`${sign}${grade.toFixed(1)}%`, x+pad, y+h-14*SCALE, T, gradeColor);
  const bx=x+pad, by=y+h-5*SCALE, bw=w-pad*2, mid=bx+bw/2;
  ctx.fillStyle=T.bg2||'#222'; ctx.fillRect(bx,by,bw,3*SCALE);
  const ratio=Math.min(Math.abs(grade)/20,1);
  if(grade>=0){
    ctx.fillStyle=T.accent; ctx.fillRect(mid,by,bw/2*ratio,3*SCALE);
  } else {
    ctx.fillStyle=T.accent; ctx.fillRect(mid-bw/2*ratio,by,bw/2*ratio,3*SCALE);
  }
  ctx.fillStyle=T.muted; ctx.fillRect(mid-SCALE,by-SCALE,2*SCALE,5*SCALE);
}

function drawDistance(x, y, w, h, pad, T) {
  const total=S.gpxData?S.gpxData.total_km.toFixed(1):'42.0';
  const cur=S.gpxData?(S.gpxData.total_km*0.4).toFixed(2):'16.80';
  lbl('DISTANCE', x+pad+4*SCALE, y+pad+12*SCALE, T);
  ctx.font = `800 ${Math.round(30*SCALE)}px Syne,sans-serif`;
  const curW = ctx.measureText(String(cur)).width;
  big(String(cur), x+pad, y+h-14*SCALE, T, T.accent);
  sm(`/ ${total} km`, x+pad+curW+6*SCALE, y+h-20*SCALE, T, T.muted);
  const bx=x+pad, by=y+h-5*SCALE, bw=w-pad*2;
  ctx.fillStyle=T.bg2||'#222'; ctx.fillRect(bx,by,bw,3*SCALE);
  ctx.fillStyle=T.accent; ctx.fillRect(bx,by,bw*0.4,3*SCALE);
}

// ── GPX path input ────────────────────────────────────────────────────────────
let gpxTimer=null;
document.getElementById('gpxPath').addEventListener('blur', e=>{
  const clean=e.target.value.trim().replace(/^["']+|["']+$/g,'').trim();
  if(clean!==e.target.value){ e.target.value=clean; S.gpxPath=clean; }
});
document.getElementById('videoPath').addEventListener('blur', e=>{
  const clean=e.target.value.trim().replace(/^["']+|["']+$/g,'').trim();
  if(clean!==e.target.value){ e.target.value=clean; S.videoPath=clean; }
});
document.getElementById('gpxPath').addEventListener('input', e=>{
  S.gpxPath=e.target.value.trim().replace(/^"|"$/g,'').replace(/^'|'$/g,'').trim();
  clearTimeout(gpxTimer);
  gpxTimer=setTimeout(()=>loadGpx(S.gpxPath), 900);
});
let videoTimer=null;
document.getElementById('videoPath').addEventListener('input', e=>{
  S.videoPath=e.target.value.trim().replace(/^"|"$/g,'').replace(/^'|'$/g,'').trim();
  const el=document.getElementById('videoPath');
  const st=document.getElementById('videoStatus');
  if(S.videoPath){ el.className='path-input'; st.className='path-status'; st.textContent='⏳ Loading...'; }
  else { el.className='path-input'; st.className='path-status'; st.textContent='Enter video file path'; S.videoFrame=null; drawPreview(); }
  checkReady();
  clearTimeout(videoTimer);
  if(S.videoPath) videoTimer=setTimeout(()=>loadFrame(S.videoPath), 900);
});
document.getElementById('outputPath').addEventListener('input', e=>{ S.outputPath=e.target.value.trim(); });

async function loadGpx(path){
  if(!path)return;
  const st=document.getElementById('gpxStatus');
  st.className='path-status'; st.textContent='⏳ Loading...';
  try{
    const r=await fetch('/preview-gpx',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path})});
    const d=await r.json();
    const el=document.getElementById('gpxPath');
    if(d.ok){
      S.gpxData=d;
      el.className='path-input valid';
      st.className='path-status ok';
      st.textContent=`✓ ${d.count} pts  ${d.total_km.toFixed(1)} km  ${Math.round(d.ele_min)}–${Math.round(d.ele_max)} m`;
      canvas.style.display='block';
      document.getElementById('previewHint').style.display='none';
      drawPreview();
    } else {
      S.gpxData=null;
      el.className='path-input error';
      st.className='path-status err';
      st.textContent='❌ '+(d.error||'Failed to read');
    }
    checkReady();
  }catch(e){
    document.getElementById('gpxStatus').textContent='❌ Server error';
  }
}

async function loadFrame(path){
  if(!path) return;
  const el=document.getElementById('videoPath');
  const st=document.getElementById('videoStatus');
  try{
    const r=await fetch('/preview-frame',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path})});
    const d=await r.json();
    if(d.ok){
      el.className='path-input valid';
      st.className='path-status ok'; st.textContent='✓ Frame loaded';
      canvas.width=d.w; canvas.height=d.h;
      const img=new Image();
      img.onload=()=>{ S.videoFrame=img; drawPreview(); checkReady(); };
      img.src=d.data;
      canvas.style.display='block';
      document.getElementById('previewHint').style.display='none';
    } else {
      el.className='path-input error';
      st.className='path-status err'; st.textContent='❌ '+(d.error||'Cannot open video');
      S.videoFrame=null;
      checkReady();
    }
  }catch(e){
    st.textContent='❌ Server error'; S.videoFrame=null;
  }
}

// ── Controls ──────────────────────────────────────────────────────────────────
document.querySelectorAll('.wtoggle').forEach(el=>{
  el.addEventListener('click',()=>{
    const w=el.dataset.widget;
    if(S.widgets.has(w)){ S.widgets.delete(w); el.classList.remove('active'); el.querySelector('.wcheck').textContent=''; }
    else { S.widgets.add(w); el.classList.add('active'); el.querySelector('.wcheck').textContent='✓'; }
    drawPreview();
  });
});
document.querySelectorAll('.pos-btn').forEach(el=>{
  el.addEventListener('click',()=>{
    document.querySelectorAll('.pos-btn').forEach(b=>b.classList.remove('active'));
    el.classList.add('active'); S.position=el.dataset.pos; drawPreview();
  });
});
document.querySelectorAll('#themeToggle .tbtn').forEach(el=>{
  el.addEventListener('click',()=>{
    document.querySelectorAll('#themeToggle .tbtn').forEach(b=>b.classList.remove('active'));
    el.classList.add('active'); S.theme=el.dataset.theme;
    if(!S.accentColor){
      document.getElementById('accentColor').value=THEME_ACCENT_DEFAULTS[S.theme];
    }
    drawPreview();
  });
});
document.getElementById('opacitySlider').addEventListener('input', e=>{
  S.opacity=parseInt(e.target.value);
  document.getElementById('opacityVal').textContent=S.opacity+'%';
  drawPreview();
});
document.getElementById('accentColor').addEventListener('input', e=>{
  const def=THEME_ACCENT_DEFAULTS[S.theme];
  S.accentColor=e.target.value.toLowerCase()===def.toLowerCase()?'':e.target.value;
  document.getElementById('accentLabel').textContent=S.accentColor||'theme default';
  drawPreview();
});
document.getElementById('accentReset').addEventListener('click',()=>{
  S.accentColor='';
  document.getElementById('accentColor').value=THEME_ACCENT_DEFAULTS[S.theme];
  document.getElementById('accentLabel').textContent='theme default';
  drawPreview();
});
document.querySelectorAll('#modeToggle .tbtn').forEach(el=>{
  el.addEventListener('click',()=>{
    document.querySelectorAll('#modeToggle .tbtn').forEach(b=>b.classList.remove('active'));
    el.classList.add('active'); S.mode=el.dataset.mode;
    document.getElementById('burnOptions').style.display=S.mode==='burn'?'':'none';
    document.getElementById('overlayOptions').style.display=S.mode==='overlay'?'':'none';
  });
});
document.querySelectorAll('#overlayFmtToggle .tbtn').forEach(el=>{
  el.addEventListener('click',()=>{
    document.querySelectorAll('#overlayFmtToggle .tbtn').forEach(b=>b.classList.remove('active'));
    el.classList.add('active'); S.overlayFmt=el.dataset.fmt;
  });
});
document.querySelectorAll('#encoderToggle .tbtn').forEach(el=>{
  el.addEventListener('click',()=>{
    document.querySelectorAll('#encoderToggle .tbtn').forEach(b=>b.classList.remove('active'));
    el.classList.add('active'); S.encoder=el.dataset.encoder;
  });
});
document.querySelectorAll('#mapTilesToggle .tbtn').forEach(el=>{
  el.addEventListener('click',()=>{
    document.querySelectorAll('#mapTilesToggle .tbtn').forEach(b=>b.classList.remove('active'));
    el.classList.add('active'); S.loadMapTiles=el.dataset.tiles==='on';
    document.getElementById('mapTileOptions').style.display=S.loadMapTiles?'':'none';
  });
});
document.getElementById('mapStyle').addEventListener('change',e=>{ S.mapStyle=e.target.value; });
document.getElementById('zoomLevel').addEventListener('change',e=>{ S.zoom=parseInt(e.target.value); });
document.getElementById('offsetSlider').addEventListener('input',e=>{
  S.offset=parseInt(e.target.value);
  document.getElementById('offsetVal').textContent=S.offset+'s';
});

// ── Render ────────────────────────────────────────────────────────────────────
function checkReady(){
  document.getElementById('renderBtn').disabled=!(S.videoFrame&&S.gpxPath&&S.gpxData?.ok);
}

document.getElementById('renderBtn').addEventListener('click',async()=>{
  const btn=document.getElementById('renderBtn');
  btn.disabled=true; btn.textContent='⏳ Rendering...';
  document.getElementById('progressSection').classList.add('visible');
  document.getElementById('progressFill').style.width='0%';
  document.getElementById('logBox').innerHTML='';
  document.getElementById('outputSection').classList.remove('visible');
  S.lastLogCount=0;

  const r=await fetch('/render',{
    method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({
      video_path:S.videoPath, gpx_path:S.gpxPath, output_path:S.outputPath||null,
      widgets:[...S.widgets].join(','), position:S.position, theme:S.theme,
      encoder:S.encoder, mode:S.mode, overlay_fmt:S.overlayFmt,
      opacity:S.opacity, accent_color:S.accentColor||'',
      load_map_tiles:S.loadMapTiles, map_style:S.mapStyle, zoom:S.zoom, offset:S.offset,
    }),
  });
  const d=await r.json();
  S.jobId=d.job_id;
  poll(S.jobId);
});

function addLog(msg,cls=''){
  const box=document.getElementById('logBox');
  const d=document.createElement('div');
  d.className=cls; d.textContent=msg;
  box.appendChild(d); box.scrollTop=box.scrollHeight;
}

async function poll(jobId){
  const r=await fetch('/status/'+jobId);
  const d=await r.json();

  if(d.logs&&d.logs.length>S.lastLogCount){
    d.logs.slice(S.lastLogCount).forEach(l=>{
      const cls=l.startsWith('✅')?'lok':l.startsWith('❌')?'lerr':l.startsWith('⏳')?'lprog':'';
      addLog(l,cls);
    });
    S.lastLogCount=d.logs.length;
  } else if(d.logs?.length===S.lastLogCount&&S.lastLogCount>0){
    const box=document.getElementById('logBox');
    const last=box.lastElementChild;
    if(last&&last.className==='lprog'&&d.logs[d.logs.length-1]?.startsWith('⏳'))
      last.textContent=d.logs[d.logs.length-1];
  }

  document.getElementById('progressFill').style.width=(d.progress||0)+'%';

  if(d.status==='done'){
    document.getElementById('progressFill').style.width='100%';
    // flush any remaining log lines (e.g. [RENDER] Widget redraws summary)
    if(d.logs&&d.logs.length>S.lastLogCount){
      d.logs.slice(S.lastLogCount).forEach(l=>{
        const cls=l.startsWith('✅')?'lok':l.startsWith('❌')?'lerr':l.startsWith('⏳')?'lprog':'';
        addLog(l,cls);
      });
      S.lastLogCount=d.logs.length;
    }
    const btn=document.getElementById('renderBtn');
    btn.disabled=false; btn.textContent='▶ Re-render';
    document.getElementById('outputSection').classList.add('visible');
    document.getElementById('dlBtn').href='/output/'+jobId;
    document.getElementById('outInfo').textContent=d.output_path||'';
  } else if(d.status==='error'){
    addLog('❌ '+(d.error||'Render failed'),'lerr');
    const btn=document.getElementById('renderBtn');
    btn.disabled=false; btn.textContent='▶ Retry';
  } else {
    setTimeout(()=>poll(jobId),1200);
  }
}
