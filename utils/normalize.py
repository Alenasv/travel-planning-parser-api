import re
from utils.geo_utils import nearest_metro

EMPTY_VALUES = {"", "-", "—", "–", "none", "null"}

MAX_METRO_DISTANCE_KM = 3.0

DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

DAY_PATTERNS = [
    ("mon", r"пн|понедельник\w*"),
    ("tue", r"вт|вторник\w*"),
    ("wed", r"ср|сред\w*"),
    ("thu", r"чт|четверг\w*"),
    ("fri", r"пт|пятниц\w*"),
    ("sat", r"сб|суббот\w*"),
    ("sun", r"вс|воскресень\w*"),
]
DAY_RE = "|".join(f"(?:{p})" for _, p in DAY_PATTERNS)

TIME_RE = r"(\d{1,2})[:.](\d{2})"
TIME_RANGE_RE = re.compile(
    rf"(?:с\s*)?{TIME_RE}\s*(?:[-–—]|до)\s*{TIME_RE}", re.IGNORECASE
)
DAY_RANGE_RE = re.compile(
    rf"(?:с\s+)?\b({DAY_RE})\b\.?\s*(?:[-–—]|по)\s*\b({DAY_RE})\b", re.IGNORECASE
)
SINGLE_DAY_RE = re.compile(rf"\b({DAY_RE})\b", re.IGNORECASE)

WORK_TIME_LINE_RE = re.compile(
    rf"{TIME_RE}|ежедневно|круглосуточно|выходн|санитарн|\b(?:{DAY_RE})\b",
    re.IGNORECASE,
)

def empty_to_none(value):
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        if value.lower() in EMPTY_VALUES:
            return None
    return value


def nearest_metro_info(coords):
    name, dist = nearest_metro(coords["lat"], coords["lon"])
    if name is None:
        return None, None

    name = re.sub(r"-\d$", "", name)
    if dist > MAX_METRO_DISTANCE_KM:
        return None, dist
    return name, dist


def valid_coords(coords):
    if not isinstance(coords, dict):
        return None
    try:
        lat = float(coords.get("lat"))
        lon = float(coords.get("lon"))
    except (TypeError, ValueError):
        return None
    if not (58.5 <= lat <= 61.5 and 27.5 <= lon <= 35.5):
        return None
    return {"lat": round(lat, 6), "lon": round(lon, 6)}


SPB_BOUNDS = {"lat": (59.63, 60.25), "lon": (29.42, 30.76)}


LENOBL_MARKERS = ("ленинградская область", "гатчин", "всеволожск", "выборг", "тосно",
                  "кировск", "шлиссельбург", "старая ладога", "сосновый бор")


def in_spb(coords, address=None, name=None):
    text = f"{address or ''} {name or ''}".lower()
    if any(marker in text for marker in LENOBL_MARKERS):
        return False
    return (SPB_BOUNDS["lat"][0] <= coords["lat"] <= SPB_BOUNDS["lat"][1]
            and SPB_BOUNDS["lon"][0] <= coords["lon"] <= SPB_BOUNDS["lon"][1])


def extract_work_time_lines(text, max_lines=6):
    text = empty_to_none(text)
    if not text:
        return None

    lines = []
    for line in re.split(r"\n+", text):
        line = line.strip(" ;,")
        if not line or len(line) > 200:
            continue
        if re.search(r"руб|₽|билет|стоимост|цена", line, re.IGNORECASE):
            continue
        if WORK_TIME_LINE_RE.search(line) and line not in lines:
            lines.append(line)

    if not lines:
        return None
    return "\n".join(lines[:max_lines])


def _day_index(token):
    token = token.lower()
    for i, (_, pattern) in enumerate(DAY_PATTERNS):
        if re.fullmatch(pattern, token):
            return i
    return None


def _days_in(segment):
    seg = segment.lower()
    if re.search(r"ежедневно|каждый день|без выходных|круглосуточно", seg):
        return list(range(7))

    days = set()
    for m in DAY_RANGE_RE.finditer(seg):
        a, b = _day_index(m.group(1)), _day_index(m.group(2))
        if a is None or b is None:
            continue
        i = a
        while True:
            days.add(i)
            if i == b:
                break
            i = (i + 1) % 7
        seg = seg.replace(m.group(0), " ")

    for m in SINGLE_DAY_RE.finditer(seg):
        idx = _day_index(m.group(1))
        if idx is not None:
            days.add(idx)

    return sorted(days)


def _fmt(h, m):
    return f"{int(h):02d}:{m}"


def parse_opening_hours(text):
    text = empty_to_none(text)
    if not text:
        return None

    hours = {}
    closed = set()
    pending = []

    for segment in re.split(r"[\n;]|,(?=\s*(?:" + DAY_RE + r"|ежедневно|выходн))", text, flags=re.IGNORECASE):
        segment = segment.strip()
        if not segment:
            continue
        low = segment.lower()

        days = sorted(set(_days_in(low)) | set(pending))
        pending = []

        if "выходн" in low and "без выходных" not in low:
            closed.update(days)
            continue

        if "круглосуточно" in low:
            for d in days or range(7):
                hours[DAYS[d]] = ["00:00", "24:00"]
            continue

        ranges = list(TIME_RANGE_RE.finditer(segment))
        if not ranges:
            pending = days
            continue

        first, last = ranges[0], ranges[-1]
        span = [_fmt(first.group(1), first.group(2)), _fmt(last.group(3), last.group(4))]
        if not days and not hours:
            days = list(range(7))
        for d in days:
            hours[DAYS[d]] = span

    for d in closed:
        hours[DAYS[d]] = None

    if not any(v is not None for v in hours.values()):
        return None
    return {d: hours[d] for d in DAYS if d in hours}


def finalize_place(place):
    p = dict(place)

    for key in ("name", "address", "category", "description", "work_time",
                "image_filename", "phone"):
        p[key] = empty_to_none(p.get(key))

    if not p.get("name"):
        return None, "нет названия"
    if not p.get("address"):
        return None, "нет адреса"
    if len(p["address"]) > 150:
        return None, "мусор в адресе"
    if not p.get("category"):
        return None, "нет категории"

    coords = valid_coords(p.get("coords"))
    if not coords:
        return None, "нет координат"
    p["coords"] = coords

    if not in_spb(coords, p["address"], p["name"]):
        return None, "вне Санкт-Петербурга"

    p["tags"] = list(dict.fromkeys(t.strip().lower() for t in p.get("tags") or [] if t and t.strip()))

    p["metro"], p["metro_distance_km"] = nearest_metro_info(coords)

    p["work_time"] = extract_work_time_lines(p.get("work_time"))
    p["opening_hours"] = parse_opening_hours(p["work_time"])

    return {
        "id": p.get("id"),
        "name": p["name"],
        "category": p["category"],
        "address": p["address"],
        "coords": p["coords"],
        "metro": p["metro"],
        "metro_distance_km": p["metro_distance_km"],
        "description": p["description"],
        "work_time": p["work_time"],
        "opening_hours": p["opening_hours"],
        "tags": p["tags"],
        "phone": p.get("phone"),
        "website": empty_to_none(p.get("website")),
        "image_filename": p["image_filename"],
        "image_source": p.get("image_source"),
        "source": p.get("source"),
        "url": p.get("url"),
    }, None
