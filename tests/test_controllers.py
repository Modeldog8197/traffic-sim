from backend.controllers import responsive
class Traffic:
    phase=0
    calls=[]
    def getPhase(self,id):return self.phase
    def getRedYellowGreenState(self,id):return 'GGrr' if self.phase==0 else 'yyrr'
    def getControlledLanes(self,id):return ['a','b','c','d']
    def setPhaseDuration(self,id,value):self.calls.append(value)
class Lane:
    def getLastStepHaltingNumber(self,lane):return 10 if lane in ['c','d'] else 0
class Conn:
    trafficlight=Traffic();lane=Lane()
def test_responsive_guards():
    c=Conn();c.trafficlight.calls=[];entered={}
    responsive(c,{'j':None},0,entered);responsive(c,{'j':None},9,entered)
    assert not c.trafficlight.calls
    responsive(c,{'j':None},10,entered);assert c.trafficlight.calls==[0]
    c.trafficlight.phase=1;responsive(c,{'j':None},11,entered)
    assert c.trafficlight.calls==[0] # never modifies yellow, never jumps phases
    c.trafficlight.phase=0
