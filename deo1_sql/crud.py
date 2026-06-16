import psycopg2
import pandas as pd

DB_URL = "postgresql://postgres.vtmpqdgrtntctvbusxec:NoviSad2024!@aws-0-eu-west-1.pooler.supabase.com:6543/postgres"

def get_connection():
    return psycopg2.connect(DB_URL)


# ─────────────────────────────────────────────
# KONTEJNERI CRUD
# ─────────────────────────────────────────────

def dodaj_kontejner(tip, kapacitet, stanje, datum, lokacija_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO kontejneri (tip, kapacitet_litara, stanje, datum_postavljanja, lokacija_id)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id
    """, (tip, kapacitet, stanje, datum, lokacija_id))
    new_id = cursor.fetchone()[0]
    conn.commit()
    cursor.close()
    conn.close()
    print(f"Kontejner '{tip}' uspešno dodat (id={new_id})!")
    return new_id

def prikazi_kontejnere():
    conn = get_connection()
    df = pd.read_sql("""
        SELECT k.id, k.tip, k.kapacitet_litara, k.stanje, k.datum_postavljanja,
               l.naziv as lokacija
        FROM kontejneri k
        JOIN lokacije l ON k.lokacija_id = l.id
        ORDER BY k.id
    """, conn)
    conn.close()
    print(df)
    return df

def azuriraj_kontejner(kontejner_id, novo_stanje):
    kontejner_id = int(kontejner_id)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE kontejneri SET stanje = %s WHERE id = %s", (novo_stanje, kontejner_id))
    conn.commit()
    cursor.close()
    conn.close()
    print(f"Kontejner {kontejner_id} ažuriran na: {novo_stanje}")

def obrisi_kontejner(kontejner_id):
    kontejner_id = int(kontejner_id)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM kontejneri WHERE id = %s", (kontejner_id,))
    conn.commit()
    cursor.close()
    conn.close()
    print(f"Kontejner {kontejner_id} obrisan!")


# ─────────────────────────────────────────────
# DEPONIJE CRUD
# ─────────────────────────────────────────────

def dodaj_deponiju(naziv, povrsina, tip_otpada, status, datum, lokacija_id):
    conn = get_connection()
    cursor = conn.cursor()
    radius = max(1, int(povrsina ** 0.5 / 2))
    cursor.execute("""
        INSERT INTO deponije (naziv, povrsina_m2, tip_otpada, status, datum_otkrivanja, lokacija_id, geom)
        SELECT %s, %s, %s, %s, %s, %s,
            ST_Buffer(ST_SetSRID(ST_MakePoint(ST_X(geom), ST_Y(geom)), 4326)::geography, %s)::geometry
        FROM lokacije WHERE id = %s
        RETURNING id
    """, (naziv, povrsina, tip_otpada, status, datum, lokacija_id, radius, lokacija_id))
    row = cursor.fetchone()
    if row is None:
        conn.rollback()
        cursor.close()
        conn.close()
        raise ValueError(f"Lokacija sa id={lokacija_id} ne postoji u bazi!")
    new_id = row[0]
    conn.commit()
    cursor.close()
    conn.close()
    print(f"Deponija '{naziv}' uspešno dodata (id={new_id})!")
    return new_id

def prikazi_deponije():
    conn = get_connection()
    df = pd.read_sql("""
        SELECT d.id, d.naziv, d.povrsina_m2, d.tip_otpada, d.status, d.datum_otkrivanja,
               l.naziv as lokacija
        FROM deponije d
        JOIN lokacije l ON d.lokacija_id = l.id
        ORDER BY d.id
    """, conn)
    conn.close()
    print(df)
    return df

def azuriraj_deponiju(deponija_id, novi_status):
    deponija_id = int(deponija_id)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE deponije SET status = %s WHERE id = %s", (novi_status, deponija_id))
    conn.commit()
    cursor.close()
    conn.close()
    print(f"Deponija {deponija_id} ažurirana na status: {novi_status}")

def obrisi_deponiju(deponija_id):
    deponija_id = int(deponija_id)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM inspekcije WHERE deponija_id = %s", (deponija_id,))
    cursor.execute("DELETE FROM deponije WHERE id = %s", (deponija_id,))
    conn.commit()
    cursor.close()
    conn.close()
    print(f"Deponija {deponija_id} i njene inspekcije obrisane!")


# ─────────────────────────────────────────────
# INSPEKCIJE CRUD
# ─────────────────────────────────────────────

def dodaj_inspekciju(datum, nalaz, preporuka, inspektor, deponija_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO inspekcije (datum, nalaz, preporuka, inspektor, deponija_id)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id
    """, (datum, nalaz, preporuka, inspektor, deponija_id))
    new_id = cursor.fetchone()[0]
    conn.commit()
    cursor.close()
    conn.close()
    print(f"Inspekcija od {datum} (inspektor: {inspektor}) uspešno dodata (id={new_id})!")
    return new_id

def prikazi_inspekcije():
    conn = get_connection()
    df = pd.read_sql("""
        SELECT i.id, i.datum, i.inspektor, i.nalaz, i.preporuka,
               d.naziv as deponija
        FROM inspekcije i
        JOIN deponije d ON i.deponija_id = d.id
        ORDER BY i.datum DESC
    """, conn)
    conn.close()
    print(df)
    return df

def azuriraj_inspekciju(inspekcija_id, nova_preporuka):
    inspekcija_id = int(inspekcija_id)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE inspekcije SET preporuka = %s WHERE id = %s", (nova_preporuka, inspekcija_id))
    conn.commit()
    cursor.close()
    conn.close()
    print(f"Inspekcija {inspekcija_id} ažurirana!")

def obrisi_inspekciju(inspekcija_id):
    inspekcija_id = int(inspekcija_id)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM inspekcije WHERE id = %s", (inspekcija_id,))
    conn.commit()
    cursor.close()
    conn.close()
    print(f"Inspekcija {inspekcija_id} obrisana!")


# ─────────────────────────────────────────────
# DEMO
# ─────────────────────────────────────────────

if __name__ == "__main__":
    # ── KONTEJNERI ────────────────────────────
    print("=" * 60)
    print("CRUD – KONTEJNERI")
    print("=" * 60)

    print("\n=== POČETNO STANJE ===")
    prikazi_kontejnere()

    # Dodaj novi kontejner i sačuvaj ID koji se vraća
    nov_id = dodaj_kontejner('reciklazni', 1500, 'dobro', '2024-06-01', 1)

    print("\n=== NAKON DODAVANJA ===")
    prikazi_kontejnere()

    # Ažuriraj i obriši novododati kontejner (koristimo nov_id, ne hardkodirani 1)
    azuriraj_kontejner(nov_id, 'lose')
    print("\n=== NAKON AŽURIRANJA ===")
    prikazi_kontejnere()

    obrisi_kontejner(nov_id)
    print("\n=== NAKON BRISANJA ===")
    prikazi_kontejnere()

    # ── DEPONIJE ──────────────────────────────
    print("\n" + "=" * 60)
    print("CRUD – DEPONIJE")
    print("=" * 60)

    print("\n=== POČETNO STANJE ===")
    prikazi_deponije()

    # Dodaj novu deponiju i sačuvaj ID
    nov_id = dodaj_deponiju('Test deponija', 200.0, 'mešoviti', 'aktivna', '2024-06-01', 1)

    print("\n=== NAKON DODAVANJA ===")
    prikazi_deponije()

    azuriraj_deponiju(nov_id, 'sanirana')
    print("\n=== NAKON AŽURIRANJA ===")
    prikazi_deponije()

    obrisi_deponiju(nov_id)
    print("\n=== NAKON BRISANJA ===")
    prikazi_deponije()

    # ── INSPEKCIJE ────────────────────────────
    print("\n" + "=" * 60)
    print("CRUD – INSPEKCIJE")
    print("=" * 60)

    print("\n=== POČETNO STANJE ===")
    prikazi_inspekcije()

    df_dep = prikazi_deponije()
    if df_dep.empty:
        print("Nema deponija u bazi — preskačem demo inspekcija.")
    else:
        deponija_id = int(df_dep.iloc[0]['id'])

        nov_ins_id = dodaj_inspekciju(
            '2024-07-01', 'Test nalaz', 'Test preporuka', 'Test Inspektor', deponija_id
        )

        print("\n=== NAKON DODAVANJA ===")
        prikazi_inspekcije()

        azuriraj_inspekciju(nov_ins_id, 'Proveriti ponovo za mesec dana')
        print("\n=== NAKON AŽURIRANJA ===")
        prikazi_inspekcije()

        obrisi_inspekciju(nov_ins_id)
        print("\n=== NAKON BRISANJA ===")
        prikazi_inspekcije()
