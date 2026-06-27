"""
baza.py — Kreiranje i punjenje PostgreSQL/PostGIS baze podataka
Učitava stvarne OSM SHP podatke za Vojvodinu i puni 5 tabela:
lokacije (gradovi), komunalna_preduzeca (JKP), kontejneri (iz pois SHP),
deponije (landfill iz landuse SHP), inspekcije (sintetičke).
"""

import psycopg2
import pandas as pd
import geopandas as gpd
import os
import random
import warnings
from dotenv import load_dotenv

# Potisnuti shapely RuntimeWarning koji se pojavljuje kod nekih geometrija
warnings.filterwarnings('ignore', category=RuntimeWarning, module='shapely')

# Učitava DB_URL iz .env fajla
load_dotenv()
DB_URL = os.environ.get("DB_URL")

# Putanja do SHP fajlova (relativan od lokacije ovog skripte)
SHP_DIR = os.path.join(os.path.dirname(__file__), '..', 'serbia_shp')

# Bounding box Vojvodine za filtriranje SHP podataka
VOJV_MINX, VOJV_MAXX = 18.8, 21.7
VOJV_MINY, VOJV_MAXY = 44.6, 46.2

# Rečnik poznatih JKP preduzeća po gradu (OSM naziv grada → (naziv JKP, telefon, email))
JKP = {
    'Нови Сад':          ('JKP Čistoća Novi Sad',          '021/6392-222', 'cistoca@novisad.rs'),
    'Зрењанин':          ('JKP Čistoća Zrenjanin',         '023/511-099',  'cistoca@zrenjanin.rs'),
    'Суботица':          ('JKP Čistoća i zelenilo Subotica','024/555-711',  'cistoca@subotica.rs'),
    'Панчево':           ('JKP Čistoća i zelenilo Pančevo', '013/333-300',  'cistoca@pancevo.rs'),
    'Сомбор':            ('JKP Komunalac Sombor',           '025/463-088',  'komunalac@sombor.rs'),
    'Кикинда':           ('JKP Komunalac Kikinda',          '0230/21-333',  'komunalac@kikinda.rs'),
    'Вршац':             ('JKP Stamben Vršac',              '013/831-050',  'stamben@vrsac.rs'),
    'Сремска Митровица': ('JKP Sirmium',                    '022/610-131',  'sirmium@sremskamitrovica.rs'),
    'Рума':              ('JKP Komunalac Ruma',              '022/470-170',  'komunalac@ruma.rs'),
    'Инђија':            ('JKP Inđija',                     '022/561-455',  'jkp@indija.rs'),
}

# Mapiranje OSM fclass kategorija kontejnera na tip i kapacitet u litrima
TIP_MAP = {
    'waste_basket':    ('komunalni',          80),
    'recycling':       ('reciklazni',       2500),
    'recycling_glass': ('reciklazni staklo', 1500),
    'recycling_paper': ('reciklazni papir',  1500),
    'recycling_metal': ('reciklazni metal',  1500),
}

# Liste vrednosti za sintetičke atribute (deponije i inspekcije)
STATUSI    = ['aktivna', 'aktivna', 'u sanaciji', 'sanirana']
TIPOVI     = ['komunalni otpad', 'mesoviti otpad', 'građevinski otpad', 'industrijski otpad']
DATUMI     = ['2019-03-12', '2020-06-08', '2021-01-25', '2021-09-14',
              '2022-04-03', '2022-11-20', '2023-02-07', '2023-08-18']
INSPEKTORI = ['Petar Petrović', 'Ana Jovanović', 'Marko Marković',
              'Jelena Nikolić', 'Stefan Ilić',  'Milica Đorđević',
              'Nikola Popović', 'Ivana Stanković']
NALAZI = [
    'Pronađena velika količina mešanog otpada',
    'Deponija sanirana, teren u dobrom stanju',
    'Nova odlagališta otpada na periferiji',
    'Sanacija u toku, postavljene mreže',
    'Lokacija čista, redovan nadzor',
    'Uočeno odlaganje industrijskog otpada',
    'Prisutan građevinski otpad sa okolnih radova',
    'Deponija u porastu, potrebna hitna intervencija',
]
PREPORUKE = [
    'Hitno čišćenje i postavljanje table zabrane',
    'Redovan mesečni nadzor',
    'Postaviti kamere i pojačati kontrolu',
    'Nastaviti sanaciju prema planu',
    'Obavestiti nadležnu inspekciju',
    'Ukloniti otpad i rekultivisati teren',
]


def get_connection():
    """Otvara konekciju na PostgreSQL/PostGIS bazu."""
    return psycopg2.connect(DB_URL)


def ucitaj_vojvodina_podatke():
    """
    Učitava tri SHP sloja za Vojvodinu:
    1. places — gradovi i kasabe (za lokacije i JKP)
    2. pois   — tačke interesa (za kontejnere i reciklažna mesta)
    3. landuse — korišćenje zemljišta (za deponije — fclass='landfill')
    Filtrira na bbox Vojvodine pomoću .cx[] coordinate indexing-a.
    """
    print("Učitavam SHP podatke za Vojvodinu...")

    # Gradovi i kasabe koji se podudaraju sa rečnikom JKP
    places = gpd.read_file(os.path.join(SHP_DIR, 'gis_osm_places_free_1.shp'))
    gradovi = places.cx[VOJV_MINX:VOJV_MAXX, VOJV_MINY:VOJV_MAXY].copy()
    gradovi = gradovi[gradovi['fclass'].isin(['city', 'town'])].dropna(subset=['name'])
    gradovi = gradovi[gradovi['name'].isin(JKP.keys())].reset_index(drop=True)
    print(f"  Gradovi: {len(gradovi)}")

    # Tačke interesa — kontejneri i reciklažna mesta iz OSM
    pois = gpd.read_file(os.path.join(SHP_DIR, 'gis_osm_pois_free_1.shp'))
    pois_v = pois.cx[VOJV_MINX:VOJV_MAXX, VOJV_MINY:VOJV_MAXY].copy()
    kontejneri = pois_v[pois_v['fclass'].isin(TIP_MAP.keys())].reset_index(drop=True)
    print(f"  Kontejneri/reciklaža: {len(kontejneri)}")

    # Deponije — OSM kategorija 'landfill' iz landuse sloja
    land = gpd.read_file(os.path.join(SHP_DIR, 'gis_osm_landuse_a_free_1.shp'))
    land_v = land.cx[VOJV_MINX:VOJV_MAXX, VOJV_MINY:VOJV_MAXY].copy()
    deponije = land_v[land_v['fclass'] == 'landfill'].reset_index(drop=True)
    print(f"  Deponije (landfill): {len(deponije)}")

    return gradovi, kontejneri, deponije


def kreiraj_tabele():
    """
    Briše postojeće tabele i kreira ih iznova sa PostGIS geometrijskim kolonama.
    Puni tabele stvarnim OSM podacima za Vojvodinu.

    Redosled punjenja je važan zbog stranih ključeva:
    1. lokacije (nema FK)
    2. komunalna_preduzeca → lokacije
    3. kontejneri → lokacije
    4. deponije → lokacije
    5. inspekcije → deponije
    """
    random.seed(42)  # Fiksan seed za reproducibilnost sintetičkih podataka
    conn = get_connection()
    cursor = conn.cursor()

    # CASCADE briše sve zavisne redove automatski
    cursor.execute("""
        DROP TABLE IF EXISTS inspekcije CASCADE;
        DROP TABLE IF EXISTS deponije CASCADE;
        DROP TABLE IF EXISTS kontejneri CASCADE;
        DROP TABLE IF EXISTS komunalna_preduzeca CASCADE;
        DROP TABLE IF EXISTS lokacije CASCADE;
    """)

    # Kreiranje tabela sa PostGIS geometrijskim tipovima
    cursor.execute("""
        CREATE TABLE lokacije (
            id SERIAL PRIMARY KEY,
            naziv VARCHAR(100),
            opstina VARCHAR(50),
            adresa VARCHAR(200),
            tip_podrucja VARCHAR(50),
            geom GEOMETRY(Point, 4326)   -- WGS84 geografska tačka
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
            geom GEOMETRY(GEOMETRY, 4326)  -- WGS84 poligon (može biti i MultiPolygon)
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

    gradovi, kontejneri_gdf, deponije_gdf = ucitaj_vojvodina_podatke()

    # ── Punjenje lokacija (gradovi iz SHP) ──
    # lok_map: osm_id → db_id (za spajanje kontejnera i deponija)
    lok_map = {}
    for _, grad in gradovi.iterrows():
        cursor.execute("""
            INSERT INTO lokacije (naziv, opstina, adresa, tip_podrucja, geom)
            VALUES (%s, %s, %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326))
            RETURNING id
        """, (grad['name'], 'Vojvodina', grad['name'], 'grad', grad.geometry.x, grad.geometry.y))
        lok_map[grad['osm_id']] = cursor.fetchone()[0]
    conn.commit()
    print(f"Lokacije unete: {len(lok_map)}")

    # ── Punjenje komunalnih preduzeća (iz JKP rečnika) ──
    for _, grad in gradovi.iterrows():
        jkp = JKP.get(grad['name'])
        if not jkp:
            continue
        lok_id = lok_map[grad['osm_id']]
        cursor.execute("""
            INSERT INTO komunalna_preduzeca (naziv, kontakt_telefon, email, zona_pokrivenosti, lokacija_id)
            VALUES (%s, %s, %s, %s, %s)
        """, (jkp[0], jkp[1], jkp[2], grad['name'], lok_id))
    conn.commit()
    print("Komunalna preduzeća uneta!")

    # ── Punjenje kontejnera (spatial join na najbliži grad) ──
    # Konverzija u UTM za tačan spatial join u metrima
    gradovi_gdf = gpd.GeoDataFrame(gradovi, geometry='geometry', crs='EPSG:4326')
    gradovi_utm = gradovi_gdf.to_crs('EPSG:32634')
    kontejneri_utm = kontejneri_gdf[['osm_id', 'fclass', 'geometry']].to_crs('EPSG:32634')

    # Svaki kontejner se dodeljuje najbližem gradu
    joined_k = gpd.sjoin_nearest(
        kontejneri_utm,
        gradovi_utm[['osm_id', 'geometry']].rename(columns={'osm_id': 'grad_osm_id'}),
        how='left'
    )

    # Ograničenje: max 5 kontejnera po gradu da se izbegne prenatrpavanje
    uneseno = {oid: 0 for oid in lok_map}
    k_count = 0
    datumi_k = ['2020-05-01','2021-03-15','2021-11-20','2022-06-10',
                '2022-09-05','2023-01-18','2023-07-22','2024-02-14']
    stanja   = ['dobro','dobro','dobro','ostecen','lose']

    for _, row in joined_k.iterrows():
        grad_oid = row.get('grad_osm_id')
        lok_id   = lok_map.get(grad_oid)
        if lok_id is None or uneseno.get(grad_oid, 0) >= 5:
            continue
        tip, kapacitet = TIP_MAP[row['fclass']]
        cursor.execute("""
            INSERT INTO kontejneri (tip, kapacitet_litara, stanje, datum_postavljanja, lokacija_id)
            VALUES (%s, %s, %s, %s, %s)
        """, (tip, kapacitet, random.choice(stanja), random.choice(datumi_k), lok_id))
        uneseno[grad_oid] = uneseno.get(grad_oid, 0) + 1
        k_count += 1
    conn.commit()
    print(f"Kontejneri uneti: {k_count}")

    # ── Punjenje deponija (iz OSM landfill poligona) ──
    deponije_wgs84 = deponije_gdf[['osm_id', 'name', 'geometry']].copy()
    deponije_utm   = deponije_wgs84.to_crs('EPSG:32634')

    # Svaka deponija se dodeljuje najbližem gradu
    joined_d = gpd.sjoin_nearest(
        deponije_utm,
        gradovi_utm[['osm_id', 'geometry']].rename(columns={'osm_id': 'grad_osm_id'}),
        how='left'
    )

    uneseno_d = {oid: 0 for oid in lok_map}
    dep_ids   = []  # ID-ovi unetih deponija (za inspekcije)

    for idx, row in joined_d.iterrows():
        grad_oid = row.get('grad_osm_id')
        lok_id   = lok_map.get(grad_oid)
        if lok_id is None or uneseno_d.get(grad_oid, 0) >= 3:
            continue
        naziv = row['name'] if pd.notna(row['name']) else f"Deponija {row['osm_id']}"
        # WKT geometrija iz originalnog WGS84 GeoDataFrame-a (ne UTM!)
        geom_wgs84 = deponije_wgs84.loc[idx, 'geometry']
        wkt        = geom_wgs84.wkt
        try:
            # Površina se računa u UTM (metri²), ne u WGS84 stepenima
            area     = row['geometry'].buffer(0).area  # buffer(0) popravlja nevalidne geometrije
            povrsina = round(area, 1) if area == area else 0.0  # NaN check
        except Exception:
            povrsina = 0.0
        cursor.execute("""
            INSERT INTO deponije (naziv, povrsina_m2, tip_otpada, status, datum_otkrivanja, lokacija_id, geom)
            VALUES (%s, %s, %s, %s, %s, %s, ST_GeomFromText(%s, 4326))
            RETURNING id
        """, (naziv, povrsina, random.choice(TIPOVI), random.choice(STATUSI),
              random.choice(DATUMI), lok_id, wkt))
        dep_ids.append(cursor.fetchone()[0])
        uneseno_d[grad_oid] = uneseno_d.get(grad_oid, 0) + 1
    conn.commit()
    print(f"Deponije unete: {len(dep_ids)}")

    # ── Punjenje inspekcija (sintetičke, vezane za prave deponije) ──
    # Inspekcije su sintetičke jer nema javno dostupnih podataka o stvarnim inspekcijama
    for i, dep_id in enumerate(dep_ids[:10]):
        cursor.execute("""
            INSERT INTO inspekcije (datum, nalaz, preporuka, inspektor, deponija_id)
            VALUES (%s, %s, %s, %s, %s)
        """, (random.choice(DATUMI), random.choice(NALAZI),
              random.choice(PREPORUKE), random.choice(INSPEKTORI), dep_id))
    conn.commit()
    print("Inspekcije unete!")

    cursor.close()
    conn.close()
    print("\nBaza uspešno popunjena sa podacima za Vojvodinu!")


if __name__ == "__main__":
    kreiraj_tabele()
