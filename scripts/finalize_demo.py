"""Refresh derived corridor summaries and release reports from recorded evidence."""
import json,shutil
from pathlib import Path
from backend.network import DATA,ROOT
from backend.analysis import corridor_outcomes
from backend.models import Scenario
from backend.frames import atomic_json
from backend.exports import report_html,report_pdf,evidence_bundle

def main():
    case=ROOT/'examples/case-study';catalog=json.loads((case/'catalog.json').read_text())
    for row in catalog['jobs']['rows']:
        path=DATA/'jobs'/row[0]/'result.json';r=json.loads(path.read_text())
        r['corridors']=corridor_outcomes(Scenario(**r['scenario']),r['manifest'],r['completed_trips'],r['routes'],r['edge_entries'])
        atomic_json(path,r);shutil.copyfile(path,case/'data/jobs'/row[0]/'result.json')
    report=json.loads((DATA/'tasks/demo-v2b-research/result.json').read_text())
    (case/'report.html').write_text(report_html(report));report_pdf(report,case/'report.pdf')
    Path('output/pdf').mkdir(parents=True,exist_ok=True);shutil.copyfile(case/'report.pdf','output/pdf/CityLab-research-report.pdf')
    evidence_bundle(report,DATA/'tasks/demo-v2b-research')
    b=json.loads((case/'data/jobs/demo-v2b-baseline/result.json').read_text());i=json.loads((case/'data/jobs/demo-v2b-timing/result.json').read_text())
    finding=json.loads((case/'index.json').read_text())['finding']
    text='# Reproducible case study\n\n'+finding+'\n\n'
    text+=f"Research: {report['completed_runs']} actual simulations, conservative maximum {report['plan']['maximum_runs']}, hard cap {report['spec']['budget']}. Five conditions, ten held-out seeds each.\n\n"
    text+='| Candidate | Completion % | Loss s/request | Bus mean s | Feasible |\n|---|---:|---:|---:|---|\n'
    for row in report['evaluation']:
        m=row['metrics'];text+=f"| {row['label']} | {100*m['completion_rate']:.2f} | {m['full_demand_loss']:.2f} | {format(m['bus_mean'],'.2f') if m['bus_mean'] is not None else 'Unavailable'} | {row['feasible']} |\n"
    text+='\n## Adverse and inconclusive findings\n\n'
    for row in report['evaluation']:
        if row['constraint_failures']:text+='- '+row['label']+': '+', '.join(row['constraint_failures'])+'.\n'
    text+='\n## Paired held-out full-demand loss\n\n| Candidate / condition | Mean difference s/request | 95% bootstrap interval | n |\n|---|---:|---|---:|\n'
    for row in report['paired']:
        e=row['effects']['full_demand_loss'];text+=f"| {row['candidate']} / {row['condition']} | {e['mean']:.2f} | {e['ci95'][0]:.2f} to {e['ci95'][1]:.2f} | {e['n']} |\n"
    cal=json.loads((DATA/'tasks/demo-v2b-calibration/result.json').read_text());text+=f"\n## Synthetic calibration\n\nSelected demand {cal['selected']['demand']}; held-out interval count MAE {cal['validation_mae']:.3f}, RMSE {cal['validation_rmse']:.3f} vehicles over {cal['completed_runs']} simulations. The source is SUMO seed 9, not field measurements.\n"
    text+='\nReproduce with `CITYLAB_DATA=data-reproduction python -m scripts.build_demo`, then `python -m scripts.finalize_demo` with the same data root. Inspect the saved specification, manifests, frozen candidates, per-seed results and reports. Intervals are exploratory and not adjusted for multiple comparisons. Generated transit routes cross n11 and n21; the disruption condition closes a service-route edge, leaving that explicit service invalid instead of silently moving its stops.\n'
    controller=json.loads((DATA/'tasks/demo-v2b-controller-study/result.json').read_text())
    text+='\n## Prespecified controller ablation\n\nThe independent controller study runs movement pressure with 5 s priority, no-priority and no-downstream variants plus baseline across the same five conditions with ten held-out seeds. This is a declared mechanistic comparison, not selection using held-out results. It executed '+str(controller['completed_runs'])+' additional runs. Multiplicity caveats apply across both studies.\n\n'
    text+='| Controller variant | Completion % | Loss s/request | Feasible |\n|---|---:|---:|---|\n'
    for row in controller['evaluation']:
        m=row['metrics'];text+=f"| {row['label']} | {100*m['completion_rate']:.2f} | {m['full_demand_loss']:.2f} | {row['feasible']} |\n"
    (case/'controller-report.html').write_text(report_html(controller))
    (ROOT/'docs/CASE_STUDY.md').write_text(text)
if __name__=='__main__':main()
