"""
mapa_spatial_operacije.py — Interaktivna mapa prostornih operacija
Vizuelizuje lokacije, zone rizika (3km) oko deponija, clip zonu Vojvodine
i linije distanci između lokacija na folium mapi.
"""

import geopandas as gpd
import pandas as pd
import psycopg2
import os
from shapely.geometry import Point
from shapely import wkt as swkt
import folium
from dotenv import load_dotenv

# Učitava DB_URL iz .env fajla
load_dotenv()
DB_URL = os.environ.get("DB_URL")

SHP_DIR = os.path.join(os.path.dirname(__file__), '..', 'serbia_shp')


def get_connection():
    """Otvara konekciju na PostgreSQL/PostGIS bazu."""
    return psycopg2.connect(DB_URL)


def ucitaj_vojvodina_granicu():
    """Učitava pravu administrativnu granicu Vojvodine (admin_level4) iz OSM SHP-a."""
    adminareas = gpd.read_file(os.path.join(SHP_DIR, 'gis_osm_adminareas_a_free_1.shp'))
    voj = adminareas[adminareas['name'].str.contains('Војводина', na=False)]
    return voj.iloc[0].geometry

def ucitaj_podatke():
    """Učitava lokacije i deponije iz baze."""
    conn = get_connection()
    lokacije_df = pd.read_sql("""
        SELECT id, naziv, ST_X(geom) as lon, ST_Y(geom) as lat FROM lokacije
    """, conn)
    deponije_df = pd.read_sql("""
        SELECT id, naziv, status, ST_AsText(geom) as geom FROM deponije WHERE geom IS NOT NULL
    """, conn)
    conn.close()
    return lokacije_df, deponije_df

def kreiraj_mapu_spatial(lokacije_df, deponije_df):
    """
    Kreira interaktivnu folium mapu sa 5 slojeva:
    1. Lokacije — plavi markeri
    2. Deponije — poligoni u boji po statusu
    3. Zona rizika (3km) — zeleni poligoni oko svake deponije
    4. Clip zona — žuti poligon koji predstavlja pravu granicu Vojvodine
    5. Distanca — crvene linije između susednih lokacija
    Svi slojevi se mogu uključiti/isključiti putem LayerControl-a.
    """
    print("Pravljenje mape sa spatial operacijama...")

    mapa = folium.Map(tiles='OpenStreetMap')
    mapa.fit_bounds([[44.6, 18.8], [46.2, 21.7]])

    # ── Kreiraj zonu rizika 3km oko deponija ──
    # Konverzija u UTM za tačan buffer u metrima, pa nazad u WGS84 za folium
    dep_geometry = [swkt.loads(g) for g in deponije_df['geom']]
    gdf_dep = gpd.GeoDataFrame(deponije_df, geometry=dep_geometry, crs='EPSG:4326')
    gdf_dep_utm = gdf_dep.to_crs('EPSG:32634')
    gdf_buffer = gdf_dep_utm.copy()
    gdf_buffer['geometry'] = gdf_dep_utm.geometry.buffer(3000)  # 3km radius
    gdf_buffer = gdf_buffer.to_crs('EPSG:4326')

    # ── Sloj 1: Lokacije (plavi markeri) ──
    fg_lokacije = folium.FeatureGroup(name='Lokacije', show=True)
    for _, row in lokacije_df.iterrows():
        folium.CircleMarker(
            location=[row['lat'], row['lon']],
            radius=8,
            popup=f"<b>{row['naziv']}</b>",
            color='blue',
            fill=True,
            fillColor='lightblue',
            fillOpacity=0.7
        ).add_to(fg_lokacije)
    fg_lokacije.add_to(mapa)

    # ── Sloj 2: Deponije (poligoni u boji po statusu) ──
    fg_deponije = folium.FeatureGroup(name='Deponije', show=True)
    status_boje = {'aktivna': 'red', 'u sanaciji': 'orange', 'sanirana': 'darkgreen'}
    for _, row in gdf_dep.iterrows():
        color = status_boje.get(row['status'], 'gray')
        geom = row.geometry
        if geom.geom_type == 'MultiPolygon':
            geom = list(geom.geoms)[0]
        folium.Polygon(
            locations=[(lat, lon) for lon, lat in geom.exterior.coords],
            popup=f"<b>{row['naziv']}</b><br>Status: {row['status']}",
            color=color, fill=True, fillColor=color, fillOpacity=0.5, weight=2
        ).add_to(fg_deponije)
    fg_deponije.add_to(mapa)

    # ── Sloj 3: Zona rizika 3km oko deponija (zeleni poligoni) ──
    fg_buffer = folium.FeatureGroup(name='Zona rizika (3km)', show=True)
    for _, row in gdf_buffer.iterrows():
        # exterior.coords vraća koordinate granice poligona
        # folium koristi (lat, lon) redosled — zato swap lon,lat
        folium.Polygon(
            locations=[(lat, lon) for lon, lat in row.geometry.exterior.coords],
            popup=f"<b>Zona rizika: {row['naziv']}</b><br>Radijus: 3km",
            color='green',
            fill=True,
            fillColor='lightgreen',
            fillOpacity=0.3,
            weight=2
        ).add_to(fg_buffer)
    fg_buffer.add_to(mapa)

    # ── Sloj 4: Clip zona — prava granica Vojvodine (ne pravougaonik) ──
    fg_clip = folium.FeatureGroup(name='Clip zona', show=True)
    voj_geom = ucitaj_vojvodina_granicu()
    if voj_geom.geom_type == 'MultiPolygon':
        voj_geom = list(voj_geom.geoms)[0]
    clip_coords = [[y, x] for x, y in voj_geom.exterior.coords]
    folium.Polygon(
        locations=clip_coords,
        popup="<b>Clip zona</b><br>Granica Vojvodine",
        color='orange',
        fill=True,
        fillColor='yellow',
        fillOpacity=0.2,
        weight=2
    ).add_to(fg_clip)
    fg_clip.add_to(mapa)

    # ── Sloj 5: Linije distanci između susednih lokacija (crvene linije) ──
    fg_distance = folium.FeatureGroup(name='Distanca između lokacija', show=True)
    for i in range(len(lokacije_df) - 1):
        lat1, lon1 = lokacije_df.iloc[i][['lat', 'lon']]
        lat2, lon2 = lokacije_df.iloc[i+1][['lat', 'lon']]
        folium.PolyLine(
            locations=[[lat1, lon1], [lat2, lon2]],
            color='red',
            weight=1,
            opacity=0.5,
            popup=f"Distanca: {lokacije_df.iloc[i]['naziv']} - {lokacije_df.iloc[i+1]['naziv']}"
        ).add_to(fg_distance)
    fg_distance.add_to(mapa)

    # Kontrola slojeva
    folium.LayerControl().add_to(mapa)

    # HTML legenda u donjem desnom uglu mape
    legend_html = '''
    <div style="position: fixed;
     bottom: 50px; right: 50px; width: 250px; height: 250px;
     background-color: white; border:2px solid grey; z-index:9999;
     font-size:14px; padding: 10px">

     <b style="color: blue;">● Lokacije</b><br>
     Tačke sa lokacijama<br><br>

     <b style="color: red;">◾ Deponije</b><br>
     Crveno=aktivna, narandžasto=u sanaciji, zeleno=sanirana<br><br>

     <b style="color: green;">◾ Zona rizika (3km)</b><br>
     Zona rizika oko deponija<br><br>

     <b style="color: orange;">◾ Clip zona</b><br>
     Granica Vojvodine<br><br>

     <b style="color: red;">— Distanca</b><br>
     Linije između lokacija<br>
    </div>
    '''
    mapa.get_root().html.add_child(folium.Element(legend_html))

    # Sačuvaj mapu kao HTML fajl u istom folderu kao ovaj skript
    out_path = os.path.join(os.path.dirname(__file__), 'mapa_spatial_operacije.html')
    mapa.save(out_path)
    print(f"Mapa sačuvana kao '{out_path}'")

if __name__ == "__main__":
    lokacije_df, deponije_df = ucitaj_podatke()
    print("\nLOKACIJE:")
    print(lokacije_df)

    kreiraj_mapu_spatial(lokacije_df, deponije_df)
    print("\nSPATIAL MAPA GOTOVA!")
