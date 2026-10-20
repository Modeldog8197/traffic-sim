# Keep API test jobs/scenarios isolated from a running local workspace.
import os,tempfile
os.environ['CITYLAB_DATA']=tempfile.mkdtemp(prefix='citylab-tests-')
