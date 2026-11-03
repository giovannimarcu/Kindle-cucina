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

GIORNI = ["lun", "mar", "mer", "gio", "ven", "sab", "dom"]
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
                          "temperature_2m_min": [7.2, 8.0, 5.1], "precipitation_probability_max": [10, 80, 0]}}
    url = ("https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s"
           "&current=temperature_2m,apparent_temperature,weather_code,wind_speed_10m"
           "&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max"
           "&timezone=%s&forecast_days=3" % (CFG["lat"], CFG["lon"], CFG["timezone"].replace("/", "%2F")))
    try:
        return get_json(url)
    except Exception as e:
        print("meteo non disponibile:", e)
        return None


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


def flights():
    ap = CFG["airport"]
    if os.environ.get("DEMO"):
        return [{"flight": "RYR4821", "city": "Londra", "iata": "STN", "eta": 4, "alt": 2300},
                {"flight": "WZZ5113", "city": "Bucarest", "iata": "OTP", "eta": 9, "alt": 4800},
                {"flight": "EZY2204", "city": "Parigi", "iata": "CDG", "eta": 17, "alt": 7900}]
    try:
        data = get_json("https://api.adsb.lol/v2/point/%s/%s/%d" % (ap["lat"], ap["lon"], CFG["radius_nm"]))
    except Exception as e:
        print("voli non disponibili:", e)
        return None
    out = []
    for a in data.get("ac", []):
        call = (a.get("flight") or "").strip()
        alt = a.get("alt_baro")
        if not call or not isinstance(alt, (int, float)) or alt > 10000:
            continue
        gs, trk, dst = a.get("gs"), a.get("track"), a.get("dst")
        if gs is None or trk is None or dst is None or gs < 60:
            continue
        brg = bearing(a["lat"], a["lon"], ap["lat"], ap["lon"])
        diff = abs((trk - brg + 180) % 360 - 180)
        if diff > 50:  # non sta puntando verso l'aeroporto
            continue
        out.append({"flight": call, "alt": int(alt), "eta": max(1, round(dst / gs * 60)), "dst": dst})
    out.sort(key=lambda x: x["eta"])
    res = []
    for f in out[:8]:
        city, iata, ok = "?", "", True
        try:
            r = get_json("https://api.adsbdb.com/v0/callsign/" + f["flight"], timeout=10)
            fr = r["response"]["flightroute"]
            if fr["destination"]["icao_code"] != ap["icao"]:
                ok = False  # va altrove (es. sorvolo)
            city, iata = fr["origin"]["municipality"], fr["origin"]["iata_code"]
        except Exception:
            pass  # rotta sconosciuta: lo mostriamo comunque se punta all'aeroporto
        if ok:
            res.append({"flight": f["flight"], "city": city, "iata": iata, "eta": f["eta"], "alt": f["alt"]})
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
    data = "%s %d %s" % (GIORNI[now.weekday()], now.day, MESI[now.month - 1])
    text(d, (W - 30, 30), data, font(30), anchor="ra")
    hline(d, 82, w=4)
    # meteo attuale
    if wx:
        c = wx["current"]
        name, kind = desc(c["weather_code"])
        icon(d, kind, 150, 215, 85)
        text(d, (300, 120), "%d°" % round(c["temperature_2m"]), font(140, True))
        text(d, (300, 285), name, font(36))
        text(d, (30, 335), "percepita %d°   vento %d km/h" % (round(c.get("apparent_temperature", c["temperature_2m"])),
                                                              round(c.get("wind_speed_10m", 0))), font(24), fill=60)
        # prossimi giorni
        dd = wx["daily"]
        colw = (W - 60) / 3
        for i in range(3):
            x0 = 30 + i * colw
            label = "Oggi" if i == 0 else GIORNI[datetime.fromisoformat(dd["time"][i]).weekday()].capitalize()
            _, kd = desc(dd["weather_code"][i])
            text(d, (x0 + colw / 2, 385), label, font(26, True), anchor="ma")
            icon(d, kd, x0 + colw / 2, 460, 36)
            text(d, (x0 + colw / 2, 515), "%d° / %d°" % (round(dd["temperature_2m_max"][i]), round(dd["temperature_2m_min"][i])),
                 font(26), anchor="ma")
            text(d, (x0 + colw / 2, 550), "pioggia %d%%" % (dd["precipitation_probability_max"][i] or 0), font(20), fill=70, anchor="ma")
    else:
        text(d, (30, 200), "Meteo non disponibile", font(36))
    hline(d, 610, w=4)
    # voli
    text(d, (30, 628), "In arrivo a %s" % CFG["airport"]["name"], font(30, True))
    y = 685
    if fl is None:
        text(d, (30, y), "Dati voli non disponibili", font(28), fill=70)
    elif not fl:
        text(d, (30, y), "Nessun volo in arrivo adesso", font(28), fill=70)
    else:
        for f in fl[:6]:
            text(d, (30, y), f["flight"], font(26, True))
            citta = (f["city"] or "?")[:16] + ((" (%s)" % f["iata"]) if f["iata"] else "")
            text(d, (230, y), citta, font(26))
            text(d, (W - 30, y), "%d min" % f["eta"], font(26, True), anchor="ra")
            hline(d, y + 46, w=1, fill=150)
            y += 54
    # piede
    hline(d, 975, w=2)
    text(d, (W / 2, 990), "aggiornato %02d:%02d" % (now.hour, now.minute), font(20), fill=90, anchor="ma")
    return im.resize((W, H), Image.LANCZOS)


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else HERE
    os.makedirs(out, exist_ok=True)
    now = datetime.now(TZ)
    im = render(weather(), flights(), now).convert("L")
    # solo grigi 8 bit, nessun canale alpha
    path = os.path.join(out, "kindle.png")
    im.save(path, optimize=True)
    chk = Image.open(path)
    assert chk.size == (W, H) and chk.mode == "L", (chk.size, chk.mode)
    print("ok", path, chk.size, chk.mode)


if __name__ == "__main__":
    main()
