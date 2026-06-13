import psycopg2
import pandas as pd

DB_URL = "postgresql://postgres.vtmpqdgrtntctvbusxec:NoviSad2024!@aws-0-eu-west-1.pooler.supabase.com:6543/postgres"

def get_connection():
    return psycopg2.connect(DB_URL)

conn = get_connection()

# 1. Kontejneri sa lokacijama
print("=== 1. Kontejneri sa lokacijama ===")
df1 = pd.read_sql("""
    SELECT k.id, k.tip, k.kapacitet_litara, k.stanje, l.naziv as lokacija, l.tip_podrucja
    FROM kontejneri k
    JOIN lokacije l ON k.lokacija_id = l.id
""", conn)
print(df1)

# 2. Aktivne deponije
print("\n=== 2. Aktivne deponije ===")
df2 = pd.read_sql("""
    SELECT d.naziv, d.povrsina_m2, d.tip_otpada, l.naziv as lokacija
    FROM deponije d
    JOIN lokacije l ON d.lokacija_id = l.id
    WHERE d.status = 'aktivna'
""", conn)
print(df2)

# 3. Inspekcije sa deponijama
print("\n=== 3. Inspekcije sa deponijama ===")
df3 = pd.read_sql("""
    SELECT i.datum, i.inspektor, i.nalaz, d.naziv as deponija
    FROM inspekcije i
    JOIN deponije d ON i.deponija_id = d.id
    ORDER BY i.datum DESC
""", conn)
print(df3)

# 4. Preduzeca sa lokacijama
print("\n=== 4. Preduzeca sa lokacijama ===")
df4 = pd.read_sql("""
    SELECT kp.naziv as preduzece, kp.zona_pokrivenosti, l.naziv as lokacija, l.tip_podrucja
    FROM komunalna_preduzeca kp
    JOIN lokacije l ON kp.lokacija_id = l.id
""", conn)
print(df4)

# 5. Osteceni kontejneri
print("\n=== 5. Osteceni kontejneri ===")
df5 = pd.read_sql("""
    SELECT k.tip, k.stanje, l.naziv as lokacija, l.adresa
    FROM kontejneri k
    JOIN lokacije l ON k.lokacija_id = l.id
    WHERE k.stanje IN ('ostecen', 'lose')
""", conn)
print(df5)

# 6. Deponije + inspekcije + lokacije
print("\n=== 6. Deponije, inspekcije i lokacije ===")
df6 = pd.read_sql("""
    SELECT d.naziv as deponija, l.naziv as lokacija, i.datum, i.inspektor, i.preporuka
    FROM deponije d
    JOIN lokacije l ON d.lokacija_id = l.id
    JOIN inspekcije i ON i.deponija_id = d.id
    WHERE d.povrsina_m2 > 200
""", conn)
print(df6)

conn.close()
print("\n=== DEO 1 KOMPLETIRAN! ===")