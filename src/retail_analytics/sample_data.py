"""Génération d'un échantillon SYNTHÉTIQUE au schéma d'Online Retail II.

⚠️ Ces données sont INVENTÉES (graine fixe, reproductibles). Elles servent uniquement à faire tourner et
tester le pipeline quand le fichier UCI n'est pas disponible. Aucun résultat obtenu dessus ne doit être
présenté comme un résultat réel. Produits, clients et montants sont fictifs ; la période (2024-2025) est
volontairement différente de celle du vrai dataset (2009-2011) pour éviter toute confusion.

Les problèmes de qualité du vrai dataset sont injectés volontairement et en quantités connues :
clients manquants, doublons exacts, annulations (factures 'C'), ajustements de stock, prix nuls,
codes non-produits (POST, M, BANK CHARGES), descriptions manquantes, ajustement 'A', lignes illisibles.
"""

from __future__ import annotations

import csv
import random
from datetime import datetime, timedelta
from pathlib import Path

HEADER = ["Invoice", "StockCode", "Description", "Quantity", "InvoiceDate", "Price", "Customer ID", "Country"]

PRODUCTS = [
    ("70001", "CERAMIC TEA CUP SAGE", 2.10), ("70002", "CERAMIC TEA CUP ROSE", 2.10),
    ("70003", "LINEN TABLE NAPKIN SET", 6.50), ("70004", "BAMBOO SERVING TRAY", 8.95),
    ("70005", "GLASS STORAGE JAR SMALL", 1.65), ("70006", "GLASS STORAGE JAR LARGE", 2.95),
    ("70007", "PAPER LANTERN WHITE", 0.85), ("70008", "PAPER LANTERN BLUE", 0.85),
    ("70009", "WOODEN PHOTO FRAME", 4.25), ("70010", "COTTON TOTE BAG STRIPE", 1.95),
    ("70011", "SCENTED CANDLE VANILLA", 3.75), ("70012", "SCENTED CANDLE CEDAR", 3.75),
    ("70013", "ENAMEL MUG CAMPER", 2.55), ("70014", "WALL CLOCK RETRO", 12.50),
    ("70015", "KIDS PAINT SET", 2.25), ("70016", "GIFT WRAP KRAFT 6 SHEETS", 0.42),
    ("70017", "STRING LIGHTS WARM", 5.95), ("70018", "DOORMAT WELCOME HOME", 7.95),
    ("70019", "HERB PLANTER TRIO", 9.95), ("70020", "RECIPE NOTEBOOK A5", 1.25),
    ("70021", "CHRISTMAS BAUBLE SET", 3.25), ("70022", "ADVENT CALENDAR FELT", 11.95),
    ("70023", "PICNIC BLANKET CHECK", 14.95), ("70024", "WATER BOTTLE STEEL", 4.95),
    ("70025", "COASTER SET CORK", 1.45), ("70026", "LUNCH BOX TIN", 2.95),
    ("70027", "BIRD FEEDER HANGING", 3.95), ("70028", "CUSHION COVER MUSTARD", 3.35),
    ("70029", "BAKING TIN HEART", 2.75), ("70030", "PENCIL CASE FOX", 0.95),
]
COUNTRIES = [("United Kingdom", 0.78), ("France", 0.05), ("Germany", 0.05), ("EIRE", 0.04),
             ("Netherlands", 0.03), ("Spain", 0.02), ("Belgium", 0.02), ("Portugal", 0.01)]
MONTH_WEIGHT = {1: 0.7, 2: 0.7, 3: 0.85, 4: 0.85, 5: 0.9, 6: 0.9, 7: 0.9, 8: 0.95,
                9: 1.2, 10: 1.35, 11: 1.6, 12: 1.0}
START = datetime(2024, 1, 1)
END = datetime(2025, 12, 31)

# Quantités d'anomalies injectées (connues => vérifiables par les tests).
N_INVOICES = 900
N_DUPLICATES = 40
N_CANCELLATIONS = 30
N_STOCK_ADJ = 12
N_ZERO_PRICE = 8
N_INVALID = 3


def _fmt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def generate_rows(seed: int = 42) -> list[list[str]]:
    rng = random.Random(seed)
    customers = []
    for cid in range(20001, 20321):
        country = rng.choices([c for c, _ in COUNTRIES], weights=[w for _, w in COUNTRIES])[0]
        customers.append((str(cid), country))

    days = [START + timedelta(days=i) for i in range((END - START).days + 1)]
    day_weights = [MONTH_WEIGHT[d.month] * (0.0 if d.weekday() == 5 else 1.0) for d in days]  # pas le samedi

    rows: list[list[str]] = []
    sales: list[list[str]] = []
    for i in range(N_INVOICES):
        invoice = str(600000 + i)
        day = rng.choices(days, weights=day_weights)[0]
        ts = day + timedelta(hours=rng.randint(8, 18), minutes=rng.randint(0, 59))
        if rng.random() < 0.2:  # client non identifié (fréquent dans le vrai dataset)
            customer, country = "", rng.choices([c for c, _ in COUNTRIES], weights=[w for _, w in COUNTRIES])[0]
        else:
            customer, country = rng.choice(customers)
        for code, desc, price in rng.sample(PRODUCTS, k=rng.randint(1, 8)):
            if desc.startswith(("CHRISTMAS", "ADVENT")) and day.month not in (10, 11, 12):
                continue
            qty = rng.choice([1, 2, 3, 4, 6, 6, 12, 12, 24, 48])
            row = [invoice, code, desc, str(qty), _fmt(ts), f"{price:.2f}", customer, country]
            rows.append(row)
            sales.append(row)
        if rng.random() < 0.08:  # frais de port sur certaines commandes
            rows.append([invoice, "POST", "POSTAGE", "1", _fmt(ts), "18.00", customer, country])

    for row in rng.sample([r for r in sales if r[6]], k=N_CANCELLATIONS):  # annulations = retours clients
        ts = datetime.strptime(row[4], "%Y-%m-%d %H:%M:%S") + timedelta(days=rng.randint(1, 20))
        qty = -rng.randint(1, int(row[3]))
        rows.append(["C" + str(700000 + len(rows)), row[1], row[2], str(qty), _fmt(min(ts, END)),
                     row[5], row[6], row[7]])

    for _ in range(N_STOCK_ADJ):  # casse / perte : quantité négative, prix nul, sans client
        code, _, _ = rng.choice(PRODUCTS)
        rows.append([str(650000 + len(rows)), code, rng.choice(["damaged", "lost", "wet/rusty", ""]),
                     str(-rng.randint(1, 30)), _fmt(rng.choice(days) + timedelta(hours=10)), "0.00", "",
                     "United Kingdom"])

    for _ in range(N_ZERO_PRICE):
        code, desc, _ = rng.choice(PRODUCTS)
        cust, country = rng.choice(customers)
        rows.append([str(660000 + len(rows)), code, desc, str(rng.randint(1, 10)),
                     _fmt(rng.choice(days) + timedelta(hours=11)), "0.00", cust, country])

    cust, country = rng.choice(customers)
    rows.append([str(670000), "M", "Manual", "1", _fmt(START + timedelta(days=40, hours=12)), "35.00", cust, country])
    rows.append([str(670001), "BANK CHARGES", "Bank Charges", "1", _fmt(START + timedelta(days=90, hours=9)),
                 "15.00", "", "United Kingdom"])
    rows.append(["A680000", "B", "Adjust bad debt", "1", _fmt(START + timedelta(days=200, hours=9)),
                 "-1250.00", "", "United Kingdom"])

    # Lignes illisibles (format cassé) : conservées et marquées invalid.
    rows.append(["690000", "70001", "CERAMIC TEA CUP SAGE", "abc", _fmt(START + timedelta(days=3)), "2.10",
                 "20001", "France"])
    rows.append(["690001", "70002", "CERAMIC TEA CUP ROSE", "2", "not a date", "2.10", "20002", "France"])
    rows.append(["690002", "", "NO CODE", "2", _fmt(START + timedelta(days=5)), "2.10", "20003", "Germany"])
    assert N_INVALID == 3

    for row in rng.sample(sales, k=N_DUPLICATES):  # doublons exacts (problème connu du vrai dataset)
        rows.append(list(row))

    rng.shuffle(rows)
    return rows


def write_sample(path: Path, seed: int = 42) -> int:
    rows = generate_rows(seed)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(HEADER)
        writer.writerows(rows)
    return len(rows)
