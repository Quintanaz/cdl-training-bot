import sqlite3
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS clips (
 id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL, url TEXT NOT NULL,
 title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', mode TEXT,
 map_name TEXT, topic TEXT, confidence TEXT NOT NULL DEFAULT 'unknown',
 status TEXT NOT NULL DEFAULT 'pending', source TEXT NOT NULL,
 submitted_by TEXT NOT NULL, created_at TEXT NOT NULL,
 published_channel INTEGER, published_message INTEGER,
 UNIQUE(guild_id, url)
);
"""
class Store:
 def __init__(self, path):
  self.db=sqlite3.connect(path)
  self.db.row_factory=sqlite3.Row
  self.db.executescript(SCHEMA)
 def add(self, guild, url, title, desc, mode, map_name, topic, conf, source, who):
  try:
   with self.db:
    cur=self.db.execute("INSERT INTO clips (guild_id,url,title,description,mode,map_name,topic,confidence,source,submitted_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
     (guild,url,title[:300],desc[:1500],mode,map_name,topic,conf,source,who,datetime.now(timezone.utc).isoformat()))
   return cur.lastrowid
  except sqlite3.IntegrityError:
   return None
 def get(self, guild, clip_id):
  return self.db.execute("SELECT * FROM clips WHERE guild_id=? AND id=?",(guild,clip_id)).fetchone()
 def pending(self,guild,limit=10):
  return self.db.execute("SELECT * FROM clips WHERE guild_id=? AND status='pending' ORDER BY id LIMIT ?",(guild,limit)).fetchall()
 def update(self,guild,clip_id,status,channel=None,message=None):
  with self.db: self.db.execute("UPDATE clips SET status=?,published_channel=?,published_message=? WHERE guild_id=? AND id=? AND status='pending'",(status,channel,message,guild,clip_id))
 def search(self,guild,query):
  s='%'+query.lower()+'%'
  return self.db.execute("SELECT * FROM clips WHERE guild_id=? AND status='approved' AND (LOWER(title) LIKE ? OR LOWER(description) LIKE ? OR LOWER(map_name) LIKE ? OR LOWER(topic) LIKE ?) ORDER BY id DESC LIMIT 10",(guild,s,s,s,s)).fetchall()
 def stats(self,guild):
  return dict(self.db.execute("SELECT status,count(*) AS n FROM clips WHERE guild_id=? GROUP BY status",(guild,)).fetchall())
