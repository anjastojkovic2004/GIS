"""
spatial_operacije.py — 5 prostornih operacija i 5 prostornih upita
Demonstrira geopandas overlay operacije (buffer, intersection, union, clip, difference)
i prostorne upite (within, overlaps, contains, distance, disjoint) nad podacima iz baze.
"""

import geopandas as gpd
import pandas as pd
import psycopg2
import os
from shapely.geometry import Point, box
from shapely import wkt as swkt
from dotenv import load_dotenv

# Učitava DB_URL iz .env fajla
load_dotenv()
DB_URL = os.environ.get("DB_URL")

SHP_DIR = os.path.join(os.path.dirname(__file__), '..', 'serbia_shp')


def get_connection():
    """Otvara konekciju na PostgreSQL/PostGIS bazu."""
    return psycopg2.connect(DB_URL)


def ucitaj_vojvodina_granicu():
    """
    Učitava pravu administrativnu granicu Vojvodine (admin_level4) iz OSM SHP-a.
    Koristi se umesto pravougaonog bbox-a jer Vojvodina nije pravougaonog oblika —
    bbox bi zahvatio i delove susednih zemalja (Rumunija, Mađarska).
    """
    # na=False - ako neki red ima ime name=Nan, dobili bismo gresku, a ovo kaze tretiraj ono sto nema imena kao ne odgovara
    adminareas = gpd.read_file(os.path.join(SHP_DIR, 'gis_osm_adminareas_a_free_1.shp'))
    voj = adminareas[adminareas['name'].str.contains('Војводина', na=False)]
    return voj.iloc[0].geometry

def ucitaj_podatke():
    """Učitava lokacije i deponije iz baze za prostorne analize."""
    conn = get_connection()

    lokacije_df = pd.read_sql("""
        SELECT id, naziv, ST_X(geom) as lon, ST_Y(geom) as lat FROM lokacije
    """, conn)

    # ST_AsText konvertuje PostGIS geometriju u WKT string
    deponije = pd.read_sql("""
        SELECT id, naziv, povrsina_m2, status, ST_AsText(geom) as geom FROM deponije
    """, conn)

    conn.close()
    return lokacije_df, deponije


# ═══════════════════════════════════════════════
# SPATIAL OPERACIJE
# ═══════════════════════════════════════════════

def buffer_operacija(deponije_df):
    """
    BUFFER — Kreira zonu rizika od 3km oko svake deponije.
    Bafer se pravi oko deponija (ne lokacija/gradova) jer to ima realno
    značenje — sanitarna zaštitna zona oko deponije zbog zagađenja,
    smrada i rizika po podzemne vode. Buffer se primenjuje na pravi
    poligon deponije, ne na jednu tačku, pa zona prati njen stvarni oblik.
    Konverzija u UTM (EPSG:32634) je neophodna jer buffer u WGS84 stepenima
    ne daje precizne metre — UTM koristi metre kao jedinicu.
    """
    print("1. BUFFER OPERACIJA — Kreiraj zonu rizika od 3km oko deponija")

    geometry = [swkt.loads(g) for g in deponije_df['geom']]
    gdf = gpd.GeoDataFrame(deponije_df, geometry=geometry, crs='EPSG:4326')

    # Projekcija u UTM zonu 34N za tačan buffer u metrima
    gdf_utm = gdf.to_crs('EPSG:32634')
    gdf_buffer = gdf_utm.copy()
    gdf_buffer['geometry'] = gdf_utm.geometry.buffer(3000)  # 3km
    # Vrati nazad u WGS84 za prikaz na mapi
    gdf_buffer = gdf_buffer.to_crs('EPSG:4326')

    print(gdf_buffer[['naziv', 'geometry']])
    return gdf_buffer

def intersection_operacija(lokacije_df, buffer_zone):
    """
    INTERSECTION — Pronalazi koje lokacije (gradovi) padaju u zonu rizika neke deponije.
    gpd.sjoin sa predicate='intersects' vrši prostorni join između tačaka i poligona.
    """
    print("\n2. INTERSECTION — Koji gradovi se nalaze u zoni rizika neke deponije?")

    geometry = [Point(xy) for xy in zip(lokacije_df['lon'], lokacije_df['lat'])]
    gdf_lokacije = gpd.GeoDataFrame(lokacije_df, geometry=geometry, crs='EPSG:4326')

    # Spatial join — pronađi sve parove (lokacija, zona_rizika) koji se seku
    intersections = gpd.sjoin(gdf_lokacije, buffer_zone, how='inner', predicate='intersects')

    print(f"Pronađeno {len(intersections)} gradova u zoni rizika deponija")
    print(intersections[['naziv_left', 'naziv_right']])
    return intersections

def union_operacija(buffer_zone):
    """
    UNION — Spaja sve zone rizika deponija u jedan poligon eliminišući preklapanja.
    union_all() je geopandas metoda koja objedinjuje sve geometrije u jednu.
    """
    print("\n3. UNION — Spoji sve zone rizika u jedan poligon")

    union_geom = buffer_zone.geometry.union_all()

    print(f"Jedinstvena unija kreirana")
    print(f"Površina: {union_geom.area:.4f} kvadratnih stepeni")

    return union_geom

def clip_operacija(lokacije_df):
    """
    CLIP — Iseca samo lokacije koje se nalaze unutar granica Vojvodine.
    Koristi pravu administrativnu granicu (ne pravougaoni bbox koji bi
    zahvatio i deo Rumunije/Mađarske jer Vojvodina nije pravougaonog oblika).
    gpd.clip() vraća samo geometrije koje se nalaze unutar klipujućeg poligona.
    """
    print("\n4. CLIP — Iseci samo lokacije u području Vojvodine")

    voj_geom = ucitaj_vojvodina_granicu()
    gdf_clip = gpd.GeoDataFrame([1], geometry=[voj_geom], crs='EPSG:4326')

    geometry = [Point(xy) for xy in zip(lokacije_df['lon'], lokacije_df['lat'])]
    gdf_lokacije = gpd.GeoDataFrame(lokacije_df, geometry=geometry, crs='EPSG:4326')

    # Clip — zadrži samo lokacije unutar prave granice Vojvodine
    clipped = gpd.clip(gdf_lokacije, gdf_clip)

    print(f"Pronađeno {len(clipped)} lokacija u klipovanoj zoni")
    print(clipped[['naziv']])
    return clipped

def difference_operacija(lokacije_df, buffer_zone):
    """
    DIFFERENCE — Pronalazi gradove koji se nalaze IZVAN svih zona rizika deponija.
    Left join + filtriranje po index_right IS NULL daje redove bez para u desnom DataFrame-u.
    Nakon sjoin obe tabele imaju 'naziv' pa se kolone preimeuju u naziv_left i naziv_right.
    """
    print("\n5. DIFFERENCE — Gradovi IZVAN zona rizika deponija")

    geometry = [Point(xy) for xy in zip(lokacije_df['lon'], lokacije_df['lat'])]
    gdf_lokacije = gpd.GeoDataFrame(lokacije_df, geometry=geometry, crs='EPSG:4326')

    # Left join: lokacije koje nemaju poklapanje dobijaju NaN u index_right
    joined = gpd.sjoin(gdf_lokacije, buffer_zone, how='left', predicate='intersects')
    difference_result = joined[joined['index_right'].isna()]

    print(f"Pronađeno {len(difference_result)} gradova izvan zona rizika")
    if len(difference_result) > 0:
        # naziv_left jer sjoin preimenuje kolone kada oba DF-a imaju kolonu 'naziv'
        print(difference_result[['naziv_left']].rename(columns={'naziv_left': 'naziv'}))
    else:
        print("Svi gradovi se nalaze u nekoj zoni rizika")
    return difference_result


# ═══════════════════════════════════════════════
# SPATIAL UPITI
# ═══════════════════════════════════════════════

def query_within(lokacije_df, buffer_zone):
    """
    WITHIN — Pronalazi gradove koji se nalaze UNUTAR unije svih zona rizika.
    .within() vraca True za tačke koje su potpuno unutar poligona.
    """
    print("\nQUERY 1: WITHIN — Gradovi UNUTAR zone rizika deponija")

    geometry = [Point(xy) for xy in zip(lokacije_df['lon'], lokacije_df['lat'])]
    gdf_lokacije = gpd.GeoDataFrame(lokacije_df, geometry=geometry, crs='EPSG:4326')

    # union_all() spaja sve zone rizika, then within proverava svaku tačku
    result = gdf_lokacije[gdf_lokacije.geometry.within(buffer_zone.geometry.union_all())]

    print(f"Pronađeno {len(result)} gradova")
    print(result[['naziv']])
    return result

def query_overlaps(lokacije_df, buffer_zone):
    """
    OVERLAPS — Pronalazi gradove koji se PREKLAPAJU sa zonama rizika.
    Koristi sjoin sa predicate='intersects' koji pokriva i within i crosses.
    """
    print("\nQUERY 2: OVERLAPS — Gradovi koji se preklapaju sa zonom rizika")

    geometry = [Point(xy) for xy in zip(lokacije_df['lon'], lokacije_df['lat'])]
    gdf_lokacije = gpd.GeoDataFrame(lokacije_df, geometry=geometry, crs='EPSG:4326')

    result = gpd.sjoin(gdf_lokacije, buffer_zone, how='inner', predicate='intersects')

    print(f"Pronađeno {len(result)} preklapanja")
    print(result[['naziv_left', 'naziv_right']])
    return result

def query_contains(lokacije_df, buffer_zone):
    """
    CONTAINS — Pronalazi zone rizika koje SADRŽE neki grad.
    predicate='within' znači da leva geometrija mora biti unutar desne.
    """
    print("\nQUERY 3: CONTAINS — Zone rizika koje sadrže neki grad")

    geometry = [Point(xy) for xy in zip(lokacije_df['lon'], lokacije_df['lat'])]
    gdf_lokacije = gpd.GeoDataFrame(lokacije_df, geometry=geometry, crs='EPSG:4326')

    result = gpd.sjoin(gdf_lokacije, buffer_zone, how='inner', predicate='within')

    print(f"Pronađeno {len(result)} sadržavanja")
    return result

def query_distance(lokacije_df):
    """
    DISTANCE — Izračunava distancu između prve dve lokacije u UTM metrima.
    Shapely .distance() metoda radi u jedinicama koordinatnog sistema,
    pa je UTM projekcija neophodna za rezultat u metrima.
    """
    print("\nQUERY 4: DISTANCE — Najbliza lokacija")

    geometry = [Point(xy) for xy in zip(lokacije_df['lon'], lokacije_df['lat'])]
    gdf_lokacije = gpd.GeoDataFrame(lokacije_df, geometry=geometry, crs='EPSG:4326')
    # Konvertuj u UTM za distancu u metrima
    gdf_utm = gdf_lokacije.to_crs('EPSG:32634')

    if len(gdf_utm) >= 2:
        dist = gdf_utm.geometry.iloc[0].distance(gdf_utm.geometry.iloc[1])
        print(f"Distanca između {lokacije_df.iloc[0]['naziv']} i {lokacije_df.iloc[1]['naziv']}: {dist:.0f}m")

def query_disjoint(lokacije_df, buffer_zone):
    """
    DISJOINT — Pronalazi gradove koji se NE dodiruju ni sa jednom zonom rizika.
    ~ operátor negira boolean seriju (ekvivalent NOT u SQL-u).
    """
    print("\nQUERY 5: DISJOINT — Gradovi koji se NE dodiruju ni sa jednom zonom rizika")

    geometry = [Point(xy) for xy in zip(lokacije_df['lon'], lokacije_df['lat'])]
    gdf_lokacije = gpd.GeoDataFrame(lokacije_df, geometry=geometry, crs='EPSG:4326')

    # Pronađi gradove koji NE seku uniju svih zona rizika
    result = gdf_lokacije[~gdf_lokacije.geometry.intersects(buffer_zone.geometry.union_all())]

    print(f"Pronađeno {len(result)} gradova van svih zona rizika")
    print(result[['naziv']])
    return result


if __name__ == "__main__":
    print("=" * 70)
    print("SPATIAL OPERACIJE I SPATIAL QUERIES")
    print("=" * 70)

    # Učitaj podatke iz baze
    lokacije_df, deponije = ucitaj_podatke()

    print("\nLOKACIJE:")
    print(lokacije_df)

    # ── 5 SPATIAL OPERACIJA ──
    buffer_zone = buffer_operacija(deponije)
    intersection_operacija(lokacije_df, buffer_zone)
    union_geom = union_operacija(buffer_zone)
    clipped = clip_operacija(lokacije_df)
    difference_operacija(lokacije_df, buffer_zone)

    # ── 5 SPATIAL UPITA ──
    query_within(lokacije_df, buffer_zone)
    query_overlaps(lokacije_df, buffer_zone)
    query_contains(lokacije_df, buffer_zone)
    query_distance(lokacije_df)
    query_disjoint(lokacije_df, buffer_zone)

    print("\n" + "=" * 70)
    print("SVE OPERACIJE I UPITI ZAVRŠENI!")
    print("=" * 70)
