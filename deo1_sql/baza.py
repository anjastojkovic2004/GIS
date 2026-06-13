import psycopg2
import pandas as pd
from dotenv import load_dotenv
import os

# Ucitavanje .env fajla
load_dotenv()
DB_URL = "postgresql://postgres.vtmpqdgrtntctvbusxec:NoviSad2024!@aws-0-eu-west-1.pooler.supabase.com:6543/postgres"

# Konekcija na bazu
def get_connection():
    conn = psycopg2.connect(DB_URL)
    return conn

# Kreiranje tabela
def kreiraj_tabele():
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        DROP TABLE IF EXISTS inspekcije CASCADE;
        DROP TABLE IF EXISTS deponije CASCADE;
        DROP TABLE IF EXISTS kontejneri CASCADE;
        DROP TABLE IF EXISTS komunalna_preduzeca CASCADE;
        DROP TABLE IF EXISTS lokacije CASCADE;
    """)

    cursor.execute("""
        CREATE TABLE lokacije (
            id SERIAL PRIMARY KEY,
            naziv VARCHAR(100),
            opstina VARCHAR(50),
            adresa VARCHAR(200),
            tip_podrucja VARCHAR(50),
            geom GEOMETRY(Point, 4326)
        );

        CREATE TABLE komunalna_preduzeca (
            id SERIAL PRIMARY KEY,
            naziv VARCHAR(100),
            kontakt_telefon VARCHAR(20),
            email VARCHAR(100),
            zona_pokrivenosti VARCHAR(100),
            lokacija_id INTEGER REFERENCES lokacije(id)
        );

        CREATE TABLE kontejneri (
            id SERIAL PRIMARY KEY,
            tip VARCHAR(50),
            kapacitet_litara INTEGER,
            stanje VARCHAR(20),
            datum_postavljanja DATE,
            lokacija_id INTEGER REFERENCES lokacije(id)
        );

        CREATE TABLE deponije (
            id SERIAL PRIMARY KEY,
            naziv VARCHAR(100),
            povrsina_m2 FLOAT,
            tip_otpada VARCHAR(100),
            status VARCHAR(50),
            datum_otkrivanja DATE,
            lokacija_id INTEGER REFERENCES lokacije(id),
            geom GEOMETRY(Polygon, 4326)
        );

        CREATE TABLE inspekcije (
            id SERIAL PRIMARY KEY,
            datum DATE,
            nalaz TEXT,
            preporuka TEXT,
            inspektor VARCHAR(100),
            deponija_id INTEGER REFERENCES deponije(id)
        );
    """)
    conn.commit()
    print("Tabele kreirane!")

    # Unos podataka
    cursor.execute("""
        INSERT INTO lokacije (naziv, opstina, adresa, tip_podrucja, geom) VALUES
        ('Liman park', 'Novi Sad', 'Bulevar cara Lazara', 'park', ST_SetSRID(ST_MakePoint(19.8335, 45.2396), 4326)),
        ('Grbavica', 'Novi Sad', 'Ulica Zarka Zrenjanina', 'stambeno', ST_SetSRID(ST_MakePoint(19.8456, 45.2431), 4326)),
        ('Sajmiste', 'Novi Sad', 'Hajduk Veljkova', 'industrijsko', ST_SetSRID(ST_MakePoint(19.8123, 45.2678), 4326)),
        ('Detelinara', 'Novi Sad', 'Ulica Temerinska', 'stambeno', ST_SetSRID(ST_MakePoint(19.8234, 45.2512), 4326)),
        ('Klisa', 'Novi Sad', 'Klisanska ulica', 'prigradsko', ST_SetSRID(ST_MakePoint(19.7987, 45.2789), 4326))
        RETURNING id
    """)
    lokacija_ids = [row[0] for row in cursor.fetchall()]
    conn.commit()
    print(f"Lokacije unete! IDs: {lokacija_ids}")

    cursor.execute("""
        INSERT INTO komunalna_preduzeca (naziv, kontakt_telefon, email, zona_pokrivenosti, lokacija_id) VALUES
        ('JKP Cistoca', '021-123-456', 'cistoca@novisad.rs', 'Liman i Grbavica', %s),
        ('JKP Gradsko zelenilo', '021-234-567', 'zelenilo@novisad.rs', 'Sajmiste', %s),
        ('EkoNS', '021-345-678', 'ekons@novisad.rs', 'Detelinara', %s),
        ('JKP Stan', '021-456-789', 'stan@novisad.rs', 'Klisa', %s),
        ('GreenCity', '021-567-890', 'greencity@novisad.rs', 'Ceo grad', %s)
    """, (lokacija_ids[0], lokacija_ids[1], lokacija_ids[2], lokacija_ids[3], lokacija_ids[4]))
    conn.commit()

    cursor.execute("""
        INSERT INTO kontejneri (tip, kapacitet_litara, stanje, datum_postavljanja, lokacija_id) VALUES
        ('komunalni', 1100, 'dobro', '2022-03-15', %s),
        ('reciklazni', 2500, 'dobro', '2023-01-10', %s),
        ('komunalni', 1100, 'ostecen', '2021-06-20', %s),
        ('podzemni', 5000, 'dobro', '2023-05-05', %s),
        ('reciklazni', 2500, 'lose', '2020-11-30', %s),
        ('komunalni', 1100, 'dobro', '2022-08-14', %s),
        ('podzemni', 5000, 'dobro', '2023-09-01', %s)
    """, (lokacija_ids[0], lokacija_ids[1], lokacija_ids[2], lokacija_ids[3], lokacija_ids[4], lokacija_ids[0], lokacija_ids[1]))
    conn.commit()

    cursor.execute("""
        INSERT INTO deponije (naziv, povrsina_m2, tip_otpada, status, datum_otkrivanja, lokacija_id, geom)
        VALUES
        ('Deponija Klisa 1', 450.5, 'mesoviti otpad', 'aktivna', '2023-02-10', %s,
         ST_Buffer(ST_SetSRID(ST_MakePoint(19.7987, 45.2789), 4326)::geography, 50)::geometry),
        ('Deponija Sajmiste', 230.0, 'gradevinski otpad', 'sanirana', '2022-07-15', %s,
         ST_Buffer(ST_SetSRID(ST_MakePoint(19.8123, 45.2678), 4326)::geography, 30)::geometry),
        ('Deponija Grbavica', 180.0, 'komunalni otpad', 'aktivna', '2023-05-20', %s,
         ST_Buffer(ST_SetSRID(ST_MakePoint(19.8456, 45.2431), 4326)::geography, 25)::geometry),
        ('Deponija Detelinara', 320.0, 'mesoviti otpad', 'u sanaciji', '2022-11-08', %s,
         ST_Buffer(ST_SetSRID(ST_MakePoint(19.8234, 45.2512), 4326)::geography, 40)::geometry),
        ('Deponija Liman', 95.0, 'komunalni otpad', 'sanirana', '2021-09-03', %s,
         ST_Buffer(ST_SetSRID(ST_MakePoint(19.8335, 45.2396), 4326)::geography, 15)::geometry)
        RETURNING id
    """, (lokacija_ids[4], lokacija_ids[2], lokacija_ids[1], lokacija_ids[3], lokacija_ids[0]))
    deponija_ids = [row[0] for row in cursor.fetchall()]
    conn.commit()

    cursor.execute("""
        INSERT INTO inspekcije (datum, nalaz, preporuka, inspektor, deponija_id) VALUES
        ('2024-01-15', 'Pronadjena velika kolicina otpada', 'Hitno ciscenje', 'Petar Petrovic', %s),
        ('2024-02-20', 'Deponija sanirana', 'Redovan nadzor', 'Ana Jovanovic', %s),
        ('2024-03-10', 'Nova odlagalista otpada', 'Postaviti kamere', 'Marko Markovic', %s),
        ('2024-04-05', 'Sanacija u toku', 'Nastaviti sanaciju', 'Jelena Nikolic', %s),
        ('2024-05-18', 'Lokacija cista', 'Mesecni nadzor', 'Stefan Ilic', %s)
    """, (deponija_ids[0], deponija_ids[1], deponija_ids[2], deponija_ids[3], deponija_ids[4]))
    conn.commit()
    print("Svi podaci uneti!")
    
    cursor.close()
    conn.close()

if __name__ == "__main__":
    kreiraj_tabele()