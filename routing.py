import heapq
from .network import describe

def route(net, trip, edits):
    start,end=trip['from'],trip['to']; kind=trip['kind']
    def permitted(e):
        edit=edits.get(e.getID())
        return (not edit or (not edit.closed and kind in edit.allowed)) and any(l.allows(kind) for l in e.getLanes())
    if trip.get('service_route'):
        path = trip['service_route']
        return path if all(permitted(net.getEdge(e)) for e in path) else None
    if not permitted(net.getEdge(start)) or not permitted(net.getEdge(end)): return None
    q=[(0,start,[])]; seen=set()
    while q:
        cost,eid,path=heapq.heappop(q)
        if eid in seen:continue
        seen.add(eid); edge=net.getEdge(eid); path=path+[eid]
        if eid==end:return path
        for nxt,connections in edge.getOutgoing().items():
            if permitted(nxt) and any(c.getFromLane().allows(kind) and c.getToLane().allows(kind) for c in connections):
                speed=edits[nxt.getID()].speed if nxt.getID() in edits else nxt.getSpeed()
                heapq.heappush(q,(cost+nxt.getLength()/speed,nxt.getID(),path))
    return None

def validate_network(s,trips,net,network_info=None,allow_all_invalid=False):
    plans={j['id']:j['phases'] for j in (network_info or describe(s.network))['junctions'] if j['signal']}
    for jid,phases in s.signals.items():
        if jid not in plans:raise ValueError(f'Unknown signal {jid}. Select a signalised junction.')
        for index in phases:
            if index<0 or index>=len(plans[jid]) or not plans[jid][index]['editable']:raise ValueError(f'{jid} phase {index} is not an editable green phase. Yellow/all-red must stay intact.')
    ids={e.getID() for e in net.getEdges()}
    unknown=set(s.roads)-ids
    if unknown:raise ValueError('Unknown road IDs: '+', '.join(sorted(unknown)))
    for name, edges in s.corridors.items():
        if not edges or set(edges)-ids: raise ValueError(f'Corridor {name} must contain known directed road IDs.')
    routes={t['id']:route(net,t,s.roads) for t in trips}
    invalid=[t['id'] for t in trips if not routes[t['id']]]
    if len(invalid)==len(trips) and not allow_all_invalid: raise ValueError('All trips are disconnected. Reopen an origin, destination, or connecting road.')
    return routes,invalid
