import sys,json
from backend.network import DATA,describe
from scripts.import_osm import main

def test_bounded_osm_import(tmp_path,monkeypatch):
    path=tmp_path/'small.osm'
    path.write_text('''<osm version="0.6"><node id="1" lat="12.91" lon="77.64"/><node id="2" lat="12.91" lon="77.645"/><node id="3" lat="12.914" lon="77.645"/><node id="4" lat="12.914" lon="77.64"/>
    <way id="10"><nd ref="1"/><nd ref="2"/><nd ref="3"/><tag k="highway" v="residential"/><tag k="lanes" v="2"/><tag k="maxspeed" v="30"/></way>
    <way id="11"><nd ref="3"/><nd ref="4"/><nd ref="1"/><tag k="highway" v="residential"/><tag k="oneway" v="yes"/><tag k="lanes" v="1"/><tag k="maxspeed" v="40"/></way></osm>''')
    monkeypatch.setattr(sys,'argv',['import_osm',str(path)]);identifier=main()
    folder=DATA/'networks'/identifier
    net=describe(folder.name);assert not net['synthetic'];assert len(net['roads'])>=3
    assert any(abs(r['speed']-8.33)<.1 for r in net['roads'])
    assert (folder/'metadata.json').exists()
