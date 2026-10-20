def configure(conn,green,overrides=None):
    plans={}
    for tid in conn.trafficlight.getIDList():
        logic=conn.trafficlight.getAllProgramLogics(tid)[0]
        for index,phase in enumerate(logic.phases):
            if ('G' in phase.state or 'g' in phase.state) and 'y' not in phase.state:
                phase.duration=(overrides or {}).get(tid,{}).get(index,green)
        conn.trafficlight.setProgramLogic(tid,logic)
        conn.trafficlight.setPhase(tid,0)
        plans[tid]=logic
    return plans

def responsive(conn,plans,clock,entered):
    # Keep SUMO's phase order, yellow and all-red. Only alter green end time.
    for tid,logic in plans.items():
        phase=conn.trafficlight.getPhase(tid)
        previous,start=entered.get(tid,(phase,clock))
        if phase!=previous:start=clock
        entered[tid]=(phase,start)
        state=conn.trafficlight.getRedYellowGreenState(tid)
        if 'y' in state or not any(c in 'Gg' for c in state):continue
        age=clock-start
        if age<10:continue
        lanes=conn.trafficlight.getControlledLanes(tid)
        green_lanes={lane for lane,c in zip(lanes,state) if c in 'Gg'}
        red_lanes={lane for lane,c in zip(lanes,state) if c=='r'}-green_lanes
        g=sum(conn.lane.getLastStepHaltingNumber(l) for l in green_lanes)
        r=sum(conn.lane.getLastStepHaltingNumber(l) for l in red_lanes)
        conn.trafficlight.setPhaseDuration(tid,0 if age>=60 or r>g+2 else 2)

class Controller:
    """Cyclic pressure-gated control: never skips a SUMO transition phase."""
    def __init__(self, conn, scenario):
        self.conn, self.s = conn, scenario
        self.plans = configure(conn, scenario.green, scenario.signals)
        self.started, self.priority_started = {}, {}
        self.movements = {}
        self.edge_of_lane = {}
        for jid in self.plans:
            links = conn.trafficlight.getControlledLinks(jid)
            mapping = {}
            for signal_index, group in enumerate(links):
                for incoming, outgoing, via in group:
                    if incoming and outgoing:
                        mapping.setdefault((incoming, outgoing), set()).add(signal_index)
                        for lane in (incoming, outgoing):
                            self.edge_of_lane[lane] = conn.lane.getEdgeID(lane)
            self.movements[jid] = mapping
            if scenario.controller != 'fixed':
                logic = self.plans[jid]
                for phase in logic.phases:
                    if 'y' not in phase.state and any(c in 'Gg' for c in phase.state):
                        phase.duration = scenario.max_green
                conn.trafficlight.setProgramLogic(jid, logic)
                conn.trafficlight.setPhase(jid, 0)

    def step(self, clock, vehicles, routes):
        lane_vehicles = {}
        for vid, vehicle in vehicles.items():
            lane_vehicles.setdefault(vehicle['lane'], []).append((vid, vehicle))
        decisions = {}
        for jid, logic in self.plans.items():
            phase = self.conn.trafficlight.getPhase(jid)
            previous, start = self.started.get(jid, (phase, 0.0))
            if phase != previous:
                start = clock
                self.priority_started.pop(jid, None)
            self.started[jid] = (phase, start)
            age = clock - start
            state = self.conn.trafficlight.getRedYellowGreenState(jid)
            movements = []
            grouped = {}
            for incoming, outgoing in self.movements[jid]:
                grouped.setdefault(incoming, []).append(outgoing)
            for (incoming, outgoing), indices in self.movements[jid].items():
                queued = 0.0
                bus = 0.0
                for vid, row in lane_vehicles.get(incoming, []):
                    route = routes.get(vid) or []
                    ri = row['route_index']
                    next_edge = route[ri + 1] if ri + 1 < len(route) else None
                    targets = [lane for lane in grouped[incoming] if self.edge_of_lane[lane] == next_edge]
                    if outgoing not in targets:
                        continue
                    queued += (1 / len(targets)) if row['speed'] < .1 else 0
                    bus += (1 / len(targets)) if row['kind'] == 'bus' else 0
                downstream = sum(v['speed'] < .1 for _, v in lane_vehicles.get(outgoing, []))
                movements.append({'incoming': incoming, 'outgoing': outgoing, 'signal_indices': sorted(indices), 'queue': queued, 'downstream_queue': downstream, 'bus_requests': bus, 'pressure': queued - (downstream if self.s.pressure_downstream else 0), 'served': any(state[i] in 'Gg' for i in indices)})
            scores = {}
            for i, p in enumerate(logic.phases):
                if 'y' in p.state or not any(c in 'Gg' for c in p.state):
                    continue
                scores[i] = sum(m['pressure'] for m in movements if any(p.state[k] in 'Gg' for k in m['signal_indices']))
            served_lanes = {m['incoming'] for m in movements if m['served']}
            other_lanes = {m['incoming'] for m in movements if not m['served']} - served_lanes
            current_q = sum(v['speed'] < .1 for lane in served_lanes for _, v in lane_vehicles.get(lane, []))
            other_q = sum(v['speed'] < .1 for lane in other_lanes for _, v in lane_vehicles.get(lane, []))
            bus_requests = sum(m['bus_requests'] for m in movements if m['served'])
            nominal = self.s.signals.get(jid, {}).get(phase, self.s.green)
            limit = self.s.max_green if self.s.controller != 'fixed' else max(nominal, self.s.max_green)
            reason = 'Protected yellow / all-red transition'
            action = 'preserve'
            if phase in scores:
                if self.s.controller == 'fixed':
                    terminate = age >= nominal
                    reason = 'Fixed phase plan'
                else:
                    terminate = other_q > current_q + 2 if self.s.controller == 'responsive' else max(scores.values(), default=0) > scores.get(phase, 0) + .5
                    reason = 'Competing incoming queue exceeds current queue' if self.s.controller == 'responsive' else 'Another phase has greater measured pressure'
                if age < self.s.min_green and self.s.controller != 'fixed':
                    reason, action = 'Minimum green safeguard', 'extend'
                elif age >= limit:
                    reason, action = 'Maximum green / cyclic service safeguard', 'end'
                elif bus_requests and self.s.transit_extension and (terminate or (self.s.controller == 'fixed' and age >= nominal - 1)):
                    first = self.priority_started.setdefault(jid, clock)
                    if clock - first < self.s.transit_extension:
                        reason, action = 'Bounded priority for approaching scheduled / generated bus', 'extend'
                    else:
                        reason, action = 'Transit extension budget exhausted', 'end'
                elif self.s.controller == 'fixed':
                    action = 'preserve'
                elif terminate:
                    action = 'end'
                else:
                    reason, action = 'Current green retained by measured queues / pressure', 'extend'
                if action != 'preserve':
                    self.conn.trafficlight.setPhaseDuration(jid, 0 if action == 'end' else 2)
            decisions[jid] = {'time': clock, 'junction': jid, 'phase': phase, 'state': state, 'elapsed': age, 'minimum': self.s.min_green, 'maximum': limit, 'scores': scores, 'movements': movements, 'bus_requests': bus_requests, 'priority_used': min(self.s.transit_extension, clock - self.priority_started[jid]) if jid in self.priority_started else 0, 'priority_limit': self.s.transit_extension, 'action': action, 'reason': reason}
        return decisions
