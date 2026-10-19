"""Validate the four committed Qt catalogs (build uses lrelease, no network)."""
from pathlib import Path
import collections,json,re,xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
def validate():
    catalogs=ROOT/'ScottAI_qt/translations';counts={};reference=None
    for code in ('ru','en','de','es'):
        tree=ET.parse(catalogs/f'ScottAI_{code}.ts');seen={}
        for message in tree.findall('.//message'):
            source=message.findtext('source');translation=message.find('translation')
            assert source and translation is not None and translation.text,(code,source)
            assert translation.get('type')!='unfinished',(code,source)
            assert collections.Counter(re.findall(r'%[1-9][0-9]?',source))==collections.Counter(re.findall(r'%[1-9][0-9]?',translation.text)),(code,source,'placeholders')
            assert collections.Counter(re.findall(r'\*[^\s)]*',source))==collections.Counter(re.findall(r'\*[^\s)]*',translation.text)),(code,source,'file filters')
            assert source not in seen,(code,source,'duplicate')
            seen[source]=translation.text
        if reference is None:reference=set(seen)
        assert set(seen)==reference,(code,'coverage')
        counts[code]=len(seen)
    print(json.dumps(dict(catalogs=counts,complete=True)))
if __name__=='__main__':validate()
