import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pytest
from catalog import clean_url,classify

def test_classifier():
    assert classify('MW4 Hardpoint Munition spawn flip',{'hardpoint':['Munition'],'snd':[],'hijack':[]})==('hardpoint','Munition','spawns','medium')

def test_ambiguous():
    assert classify('great CDL gameplay',{'hardpoint':[],'snd':[],'hijack':[]})[0] is None

def test_urls():
    assert clean_url('https://x.com/a/status/123?utm_source=abc')=='https://x.com/a/status/123'
    with pytest.raises(ValueError): clean_url('http://localhost/x')
    with pytest.raises(ValueError): clean_url('https://x.com.evil.test/')
