#!/usr/bin/env python3
import gzip
import io
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from copy import deepcopy
from pathlib import Path

SOURCES = [
    "https://epgshare01.online/epgshare01/epg_ripper_IT1.xml.gz",
    "https://raw.githubusercontent.com/matthuisman/i.mjh.nz/master/PlutoTV/it.xml",
    "https://www.epgitalia.tv/guide2",
    "https://tvit.leicaflorianrobert.dev/epg/list.xml",
]

# ID canonici che userà la nostra M3U.
CANONICAL = {
    "TV2000.it": ["tv2000", "tv 2000"],
    "QVC.it": ["qvc", "qvc hd"],
    "Italia53.it": ["italia 53", "canale italia 53"],
    "Sportitalia.it": ["sportitalia", "sportitalia hd", "sport italia"],
    "iL61.it": ["il61", "il 61", "i l61"],
    "DonnaTV.it": ["donna tv", "donnatv", "donnatv italia"],
    "IlSole24OreTV.it": ["il sole 24 ore tv", "ilsole24ore tv", "ilsole24oretv", "il sole24ore tv"],
    "AlmaTV.it": ["alma tv", "almatv"],
    "Radio105.it": ["radio 105", "radio 105 tv", "105 tv"],
    "BomChannel.it": ["bom channel", "bomchannel"],
    "Catfish.pluto.it": ["catfish"],
}

PLAYLIST_NAMES = {
    "TV2000": "TV2000.it",
    "QVC HD": "QVC.it",
    "Italia 53": "Italia53.it",
    "SportItalia HD": "Sportitalia.it",
    "iL61": "iL61.it",
    "Donna TV": "DonnaTV.it",
    "IlSole24OreTV": "IlSole24OreTV.it",
    "Alma TV": "AlmaTV.it",
    "Radio 105": "Radio105.it",
    "Bom Channel": "BomChannel.it",
    "Catfish (Pluto TV)": "Catfish.pluto.it",
}


def norm(s: str) -> str:
    s = (s or "").lower().strip()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()

ALIASES = {norm(alias): cid for cid, aliases in CANONICAL.items() for alias in aliases}


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 EPG-Merger/1.0"})
    with urllib.request.urlopen(req, timeout=45) as r:
        data = r.read()
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    return data


def channel_display_names(ch):
    return [(el.text or "").strip() for el in ch.findall("display-name")]


def canonical_for_channel(ch):
    for name in channel_display_names(ch):
        cid = ALIASES.get(norm(name))
        if cid:
            return cid
    return None


def parse_source(url):
    data = fetch(url)
    root = ET.fromstring(data)
    if root.tag != "tv":
        raise ValueError(f"Root XML non valido: {root.tag}")
    return root


def merge():
    out = ET.Element("tv", {
        "generator-info-name": "dambro23 unified EPG",
        "generator-info-url": "https://github.com/dambro23/tv",
    })
    channels = {}
    programmes = []
    prog_seen = set()
    id_maps = []

    for url in SOURCES:
        print(f"Scarico: {url}")
        try:
            root = parse_source(url)
        except Exception as e:
            print(f"ATTENZIONE: sorgente saltata: {url}: {e}", file=sys.stderr)
            continue

        id_map = {}
        for ch in root.findall("channel"):
            old_id = ch.get("id", "")
            new_id = canonical_for_channel(ch) or old_id
            id_map[old_id] = new_id
            if new_id not in channels:
                c = deepcopy(ch)
                c.set("id", new_id)
                channels[new_id] = c

        id_maps.append(id_map)
        for p in root.findall("programme"):
            old = p.get("channel", "")
            new = id_map.get(old, old)
            title_el = p.find("title")
            title = (title_el.text or "") if title_el is not None else ""
            key = (new, p.get("start", ""), p.get("stop", ""), title)
            if key in prog_seen:
                continue
            prog_seen.add(key)
            q = deepcopy(p)
            q.set("channel", new)
            programmes.append(q)

    # Metti prima i canali e poi i programmi come da XMLTV.
    for ch in channels.values():
        out.append(ch)
    programmes.sort(key=lambda p: (p.get("channel", ""), p.get("start", "")))
    for p in programmes:
        out.append(p)

    xml = ET.tostring(out, encoding="utf-8", xml_declaration=True)
    Path("epg_italia_unificato.xml").write_bytes(xml)
    with gzip.open("epg_italia_unificato.xml.gz", "wb", compresslevel=9) as f:
        f.write(xml)
    print(f"EPG creato: {len(channels)} canali, {len(programmes)} programmi")


def patch_playlist():
    path = Path("Proiettore_SSIPTV_01_LOGHI_FIX7_EPG.m3u")
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    epg_url = "https://raw.githubusercontent.com/dambro23/tv/main/epg_italia_unificato.xml.gz"
    if lines and lines[0].startswith("#EXTM3U"):
        lines[0] = f'#EXTM3U x-tvg-url="{epg_url}"'

    out = []
    for line in lines:
        if line.startswith("#EXTINF:") and "," in line:
            head, display = line.rsplit(",", 1)
            wanted = PLAYLIST_NAMES.get(display.strip())
            if wanted:
                if re.search(r'\btvg-id="[^"]*"', head):
                    head = re.sub(r'\btvg-id="[^"]*"', f'tvg-id="{wanted}"', head)
                else:
                    head += f' tvg-id="{wanted}"'
                line = head + "," + display
        out.append(line)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    print("Playlist aggiornata con EPG unificato e tvg-id canonici")


if __name__ == "__main__":
    merge()
    patch_playlist()
