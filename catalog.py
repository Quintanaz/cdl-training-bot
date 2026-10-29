"""Static channel specifications and conservative topic classifier."""
import re
from urllib.parse import urlsplit, urlunsplit

CATEGORIES = {
    "00・START HERE": ["welcome-and-guide", "cdl-rules-and-map-pool", "patch-notes-and-meta", "resources-and-creators"],
    "01・COMPETITIVE FUNDAMENTALS": ["spawn-system", "spawn-scenarios", "map-control", "positioning-and-angles", "timings-and-routes", "minimap-awareness", "teamwork-and-trading", "comms-and-information", "gunskill-and-movement", "decision-making"],
    "02・HARDPOINT": ["hp-fundamentals", "hp-spawn-logic", "hp-rotations-and-timings", "hp-setups-and-breaks", "hp-map-library"],
    "03・SEARCH & DESTROY": ["snd-fundamentals", "snd-nade-spots", "snd-opening-strats", "snd-positioning", "snd-clutches-and-retakes", "snd-map-library"],
    "04・HIJACK": ["hijack-fundamentals", "hijack-spike-control", "hijack-attacks-and-defense", "hijack-team-setups", "hijack-map-library"],
    "05・TRAINING & REVIEW": ["daily-training", "vod-review", "mistakes-to-fix", "practice-drills", "scrim-notes", "alex-and-me-progress"],
    "06・CONTENT COLLECTION": ["incoming-clips", "clips-to-review", "verified-guides", "outdated-information", "content-requests"],
}
FORUMS = {"hp-map-library", "snd-map-library", "hijack-map-library"}
FORUM_TAGS = {
 "hp-map-library": ["Spawns", "Rotations", "Positioning", "Setups", "Breaks", "Nades", "VODs"],
 "snd-map-library": ["Nades", "Openings", "Attack", "Defense", "Positioning", "Postplant", "Retakes", "VODs"],
 "hijack-map-library": ["Spike", "Openings", "Attack", "Defense", "Positioning", "Situations", "VODs"],
}
TOPICS = {
 "hardpoint": ["spawns", "rotations", "positioning", "setups", "breaks", "nades", "vods"],
 "snd": ["nades", "openings", "attack", "defense", "positioning", "postplant", "retakes", "vods"],
 "hijack": ["spike", "openings", "attack", "defense", "positioning", "situations", "vods"],
}
KEYWORDS = {
 "spawns": ["spawn", "anchoring", "anchor", "flip", "blocker"],
 "rotations": ["rotation", "rotate", "rotating", "hill order", "p2", "p3", "p4", "p5"],
 "positioning": ["position", "angle", "headglitch", "head glitch", "power spot", "crossfire", "off-angle"],
 "setups": ["setup", "set up", "hold"],
 "breaks": ["break", "clear hill", "pinch"],
 "nades": ["nade", "grenade", "stun", "flash", "semtex", "lineup", "utility"],
 "vods": ["vod", "pov", "breakdown", "analysis"],
 "openings": ["opening", "rush route", "first blood", "early round"],
 "attack": ["attack", "execute", "site hit", "a hit", "b hit", "plant"],
 "defense": ["defend", "defense", "defence", "site hold"],
 "postplant": ["postplant", "post-plant", "bomb down", "after plant"],
 "retakes": ["retake", "clutch", "1v2", "1v3", "1v1"],
 "spike": ["data spike", "spike", "upload", "pass"],
 "situations": ["recover", "outnumbered", "reset"],
}
MODE_ALIASES = {
 "hardpoint": ["hardpoint", "hp", "hill"],
 "snd": ["search and destroy", "search & destroy", "snd", "s&d"],
 "hijack": ["hijack", "data spike", "comm station"],
}
SOURCE_HOSTS = {"x.com", "twitter.com", "www.x.com", "www.twitter.com", "reddit.com", "www.reddit.com", "old.reddit.com", "redd.it"}

def clean_url(value):
    url = urlsplit(value.strip())
    if url.scheme != "https" or url.hostname not in SOURCE_HOSTS:
        raise ValueError("Use an HTTPS X/Twitter or Reddit post URL")
    return urlunsplit(("https", url.netloc.lower(), url.path.rstrip("/"), "", ""))

def matches(text, phrase):
    return bool(re.search(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", text))

def classify(text, maps):
    lower = text.lower()
    scored = {mode: sum(1 for word in words if matches(lower, word)) for mode, words in MODE_ALIASES.items()}
    best_mode = max(scored, key=scored.get)
    if scored[best_mode] == 0 or list(scored.values()).count(scored[best_mode]) > 1:
        return None, None, None, "unknown"
    known = [m for m in maps.get(best_mode, []) if matches(lower, m.lower())]
    map_name = known[0] if len(known) == 1 else None
    candidates = TOPICS[best_mode]
    topic_score = {t: sum(1 for k in KEYWORDS[t] if matches(lower, k)) for t in candidates}
    topic = max(topic_score, key=topic_score.get)
    if topic_score[topic] == 0 or list(topic_score.values()).count(topic_score[topic]) > 1:
        topic = None
    confidence = "medium" if map_name and topic else "low"
    return best_mode, map_name, topic, confidence
