#!/usr/bin/env python3
"""Generate a synthetic, deliberately messy stand-in for the Kaggle dataset.

The assessment's dataset is a Kaggle download, so the repository cannot ship
it. This script emits JSON with the same *shape* -- nested objects, mixed
timestamp encodings, and the same families of dirty data described in the brief
-- so the notebook runs end to end before the real file is in place.

The signal in the fraud label is synthetic but not random: fraud rate rises at
night, in card-not-present categories, with transaction amount, with
cardholder age, and with cardholder-to-merchant distance. That is what makes
the charts say something.

    python scripts/generate_sample_data.py --rows 40000 --out data/raw/transactions.json
"""

from __future__ import annotations

import argparse
import json
import math
import random
import string
from datetime import date, datetime, timedelta, timezone

# --------------------------------------------------------------------------
# Reference pools
# --------------------------------------------------------------------------

CATEGORIES = {
    # category: (base fraud multiplier, typical amount mean/sigma for lognormal)
    "grocery_pos": (1.9, (3.9, 0.7)),
    "shopping_net": (2.6, (3.6, 1.1)),
    "misc_net": (2.4, (3.2, 1.2)),
    "gas_transport": (1.4, (3.4, 0.6)),
    "shopping_pos": (1.1, (3.7, 0.9)),
    "entertainment": (0.8, (3.3, 0.9)),
    "food_dining": (0.7, (3.2, 0.7)),
    "personal_care": (0.6, (3.1, 0.7)),
    "health_fitness": (0.6, (3.3, 0.8)),
    "kids_pets": (0.7, (3.3, 0.8)),
    "home": (0.9, (3.6, 0.9)),
    "travel": (1.2, (4.6, 1.0)),
    "misc_pos": (0.8, (3.2, 0.9)),
    "grocery_net": (1.5, (3.4, 0.8)),
}

MERCHANT_STEMS = [
    "Rippin, Kub and Mann", "Heller-Langosh", "Lind-Buckridge", "Kiehn Inc",
    "Beier-Hyatt", "Stroman, Hudson and Erdman", "Kozey-Boehm", "Schmidt Ltd",
    "Predovic Inc", "Dickinson Ltd", "Kuhn LLC", "Swaniawski, Nitzsche and Welch",
    "Hodkiewicz-Gottlieb", "Corwin-Collins", "Reichel LLC", "Goyette Inc",
    "Cormier LLC", "Ruecker Group", "Kerluke-Abshire", "Terry-Huel",
]

FIRST_NAMES = [
    "Jennifer", "Edward", "Stephanie", "Brandon", "Ashley", "Michael", "Tyler",
    "Christina", "Jason", "Nicole", "Daniel", "Rebecca", "Kevin", "Amanda",
    "Joshua", "Melissa", "Andrew", "Laura", "Justin", "Danielle", "Wei",
    "Priya", "Omar", "Sofia", "Hiroshi", "Aisha", "Mateo", "Ingrid",
]
LAST_NAMES = [
    "Banks", "Sanchez", "Gill", "Williams", "Lopez", "Hernandez", "Carter",
    "Nguyen", "Patel", "Okafor", "Kowalski", "Rossi", "Tanaka", "Ahmed",
    "Fischer", "Novak", "Silva", "Andersen", "Murphy", "Zhang",
]
JOBS = [
    "Psychologist, counselling", "Systems developer", "Nature conservation officer",
    "Patent attorney", "Dance movement psychotherapist", "Materials engineer",
    "Designer, ceramics/pottery", "Sports coach", "Radiographer, therapeutic",
    "Special educational needs teacher", "Chartered accountant", "Chief of Staff",
]

# (city, state, zip, lat, long, population)
CITIES = [
    ("Moravian Falls", "NC", "28654", 36.0788, -81.1781, 3495),
    ("Orient", "WA", "99160", 48.8878, -118.2105, 149),
    ("Malad City", "ID", "83252", 42.1808, -112.2620, 4154),
    ("Boulder", "CO", "80301", 40.0274, -105.2519, 108250),
    ("Doe Hill", "VA", "24433", 38.4207, -79.4629, 1939),
    ("Dublin", "PA", "18917", 40.3750, -75.2045, 2158),
    ("Clarksville", "TN", "37040", 36.5298, -87.3595, 151330),
    ("Wales", "AK", "99783", 65.6098, -168.0633, 145),
    ("Houston", "TX", "77036", 29.6997, -95.5350, 2304580),
    ("Brooklyn", "NY", "11226", 40.6465, -73.9570, 2559903),
    ("Mesa", "AZ", "85201", 33.4357, -111.8535, 508958),
    ("Portland", "OR", "97206", 45.4823, -122.5975, 654741),
    ("Greenville", "SC", "29601", 34.8497, -82.4013, 70635),
    ("Fort Wayne", "IN", "46802", 41.0715, -85.1520, 265974),
]

BICS = ["CHASUS33", "BOFAUS3N", "CITIUS33", "WFBIUS6S", "USBKUS44", "PNCCUS33"]


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def luhn_check_digit(partial: str) -> str:
    """Return the digit that makes ``partial`` a Luhn-valid number."""
    total = 0
    for i, ch in enumerate(reversed(partial)):
        d = int(ch)
        if i % 2 == 0:  # position of the check digit is odd from the right
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return str((10 - total % 10) % 10)


def make_card_number(rng: random.Random) -> str:
    bin6 = rng.choice(["453201", "541122", "374512", "601199", "270318"])
    body = "".join(rng.choice(string.digits) for _ in range(16 - len(bin6) - 1))
    partial = bin6 + body
    return partial + luhn_check_digit(partial)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def jitter_point(rng: random.Random, lat: float, lon: float, max_km: float):
    """Offset a coordinate by up to ``max_km`` in a random direction."""
    bearing = rng.uniform(0, 2 * math.pi)
    dist = rng.uniform(0, max_km) / 111.0
    return lat + dist * math.cos(bearing), lon + dist * math.sin(bearing) / max(
        math.cos(math.radians(lat)), 0.2
    )


# --------------------------------------------------------------------------
# Population
# --------------------------------------------------------------------------

def build_cardholders(rng: random.Random, n: int) -> list[dict]:
    people = []
    for _ in range(n):
        city, state, zipc, lat, lon, pop = rng.choice(CITIES)
        birth = date(1940, 1, 1) + timedelta(days=rng.randint(0, 22000))
        people.append(
            {
                "cc_num": make_card_number(rng),
                "first": rng.choice(FIRST_NAMES),
                "last": rng.choice(LAST_NAMES),
                "gender": rng.choice(["M", "F"]),
                "street": f"{rng.randint(1, 9999)} {rng.choice(['Perry Cove', 'Oak Ridge', 'Elm St', 'Lakeview Dr', 'Sunset Blvd', 'Maple Ave'])}",
                "city": city,
                "state": state,
                "zip": zipc,
                "lat": lat,
                "long": lon,
                "city_pop": pop,
                "job": rng.choice(JOBS),
                "dob": birth.isoformat(),
                "cc_bic": rng.choice(BICS),
            }
        )
    return people


def build_merchants(rng: random.Random, n: int) -> list[dict]:
    merchants = []
    for _ in range(n):
        city, state, zipc, lat, lon, _pop = rng.choice(CITIES)
        mlat, mlon = jitter_point(rng, lat, lon, 120)
        # Merchants register between 2012 and a month before the transaction
        # window closes. Transactions are then only ever drawn AFTER their own
        # merchant's registration (see build_row), so "transaction predates
        # merchant" is never an accident of the generator -- it is injected
        # deliberately, at a chosen rate, like every other defect here.
        eff = datetime(2012, 1, 1, tzinfo=timezone.utc) + timedelta(
            days=rng.randint(0, 3258), seconds=rng.randint(0, 86399)
        )
        upd = eff + timedelta(days=rng.randint(1, 1200), seconds=rng.randint(0, 86399))
        merchants.append(
            {
                "merchant": "fraud_" + rng.choice(MERCHANT_STEMS),
                "category": rng.choice(list(CATEGORIES)),
                "merch_lat": round(mlat, 6),
                "merch_long": round(mlon, 6),
                "merch_zipcode": zipc,
                "merch_eff_time": eff,
                "merch_last_update_time": upd,
            }
        )
    return merchants


# --------------------------------------------------------------------------
# Fraud model -- deterministic drivers so the charts have something to find
# --------------------------------------------------------------------------

def fraud_probability(local_hour: int, category: str, amt: float, age: int,
                      distance_km: float, merchant_age_days: float) -> float:
    """``local_hour`` is the cardholder's local (UTC+8) hour, not UTC."""
    p = 0.0024
    p *= CATEGORIES[category][0]
    # Night-time lift: 22:00-03:59 local.
    p *= 6.0 if local_hour in (22, 23, 0, 1, 2, 3) else 1.0
    # Large tickets.
    p *= 1.0 + min(amt / 4000.0, 6.0)
    # Older cardholders are targeted more in this population.
    p *= 1.0 + max(0.0, (age - 55) / 40.0)
    # Card-present fraud clusters far from the registered address. The scale is
    # set against this population's actual geography (US-wide, so distances run
    # to thousands of km); saturating at 300 km would flatten four of the five
    # distance quintiles into one indistinguishable band.
    p *= 1.0 + min(distance_km / 1500.0, 2.0)
    # Recently registered merchants are riskier.
    p *= 2.2 if merchant_age_days < 365 else 1.0
    return min(p, 0.85)


# --------------------------------------------------------------------------
# Dirt injection
# --------------------------------------------------------------------------

def dirty_name(rng: random.Random, first: str, last: str):
    """Return a person_name string, sometimes malformed."""
    roll = rng.random()
    if roll < 0.80:
        return f"{first}, {last}"
    if roll < 0.84:
        return f"  {first} ,  {last}  "           # stray whitespace
    if roll < 0.88:
        return f"{first} {last}"                   # comma missing entirely
    if roll < 0.905:
        return f"{first.upper()}, {last.upper()}"  # shouting
    if roll < 0.925:
        return f"{rng.choice(['Dr.', 'Mr.', 'Mrs.', 'Ms.'])} {first}, {last}"
    if roll < 0.94:
        return f"{first}, {last} {rng.choice(['Jr.', 'III', 'MD', 'DVM', 'PhD'])}"
    if roll < 0.955:
        return f"{first},, {last}"                 # doubled separator
    if roll < 0.968:
        return f"{first}, {last}, {rng.choice(['Jr', 'II'])}"   # three parts
    if roll < 0.978:
        return f"{first.lower()},{last.lower()}"   # no space, lowercase
    if roll < 0.986:
        return ""                                   # empty
    if roll < 0.993:
        return None                                 # genuinely missing
    return rng.choice(["N/A", "null", "-", "???", first])       # junk / single token


def dirty_amount(rng: random.Random, amt: float):
    roll = rng.random()
    if roll < 0.955:
        return round(amt, 2)
    if roll < 0.968:
        return f"${amt:,.2f}"          # currency string with thousands separator
    if roll < 0.976:
        return f"{amt:.2f}"            # numeric-looking string
    if roll < 0.984:
        return round(-amt, 2)          # negative (refund leaked in, or a sign bug)
    if roll < 0.99:
        return 0.0
    if roll < 0.995:
        return None
    return rng.choice(["N/A", "unknown", ""])


def dirty_gender(rng: random.Random, g: str):
    roll = rng.random()
    if roll < 0.90:
        return g
    return rng.choice([g.lower(), "Male" if g == "M" else "Female",
                       "MALE" if g == "M" else "FEMALE", "U", "", None])


def dirty_zip(rng: random.Random, z: str):
    roll = rng.random()
    if roll < 0.93:
        return z
    return rng.choice([z.lstrip("0"), f"{z}-{rng.randint(1000, 9999)}",
                       f" {z} ", int(z), None, ""])


def dirty_state(rng: random.Random, s: str):
    roll = rng.random()
    if roll < 0.94:
        return s
    return rng.choice([s.lower(), f"{s[0]}.{s[1]}.", f" {s}", "XX", None])


def dirty_dob(rng: random.Random, d: str):
    roll = rng.random()
    if roll < 0.92:
        return d
    y, m, dd = d.split("-")
    return rng.choice([f"{m}/{dd}/{y}", f"{dd}-{m}-{y}", f"{d} 00:00:00",
                       "2035-01-01", None, ""])


def dirty_card(rng: random.Random, cc: str):
    roll = rng.random()
    if roll < 0.93:
        return cc
    return rng.choice([
        " ".join(cc[i:i + 4] for i in range(0, 16, 4)),   # spaced
        "-".join(cc[i:i + 4] for i in range(0, 16, 4)),   # dashed
        cc[:-1] + str((int(cc[-1]) + 1) % 10),            # breaks the Luhn check
        cc[:12],                                          # truncated
        int(cc),                                          # numeric, loses nothing but type
        None,
    ])


def dirty_flag(rng: random.Random, f: int):
    roll = rng.random()
    if roll < 0.94:
        return f
    return rng.choice([str(f), "yes" if f else "no", "Y" if f else "N",
                       bool(f), None, 2])


def dirty_coord(rng: random.Random, v: float):
    roll = rng.random()
    if roll < 0.96:
        return round(v, 6)
    return rng.choice([999.0, -999.0, 0.0, str(round(v, 6)), None])


def encode_time(rng: random.Random, dt: datetime):
    """The same instant, encoded a different way each time."""
    roll = rng.random()
    if roll < 0.45:
        return int(dt.timestamp())                       # epoch seconds
    if roll < 0.70:
        return int(dt.timestamp() * 1000)                # epoch milliseconds
    if roll < 0.85:
        return dt.strftime("%Y-%m-%d %H:%M:%S")          # naive UTC string
    if roll < 0.94:
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")         # ISO-8601 with Z
    if roll < 0.97:
        return dt.strftime("%d/%m/%Y %H:%M")             # day-first
    if roll < 0.99:
        return ""
    return None


def dirty_category(rng: random.Random, c: str):
    roll = rng.random()
    if roll < 0.95:
        return c
    return rng.choice([c.upper(), c.replace("_", " ").title(), f" {c} ", c.title()])


# --------------------------------------------------------------------------
# Row assembly
# --------------------------------------------------------------------------

def _corrupt_eff_time(rng: random.Random, merch: dict, ts: datetime) -> datetime:
    roll = rng.random()
    if roll < 0.020:
        return merch["merch_last_update_time"] + timedelta(days=400)
    if roll < 0.035:
        return ts + timedelta(days=rng.randint(30, 400))
    return merch["merch_eff_time"]


def build_row(rng: random.Random, idx: int, person: dict, merch: dict,
              start: datetime, end: datetime) -> dict:
    # A transaction cannot happen at a merchant that does not exist yet.
    low = max(start, merch["merch_eff_time"] + timedelta(hours=1))
    ts = low + timedelta(seconds=rng.randint(0, int((end - low).total_seconds())))

    mu, sigma = CATEGORIES[merch["category"]][1]
    amt = float(min(rng.lognormvariate(mu, sigma), 25000.0))

    age = (ts.date() - date.fromisoformat(person["dob"])).days // 365
    dist = haversine_km(person["lat"], person["long"],
                        merch["merch_lat"], merch["merch_long"])
    merchant_age_days = (ts - merch["merch_eff_time"]).days

    # Fraud follows the cardholder's LOCAL clock, and the analysis renders in
    # UTC+8 -- so the night-time lift has to be applied on the local hour, not
    # the UTC one, or the peak lands eight hours away from where it belongs.
    local_hour = (ts.hour + 8) % 24
    p = fraud_probability(local_hour, merch["category"], amt, age, dist,
                          max(merchant_age_days, 0))
    is_fraud = 1 if rng.random() < p else 0
    if is_fraud:
        # Fraudulent charges skew higher and rounder.
        amt = round(amt * rng.uniform(1.5, 6.0), 2)

    return {
        "Unnamed: 0": idx,
        "trans_date_trans_time": encode_time(rng, ts),
        "cc_num": dirty_card(rng, person["cc_num"]),
        "merchant": merch["merchant"] if rng.random() > 0.03 else f" {merch['merchant']} ",
        "category": dirty_category(rng, merch["category"]),
        "amt": dirty_amount(rng, amt),
        # Nested block -- this is what the notebook has to flatten.
        "personal_detail": {
            "person_name": dirty_name(rng, person["first"], person["last"]),
            "gender": dirty_gender(rng, person["gender"]),
            "address": {
                "street": person["street"],
                "city": person["city"],
                "state": dirty_state(rng, person["state"]),
                "zip": dirty_zip(rng, person["zip"]),
            },
            "lat": dirty_coord(rng, person["lat"]),
            "long": dirty_coord(rng, person["long"]),
            "city_pop": person["city_pop"],
            "job": person["job"],
            "dob": dirty_dob(rng, person["dob"]),
        },
        "trans_num": "".join(rng.choice("0123456789abcdef") for _ in range(32)),
        "merch_lat": merch["merch_lat"],
        "merch_long": merch["merch_long"],
        "is_fraud": dirty_flag(rng, is_fraud),
        "merch_zipcode": merch["merch_zipcode"] if rng.random() > 0.06 else None,
        "merch_last_update_time": encode_time(rng, merch["merch_last_update_time"]),
        # Two impossible-timestamp defects, injected at controlled rates rather
        # than emerging by accident: effective time after last update (~2%), and
        # effective time after the transaction itself (~1.5%).
        "merch_eff_time": encode_time(rng, _corrupt_eff_time(rng, merch, ts)),
        "cc_bic": person["cc_bic"] if rng.random() > 0.04 else None,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rows", type=int, default=40_000)
    ap.add_argument("--out", default="data/raw/transactions.json")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--cardholders", type=int, default=900)
    ap.add_argument("--merchants", type=int, default=650)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    people = build_cardholders(rng, args.cardholders)
    merchants = build_merchants(rng, args.merchants)

    start = datetime(2019, 1, 1, tzinfo=timezone.utc)
    end = datetime(2021, 1, 1, tzinfo=timezone.utc)

    rows = []
    for i in range(args.rows):
        rows.append(build_row(rng, i, rng.choice(people), rng.choice(merchants),
                              start, end))

    # Exact duplicates and replayed transaction numbers -- both show up in real
    # feeds when an upstream job is re-run.
    for _ in range(int(args.rows * 0.012)):
        rows.append(json.loads(json.dumps(rng.choice(rows))))
    for _ in range(int(args.rows * 0.004)):
        clone = json.loads(json.dumps(rng.choice(rows)))
        clone["amt"] = round(rng.uniform(5, 500), 2)
        rows.append(clone)

    # A handful of structurally broken lines: no reader survives these cleanly,
    # which is the point -- they should land in _corrupt_record.
    rng.shuffle(rows)

    with open(args.out, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
        fh.write('{"Unnamed: 0": 999999, "cc_num": , "amt": }\n')
        fh.write("{not json at all}\n")

    fraud = sum(
        1 for r in rows
        if r["is_fraud"] in (1, "1", "yes", "Y", True)
    )
    print(f"wrote {len(rows) + 2:,} lines to {args.out}")
    print(f"  labelled fraud: {fraud:,} ({fraud / len(rows):.2%})")
    print("  + 2 structurally corrupt lines")


if __name__ == "__main__":
    main()
