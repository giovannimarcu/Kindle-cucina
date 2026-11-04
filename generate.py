#!/usr/bin/env python3
"""Genera kindle.png (758x1024, grigi 8 bit) con meteo e voli in arrivo.
Uso: python3 generate.py [cartella_output]   |   DEMO=1 usa dati finti."""
import json, math, os, sys, urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo
from PIL import Image, ImageDraw, ImageFont

W, H, S = 758, 1024, 2  # S = supersampling
HERE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(HERE, "config.json")))
TZ = ZoneInfo(CFG["timezone"])
UA = {"User-Agent": "kindle-cucina/1.0 (uso personale)"}
DBG = {"voli": ""}

GIORNI = ["lun", "mar", "mer", "gio", "ven", "sab", "dom"]
GIORNI_L = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]
MESI_L = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"]
MESI = ["gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic"]


def get_json(url, timeout=20):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


# ---------------- meteo ----------------
def weather():
    if os.environ.get("DEMO"):
        return {"current": {"temperature_2m": 11.4, "weather_code": 3, "apparent_temperature": 9.8, "wind_speed_10m": 9.0},
                "daily": {"time": ["2026-11-03", "2026-11-04", "2026-11-05"],
                          "weather_code": [3, 61, 0], "temperature_2m_max": [13.1, 12.0, 14.5],
                          "temperature_2m_min": [7.2, 8.0, 5.1], "precipitation_probability_max": [10, 80, 0]},
                "hourly": {"time": ["2026-11-04T%02d:00" % h for h in range(24)] + ["2026-11-05T%02d:00" % h for h in range(24)],
                           "precipitation_probability": [0]*14 + [60, 70, 80, 70, 20, 0, 0, 0, 0, 0] + [0]*24,
                           "precipitation": [0]*14 + [0.4, 0.8, 1.2, 0.5, 0, 0, 0, 0, 0, 0] + [0]*24}}
    url = ("https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s"
           "&current=temperature_2m,apparent_temperature,weather_code,wind_speed_10m"
           "&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max"
           "&hourly=precipitation_probability,precipitation"
           "&timezone=%s&forecast_days=3" % (CFG["lat"], CFG["lon"], CFG["timezone"].replace("/", "%2F")))
    try:
        return get_json(url)
    except Exception as e:
        print("meteo non disponibile:", e)
        return None


def ore_pioggia(wx, now):
    """Testo con le fasce orarie di pioggia nelle prossime 24 ore."""
    h = (wx or {}).get("hourly")
    if not h:
        return ""
    adesso = now.replace(tzinfo=None, minute=0, second=0, microsecond=0)
    ore = []
    for t, p, mm in zip(h["time"], h["precipitation_probability"], h["precipitation"]):
        dt = datetime.fromisoformat(t)
        if adesso <= dt < adesso.replace(hour=0) + __import__("datetime").timedelta(days=2):
            if (dt - adesso).total_seconds() <= 24 * 3600:
                ore.append((dt, (p or 0) >= 40 or (mm or 0) >= 0.3))
    fasce, cur = [], None
    for dt, pioggia in ore:
        if pioggia and cur is None:
            cur = [dt, dt]
        elif pioggia:
            cur[1] = dt
        elif cur is not None:
            fasce.append(cur); cur = None
    if cur is not None:
        fasce.append(cur)
    if not fasce:
        return "Nessuna pioggia prevista nelle prossime 24 ore"
    pezzi = []
    for a, b in fasce[:2]:
        fine = b.hour + 1
        giorno = "" if a.date() == adesso.date() else "domani "
        pezzi.append("%sdalle %d alle %d" % (giorno, a.hour, fine % 24 if fine != 24 else 24))
    return "Pioggia " + " e ".join(pezzi)


def desc(code):
    if code == 0: return "Sereno", "sun"
    if code in (1, 2): return "Poco nuvoloso", "partly"
    if code == 3: return "Coperto", "cloud"
    if code in (45, 48): return "Nebbia", "fog"
    if code in (51, 53, 55, 56, 57): return "Pioggerella", "rain"
    if code in (61, 63, 65, 66, 67): return "Pioggia", "rain"
    if code in (71, 73, 75, 77, 85, 86): return "Neve", "snow"
    if code in (80, 81, 82): return "Rovesci", "rain"
    if code in (95, 96, 99): return "Temporale", "storm"
    return "Variabile", "cloud"


# ---------------- voli ----------------
def bearing(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def dist_nm(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((p2 - p1) / 2) ** 2 +
         math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 2 * 3440.065 * math.asin(math.sqrt(a))


def flights():
    ap = CFG["airport"]
    mode = CFG.get("mode", "partenze")
    if os.environ.get("DEMO"):
        base = [{"flight": "RYR4821", "city": "Londra", "iata": "STN", "alt": 2300, "casa": True},
                {"flight": "WZZ5113", "city": "Bucarest", "iata": "OTP", "alt": 4800, "casa": False},
                {"flight": "EZY2204", "city": "Parigi", "iata": "CDG", "alt": 7900, "casa": False}]
        return base
    try:
        data = get_json("https://api.adsb.lol/v2/point/%s/%s/%d" % (ap["lat"], ap["lon"], CFG["radius_nm"]))
    except Exception as e:
        print("voli non disponibili:", e)
        DBG["voli"] = "voli err: %s" % str(e)[:40]
        return None
    if "ac" not in data:
        DBG["voli"] = "risposta senza ac: %s" % str(data)[:60]
    tot = len(data.get("ac", []))
    cand = []
    for a in data.get("ac", []):
        call = (a.get("flight") or "").strip()
        alt = a.get("alt_baro")
        if not call or not isinstance(alt, (int, float)) or alt > 12000:
            continue
        if a.get("category") == "A7":  # elicotteri
            continue
        gs, trk, dst = a.get("gs"), a.get("track"), a.get("dst")
        if gs is None or trk is None or dst is None or gs < 90:
            continue
        brg = bearing(a["lat"], a["lon"], ap["lat"], ap["lon"])
        diff = abs((trk - brg + 180) % 360 - 180)  # 0 = verso l'aeroporto, 180 = si allontana
        rate = a.get("baro_rate", a.get("geom_rate", 0)) or 0
        if mode == "arrivi":
            if diff > 65 or alt > 10000:
                continue
        else:
            # partenza: si allontana, sale (o e' ancora bassa), non troppo lontano
            if diff < 100 or dst > 25 or not (rate > 300 or alt < 3000):
                continue
        casa = dist_nm(a["lat"], a["lon"], CFG["lat"], CFG["lon"]) <= CFG.get("casa_nm", 2.5)
        cand.append({"flight": call, "alt": int(alt), "dst": dst, "gs": gs, "casa": casa})
    cand.sort(key=lambda x: x["dst"])
    res = []
    for f in cand[:8]:
        city, iata, ok = "?", "", True
        forte = f["alt"] <= 6000 and f["dst"] <= 15
        try:
            r = get_json("https://api.adsbdb.com/v0/callsign/" + f["flight"], timeout=10)
            fr = r["response"]["flightroute"]
            if mode == "arrivi":
                if fr["destination"]["icao_code"] == ap["icao"]:
                    city, iata = fr["origin"]["municipality"], fr["origin"]["iata_code"]
                elif not forte:
                    ok = False
            else:
                if fr["origin"]["icao_code"] == ap["icao"]:
                    city, iata = fr["destination"]["municipality"], fr["destination"]["iata_code"]
                elif not forte:
                    ok = False
        except Exception:
            pass
        if ok:
            res.append({"flight": f["flight"], "city": city, "iata": iata, "alt": f["alt"], "casa": f["casa"]})
    if "ac" in data:
        DBG["voli"] = "aerei %d, candidati %d, mostrati %d" % (tot, len(cand), len(res))
    res.sort(key=lambda x: (not x["casa"]))  # prima quelli sopra casa
    return res[:6]


# ---------------- disegno ----------------
def font(size, bold=False):
    names = ["DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"]
    for d in ["/usr/share/fonts/truetype/dejavu/", "/usr/share/fonts/dejavu/", "/Library/Fonts/", ""]:
        for n in names:
            try:
                return ImageFont.truetype(d + n, int(size * S))
            except Exception:
                pass
    return ImageFont.load_default()


def icon(d, kind, cx, cy, r):
    cx, cy, r = cx * S, cy * S, r * S
    k = 0  # nero
    def sun(x, y, rr):
        d.ellipse([x - rr * .5, y - rr * .5, x + rr * .5, y + rr * .5], outline=k, width=int(S * 3))
        for i in range(8):
            a = math.radians(i * 45)
            d.line([x + math.cos(a) * rr * .7, y + math.sin(a) * rr * .7,
                    x + math.cos(a) * rr * 1.0, y + math.sin(a) * rr * 1.0], fill=k, width=int(S * 3))
    def cloud(x, y, rr):
        w = int(S * 3)
        d.ellipse([x - rr, y - rr * .1, x - rr * .1, y + rr * .6], fill=255, outline=k, width=w)
        d.ellipse([x - rr * .55, y - rr * .6, x + rr * .35, y + rr * .35], fill=255, outline=k, width=w)
        d.ellipse([x - rr * .0, y - rr * .2, x + rr * .95, y + rr * .6], fill=255, outline=k, width=w)
        d.rectangle([x - rr * .6, y + rr * .05, x + rr * .5, y + rr * .58], fill=255)
        d.line([x - rr * .6, y + rr * .6, x + rr * .5, y + rr * .6], fill=k, width=w)
    if kind == "sun":
        sun(cx, cy, r)
    elif kind == "partly":
        sun(cx - r * .35, cy - r * .3, r * .8); cloud(cx + r * .1, cy + r * .1, r * .8)
    elif kind == "cloud":
        cloud(cx, cy, r)
    elif kind == "fog":
        cloud(cx, cy - r * .2, r * .85)
        for i in range(3):
            y = cy + r * (.55 + i * .22)
            d.line([cx - r * .8, y, cx + r * .8, y], fill=k, width=int(S * 3))
    elif kind == "rain":
        cloud(cx, cy - r * .25, r * .85)
        for i in range(3):
            x = cx - r * .5 + i * r * .5
            d.line([x, cy + r * .5, x - r * .2, cy + r * .95], fill=k, width=int(S * 3))
    elif kind == "snow":
        cloud(cx, cy - r * .25, r * .85)
        for i in range(3):
            x = cx - r * .5 + i * r * .5
            d.ellipse([x - S * 3, cy + r * .6 - S * 3, x + S * 3, cy + r * .6 + S * 3], fill=k)
    elif kind == "storm":
        cloud(cx, cy - r * .25, r * .85)
        d.polygon([(cx + r * .05, cy + r * .3), (cx - r * .25, cy + r * .75), (cx, cy + r * .72),
                   (cx - r * .15, cy + r * 1.05), (cx + r * .3, cy + r * .6), (cx + r * .05, cy + r * .62)], fill=k)


def text(d, xy, s, f, fill=0, anchor="la"):
    d.text((xy[0] * S, xy[1] * S), s, font=f, fill=fill, anchor=anchor)


def hline(d, y, x0=30, x1=W - 30, w=2, fill=0):
    d.line([x0 * S, y * S, x1 * S, y * S], fill=fill, width=int(w * S))


def render(wx, fl, now):
    im = Image.new("L", (W * S, H * S), 255)
    d = ImageDraw.Draw(im)
    # intestazione
    text(d, (30, 24), CFG["place"], font(40, True))
    data = "%s %d %s" % (GIORNI_L[now.weekday()], now.day, MESI_L[now.month - 1])
    text(d, (W - 30, 22), data, font(32, True), anchor="ra")
    text(d, (W - 30, 62), "aggiornato alle %02d:%02d" % (now.hour, now.minute), font(22), fill=70, anchor="ra")
    hline(d, 92, w=4)
    # meteo attuale
    if wx:
        c = wx["current"]
        name, kind = desc(c["weather_code"])
        icon(d, kind, 150, 225, 85)
        text(d, (300, 130), "%d°" % round(c["temperature_2m"]), font(140, True))
        text(d, (300, 295), name, font(36))
        text(d, (30, 345), "percepita %d°   vento %d km/h" % (round(c.get("apparent_temperature", c["temperature_2m"])),
                                                              round(c.get("wind_speed_10m", 0))), font(24), fill=60)
        rp = ore_pioggia(wx, now)
        if rp:
            text(d, (30, 378), rp, font(26, True))
        # prossimi giorni
        dd = wx["daily"]
        colw = (W - 60) / 3
        for i in range(3):
            x0 = 30 + i * colw
            label = "Oggi" if i == 0 else GIORNI[datetime.fromisoformat(dd["time"][i]).weekday()].capitalize()
            _, kd = desc(dd["weather_code"][i])
            text(d, (x0 + colw / 2, 430), label, font(26, True), anchor="ma")
            icon(d, kd, x0 + colw / 2, 505, 36)
            text(d, (x0 + colw / 2, 560), "%d° / %d°" % (round(dd["temperature_2m_max"][i]), round(dd["temperature_2m_min"][i])),
                 font(26), anchor="ma")
            text(d, (x0 + colw / 2, 595), "pioggia %d%%" % (dd["precipitation_probability_max"][i] or 0), font(20), fill=70, anchor="ma")
    else:
        text(d, (30, 200), "Meteo non disponibile", font(36))
    hline(d, 645, w=4)
    # treni (segnaposto, in preparazione)
    text(d, (30, 665), "Treni da Treviglio Centrale", font(30, True))
    text(d, (30, 720), "In preparazione", font(28), fill=90)
    return im.resize((W, H), Image.LANCZOS)


def probe_tabellone(out):
    """Test una tantum: legge la pagina partenze dell'aeroporto e scrive cosa trova."""
    import re
    righe = []
    ua = {"User-Agent": "Kindle-cucina-test/1.0 (uso personale, una sola richiesta)"}
    def prendi(url):
        req = urllib.request.Request(url, headers=ua)
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.status, r.headers.get("Content-Type", ""), r.read().decode("utf-8", "replace")
    pagine = ["https://www.milanbergamoairport.it/it/voli/partenze/",
              "https://www.milanbergamoairport.it/en/flights/departures/"]
    for u in pagine:
        righe.append("== " + u)
        try:
            st, ct, body = prendi(u)
            righe.append("stato %s tipo %s lunghezza %d" % (st, ct, len(body)))
            righe.append("contiene 'FR' o orari: %s" % bool(re.search(r"\b\d{2}:\d{2}\b", body)))
            urls = set(re.findall(r"https?://[^\"'\s<>)]*", body))
            utili = sorted(x for x in urls if re.search(r"api|flight|voli|json|departure|partenz", x, re.I))
            righe.append("indirizzi interessanti: %d" % len(utili))
            righe += utili[:30]
            righe.append("--- inizio pagina ---")
            righe.append(re.sub(r"\s+", " ", body)[:1500])
        except Exception as e:
            righe.append("ERRORE %r" % (e,))
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "test_tabellone.txt"), "w") as f:
        f.write("\n".join(righe))


def probe_treni(out):
    """Test una tantum: prova ViaggiaTreno per le partenze da Treviglio."""
    import re
    righe = []
    ua = {"User-Agent": "Kindle-cucina-test/1.0 (uso personale, poche richieste)"}
    base = "https://www.viaggiatreno.it/infomobilita/resteasy/viaggiatreno/"
    def prendi(url):
        req = urllib.request.Request(url, headers=ua)
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.status, r.read().decode("utf-8", "replace")
    try:
        st, body = prendi(base + "cercaStazione/Treviglio")
        righe.append("cercaStazione stato %s" % st)
        righe.append(body[:800])
        ids = re.findall(r'"id"\s*:\s*"(S\d+)"', body)
    except Exception as e:
        righe.append("cercaStazione ERRORE %r" % (e,))
        ids = []
    adesso = datetime.now(TZ)
    quando = adesso.strftime("%a %b %d %Y %H:%M:%S GMT+0100")
    for sid in ids[:3]:
        try:
            st, body = prendi(base + "partenze/%s/%s" % (sid, urllib.request.quote(quando)))
            righe.append("== partenze %s stato %s lunghezza %d" % (sid, st, len(body)))
            righe.append(body[:2500])
        except Exception as e:
            righe.append("== partenze %s ERRORE %r" % (sid, e))
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "test_treni.txt"), "w") as f:
        f.write("\n".join(righe))


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else HERE
    os.makedirs(out, exist_ok=True)
    now = datetime.now(TZ)
    im = render(weather(), None, now).convert("L")
    # solo grigi 8 bit, nessun canale alpha
    path = os.path.join(out, "kindle.png")
    im.save(path, optimize=True)
    chk = Image.open(path)
    assert chk.size == (W, H) and chk.mode == "L", (chk.size, chk.mode)
    print("ok", path, chk.size, chk.mode)
    try:
        if json.load(open(os.path.join(HERE, "config.json"))).get("test_tabellone"):
            probe_tabellone(out)
            probe_treni(out)
    except Exception as e:
        print("probe errore", e)


if __name__ == "__main__":
    main()
