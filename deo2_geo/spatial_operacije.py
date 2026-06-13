import geopandas as gpd
import pandas as pd
import psycopg2
from shapely.geometry import Point, box, Polygon
import folium

DB_URL = "postgresql://postgres.vtmpqdgrtntctvbusxec:NoviSad2024!@aws-0-eu-west-1.pooler.supabase.com:6543/postgres"

def get_connection():
    return psycopg2.connect(DB_URL)

# Učitavanje podataka
def ucitaj_podatke():
    conn = get_connection()
    
    # Lokacije
    lokacije_df = pd.read_sql("""
        SELECT id, naziv, ST_X(geom) as lon, ST_Y(geom) as lat FROM lokacije
    """, conn)
    
    # Deponije sa geometrijom
    deponije = pd.read_sql("""
        SELECT id, naziv, povrsina_m2, status, ST_AsText(geom) as geom FROM deponije
    """, conn)
    
    conn.close()
    return lokacije_df, deponije

# SPATIAL OPERACIJE

# 1. BUFFER — Kreiraj zonu od 500m oko svake deponije
def buffer_operacija(lokacije_df):
    print("1️⃣ BUFFER OPERACIJA — Kreiraj zaštitnu zonu od 500m oko lokacija")
    
    # Kreiraj tačke
    geometry = [Point(xy) for xy in zip(lokacije_df['lon'], lokacije_df['lat'])]
    gdf = gpd.GeoDataFrame(lokacije_df, geometry=geometry, crs='EPSG:4326')
    
    # Buffer u metrima (mora se konvertovati u UTM)
    gdf_utm = gdf.to_crs('EPSG:32634')  # UTM zona 34N
    gdf_buffer = gdf_utm.copy()
    gdf_buffer['geometry'] = gdf_utm.geometry.buffer(500)  # 500m
    gdf_buffer = gdf_buffer.to_crs('EPSG:4326')
    
    print(gdf_buffer[['naziv', 'geometry']])
    return gdf_buffer

# 2. INTERSECTION — Pronađi koja lokacija se nalazi u zaštitnoj zoni
def intersection_operacija(lokacije_df, buffer_zone):
    print("\n2️⃣ INTERSECTION — Koja lokacija se nalazi u drugoj zaštitnoj zoni?")
    
    geometry = [Point(xy) for xy in zip(lokacije_df['lon'], lokacije_df['lat'])]
    gdf_lokacije = gpd.GeoDataFrame(lokacije_df, geometry=geometry, crs='EPSG:4326')
    
    # Pronađi preseke
    intersections = gpd.sjoin(gdf_lokacije, buffer_zone, how='inner', predicate='intersects')
    
    print(f"Pronađeno {len(intersections)} lokacija u zaštitnim zonama")
    print(intersections[['naziv_left', 'naziv_right']])
    return intersections

# 3. UNION — Spoji sve zaštitne zone u jedan veliki poligon
def union_operacija(buffer_zone):
    print("\n3️⃣ UNION — Spoji sve zaštitne zone u jedan poligon")
    
    # Unija svih buffer zona
    union_geom = buffer_zone.geometry.unary_union
    
    print(f"Единствена unija kreirана")
    print(f"Površina: {union_geom.area:.4f} kvadratnih stepeni")
    
    return union_geom

# 4. CLIP — Iseci samo deponije koje se nalaze u određenom području
def clip_operacija(lokacije_df):
    print("\n4️⃣ CLIP — Iseci samo lokacije u području oko Novog Sada")
    
    # Definiši klipujuću zonu (kvadrat oko Novog Sada)
    clip_box = box(19.7, 45.1, 20.0, 45.4)
    gdf_clip = gpd.GeoDataFrame([1], geometry=[clip_box], crs='EPSG:4326')
    
    # Kreiraj GeoDataFrame lokacija
    geometry = [Point(xy) for xy in zip(lokacije_df['lon'], lokacije_df['lat'])]
    gdf_lokacije = gpd.GeoDataFrame(lokacije_df, geometry=geometry, crs='EPSG:4326')
    
    # Clip — pronađi samo lokacije koje su u kvadratu
    clipped = gpd.clip(gdf_lokacije, gdf_clip)
    
    print(f"Pronađeno {len(clipped)} lokacija u klipovanoj zoni")
    print(clipped[['naziv']])
    return clipped

# 5. DIFFERENCE — Pronađi sve lokacije izvan zaštitne zone
def difference_operacija(lokacije_df, buffer_zone):
    print("\n5️⃣ DIFFERENCE — Lokacije IZVAN zaštitnih zona")
    
    geometry = [Point(xy) for xy in zip(lokacije_df['lon'], lokacije_df['lat'])]
    gdf_lokacije = gpd.GeoDataFrame(lokacije_df, geometry=geometry, crs='EPSG:4326')
    
    # Pronađi lokacije koje se NE nalaze u buffer zonama
    joined = gpd.sjoin(gdf_lokacije, buffer_zone, how='left', predicate='intersects')
    difference_result = joined[joined['index_right'].isna()]
    
    print(f"Pronađeno {len(difference_result)} lokacija izvan zaštitnih zona")
    if len(difference_result) > 0:
        print(difference_result[['naziv']])
    else:
        print("Sve lokacije se nalaze u zaštitnim zonama")
    return difference_result

# SPATIAL QUERIES

# 1. WITHIN — Pronađi sve lokacije koje se nalaze UNUTAR zaštitne zone
def query_within(lokacije_df, buffer_zone):
    print("\n🔍 QUERY 1: WITHIN — Lokacije UNUTAR zaštitne zone")
    
    geometry = [Point(xy) for xy in zip(lokacije_df['lon'], lokacije_df['lat'])]
    gdf_lokacije = gpd.GeoDataFrame(lokacije_df, geometry=geometry, crs='EPSG:4326')
    
    # Within query
    result = gdf_lokacije[gdf_lokacije.geometry.within(buffer_zone.geometry.unary_union)]
    
    print(f"Pronađeno {len(result)} lokacija")
    print(result[['naziv']])
    return result

# 2. OVERLAPS — Pronađi sve lokacije koje se PREKLAPAJU sa zaštitnom zonom
def query_overlaps(lokacije_df, buffer_zone):
    print("\n🔍 QUERY 2: OVERLAPS — Lokacije koje se preklapaju")
    
    geometry = [Point(xy) for xy in zip(lokacije_df['lon'], lokacije_df['lat'])]
    gdf_lokacije = gpd.GeoDataFrame(lokacije_df, geometry=geometry, crs='EPSG:4326')
    
    result = gpd.sjoin(gdf_lokacije, buffer_zone, how='inner', predicate='intersects')
    
    print(f"Pronađeno {len(result)} preklapanja")
    print(result[['naziv_left', 'naziv_right']])
    return result

# 3. CONTAINS — Pronađi sve zaštitne zone koje SADRŽE lokacije
def query_contains(lokacije_df, buffer_zone):
    print("\n🔍 QUERY 3: CONTAINS — Zaštitne zone koje sadrže lokacije")
    
    geometry = [Point(xy) for xy in zip(lokacije_df['lon'], lokacije_df['lat'])]
    gdf_lokacije = gpd.GeoDataFrame(lokacije_df, geometry=geometry, crs='EPSG:4326')
    
    result = gpd.sjoin(gdf_lokacije, buffer_zone, how='inner', predicate='contains')
    
    print(f"Pronađeno {len(result)} sadržavanja")
    return result

# 4. DISTANCE — Pronađi najblizu lokaciju svakom kontejanru
def query_distance(lokacije_df):
    print("\n🔍 QUERY 4: DISTANCE — Najbliza lokacija")
    
    geometry = [Point(xy) for xy in zip(lokacije_df['lon'], lokacije_df['lat'])]
    gdf_lokacije = gpd.GeoDataFrame(lokacije_df, geometry=geometry, crs='EPSG:4326')
    gdf_utm = gdf_lokacije.to_crs('EPSG:32634')
    
    # Distanca između prvih dvaju lokacija
    if len(gdf_utm) >= 2:
        dist = gdf_utm.geometry.iloc[0].distance(gdf_utm.geometry.iloc[1])
        print(f"Distanca između {lokacije_df.iloc[0]['naziv']} i {lokacije_df.iloc[1]['naziv']}: {dist:.0f}m")

# 5. DISJOINT — Pronađi lokacije koje se NE dodiruju
def query_disjoint(lokacije_df, buffer_zone):
    print("\n🔍 QUERY 5: DISJOINT — Lokacije koje se NE dodiruju sa zonom")
    
    geometry = [Point(xy) for xy in zip(lokacije_df['lon'], lokacije_df['lat'])]
    gdf_lokacije = gpd.GeoDataFrame(lokacije_df, geometry=geometry, crs='EPSG:4326')
    
    result = gdf_lokacije[~gdf_lokacije.geometry.intersects(buffer_zone.geometry.unary_union)]
    
    print(f"Pronađeno {len(result)} disjunktnih lokacija")
    print(result[['naziv']])
    return result

if __name__ == "__main__":
    print("="*70)
    print("SPATIAL OPERACIJE I SPATIAL QUERIES")
    print("="*70)
    
    # Učitaj podatke
    lokacije_df, deponije = ucitaj_podatke()
    
    print("\n📍 LOKACIJE:")
    print(lokacije_df)
    
    # SPATIAL OPERACIJE
    buffer_zone = buffer_operacija(lokacije_df)
    intersection_operacija(lokacije_df, buffer_zone)
    union_geom = union_operacija(buffer_zone)
    clipped = clip_operacija(lokacije_df)
    difference_operacija(lokacije_df, buffer_zone)
    
    # SPATIAL QUERIES
    query_within(lokacije_df, buffer_zone)
    query_overlaps(lokacije_df, buffer_zone)
    query_contains(lokacije_df, buffer_zone)
    query_distance(lokacije_df)
    query_disjoint(lokacije_df, buffer_zone)
    
    print("\n" + "="*70)
    print("✅ SVE OPERACIJE I UPITI ZAVRŠENI!")
    print("="*70)