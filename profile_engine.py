import cProfile,pstats
from pathlib import Path
from backend.engine import execute
from backend.models import Scenario
p=cProfile.Profile();p.enable();execute(Scenario(duration=120,clearance=180,demand=160),Path('data/profile-v2'));p.disable();p.dump_stats('docs/engine-profile.prof')
with open('docs/engine-profile.txt','w') as f:pstats.Stats(p,stream=f).sort_stats('cumulative').print_stats(30)
