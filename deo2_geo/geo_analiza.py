import geopandas as gpd
import folium
import pandas as pd
import psycopg2
from shapely.geometry import Point
import urllib.request
import zipfile
import os

DB_URL = "postgresql://postgres.vtmpqdgrtntctvbusxec:NoviSad2024!@aws-0-eu-west-1.pooler.supabase.com:6543/postgres"
SHP_DIR = os.path.join(os.path.dirname(__file__), '..', 'serbia_shp')

def get_connection():
    return psycopg2.connect(DB_URL)


# ─────────────────────────────────────────────
# 1. Preuzimanje SHP podataka
# ─────────────────────────────────────────────
def preuzmi_shp_podatke():
    if not os.path.exists(SHP_DIR):
        print("Preuzimanje SHP podataka za Srbiju...")
        url = "https://download.geofabrik.de/europe/serbia-latest-free.shp.zip"
        urllib.request.urlretrieve(url, "serbia.zip")
        with zipfile.ZipFile("serbia.zip", 'r') as z:
            z.extractall(SHP_DIR)
        os.remove("serbia.zip")
        print("SHP fajlovi preuzeti!")
    else:
        print("SHP fajlovi vec postoje!")


# ─────────────────────────────────────────────
# 2. Učitavanje SHP fajlova u GeoDataFrame
# ─────────────────────────────────────────────
def ucitaj_shp_podatke():
    """Ucitava places i landuse SHP, filtrira na Novi Sad bbox."""
    print("\nUcitavanje SHP podataka...")

    # 2a. Mesta (tacke)
    places_path = os.path.join(SHP_DIR, 'gis_osm_places_free_1.shp')
    gdf_places = gpd.read_file(places_path)
    gdf_places = gdf_places.cx[19.6:20.1, 45.1:45.5].copy()
    print(f"  Places — {len(gdf_places)} objekata u oblasti Novog Sada")

    # 2b. Korišćenje zemljišta (poligoni)
    landuse_path = os.path.join(SHP_DIR, 'gis_osm_landuse_a_free_1.shp')
    gdf_landuse = gpd.read_file(landuse_path)
    gdf_landuse = gdf_landuse.cx[19.7:20.0, 45.15:45.40].copy()
    print(f"  Landuse — {len(gdf_landuse)} poligona u oblasti Novog Sada")

    return gdf_places, gdf_landuse


# ─────────────────────────────────────────────
# 3. Učitavanje podataka iz baze
# ─────────────────────────────────────────────
def ucitaj_podatke_iz_baze():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, naziv, opstina, adresa, tip_podrucja,
               ST_X(geom) as lon, ST_Y(geom) as lat
        FROM lokacije
    """)
    rows = cursor.fetchall()
    df_lokacije = pd.DataFrame(rows,
        columns=['id', 'naziv', 'opstina', 'adresa', 'tip_podrucja', 'lon', 'lat'])

    df_kontejneri = pd.read_sql("""
        SELECT k.id, k.tip, k.stanje, k.kapacitet_litara,
               l.naziv as lokacija, l.id as lokacija_id
        FROM kontejneri k
        JOIN lokacije l ON k.lokacija_id = l.id
    """, conn)

    cursor.execute("""
        SELECT id, naziv, povrsina_m2, tip_otpada, status,
               ST_AsText(geom) as geom_text
        FROM deponije
    """)
    deponije_data = cursor.fetchall()

    cursor.close()
    conn.close()
    return df_lokacije, df_kontejneri, deponije_data


# ─────────────────────────────────────────────
# 4. Spajanje SHP sa podacima iz baze (join)
# ─────────────────────────────────────────────
def spoji_shp_sa_bazom(df_lokacije, gdf_places):
    """
    Spatial join: za svaku lokaciju iz baze pronalazi
    najblizi objekat iz OSM places SHP-a.
    """
    print("\nSpatial join — SHP places + lokacije iz baze...")

    # Konvertuj lokacije u GeoDataFrame
    geometry = [Point(xy) for xy in zip(df_lokacije['lon'], df_lokacije['lat'])]
    gdf_baza = gpd.GeoDataFrame(df_lokacije.copy(), geometry=geometry, crs='EPSG:4326')

    if gdf_places.crs != gdf_baza.crs:
        gdf_places = gdf_places.to_crs(gdf_baza.crs)

    # Nearest join — svaka lokacija iz baze dobija atribute najblizeg OSM mesta
    joined = gpd.sjoin_nearest(
        gdf_baza[['id', 'naziv', 'lon', 'lat', 'geometry']],
        gdf_places[['name', 'fclass', 'geometry']],
        how='left',
        distance_col='distanca_stepen'
    )
    joined['distanca_m'] = joined['distanca_stepen'] * 111320  # gruba konverzija stepeni→m

    df_joined = pd.DataFrame(joined.drop(columns='geometry'))
    print(df_joined[['naziv', 'name', 'fclass', 'distanca_m']].to_string(index=False))
    return df_joined


# ─────────────────────────────────────────────
# 5. Kreiranje mape sa svim slojevima i rasterom
# ─────────────────────────────────────────────
def kreiraj_mapu(df_lokacije, df_kontejneri, deponije_data, gdf_places, gdf_landuse):
    print("\nKreiranje mape...")

    mapa = folium.Map(location=[45.2552, 19.8362], zoom_start=12)

    # ── Raster podloga: satelitski snimak (Esri World Imagery WMS tile) ──
    folium.TileLayer(
        tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        attr='Esri World Imagery',
        name='Satelitska podloga (Raster)',
        overlay=False,
        control=True
    ).add_to(mapa)
    folium.TileLayer('OpenStreetMap', name='OpenStreetMap', overlay=False, control=True).add_to(mapa)

    # ── SHP sloj 1: OSM Mesta (tacke) ──
    fg_places = folium.FeatureGroup(name='OSM Mesta (SHP)', show=False)
    for _, row in gdf_places.iterrows():
        if row.geometry is not None and row.geometry.geom_type == 'Point':
            folium.CircleMarker(
                location=[row.geometry.y, row.geometry.x],
                radius=3,
                popup=f"<b>{row.get('name', 'N/A')}</b><br>Tip: {row.get('fclass', '')}",
                color='purple',
                fill=True,
                fillOpacity=0.7
            ).add_to(fg_places)
    fg_places.add_to(mapa)

    # ── SHP sloj 2: OSM Korišćenje zemljišta (poligoni) ──
    landuse_colors = {
        'residential': '#f0e68c', 'industrial': '#cd853f',
        'commercial': '#ffa07a', 'forest': '#228b22',
        'farmland': '#adff2f', 'park': '#90ee90',
        'meadow': '#7cfc00', 'allotments': '#d2b48c'
    }
    fg_landuse = folium.FeatureGroup(name='OSM Korišćenje zemljišta (SHP)', show=False)
    for _, row in gdf_landuse.iterrows():
        if row.geometry is None:
            continue
        ftype = row.get('fclass', 'other')
        color = landuse_colors.get(ftype, '#cccccc')
        geom = row.geometry
        coords = []
        if geom.geom_type == 'Polygon':
            coords = [[y, x] for x, y in geom.exterior.coords]
        elif geom.geom_type == 'MultiPolygon':
            coords = [[y, x] for x, y in list(geom.geoms)[0].exterior.coords]
        if coords:
            folium.Polygon(
                locations=coords,
                popup=f"Tip: {ftype}<br>Naziv: {row.get('name', '')}",
                color=color, fill=True, fillColor=color,
                fillOpacity=0.45, weight=1
            ).add_to(fg_landuse)
    fg_landuse.add_to(mapa)

    # ── Sloj 3: Lokacije iz baze ──
    fg_lokacije = folium.FeatureGroup(name='Lokacije (baza)', show=True)
    for _, row in df_lokacije.iterrows():
        folium.CircleMarker(
            location=[row['lat'], row['lon']],
            radius=7,
            popup=f"<b>{row['naziv']}</b><br>{row['opstina']}<br>Tip: {row['tip_podrucja']}",
            color='blue', fill=True, fillColor='lightblue', fillOpacity=0.8,
            tooltip=row['naziv']
        ).add_to(fg_lokacije)
    fg_lokacije.add_to(mapa)

    # ── Sloj 4: Kontejneri ──
    fg_kontejneri = folium.FeatureGroup(name='Kontejneri (baza)', show=True)
    for _, row in df_kontejneri.iterrows():
        lok = df_lokacije[df_lokacije['id'] == row['lokacija_id']]
        if lok.empty:
            continue
        lat, lon = lok.iloc[0][['lat', 'lon']]
        color = 'green' if row['stanje'] == 'dobro' else ('orange' if row['stanje'] == 'ostecen' else 'red')
        folium.Marker(
            location=[lat, lon],
            popup=(f"<b>{row['tip']}</b><br>"
                   f"Stanje: {row['stanje']}<br>"
                   f"Kapacitet: {row['kapacitet_litara']} L<br>"
                   f"Lokacija: {row['lokacija']}"),
            icon=folium.Icon(color=color, icon='trash'),
            tooltip=f"{row['tip']} — {row['stanje']}"
        ).add_to(fg_kontejneri)
    fg_kontejneri.add_to(mapa)

    # ── Sloj 5: Deponije (poligoni) ──
    fg_deponije = folium.FeatureGroup(name='Deponije (baza)', show=True)
    for deponija in deponije_data:
        _, naziv, povrsina, tip_otpada, status, geom_text = deponija
        if not geom_text or 'POLYGON' not in geom_text:
            continue
        color = 'red' if status == 'aktivna' else ('orange' if status == 'u sanaciji' else 'green')
        coords_str = geom_text.replace('POLYGON((', '').replace('))', '').strip()
        try:
            coords = [[float(y), float(x)] for x, y in [c.split() for c in coords_str.split(',')]]
            folium.Polygon(
                locations=coords,
                popup=(f"<b>{naziv}</b><br>"
                       f"Površina: {povrsina} m²<br>"
                       f"Tip: {tip_otpada}<br>"
                       f"Status: {status}"),
                color=color, fill=True, fillColor=color,
                fillOpacity=0.5, weight=2
            ).add_to(fg_deponije)
        except Exception:
            continue
    fg_deponije.add_to(mapa)

    # Kontrola slojeva
    folium.LayerControl(collapsed=False).add_to(mapa)

    mapa.save('mapa_novi_sad.html')
    print("Mapa sacuvana kao 'mapa_novi_sad.html'")


if __name__ == "__main__":
    preuzmi_shp_podatke()

    # 2. Ucitaj SHP
    gdf_places, gdf_landuse = ucitaj_shp_podatke()

    print("\n=== DataFrame iz SHP (places) ===")
    print(gdf_places[['name', 'fclass', 'geometry']].head(10).to_string(index=False))

    print("\n=== DataFrame iz SHP (landuse) ===")
    print(gdf_landuse[['name', 'fclass', 'geometry']].head(10).to_string(index=False))

    # 3. Ucitaj bazu
    df_lokacije, df_kontejneri, deponije_data = ucitaj_podatke_iz_baze()

    print("\n=== Lokacije (baza) ===")
    print(df_lokacije[['naziv', 'opstina', 'tip_podrucja', 'lon', 'lat']].to_string(index=False))

    # 4. Spatial join SHP + baza
    df_joined = spoji_shp_sa_bazom(df_lokacije, gdf_places)
    print("\n=== Joined DataFrame (lokacije + OSM places) ===")
    print(df_joined[['naziv', 'name', 'fclass', 'distanca_m']].to_string(index=False))

    # 5. Kreiraj mapu
    kreiraj_mapu(df_lokacije, df_kontejneri, deponije_data, gdf_places, gdf_landuse)

    print("\n=== DEO 2 ZAVRSEN! ===")
