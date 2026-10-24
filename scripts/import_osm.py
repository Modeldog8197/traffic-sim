"""Import an HSR OSM XML file using the same validation as the application."""
import argparse,json
from backend.imports import convert_osm
from backend.network import describe
from pathlib import Path

def main():
    p=argparse.ArgumentParser();p.add_argument('extract',type=Path);a=p.parse_args()
    result=describe(convert_osm(a.extract.read_bytes(),source='Local OSM XML import'))
    print(json.dumps({'id':result['id'],'roads':len(result['roads']),'topology':result['topology']},indent=2))
    return result['id']
if __name__=='__main__':main()
