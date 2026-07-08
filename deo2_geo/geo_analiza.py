"""
geo_analiza.py — Geografska analiza i vizuelizacija podataka
Učitava OSM SHP podatke za Vojvodinu, spaja ih sa podacima iz PostGIS baze
i kreira interaktivnu folium mapu sa više slojeva i satelitskom podlogom.
"""
# WKT - Well-Known Text - standardni tekstualni format (OGC standard) za zapisivanje geometrijskih
# oblika kao obicnog stringa. To je zajednicki jezik preko kog PostGIS (baza) i Shapely/GeoPandas
# (Python) razmenjuju geometriju, jer PostGIS interno cuva geometriju u binarnom formatu koji Python 
# biblioteke ne mogu direktno da procitaju

import geopandas as gpd
import folium
import pandas as pd
import psycopg2
from shapely.geometry import Point
from shapely import wkt as swkt
import urllib.request
import zipfile
import os
from dotenv import load_dotenv

# Učitava varijable iz .env fajla (DB_URL i sl.)
load_dotenv()
DB_URL = os.environ.get("DB_URL")

# Putanja do foldera sa SHP fajlovima (relativan od lokacije ovog skripte)
SHP_DIR = os.path.join(os.path.dirname(__file__), '..', 'serbia_shp')

def get_connection():
    """Otvara konekciju na PostgreSQL/PostGIS bazu."""
    return psycopg2.connect(DB_URL)


# ─────────────────────────────────────────────
# 1. Preuzimanje SHP podataka
# Ovo je samo fallback ako folder sa .shp fajlovima vec ne postoji, onda ce se preuzeti sa GEofabrik sajta
# ─────────────────────────────────────────────
def preuzmi_shp_podatke():
    """
    Preuzima OSM SHP fajlove za Srbiju sa Geofabrik servera ako već ne postoje.
    Zip arhiva se raspakuje u SHP_DIR folder.
    """
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
    """
    Učitava mesta i landuse SHP fajlove i filtrira ih na bbox Vojvodine.
    .cx[] je GeoPandas indeksiranje po koordinatama (coordinate indexing).
    """
    # Za razliku od baza.py, ovde uzimamo sva mesta i sve landuse povrsine unutar bbox Vojvodine
    # Razlog: ovi slojevi ovde sluze kao vizuelna referentna podloga na mapi (OSM mesta, OSM koriscena zemljista, 
    # slojevi koji se mogu ukljucivati/iskljucivati) 
    print("\nUcitavanje SHP podataka...")

    # 2a. Mesta (tačke) — gradovi, sela, naselja
    places_path = os.path.join(SHP_DIR, 'gis_osm_places_free_1.shp')
    gdf_places = gpd.read_file(places_path)
    # Filtriraj samo objekte unutar bbox Vojvodine [lon_min:lon_max, lat_min:lat_max]
    gdf_places = gdf_places.cx[18.8:21.7, 44.6:46.2].copy()
    print(f"  Places — {len(gdf_places)} objekata u Vojvodini")

    # 2b. Korišćenje zemljišta (poligoni) — šume, industrijske zone, stambene zone...
    landuse_path = os.path.join(SHP_DIR, 'gis_osm_landuse_a_free_1.shp')
    gdf_landuse = gpd.read_file(landuse_path)
    gdf_landuse = gdf_landuse.cx[18.8:21.7, 44.6:46.2].copy()
    print(f"  Landuse — {len(gdf_landuse)} poligona u Vojvodini")

    return gdf_places, gdf_landuse


# ─────────────────────────────────────────────
# 3. Učitavanje podataka iz baze
# ─────────────────────────────────────────────
def ucitaj_podatke_iz_baze():
    """
    Čita lokacije, kontejnere i deponije iz PostGIS baze.
    ST_X/ST_Y ekstrahuju koordinate iz geometry kolone.
    ST_AsText konvertuje poligon u WKT string za prikaz na mapi.
    """
    conn = get_connection()
    # cursor sluzi kao posrednik izmedju baze i Python koda
    cursor = conn.cursor()

    # Lokacije — koordinate se ekstrahuju iz PostGIS tačke
    cursor.execute("""
        SELECT id, naziv, opstina, adresa, tip_podrucja,
               ST_X(geom) as lon, ST_Y(geom) as lat
        FROM lokacije
    """)
    # Fetchall preuzima podatke iz upita u Python promenljivu
    rows = cursor.fetchall()
    df_lokacije = pd.DataFrame(rows,
        columns=['id', 'naziv', 'opstina', 'adresa', 'tip_podrucja', 'lon', 'lat']) #Rucno pravljen DataFrame

    # Kontejneri — sopstvena geom koordinata (ne koordinata grada), JOIN za naziv lokacije
    df_kontejneri = pd.read_sql("""
        SELECT k.id, k.tip, k.stanje, k.kapacitet_litara,
               ST_X(k.geom) as lon, ST_Y(k.geom) as lat,
               l.naziv as lokacija, l.id as lokacija_id
        FROM kontejneri k
        JOIN lokacije l ON k.lokacija_id = l.id
    """, conn)  # odmah u DataFrame 

    # Deponije — geometrija kao WKT (Well-Known Text) za crtanje poligona na mapi
    # ostaje lista tuplova, posto ce kasnije trebati da se iterira kroz njega
    # (lakse je iterirati kroz tuple, nego kroz DataFrame). ST_AsText(geom) - pretvara
    # PostGIS poligon u WKT tekst
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
# 4. Spajanje SHP sa podacima iz baze (spatial join)
# ─────────────────────────────────────────────
def spoji_shp_sa_bazom(df_lokacije, gdf_places):
    """
    Spatial join: za svaku lokaciju iz baze pronalazi najbliži objekat iz OSM places SHP-a.
    gpd.sjoin_nearest() pronalazi najbližeg suseda za svaku tačku.
    distance_col čuva distancu u stepenima — množi se sa 111320 za aproksimaciju u metrima.
    """
    print("\nSpatial join — SHP places + lokacije iz baze...")

    # Konvertuj DataFrame lokacija u GeoDataFrame (dodaj geometry kolonu)
    geometry = [Point(xy) for xy in zip(df_lokacije['lon'], df_lokacije['lat'])]
    gdf_baza = gpd.GeoDataFrame(df_lokacije.copy(), geometry=geometry, crs='EPSG:4326')#ovo je oznaka za WGS84

    # Uskladi koordinatne sisteme ako se razlikuju
    if gdf_places.crs != gdf_baza.crs:
        gdf_places = gdf_places.to_crs(gdf_baza.crs)

    # Nearest join — svaka lokacija iz baze dobija atribute najbližeg OSM mesta, radi se sa WGS84 
    # Ovaj postupak daje brz uvid u to koliko se dobro lokacije iz baze poklapaju sa OSM podacima.
    # Svrha ovoga je da se potvrdi da li se baza i OSM slazu
    # distance_m ne upisujemo nazad u bazu, on nam je samo brza provera
    joined = gpd.sjoin_nearest(
        gdf_baza[['id', 'naziv', 'lon', 'lat', 'geometry']],
        gdf_places[['name', 'fclass', 'geometry']],
        how='left',
        distance_col='distanca_stepen'
    )
    # Gruba konverzija stepeni → metara (1 stepen ≈ 111.32 km na ekvatoru)
    joined['distanca_m'] = joined['distanca_stepen'] * 111320

    df_joined = pd.DataFrame(joined.drop(columns='geometry'))
    print(df_joined[['naziv', 'name', 'fclass', 'distanca_m']].to_string(index=False))
    return df_joined


# ─────────────────────────────────────────────
# 5. Kreiranje mape sa svim slojevima i rasterom
# ─────────────────────────────────────────────
def kreiraj_mapu(df_lokacije, df_kontejneri, deponije_data, gdf_places, gdf_landuse):
    """
    Kreira interaktivnu folium mapu sa sledećim slojevima:
    - Raster podloga: Esri World Imagery satelitski snimak ili OSM standardni tile
    - SHP sloj 1: OSM mesta (tačke)
    - SHP sloj 2: OSM korišćenje zemljišta (poligoni)
    - Sloj 3: Lokacije iz baze
    - Sloj 4: Kontejneri (boje po stanju)
    - Sloj 5: Deponije (poligoni, boje po statusu)
    Svi slojevi se mogu uključiti/isključiti putem LayerControl-a.
    """
    # Esri World Imagery i OSM  standarni tile, oba sa overaly=false, sto ih cini medjusobno iskljucivim
    # odnosno mogu se pomocu LayerControl birati kao osnova (ili jedan ili drugi)
    print("\nKreiranje mape...")

    # fit_bounds automatski podešava zoom da prikaže celu Vojvodinu
    mapa = folium.Map()
    mapa.fit_bounds([[44.6, 18.8], [46.2, 21.7]])

    # Raster podloga: satelitski snimak (Esri World Imagery WMS tile) ──
    folium.TileLayer(
        tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        attr='Esri World Imagery',
        name='Satelitska podloga (Raster)',
        overlay=False,   # bazni sloj, ne overlay
        control=True
    ).add_to(mapa)
    folium.TileLayer('OpenStreetMap', name='OpenStreetMap', overlay=False, control=True).add_to(mapa)

    # ── SHP sloj 1: OSM Mesta (tačke) ──
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
    # Svaki tip korišćenja zemljišta ima svoju boju
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
        # Shapely geometrija može biti Polygon ili MultiPolygon — prikazujemo prvu
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

    # ── Sloj 4: Kontejneri (sopstvena OSM koordinata, boja po stanju) ──
    fg_kontejneri = folium.FeatureGroup(name='Kontejneri (baza)', show=True)
    for _, row in df_kontejneri.iterrows():
        # Zeleno = dobro, narandžasto = oštećen, crveno = loše
        color = 'green' if row['stanje'] == 'dobro' else ('orange' if row['stanje'] == 'ostecen' else 'red')
        folium.Marker(
            location=[row['lat'], row['lon']],
            popup=(f"<b>{row['tip']}</b><br>"
                   f"Stanje: {row['stanje']}<br>"
                   f"Kapacitet: {row['kapacitet_litara']} L<br>"
                   f"Lokacija: {row['lokacija']}"),
            icon=folium.Icon(color=color, icon='trash'),
            tooltip=f"{row['tip']} — {row['stanje']}"
        ).add_to(fg_kontejneri)
    fg_kontejneri.add_to(mapa)

    # ── Sloj 5: Deponije (poligon + marker na centroidu, boja po statusu) ──
    fg_deponije = folium.FeatureGroup(name='Deponije (baza)', show=True)
    for deponija in deponije_data:
        _, naziv, povrsina, tip_otpada, status, geom_text = deponija
        if not geom_text:
            continue
        # Crveno = aktivna, narandžasto = u sanaciji, zeleno = sanirana
        color = 'red' if status == 'aktivna' else ('orange' if status == 'u sanaciji' else 'green')
        popup_html = (f"<b>{naziv}</b><br>"
                      f"Površina: {povrsina} m²<br>"
                      f"Tip: {tip_otpada}<br>"
                      f"Status: {status}")
        try:
            geom = swkt.loads(geom_text)
            if geom.geom_type == 'MultiPolygon':
                geom = list(geom.geoms)[0]
            coords = [[y, x] for x, y in geom.exterior.coords]
            folium.Polygon(
                locations=coords,
                popup=popup_html,
                color=color, fill=True, fillColor=color,
                fillOpacity=0.5, weight=2
            ).add_to(fg_deponije)
            # Marker na centroidu — poligon sam po sebi nije uvek dovoljno uočljiv
            centroid = geom.centroid
            folium.Marker(
                location=[centroid.y, centroid.x],
                popup=popup_html,
                tooltip=naziv,
                icon=folium.Icon(color=color, icon='warning-sign', prefix='glyphicon')
            ).add_to(fg_deponije)
        except Exception:
            continue  # Preskoči deponije sa nevalidnom geometrijom
    fg_deponije.add_to(mapa)

    # Kontrola slojeva — dugme za uključivanje/isključivanje slojeva
    folium.LayerControl(collapsed=False).add_to(mapa)

    out_path = os.path.join(os.path.dirname(__file__), 'mapa_vojvodina.html')
    mapa.save(out_path)
    print(f"Mapa sacuvana kao '{out_path}'")


if __name__ == "__main__":
    preuzmi_shp_podatke()

    # Učitaj SHP podatke za Vojvodinu
    gdf_places, gdf_landuse = ucitaj_shp_podatke()

    print("\n=== DataFrame iz SHP (places) ===")
    print(gdf_places[['name', 'fclass', 'geometry']].head(10).to_string(index=False))

    print("\n=== DataFrame iz SHP (landuse) ===")
    print(gdf_landuse[['name', 'fclass', 'geometry']].head(10).to_string(index=False))

    # Učitaj podatke iz baze
    df_lokacije, df_kontejneri, deponije_data = ucitaj_podatke_iz_baze()

    print("\n=== Lokacije (baza) ===")
    print(df_lokacije[['naziv', 'opstina', 'tip_podrucja', 'lon', 'lat']].to_string(index=False))

    # Spatial join: spoji lokacije iz baze sa najbližim OSM mestima
    df_joined = spoji_shp_sa_bazom(df_lokacije, gdf_places)
    print("\n=== Joined DataFrame (lokacije + OSM places) ===")
    print(df_joined[['naziv', 'name', 'fclass', 'distanca_m']].to_string(index=False))

    # Kreiraj interaktivnu mapu sa svim slojevima
    kreiraj_mapu(df_lokacije, df_kontejneri, deponije_data, gdf_places, gdf_landuse)

    print("\n=== DEO 2 ZAVRSEN! ===")
