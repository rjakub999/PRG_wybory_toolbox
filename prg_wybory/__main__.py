import argparse
import json
from .pipeline import run,diagnostics,STAGES

def main():
    parser=argparse.ArgumentParser(description='PRG Wybory — Python Toolbox / CLI')
    parser.add_argument('--config')
    parser.add_argument('--through',choices=['all',*STAGES],default='all')
    parser.add_argument('--resume',help='Katalog konkretnego przebiegu z manifest.json')
    parser.add_argument('--diagnostics',action='store_true')
    args=parser.parse_args()
    if args.diagnostics: print(json.dumps(diagnostics(),ensure_ascii=False,indent=2))
    elif args.config: print(run(args.config,args.through,args.resume))
    else: parser.error('Podaj --config lub --diagnostics')

if __name__=='__main__': main()
