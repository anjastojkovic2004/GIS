import psycopg2
import pandas as pd

DB_URL = "postgresql://postgres.vtmpqdgrtntctvbusxec:NoviSad2024!@aws-0-eu-west-1.pooler.supabase.com:6543/postgres"

def get_connection():
    return psycopg2.connect(DB_URL)

# CREATE
def dodaj_kontejner(tip, kapacitet, stanje, datum, lokacija_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO kontejneri (tip, kapacitet_litara, stanje, datum_postavljanja, lokacija_id)
        VALUES (%s, %s, %s, %s, %s)
    """, (tip, kapacitet, stanje, datum, lokacija_id))
    conn.commit()
    cursor.close()
    conn.close()
    print(f"Kontejner '{tip}' uspesno dodat!")

# READ
def prikazi_kontejnere():
    conn = get_connection()
    df = pd.read_sql("SELECT * FROM kontejneri", conn)
    conn.close()
    print(df)
    return df

# UPDATE
def azuriraj_kontejner(kontejner_id, novo_stanje):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE kontejneri SET stanje = %s WHERE id = %s", (novo_stanje, kontejner_id))
    conn.commit()
    cursor.close()
    conn.close()
    print(f"Kontejner {kontejner_id} azuriran na: {novo_stanje}")

# DELETE
def obrisi_kontejner(kontejner_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM kontejneri WHERE id = %s", (kontejner_id,))
    conn.commit()
    cursor.close()
    conn.close()
    print(f"Kontejner {kontejner_id} obrisan!")

if __name__ == "__main__":
    print("=== POCETNO STANJE ===")
    prikazi_kontejnere()

    dodaj_kontejner('reciklazni', 1500, 'dobro', '2024-06-01', 3)
    print("\n=== NAKON DODAVANJA ===")
    prikazi_kontejnere()

    azuriraj_kontejner(1, 'lose')
    print("\n=== NAKON AZURIRANJA ===")
    prikazi_kontejnere()

    obrisi_kontejner(1)
    print("\n=== NAKON BRISANJA ===")
    prikazi_kontejnere()