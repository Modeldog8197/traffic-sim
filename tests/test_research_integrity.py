import copy
import json
from pathlib import Path
import pytest
from backend.comparison import compare
from backend.calibration import CalibrationSpec
from backend.models import Scenario

def test_unavailable_mean_is_not_zero():
    source=Path(__file__).resolve().parents[1]/'examples/case-study/data/jobs/demo-v2b-baseline/result.json'
    a=json.loads(source.read_text());b=copy.deepcopy(a)
    b['metrics']['mean']=None;b['metrics']['completion_rate']=0
    result=compare(a,b)
    assert 'unavailable' in result['interpretation']
    assert next(r for r in result['rows'] if r['metric']=='mean')['difference'] is None
    assert next(r for r in result['rows'] if r['metric']=='throughput')['baseline']==1560
    b['metrics']['mean']=20;b['metrics']['completion_rate']=None
    assert 'completion unavailable' in compare(a,b)['interpretation']

@pytest.mark.parametrize('field',['fit_seeds','validation_seeds'])
def test_duplicate_calibration_seeds_are_not_independent(field):
    with pytest.raises(ValueError,match='independent'):
        CalibrationSpec(observation_id='fixture',scenario=Scenario(),**{field:[11,11] if field=='fit_seeds' else [101,101]})
