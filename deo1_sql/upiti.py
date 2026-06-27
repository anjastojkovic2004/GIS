"""
upiti.py — SQL upiti nad PostgreSQL/PostGIS bazom
Demonstrira 10 JOIN upita sa WHERE filterima, GROUP BY i agregacijama.
Baza je hostovana na Supabase cloud platformi.
"""

import psycopg2
import pandas as pd
import os

# URL konekcije se učitava iz env varijable, uz fallback na hardkodirani string
DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres.vtmpqdgrtntctvbusxec:NoviSad2024!@aws-0-eu-west-1.pooler.supabase.com:6543/postgres"
)

def get_connection():
    return psycopg2.connect(DB_URL)

conn = get_connection()

# ─────────────────────────────────────────────
# UPIT 1: Kontejneri sa lokacijama
# JOIN kontejneri ↔ lokacije — prikazuje tip, kapacitet i stanje svakog kontejnera
# ─────────────────────────────────────────────
print("=== 1. Kontejneri sa lokacijama ===")
df1 = pd.read_sql("""
    SELECT k.id, k.tip, k.kapacitet_litara, k.stanje, l.naziv as lokacija, l.tip_podrucja
    FROM kontejneri k
    JOIN lokacije l ON k.lokacija_id = l.id
""", conn)
print(df1)

# ─────────────────────────────────────────────
# UPIT 2: Aktivne deponije
# WHERE filter — prikazuje samo deponije sa statusom 'aktivna'
# ─────────────────────────────────────────────
print("\n=== 2. Aktivne deponije ===")
df2 = pd.read_sql("""
    SELECT d.naziv, d.povrsina_m2, d.tip_otpada, l.naziv as lokacija
    FROM deponije d
    JOIN lokacije l ON d.lokacija_id = l.id
    WHERE d.status = 'aktivna'
""", conn)
print(df2)

# ─────────────────────────────────────────────
# UPIT 3: Inspekcije sa deponijama
# JOIN inspekcije ↔ deponije, sortirano po datumu (najnovije prve)
# ─────────────────────────────────────────────
print("\n=== 3. Inspekcije sa deponijama ===")
df3 = pd.read_sql("""
    SELECT i.datum, i.inspektor, i.nalaz, d.naziv as deponija
    FROM inspekcije i
    JOIN deponije d ON i.deponija_id = d.id
    ORDER BY i.datum DESC
""", conn)
print(df3)

# ─────────────────────────────────────────────
# UPIT 4: Preduzeća sa lokacijama
# JOIN komunalna_preduzeca ↔ lokacije
# ─────────────────────────────────────────────
print("\n=== 4. Preduzeca sa lokacijama ===")
df4 = pd.read_sql("""
    SELECT kp.naziv as preduzece, kp.zona_pokrivenosti, l.naziv as lokacija, l.tip_podrucja
    FROM komunalna_preduzeca kp
    JOIN lokacije l ON kp.lokacija_id = l.id
""", conn)
print(df4)

# ─────────────────────────────────────────────
# UPIT 5: Oštećeni i loši kontejneri
# WHERE sa IN operatorom — filtrira više vrednosti odjednom
# ─────────────────────────────────────────────
print("\n=== 5. Osteceni kontejneri ===")
df5 = pd.read_sql("""
    SELECT k.tip, k.stanje, l.naziv as lokacija, l.adresa
    FROM kontejneri k
    JOIN lokacije l ON k.lokacija_id = l.id
    WHERE k.stanje IN ('ostecen', 'lose')
""", conn)
print(df5)

# ─────────────────────────────────────────────
# UPIT 6: Deponije + inspekcije + lokacije (trostruki JOIN)
# Prikazuje samo deponije veće od 200 m² koje imaju bar jednu inspekciju
# ─────────────────────────────────────────────
print("\n=== 6. Deponije, inspekcije i lokacije ===")
df6 = pd.read_sql("""
    SELECT d.naziv as deponija, l.naziv as lokacija, i.datum, i.inspektor, i.preporuka
    FROM deponije d
    JOIN lokacije l ON d.lokacija_id = l.id
    JOIN inspekcije i ON i.deponija_id = d.id
    WHERE d.povrsina_m2 > 200
""", conn)
print(df6)

# ─────────────────────────────────────────────
# UPIT 7: Agregacija — broj kontejnera i ukupni kapacitet po lokaciji
# GROUP BY + COUNT + SUM + LEFT JOIN (uključuje lokacije bez kontejnera)
# COALESCE zamenjuje NULL sa 0 kada nema kontejnera na lokaciji
# ─────────────────────────────────────────────
print("\n=== 7. Broj kontejnera i ukupni kapacitet po lokaciji ===")
df7 = pd.read_sql("""
    SELECT l.naziv as lokacija, l.opstina,
           COUNT(k.id) as broj_kontejnera,
           COALESCE(SUM(k.kapacitet_litara), 0) as ukupni_kapacitet_l
    FROM lokacije l
    LEFT JOIN kontejneri k ON k.lokacija_id = l.id
    GROUP BY l.id, l.naziv, l.opstina
    ORDER BY broj_kontejnera DESC
""", conn)
print(df7)

# ─────────────────────────────────────────────
# UPIT 8: Poslednja inspekcija po deponiji
# GROUP BY + MAX (datum) + COUNT — statistike inspekcija po deponiji
# ─────────────────────────────────────────────
print("\n=== 8. Poslednja inspekcija po deponiji ===")
df8 = pd.read_sql("""
    SELECT d.naziv as deponija, d.status,
           MAX(i.datum) as datum_poslednje_inspekcije,
           COUNT(i.id) as ukupno_inspekcija
    FROM deponije d
    JOIN inspekcije i ON i.deponija_id = d.id
    GROUP BY d.id, d.naziv, d.status
    ORDER BY datum_poslednje_inspekcije DESC
""", conn)
print(df8)

# ─────────────────────────────────────────────
# UPIT 9: Lokacije bez kontejnera
# LEFT JOIN + IS NULL — anti-join obrazac za pronalaženje "praznih" lokacija
# ─────────────────────────────────────────────
print("\n=== 9. Lokacije bez kontejnera ===")
df9 = pd.read_sql("""
    SELECT l.naziv, l.opstina, l.tip_podrucja
    FROM lokacije l
    LEFT JOIN kontejneri k ON k.lokacija_id = l.id
    WHERE k.id IS NULL
""", conn)
print(df9)

# ─────────────────────────────────────────────
# UPIT 10: Sveobuhvatni izveštaj po lokaciji
# Trostruki LEFT JOIN sa COUNT DISTINCT da se izbjegne dupliranje redova
# COALESCE(SUM(DISTINCT ...), 0) — ukupna površina bez duplikata
# ─────────────────────────────────────────────
print("\n=== 10. Sveobuhvatni izveštaj po lokaciji ===")
df10 = pd.read_sql("""
    SELECT l.naziv as lokacija, l.opstina,
           COUNT(DISTINCT k.id) as kontejneri,
           COUNT(DISTINCT d.id) as deponije,
           COUNT(DISTINCT i.id) as inspekcije,
           COALESCE(SUM(DISTINCT d.povrsina_m2), 0) as ukupna_povrsina_m2
    FROM lokacije l
    LEFT JOIN kontejneri k ON k.lokacija_id = l.id
    LEFT JOIN deponije d ON d.lokacija_id = l.id
    LEFT JOIN inspekcije i ON i.deponija_id = d.id
    GROUP BY l.id, l.naziv, l.opstina
    ORDER BY deponije DESC, kontejneri DESC
""", conn)
print(df10)

conn.close()
print("\n=== DEO 1 KOMPLETIRAN! ===")
