"""Conservative CDL map-pool candidate extraction. No unsourced auto-confirmation."""
import json, re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

MODES={'hardpoint':r'hardpoint','snd':r'(?:search\s*(?:&|and)\s*destroy|s\s*&\s*d)','hijack':r'hijack'}
OFFICIAL={'callofdutyleague.com','www.callofdutyleague.com','callofduty.com','www.callofduty.com'}

class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(); self.lines=[]; self.buf=[]; self.skip=0
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style','noscript'): self.skip+=1
        if tag in ('p','h1','h2','h3','h4','li','tr','br','section') and self.buf:
            self.lines.append(' '.join(self.buf)); self.buf=[]
    def handle_endtag(self,tag):
        if tag in ('script','style','noscript') and self.skip:self.skip-=1
        if tag in ('p','h1','h2','h3','h4','li','tr','section') and self.buf:
            self.lines.append(' '.join(self.buf)); self.buf=[]
    def handle_data(self,data):
        if not self.skip and data.strip(): self.buf.append(data.strip())
    def finish(self):
        if self.buf:self.lines.append(' '.join(self.buf))
        return [' '.join(x.split()) for x in self.lines]

def is_official(url):
    p=urlparse(url);return p.scheme=='https' and p.hostname in OFFICIAL

def extract_candidates(html,known_maps,url):
    """Only flag explicit mode/map co-occurrences for human verification."""
    if not is_official(url):return []
    parser=TextExtractor();parser.feed(html); lines=parser.finish()
    out=[];seen=set()
    for line in lines:
        if len(line)>600:continue
        for mode,pattern in MODES.items():
            if not re.search(pattern,line,re.I):continue
            for name in known_maps:
                if re.search(r'(?<![\w])'+re.escape(name)+r'(?![\w])',line,re.I):
                    key=(mode,name.lower())
                    if key not in seen:
                        seen.add(key);out.append({'mode':mode,'map':name,'evidence':line[:400],'url':url,'status':'unverified'})
    return out

class CandidateStore:
    def __init__(self,path):
        self.path=Path(path)
        try:self.data=json.loads(self.path.read_text(encoding='utf8'))
        except (OSError,ValueError):self.data={}
    def add(self,items):
        new=[]
        for item in items:
            key=f'{item["mode"]}:{item["map"].casefold()}:{item["url"]}'
            if key not in self.data:
                self.data[key]=item;new.append(item)
        if new:self.path.write_text(json.dumps(self.data,ensure_ascii=False,indent=2),encoding='utf8')
        return new
    def pending(self):return [x for x in self.data.values() if x.get('status')=='unverified']
    def set_status(self,mode,map_name,status):
        n=0
        for x in self.data.values():
            if x['mode']==mode and x['map'].casefold()==map_name.casefold():
                x['status']=status;n+=1
        if n:self.path.write_text(json.dumps(self.data,ensure_ascii=False,indent=2),encoding='utf8')
        return n
