"""Evidence exports share backend comparisons; all text is HTML-escaped."""
import csv
import html
import io
import json
import zipfile
from pathlib import Path
from .network import DATA, ROOT
from .frames import atomic_json

UNITS = {'mean':'s','delay':'s','p95':'s','bus_mean':'s','full_demand_loss':'s/request','person_loss':'s/person','completion_rate':'fraction','co2_kg':'kg','queue_seconds':'vehicle·s','od_inequality':'s'}

def report_html(report):
    esc = lambda v: html.escape(str(v))
    rows = report.get('evaluation', [])
    body = ''
    if rows:
        body += '<h2>Held-out outcomes</h2><p>Completion constraints apply before ranking. The frontier includes only evaluated feasible candidates. A lower completed-trip mean does not establish better service.</p><table><tr><th>Candidate</th><th>Feasible</th><th>Completion</th><th>Full-demand loss</th><th>Bus mean</th><th>Modelled CO₂</th></tr>'
        for r in rows:
            m = r['metrics']
            def f(k): return '—' if m.get(k) is None else f'{m[k]:.3f}'
            body += f"<tr><td>{esc(r['label'])}</td><td>{esc(r['feasible'])}</td><td>{f('completion_rate')}</td><td>{f('full_demand_loss')} s</td><td>{f('bus_mean')} s</td><td>{f('co2_kg')} kg</td></tr>"
        body += '</table>'
        points=''
        lo=min(r['metrics']['full_demand_loss'] for r in rows)-10;hi=max(r['metrics']['full_demand_loss'] for r in rows)+10
        for i,r in enumerate(rows):
            x=60+(r['metrics']['full_demand_loss']-lo)/(hi-lo)*490;y=210-r['metrics']['completion_rate']*170
            points+=f'<circle cx="{x}" cy="{y}" r="6" fill="{"#285c51" if r["feasible"] else "#b77b54"}"/><text x="{x+8}" y="{y-6}" font-size="11">{i+1}</text>'
        body+=f'<h2>Evaluated trade-offs</h2><svg viewBox="0 0 600 260" role="img" aria-label="Completion versus full-demand loss"><path d="M60 30V210H560" fill="none" stroke="#a7b6a1"/>{points}<text x="10" y="40" font-size="11">100%</text><text x="22" y="210" font-size="11">0%</text><text x="60" y="235" font-size="11">{lo:.1f}</text><text x="520" y="235" font-size="11">{hi:.1f}</text><text x="180" y="255" font-size="11">Full-demand loss (s/request)</text></svg><p>Numbers match table rows. Teal: feasible; brown: a service constraint failed. The computed frontier uses all selected objectives.</p>'
        body += '<h2>Paired effects by condition</h2>' 
        for p in report.get('paired', []):
            body += f"<h3>{esc(p['candidate'])} · {esc(p['condition'])}</h3><table><tr><th>Metric</th><th>Paired mean difference</th><th>95% interval</th><th>Runs</th></tr>"
            for k in ['full_demand_loss','mean','completion_rate','bus_mean','co2_kg']:
                e=p['effects'][k];interval=e['ci95']
                body += f"<tr><td>{esc(k)} ({esc(UNITS.get(k,''))})</td><td>{esc(e['mean'])}</td><td>{esc(interval)}</td><td>{e['n']}</td></tr>"
            body += '</table>'
        body += '<h2>Run provenance and distributional evidence</h2><p>Each replicate uses its own seed. Overall summaries average tested conditions within each seed; condition-specific paired effects use ten seed pairs in the bundled research case.</p>'
        body += '<p>Application: CityLab 2.0.0. Engine: SUMO 1.27.1. Timestep: 0.5 seconds. Synthetic generated demand; occupancy assumptions are part of the immutable configuration. Emissions: HBEFA3/PC_G_EU4 and HBEFA3/Bus, integrated over the timestep.</p>'
        body += '<table><tr><th>Candidate / class</th><th>Requests across runs</th><th>Completed</th><th>Loss s/request</th></tr>'
        for candidate in report.get('frozen',[]):
            for group in ['Class · passenger','Class · bus']:
                gs=[g for r in report['records'] if r['stage']=='evaluation' and r['candidate']==candidate['id'] for g in r.get('groups',[]) if g['group']==group]
                if gs:
                    n=sum(g['requested'] for g in gs);done=sum(g['completed'] for g in gs);loss=sum(g['full_demand_loss']*g['requested'] for g in gs)/n
                    body+=f"<tr><td>{esc(candidate['label'])} / {esc(group)}</td><td>{n}</td><td>{done}</td><td>{loss:.2f}</td></tr>"
        body+='</table><p>Per-run OD sample sizes and exact network/configuration hashes are included in the machine-readable results. Small groups are flagged, never ranked.</p>'
        body += '<h2>Interventions and constraints</h2><pre>' +esc(json.dumps(report['spec'],indent=2))+'</pre>'
    else:
        body += '<h2>Computed evidence</h2><pre>'+esc(json.dumps(report,indent=2))+'</pre>'
    return '<!doctype html><html><head><meta charset="utf-8"><title>CityLab evidence report</title><style>@page{size:A4;margin:18mm}body{font:13px system-ui;color:#243a3c;max-width:1000px;margin:30px auto;line-height:1.55}h1{font-size:30px}h2{margin-top:28px;border-top:1px solid #aaa;padding-top:12px}table{width:100%;border-collapse:collapse;font-size:11px}td,th{padding:8px;text-align:left;border-bottom:1px solid #ddd}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:10px}tr{break-inside:avoid}.bar{height:12px;background:#567f80}button{padding:10px}@media print{button{display:none}}</style></head><body><button onclick="window.print()">Print / Save as PDF</button><h1>CityLab · Evidence report</h1><p>How can we improve movement without hiding journeys, people or streets that become worse off?</p><p>Generated traffic demand and actual SUMO outputs. Not live traffic or a validated digital twin.</p>'+body+'<h2>Interpretation and limitations</h2><p>Results apply only within this model and these tested conditions. Runs—not vehicles—are experimental replicates. Bootstrap intervals are exploratory and unadjusted for multiple comparisons; small samples can be inconclusive. Non-completed trips are censored; the full-demand loss applies an explicit one-horizon penalty. Person outcomes depend on assumed occupancy. Emissions are SUMO HBEFA model estimates.</p><p>Reproduce from the included configuration, manifests, network hashes, application revision and pinned dependencies. See METHODOLOGY.md for equations, controller deviations and sampling definitions.</p></body></html>'

def evidence_bundle(report, folder):
    out = Path(folder) / 'evidence.zip'
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('report.json', json.dumps(report, indent=2))
        z.writestr('report.html', report_html(report))
        pdf=report_pdf(report,Path(folder)/'report.pdf');z.write(pdf,'report.pdf')
        if (Path(folder)/'frozen.json').exists():z.write(Path(folder)/'frozen.json','frozen.json')
        run_ids = sorted({r['run_id'] for r in report.get('records', [])})
        for id in run_ids:
            run = DATA / 'jobs' / id
            for name in ['result.json','manifest.json','network.json','network.net.xml','routes.xml']:
                if (run / name).exists(): z.write(run/name,f'runs/{id}/{name}')
        for name in ['README.md','docs/METHODOLOGY.md','requirements.lock.txt','frontend/pnpm-lock.yaml']:
            if (ROOT/name).exists(): z.write(ROOT/name,name)
    return out


def report_pdf(report, output):
    """Portable vector PDF export; independent of a browser installation."""
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.colors import HexColor, white
    from reportlab.lib.pagesizes import A4
    from reportlab.graphics.shapes import Drawing, Line, Circle, String
    styles=getSampleStyleSheet()
    styles.add(ParagraphStyle(name='SmallNote',parent=styles['BodyText'],fontSize=8,leading=12,textColor=HexColor('#617264')))
    for name in ['Title','Heading1','Heading2','Heading3']:
        styles[name].textColor=HexColor('#285c51')
    styles['BodyText'].fontSize=9;styles['BodyText'].leading=14
    story=[]
    def p(text,style='BodyText'):
        story.append(Paragraph(html.escape(str(text)).replace('\n','<br/>'),styles[style]));story.append(Spacer(1,7))
    def table(headers,rows,widths=None):
        data=[[Paragraph(html.escape(str(v)),styles['SmallNote']) for v in row] for row in [headers]+rows]
        t=Table(data,colWidths=widths or [490/len(headers)]*len(headers),repeatRows=1,hAlign='LEFT')
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),HexColor('#e8eee2')),('GRID',(0,0),(-1,-1),.3,HexColor('#d7dfd0')),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),7)]))
        story.append(t);story.append(Spacer(1,13))
    def f(v):return 'Unavailable' if v is None else f'{v:.2f}'
    p('CITYLAB / RECORDED RESEARCH','SmallNote')
    p('Better movement. Complete evidence.','Title')
    p(report.get('question','Bounded calibration of a generated demand model.'))
    spec=report.get('spec',{});scenario=spec.get('scenario',{})
    p(spec.get('name','Synthetic observation calibration'),'Heading2')
    p('Generated demand and actual SUMO outputs. These are model experiments, not Bangalore measurements or field validation.','SmallNote')
    p('Protocol and provenance','Heading2')
    p(f"Network: {scenario.get('network')}. Demand: {scenario.get('demand')} requests. Departures: {scenario.get('duration')} s; clearance: {scenario.get('clearance')} s. Seed sets: search {spec.get('search_seeds')}, tuning {spec.get('tuning_seeds')}, held-out {spec.get('evaluation_seeds')}. Conditions: {spec.get('conditions')}.")
    p(f"Executed: {report.get('completed_runs')} simulations; conservative planned maximum: {report.get('plan',{}).get('maximum_runs')}; hard budget: {spec.get('budget')}. Candidate selection used training and tuning only. Frozen candidates were saved before evaluation.")
    p(f"Search: {report.get('plan',{}).get('method')}. Minimum completion {spec.get('min_completion')}; maximum paired completion drop {spec.get('max_completion_drop')}; maximum invalid fraction {spec.get('max_invalid_fraction')}. Constraints apply to every paired seed and condition.")
    rows=report.get('evaluation',[])
    if rows:
        p('Held-out outcomes','Heading2')
        table(['Candidate / feasible','Completion %','Loss s/request','Bus mean s','CO2 kg'],[[r['label']+' / '+str(r['feasible']),f(r['metrics']['completion_rate']*100),f(r['metrics']['full_demand_loss']),f(r['metrics']['bus_mean']),f(r['metrics']['co2_kg'])] for r in rows],[170,75,90,80,75])
        d=Drawing(490,200);d.add(Line(48,35,465,35,strokeColor=HexColor('#8e9f89')));d.add(Line(48,35,48,180,strokeColor=HexColor('#8e9f89')))
        low=min(r['metrics']['full_demand_loss'] for r in rows);high=max(r['metrics']['full_demand_loss'] for r in rows)
        for i,r in enumerate(rows):
            x=60+(r['metrics']['full_demand_loss']-low)/max(1,high-low)*375;y=35+r['metrics']['completion_rate']*135
            d.add(Circle(x,y,5,fillColor=HexColor('#285c51' if r['feasible'] else '#b77b54'),strokeColor=white));d.add(String(x-3,y+10,str(i+1),fontSize=8))
        for x,val in [(60,low),(435,high)]:d.add(String(x-10,22,f(val),fontSize=8))
        for y,val in [(35,'0'),(170,'100')]:d.add(String(20,y,val,fontSize=8))
        d.add(String(145,5,'Full-demand loss (s/request), lower is better',fontSize=9));d.add(String(10,185,'Completion (%)',fontSize=9));story.append(d)
        p('Numbers identify table rows. Teal: feasible; brown: constraint not met. Frontier membership is computed across the chosen objectives, not just these two axes. No claim of a global optimum.','SmallNote')
        p('Exact frozen interventions','Heading2')
        for row in rows:p(row['label']+': '+json.dumps(row['changes'],sort_keys=True)+'. '+('; '.join(row['constraint_failures']) or 'All tested service constraints met.'))
        story.append(PageBreak());p('Paired effects by held-out condition','Heading1')
        p('Candidate minus baseline. Completion is percentage points; losses and bus means are seconds. Each row uses independent seed-pair differences, not individual vehicle samples. Intervals are percentile bootstrap intervals (2,000 resamples); they are exploratory and not adjusted for multiple comparisons.','SmallNote')
        for pair in report.get('paired',[]):
            section_start=len(story)
            story.append(Paragraph(html.escape(pair['candidate']+' / '+pair['condition']),styles['Heading3']))
            rr=[]
            for key in ['full_demand_loss','mean','completion_rate','bus_mean','co2_kg']:
                e=pair['effects'][key];scale=100 if key=='completion_rate' else 1
                interval='Unavailable' if not e['ci95'] else ' to '.join(f(v*scale) for v in e['ci95'])
                rr.append([key+' ('+('pp' if key=='completion_rate' else UNITS.get(key,''))+')',f(e['mean']*scale) if e['mean'] is not None else 'Unavailable',interval,e['n']])
            table(['Outcome','Mean difference','95% interval','Seed pairs'],rr,[175,105,135,75])
            story[section_start:]=[KeepTogether(story[section_start:])]
        p('Distributional impacts','Heading2')
        for candidate in report.get('frozen',[]):
            rec=[r for r in report['records'] if r['stage']=='evaluation' and r['candidate']==candidate['id']]
            rr=[]
            for group in ['Class · passenger','Class · bus']:
                gs=[g for r in rec for g in r.get('groups',[]) if g['group']==group]
                if gs:
                    requested=sum(g['requested'] for g in gs);completed=sum(g['completed'] for g in gs)
                    rr.append([group,requested,completed,f(sum(g['full_demand_loss']*g['requested'] for g in gs)/requested)])
            if rr:
                start=len(story);p(candidate['label'],'Heading3');table(['Class','Requests across runs','Completed','Loss s/request'],rr)
                story[start:]=[KeepTogether(story[start:])]
        p('OD-specific sample sizes and per-run group effects remain in report.json and each run result. Groups below ten requested trips are flagged and are not ranked. Pooled group totals describe the tested runs; they are not additional statistical replicates.','SmallNote')
    else:
        p(report.get('interpretation','Computed calibration evidence'),'Heading2')
        p(f"Selected demand: {report.get('selected',{}).get('demand')}; validation count MAE {f(report.get('validation_mae'))}; RMSE {f(report.get('validation_rmse'))} vehicles.")
    p('Assumptions, adverse findings and reproduction','Heading2')
    p('No candidate is endorsed when completion constraints fail. A reduction in emissions accompanied by fewer completed journeys remains visible. Completed-trip means are conditional on completion; unfinished travel times are censored. Full-demand loss assigns each unfinished request elapsed time since scheduled departure plus one horizon penalty. Person weighting uses scenario occupancy assumptions, not measured ridership.')
    p('Pressure control is a cyclic, bounded adaptation inspired by Varaiya (2013), The max-pressure controller for arbitrary networks of signalized intersections. It uses SUMO controlled-link movements, downstream queues and protected phase order; it does not estimate saturation flows and does not inherit theoretical stability guarantees. Vehicle physics, network defaults and emissions classes limit interpretation.')
    p('Extract the CityLab release, install requirements.lock.txt, and run python -m scripts.build_demo with a fresh CITYLAB_DATA directory. The supplied study-spec.json, frozen.json, manifest files, immutable networks, SUMO version and application revision identify the experiment. The ZIP includes machine-readable per-seed outcomes and exact configurations. Use the in-app Evidence view for route, queue, completion, class and OD inspection.')
    p('Synthetic geometry is a constructed 4 x 4 grid. The separately included HSR OpenStreetMap extract is uncalibrated, contains disconnected components, and is attributed to OpenStreetMap contributors under ODbL. No synthetic fixture is presented as a field observation.','SmallNote')
    def footer(c,doc):
        c.setFont('Helvetica',8);c.setFillColor(HexColor('#617264'));c.drawString(52,28,'CityLab 2.0 / Generated demand / Recorded SUMO evidence');c.drawRightString(543,28,str(doc.page))
    SimpleDocTemplate(str(output),pagesize=A4,rightMargin=52,leftMargin=52,topMargin=42,bottomMargin=45,title='CityLab research evidence').build(story,onFirstPage=footer,onLaterPages=footer)
    return Path(output)
