"""
crud.py — CRUD operacije nad PostgreSQL/PostGIS bazom
Implementira Create, Read, Update, Delete za svih 5 tabela:
lokacije, komunalna_preduzeca, kontejneri, deponije, inspekcije
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
    """Otvara i vraća novu konekciju na PostgreSQL bazu."""
    return psycopg2.connect(DB_URL)


# ─────────────────────────────────────────────
# LOKACIJE CRUD
# ─────────────────────────────────────────────

def dodaj_lokaciju(naziv, opstina, adresa, tip_podrucja, lon, lat):
    """
    Dodaje novu lokaciju u bazu sa PostGIS geometrijom (tačka).
    ST_MakePoint(lon, lat) kreira tačku, ST_SetSRID postavlja koordinatni sistem EPSG:4326 (WGS84).
    Vraća ID novog reda.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO lokacije (naziv, opstina, adresa, tip_podrucja, geom)
        VALUES (%s, %s, %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326))
        RETURNING id
    """, (naziv, opstina, adresa, tip_podrucja, lon, lat))
    new_id = cursor.fetchone()[0]
    conn.commit()
    cursor.close()
    conn.close()
    print(f"Lokacija '{naziv}' uspešno dodata (id={new_id})!")
    return new_id

def prikazi_lokacije():
    """
    Čita sve lokacije iz baze.
    ST_X i ST_Y ekstrahuju longitude i latitude iz PostGIS geometry kolone.
    """
    conn = get_connection()
    df = pd.read_sql("""
        SELECT id, naziv, opstina, adresa, tip_podrucja,
               ST_X(geom) as lon, ST_Y(geom) as lat
        FROM lokacije
        ORDER BY id
    """, conn)
    conn.close()
    print(df)
    return df

def azuriraj_lokaciju(lokacija_id, novi_naziv, nova_opstina, nova_adresa, novi_tip):
    """
    Ažurira sve atribute lokacije po ID-u.
    int() konverzija je neophodna jer pandas može da vrati numpy.int64
    koji psycopg2 ne može da adaptira.
    """
    lokacija_id = int(lokacija_id)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE lokacije
        SET naziv = %s, opstina = %s, adresa = %s, tip_podrucja = %s
        WHERE id = %s
    """, (novi_naziv, nova_opstina, nova_adresa, novi_tip, lokacija_id))
    conn.commit()
    cursor.close()
    conn.close()
    print(f"Lokacija {lokacija_id} ažurirana!")

def obrisi_lokaciju(lokacija_id):
    """
    Briše lokaciju po ID-u.
    Napomena: ako lokacija ima kontejnere ili deponije, brisanje će fail-ovati
    zbog stranog ključa — prvo obriši zavisne redove.
    """
    lokacija_id = int(lokacija_id)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM lokacije WHERE id = %s", (lokacija_id,))
    conn.commit()
    cursor.close()
    conn.close()
    print(f"Lokacija {lokacija_id} obrisana!")


# ─────────────────────────────────────────────
# KOMUNALNA PREDUZEĆA CRUD
# ─────────────────────────────────────────────

def dodaj_preduzece(naziv, kontakt_telefon, email, zona_pokrivenosti, lokacija_id):
    """
    Dodaje novo komunalno preduzeće vezano za lokaciju putem stranog ključa.
    Vraća ID novog reda.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO komunalna_preduzeca (naziv, kontakt_telefon, email, zona_pokrivenosti, lokacija_id)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id
    """, (naziv, kontakt_telefon, email, zona_pokrivenosti, lokacija_id))
    new_id = cursor.fetchone()[0]
    conn.commit()
    cursor.close()
    conn.close()
    print(f"Preduzeće '{naziv}' uspešno dodato (id={new_id})!")
    return new_id

def prikazi_preduzeca():
    """
    Čita sva komunalna preduzeća uz naziv lokacije (JOIN).
    """
    conn = get_connection()
    df = pd.read_sql("""
        SELECT kp.id, kp.naziv, kp.kontakt_telefon, kp.email,
               kp.zona_pokrivenosti, l.naziv as lokacija
        FROM komunalna_preduzeca kp
        JOIN lokacije l ON kp.lokacija_id = l.id
        ORDER BY kp.id
    """, conn)
    conn.close()
    print(df)
    return df

def azuriraj_preduzece(preduzece_id, novi_telefon, novi_email, nova_zona):
    """Ažurira kontakt podatke i zonu pokrivenosti preduzeća po ID-u."""
    preduzece_id = int(preduzece_id)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE komunalna_preduzeca
        SET kontakt_telefon = %s, email = %s, zona_pokrivenosti = %s
        WHERE id = %s
    """, (novi_telefon, novi_email, nova_zona, preduzece_id))
    conn.commit()
    cursor.close()
    conn.close()
    print(f"Preduzeće {preduzece_id} ažurirano!")

def obrisi_preduzece(preduzece_id):
    """Briše komunalno preduzeće po ID-u."""
    preduzece_id = int(preduzece_id)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM komunalna_preduzeca WHERE id = %s", (preduzece_id,))
    conn.commit()
    cursor.close()
    conn.close()
    print(f"Preduzeće {preduzece_id} obrisano!")


# ─────────────────────────────────────────────
# KONTEJNERI CRUD
# ─────────────────────────────────────────────

def dodaj_kontejner(tip, kapacitet, stanje, datum, lokacija_id):
    """
    Dodaje novi kontejner vezan za lokaciju.
    RETURNING id vraća ID novog reda direktno iz INSERT naredbe.
    """
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
    """Čita sve kontejnere sa nazivom lokacije (JOIN)."""
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
    """Ažurira stanje kontejnera (dobro / ostecen / lose) po ID-u."""
    kontejner_id = int(kontejner_id)  # numpy.int64 → Python int (psycopg2 zahteva)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE kontejneri SET stanje = %s WHERE id = %s", (novo_stanje, kontejner_id))
    conn.commit()
    cursor.close()
    conn.close()
    print(f"Kontejner {kontejner_id} ažuriran na: {novo_stanje}")

def obrisi_kontejner(kontejner_id):
    """Briše kontejner po ID-u."""
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
    """
    Dodaje novu deponiju sa PostGIS geometrijom (poligon).
    Geometrija se kreira kao krug (ST_Buffer) oko koordinata lokacije.
    Radijus se računa iz površine kako bi poligon bio proporcionalan veličini deponije.
    INSERT...SELECT preuzima koordinate lokacije direktno iz tabele lokacije.
    Vraća ID novog reda ili podiže ValueError ako lokacija ne postoji.
    """
    conn = get_connection()
    cursor = conn.cursor()
    # Radijus u metrima: aproksimacija iz površine, min 1m da se izbegne prazan buffer
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
        # INSERT...SELECT vratio 0 redova — lokacija ne postoji
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
    """Čita sve deponije sa nazivom lokacije (JOIN)."""
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
    """Ažurira status deponije (aktivna / u sanaciji / sanirana) po ID-u."""
    deponija_id = int(deponija_id)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE deponije SET status = %s WHERE id = %s", (novi_status, deponija_id))
    conn.commit()
    cursor.close()
    conn.close()
    print(f"Deponija {deponija_id} ažurirana na status: {novi_status}")

def obrisi_deponiju(deponija_id):
    """
    Briše deponiju i sve njene inspekcije.
    Inspekcije se moraju obrisati prve jer imaju strani ključ na deponiju (ON DELETE nije CASCADE).
    """
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
    """
    Dodaje novu inspekciju vezanu za deponiju putem stranog ključa.
    Vraća ID novog reda.
    """
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
    """Čita sve inspekcije sa nazivom deponije (JOIN), sortirano po datumu."""
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
    """Ažurira preporuku inspekcije po ID-u."""
    inspekcija_id = int(inspekcija_id)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE inspekcije SET preporuka = %s WHERE id = %s", (nova_preporuka, inspekcija_id))
    conn.commit()
    cursor.close()
    conn.close()
    print(f"Inspekcija {inspekcija_id} ažurirana!")

def obrisi_inspekciju(inspekcija_id):
    """Briše inspekciju po ID-u."""
    inspekcija_id = int(inspekcija_id)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM inspekcije WHERE id = %s", (inspekcija_id,))
    conn.commit()
    cursor.close()
    conn.close()
    print(f"Inspekcija {inspekcija_id} obrisana!")


# ─────────────────────────────────────────────
# DEMO — pokretanje svih CRUD operacija
# ─────────────────────────────────────────────

if __name__ == "__main__":

    # ── LOKACIJE ──────────────────────────────
    print("=" * 60)
    print("CRUD – LOKACIJE")
    print("=" * 60)

    print("\n=== POČETNO STANJE ===")
    prikazi_lokacije()

    # Dodaj test lokaciju i sačuvaj vraćeni ID
    nov_id = dodaj_lokaciju('Test lokacija', 'Novi Sad', 'Test adresa 1', 'stambeno', 19.85, 45.25)

    print("\n=== NAKON DODAVANJA ===")
    prikazi_lokacije()

    azuriraj_lokaciju(nov_id, 'Test lokacija izmenjena', 'Novi Sad', 'Nova adresa 2', 'industrijsko')
    print("\n=== NAKON AŽURIRANJA ===")
    prikazi_lokacije()

    obrisi_lokaciju(nov_id)
    print("\n=== NAKON BRISANJA ===")
    prikazi_lokacije()

    # ── KOMUNALNA PREDUZEĆA ───────────────────
    print("\n" + "=" * 60)
    print("CRUD – KOMUNALNA PREDUZEĆA")
    print("=" * 60)

    print("\n=== POČETNO STANJE ===")
    prikazi_preduzeca()

    # Uzimamo ID prve lokacije dinamički — ne hardkodiramo
    df_lok = prikazi_lokacije()
    lok_id = int(df_lok.iloc[0]['id'])

    nov_id = dodaj_preduzece('Test Komunalno', '021-000-000', 'test@komunalno.rs', 'Zona Test', lok_id)

    print("\n=== NAKON DODAVANJA ===")
    prikazi_preduzeca()

    azuriraj_preduzece(nov_id, '021-111-111', 'novo@komunalno.rs', 'Zona Izmenjena')
    print("\n=== NAKON AŽURIRANJA ===")
    prikazi_preduzeca()

    obrisi_preduzece(nov_id)
    print("\n=== NAKON BRISANJA ===")
    prikazi_preduzeca()

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

    # Uzimamo prvu deponiju iz baze — demo inspekcija mora imati validnu deponiju
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
