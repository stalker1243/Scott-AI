"""Summarize Scott's technical timings from JSONL or a support ZIP, without extracting files."""
from pathlib import Path
import argparse
from collections import defaultdict
import json
import math
import re
import zipfile

LIMIT=16*1024*1024
PREFIXES=('setup.','voice_setup.','download.','tts.','voice.','chat.','memory.',
          '00.','01.','02.','llm.','stt.','разбор','команда.','ответ.','веб.')

def sources(path):
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            for info in archive.infolist():
                name=Path(info.filename).name
                if re.fullmatch(r'timings(?:-legacy)?\.jsonl(?:\.[12])?',name) and info.file_size<=LIMIT:
                    with archive.open(info) as stream:
                        yield from stream
    else:
        if path.stat().st_size>LIMIT:
            raise ValueError('Timing file exceeds 16 MiB; use the bounded diagnostic logs.')
        with path.open('rb') as stream:
            yield from stream

def analyze(path):
    stages=defaultdict(list)
    requests=defaultdict(dict)
    playback=[]
    ignored=0
    for raw in sources(Path(path)):
        try:
            if len(raw)>16384:
                raise ValueError('large row')
            row=json.loads(raw)
            name=row['stage']; ms=row['ms']
            if not isinstance(name,str) or not name.startswith(PREFIXES) or not re.fullmatch(r'[\w.:-]{1,96}',name):
                raise ValueError('invalid stage')
            if type(ms) not in (int,float) or not math.isfinite(ms) or ms<0 or type(row.get('ok')) is not bool:
                raise ValueError('invalid sample')
            meta=row.get('meta') if isinstance(row.get('meta'),dict) else {}
            metric=meta.get('metric')
            if metric=='audio_output':
                mode=meta.get('mode');frames=meta.get('frames');rate=meta.get('rate')
                aborted=meta.get('aborted')
                if mode not in ('file','stream') or type(frames) is not int or not 0<=frames<=14400000 \
                        or type(rate) is not int or not 8000<=rate<=192000 or type(aborted) is not bool:
                    raise ValueError('invalid audio diagnostic')
                item=dict(mode=mode,frames=frames,rate=rate,aborted=aborted)
                ident=meta.get('request_id','')
                if isinstance(ident,str) and re.fullmatch('[a-f0-9]{12,32}',ident): item['id']=ident
                start,finish=meta.get('started_ms'),meta.get('finished_ms')
                if type(start) in (int,float) and type(finish) in (int,float) \
                        and math.isfinite(start) and math.isfinite(finish) and 0<=start<=finish:
                    item.update(started_ms=round(start,2),finished_ms=round(finish,2))
                if mode=='stream':
                    counts={key:meta.get(key) for key in ('blocks','underflow_blocks','supply_gap_count')}
                    gap=meta.get('max_supply_gap_ms')
                    if any(type(value) is not int or not 0<=value<=128 for value in counts.values()) \
                            or counts['underflow_blocks']>counts['blocks'] or counts['supply_gap_count']>counts['blocks'] \
                            or type(gap) not in (int,float) or not math.isfinite(gap) or not 0<=gap<=3600000:
                        raise ValueError('invalid stream diagnostic')
                    item.update(counts,max_supply_gap_ms=round(gap,2))
                playback.append(item)
            if metric not in ('duration','milestone','audio_output'):
                metric='milestone' if name.startswith(('voice.','chat.')) and ('.first_' in name or name.endswith(('.total','.result_ready'))) else 'duration'
            stages[(name,metric)].append((ms,row['ok']))
            ident=meta.get('request_id','')
            if isinstance(ident,str) and re.fullmatch('[a-f0-9]{12,32}',ident) and metric=='milestone':
                requests[ident][name]=round(ms,2)
        except (ValueError,TypeError,KeyError,OverflowError):
            ignored+=1
    summary=[]
    by_request=defaultdict(list)
    for item in playback:
        if 'id' in item and 'started_ms' in item: by_request[item['id']].append(item)
    for group in by_request.values():
        previous=None
        for item in sorted(group,key=lambda value:value['started_ms']):
            if previous is not None:
                item['previous_output_gap_ms']=round(max(0,item['started_ms']-previous),2)
            previous=max(previous or 0,item['finished_ms'])
    for (name,metric),samples in sorted(stages.items()):
        values=sorted(ms for ms,_ in samples)
        summary.append(dict(stage=name,metric=metric,calls=len(values),not_ok=sum(not ok for _,ok in samples),
            median_ms=round(values[round(.5*(len(values)-1))],2),p95_ms=round(values[round(.95*(len(values)-1))],2),max_ms=round(values[-1],2)))
    return dict(records=sum(len(values) for values in stages.values()),ignored=ignored,stages=summary,
        requests=[dict(id=ident,milestones_ms=values) for ident,values in sorted(requests.items())],
        playback=dict(sessions=len(playback),stream_sessions=sum(item['mode']=='stream' for item in playback),
            file_sessions=sum(item['mode']=='file' for item in playback),aborted_sessions=sum(item['aborted'] for item in playback),
            driver_underflow_blocks=sum(item.get('underflow_blocks',0) for item in playback),
            supply_gap_count=sum(item.get('supply_gap_count',0) for item in playback),
            max_estimated_supply_gap_ms=max([0]+[item.get('max_supply_gap_ms',0) for item in playback]),
            max_inter_output_gap_ms=max([0]+[item.get('previous_output_gap_ms',0) for item in playback]),
            output=playback),
        notes=['Durations can overlap: do not sum nested stages.',
               'Voice milestones begin when recording closes; VAD end-of-speech wait is outside that interval.',
               'Audio submitted means the device API accepted data; physical sound onset is not measured.',
               'Supply gaps are estimates from block arrival and submitted audio duration, not microphone or speaker measurements.',
               'Driver underflow blocks and late supply are separate signals; file playback has no driver underflow counter.',
               'Gaps between output sessions can include intentional sentence pauses or waiting for the model.',
               'A hard process stop can leave a stage without a completion record; inspect setup.log as well.',
               'A false setup readiness check means preparation is needed, not necessarily a network error.'])

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input',type=Path)
    parser.add_argument('--out',type=Path)
    args=parser.parse_args()
    try:
        output=json.dumps(analyze(args.input),ensure_ascii=False,indent=2)
        if args.out:
            args.out.write_text(output+'\n',encoding='utf-8')
        else:
            print(output)
    except (OSError,ValueError,zipfile.BadZipFile):
        parser.exit(2,'Could not read timings. Check the file or diagnostic ZIP.\n')

if __name__=='__main__':
    main()
