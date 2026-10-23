import { useMemo, useState } from 'react';
import { MapContainer, TileLayer, GeoJSON, Rectangle, useMap } from 'react-leaflet';
import { Satellite, Waves, ShieldCheck, Bot, Search, Play, Download, ChevronDown, AlertTriangle, Activity, Layers3, MapPin, CalendarDays, LoaderCircle } from 'lucide-react';

const API = 'http://127.0.0.1:8000';
type Result = any;
function Stat({label,value,sub,tone='blue'}:{label:string,value:string,sub:string,tone?:string}) {
 return <div className={`stat ${tone}`}><div className="eyebrow">{label}</div><div className="stat-value">{value}</div><div className="stat-sub">{sub}</div></div>
}
function MapBounds({bbox}:{bbox:number[]}) {
 const map=useMap(); useMemo(()=>{if(bbox?.length===4) map.fitBounds([[bbox[1],bbox[0]],[bbox[3],bbox[2]]],{padding:[18,18]}); return null},[map,bbox.join(',')]); return null;
}
export default function App(){
 const [tab,setTab]=useState('Satellite Comparison');
 const [bbox,setBbox]=useState('85.5,27.7,85.8,28.0');
 const [preStart,setPreStart]=useState('2026-08-01'), [preEnd,setPreEnd]=useState('2026-08-25');
 const [postStart,setPostStart]=useState('2026-08-26'), [postEnd,setPostEnd]=useState('2026-09-10');
 const [orbit,setOrbit]=useState('ANY'), [pol,setPol]=useState('VV');
 const [scenes,setScenes]=useState<any[]>([]), [result,setResult]=useState<Result|null>(null);
 const [busy,setBusy]=useState(false), [error,setError]=useState(''), [question,setQuestion]=useState('What areas are candidate inundation?'), [answer,setAnswer]=useState<any>(null);
 const [language,setLanguage]=useState('en');
 const box=useMemo(()=>bbox.split(',').map(Number),[bbox]);
 async function searchScenes(){
   setBusy(true);setError('');
   try { const r=await fetch(`${API}/api/scenes?bbox=${encodeURIComponent(bbox)}&start=${preStart}&end=${postEnd}&orbit_direction=${orbit}&polarization=${pol}&limit=20`); const d=await r.json(); if(!r.ok)throw new Error(d.detail||'Scene search failed'); setScenes(d.items||[]); }
   catch(e:any){setError(e.message+' — ensure the FastAPI backend is running and internet access is available.')} finally{setBusy(false)}
 }
 async function runAnalysis(){
   setBusy(true);setError('');setAnswer(null);
   try { const r=await fetch(`${API}/api/analyze`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({bbox:box,pre_start:preStart,pre_end:preEnd,post_start:postStart,post_end:postEnd,orbit_direction:orbit,polarization:pol})}); const d=await r.json(); if(!r.ok)throw new Error(d.detail||'Analysis failed');setResult(d);setTab('Surface Change Detection');}
   catch(e:any){setError(e.message)} finally{setBusy(false)}
 }
 async function ask(){
   try { const r=await fetch(`${API}/api/copilot/ask`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question,job_id:result?.job_id,language})});setAnswer(await r.json());}
   catch(e:any){setAnswer({answer:'Cannot connect to the API. Start the FastAPI backend first.',evidence:[]})}
 }
 function downloadReport(){if(result?.job_id)window.open(`${API}/api/report/${result.job_id}`,'_blank')}
 const stats=result?.statistics;
 const nav=[['Satellite Comparison',Satellite],['Surface Change Detection',Waves],['Reference Validation',ShieldCheck],['Situation-Report Copilot',Bot]] as const;
 return <div className="app">
  <aside className="sidebar"><div className="brand"><div className="brand-icon"><Satellite size={22}/></div><div><b>VARUNA</b><small>FLOOD INTELLIGENCE</small></div></div>
   <div className="side-label">WORKSPACE</div>{nav.map(([name,Icon])=><button key={name} className={`nav ${tab===name?'active':''}`} onClick={()=>setTab(name)}><Icon size={17}/><span>{name}</span></button>)}
   <div className="side-bottom"><div className="live-dot"/> <span>Satellite services</span><b>Connected*</b><small>*API connection required</small></div>
  </aside>
  <main className="main"><header className="topbar"><div><div className="breadcrumb">DISASTER MONITORING / <b>{tab.toUpperCase()}</b></div><h1>{tab}</h1></div><div className="top-right"><span className="pill"><span className="live-dot"/> Evidence-grounded</span><button className="btn outline" onClick={downloadReport} disabled={!result}><Download size={15}/> Export report</button></div></header>
  <section className="content">
   {error&&<div className="error"><AlertTriangle size={18}/><div><b>Request could not be completed</b><p>{error}</p></div><button onClick={()=>setError('')}>×</button></div>}
   <div className="panel">
    <div className="panel-heading"><div><span className="section-kicker">ANALYSIS CONFIGURATION</span><h3>Observation parameters</h3></div><span className="tag">Sentinel-1 GRD · STAC</span></div>
    <div className="form-grid">
     <label className="field wide"><span>Area of interest · bbox (min lon, min lat, max lon, max lat)</span><input value={bbox} onChange={e=>setBbox(e.target.value)} placeholder="85.5,27.7,85.8,28.0"/></label>
     <label className="field"><span>Pre-event start</span><input type="date" value={preStart} onChange={e=>setPreStart(e.target.value)}/></label>
     <label className="field"><span>Pre-event end</span><input type="date" value={preEnd} onChange={e=>setPreEnd(e.target.value)}/></label>
     <label className="field"><span>Post-event start</span><input type="date" value={postStart} onChange={e=>setPostStart(e.target.value)}/></label>
     <label className="field"><span>Post-event end</span><input type="date" value={postEnd} onChange={e=>setPostEnd(e.target.value)}/></label>
     <label className="field"><span>Orbit direction</span><select value={orbit} onChange={e=>setOrbit(e.target.value)}><option value="ANY">Any orbit</option><option value="ASCENDING">Ascending</option><option value="DESCENDING">Descending</option></select></label>
     <label className="field"><span>Polarization</span><select value={pol} onChange={e=>setPol(e.target.value)}><option>VV</option><option>VH</option></select></label>
    </div>
    <div className="actions"><button className="btn outline" onClick={searchScenes} disabled={busy}><Search size={16}/> Search acquisitions</button><button className="btn primary" onClick={runAnalysis} disabled={busy}><Play size={15}/>{busy?'Processing…':'Run real satellite analysis'}</button></div>
   </div>
   {tab==='Satellite Comparison'&&<><div className="section-title"><div><span className="section-kicker">OBSERVATION TELEMETRY</span><h2>Acquisition comparison</h2></div><span className="tag">Live catalogue query</span></div>
    <div className="two-cards"><div className="scene-card pre"><div className="eyebrow">PRE-EVENT WINDOW</div><h2>{preStart} — {preEnd}</h2><p>Sentinel-1 GRD · {pol} polarization</p><div className="scene-foot"><CalendarDays size={15}/> {result?.pre_scene?.datetime||'Run analysis to select a scene'}</div></div><div className="scene-card post"><div className="eyebrow">POST-EVENT WINDOW</div><h2>{postStart} — {postEnd}</h2><p>Sentinel-1 GRD · {pol} polarization</p><div className="scene-foot"><CalendarDays size={15}/> {result?.post_scene?.datetime||'Run analysis to select a scene'}</div></div></div>
    <div className="panel"><div className="panel-heading"><h3>Acquisition metadata</h3><span className="tag">{scenes.length} scenes found</span></div>{scenes.length? <div className="table-wrap"><table><thead><tr><th>Acquisition ID</th><th>Date/time UTC</th><th>Platform</th><th>Orbit</th><th>Relative orbit</th></tr></thead><tbody>{scenes.map(s=><tr key={s.id}><td className="mono">{s.id}</td><td>{s.datetime||'—'}</td><td>{s.platform||'—'}</td><td>{s.orbit_direction||'—'}</td><td>{s.relative_orbit??'—'}</td></tr>)}</tbody></table></div>:<div className="empty">Search acquisitions to see real scene metadata. No example values are fabricated.</div>}</div>
    <div className="panel"><h3>Radar backscatter physics</h3><p className="muted">Calibrated SAR intensity responds to surface roughness, dielectric properties, geometry, and vegetation. Smooth open water can produce a specular reflection away from the sensor and appear dark; rough water, urban structures, and vegetation can behave differently. Threshold-based changes are candidates that require context and validation.</p></div>
   </>}
   {tab==='Surface Change Detection'&&<><div className="section-title"><div><span className="section-kicker">RAW BASIN BASELINE STATISTICS</span><h2>Surface change classification</h2></div><span className="tag">Threshold-based · candidate classes</span></div>
    <div className="stats-grid"><Stat label="Candidate floodwater" value={stats?`${stats.candidate_inundation_km2} km²`:'—'} sub={stats?`${stats.candidate_inundation_pixels.toLocaleString()} px · ${stats.candidate_inundation_pct}%`:'Waiting for a completed analysis'} tone="blue"/><Stat label="Candidate debris / scour" value={stats?`${stats.candidate_disturbance_km2} km²`:'—'} sub={stats?`${stats.candidate_disturbance_pixels.toLocaleString()} px · ${stats.candidate_disturbance_pct}%`:'Waiting for a completed analysis'} tone="orange"/><Stat label="Permanent water baseline" value="Not estimated" sub="Requires a calibrated multi-temporal water model" tone="green"/><Stat label="Unchanged surface" value={stats?`${stats.unchanged_km2} km²`:'—'} sub={stats?`${stats.unchanged_pixels.toLocaleString()} pixels`:'Waiting for a completed analysis'} tone="neutral"/></div>
    <div className="panel"><div className="panel-heading"><h3>Classification decision rules</h3><span className="tag">VV backscatter delta</span></div><div className="table-wrap"><table><thead><tr><th>Class</th><th>Decision rule</th><th>Computed area</th></tr></thead><tbody><tr><td><b className="blue-text">Candidate inundation</b></td><td>Δσ° ≤ −3.5 dB (configurable specular drop)</td><td>{stats?`${stats.candidate_inundation_km2} km²`:'—'}</td></tr><tr><td><b className="orange-text">Candidate disturbance</b></td><td>Δσ° ≥ +3.5 dB (configurable backscatter increase)</td><td>{stats?`${stats.candidate_disturbance_km2} km²`:'—'}</td></tr><tr><td>Unchanged surface</td><td>−3.5 &lt; Δσ° &lt; +3.5 dB</td><td>{stats?`${stats.unchanged_km2} km²`:'—'}</td></tr></tbody></table></div><p className="fine">These rules are initial screening thresholds, not a universal flood classifier. Terrain, vegetation, urban areas, soil moisture, and acquisition geometry can cause false positives and false negatives.</p></div>
   </>}
   {tab==='Reference Validation'&&<><div className="section-title"><div><span className="section-kicker">INDEPENDENT REFERENCE COMPARISON</span><h2>Reference validation</h2></div><span className="tag">Reference required</span></div><div className="stats-grid"><Stat label="Candidate inundation" value={stats?`${stats.candidate_inundation_km2} km²`:'—'} sub="From satellite-derived change mask" tone="blue"/><Stat label="Precision" value={result?.validation?`${(result.validation.precision*100).toFixed(2)}%`:'Not calculated'} sub="Requires reference footprint" tone="purple"/><Stat label="Recall" value={result?.validation?`${(result.validation.recall*100).toFixed(2)}%`:'Not calculated'} sub="Requires reference footprint" tone="orange"/><Stat label="Intersection over Union" value={result?.validation?`${(result.validation.iou*100).toFixed(2)}%`:'Not calculated'} sub="Requires reference footprint" tone="green"/></div><div className="panel"><h3>How to validate</h3><ol className="steps"><li>Run the satellite analysis to generate the candidate inundation footprint.</li><li>Obtain an independent, dated flood reference footprint from a trusted source (for example, an official Copernicus EMS activation product where available).</li><li>Submit the GeoJSON reference to <code>POST /api/validate</code> using the current job ID. See README for the request body.</li><li>Record the reference source, acquisition date, spatial resolution, and any mismatch in time or scale.</li></ol>{result?.validation&&<pre className="json">{JSON.stringify(result.validation,null,2)}</pre>}</div></>}
   {tab==='Situation-Report Copilot'&&<><div className="section-title"><div><span className="section-kicker">OPERATIONAL AI Q&A</span><h2>Evidence-grounded situation assistant</h2></div><div className="lang"><button className={language==='en'?'selected':''} onClick={()=>setLanguage('en')}>EN</button><button className={language==='ne'?'selected':''} onClick={()=>setLanguage('ne')}>नेपाली</button></div></div><div className="quick-asks">{['Isolated settlements','Road exposure','Hazard areas','SAR telemetry','Casualty query (refusal test)'].map((x,i)=><button key={x} onClick={()=>setQuestion(['What settlements are inside candidate inundation areas?','What roads intersect the candidate flood footprint?','Summarize candidate hazard areas and uncertainty.','What are the acquisition dates and thresholds?','How many casualties and deaths occurred?'][i])}>{['🏘️','🛣️','🌊','🛰️','⚠️'][i]} {x}</button>)}</div><div className="ask-row"><input value={question} onChange={e=>setQuestion(e.target.value)} onKeyDown={e=>e.key==='Enter'&&ask()} placeholder="Ask about the current satellite analysis…"/><button className="btn primary" onClick={ask}><Bot size={16}/> Ask</button></div>{answer&&<div className="answer"><div className="answer-title"><ShieldCheck size={18}/>{answer.refused?'Scientific disclosure':'Evidence-grounded response'}</div><p>{answer.answer}</p>{answer.evidence?.length>0&&<><b>Evidence used</b><ul>{answer.evidence.map((e:string)=><li key={e}>{e}</li>)}</ul></>}</div>}<div className="panel"><h3>Operational safety</h3><p className="muted">The copilot only summarizes the selected analysis response. It does not infer casualty counts from imagery. Road and settlement exposure requires suitable, current vector datasets and spatial-intersection processing; these layers are not silently fabricated when unavailable.</p><button className="btn outline" onClick={downloadReport} disabled={!result}><Download size={15}/> Open full situation briefing (PDF)</button></div></>}
   {result&&<div className="section-title"><div><span className="section-kicker">GEOSPATIAL OUTPUT</span><h2>Analysis map</h2></div><span className="tag mono">{result.job_id.slice(0,8)}</span></div>}
   {result&&<div className="panel map-panel"><div className="map-legend"><span><i className="legend-blue"/> Candidate inundation</span><span><i className="legend-orange"/> Candidate disturbance</span><span className="muted">OpenStreetMap basemap</span></div><MapContainer center={[(box[1]+box[3])/2,(box[0]+box[2])/2]} zoom={10} scrollWheelZoom style={{height:430,width:'100%'}}><TileLayer attribution='&copy; OpenStreetMap contributors' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"/><MapBounds bbox={result.bbox}/>{result.geojson?.candidate_inundation&&<GeoJSON data={result.geojson.candidate_inundation as any} style={{color:'#1677c8',weight:1,fillColor:'#278ee5',fillOpacity:.5}}/>}{result.geojson?.candidate_disturbance&&<GeoJSON data={result.geojson.candidate_disturbance as any} style={{color:'#bd6b2b',weight:1,fillColor:'#e59b58',fillOpacity:.45}}/>}</MapContainer><p className="fine">The map shows candidate change polygons generated from the selected scenes. Small isolated components may be speckle/noise; inspect them before interpretation.</p></div>}
   <footer>VARUNA Flood Intelligence · Research prototype · Verify all findings with authoritative references before operational decisions.</footer>
  </section></main>
 </div>
}
