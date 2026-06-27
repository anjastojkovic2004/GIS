"""
mapa_spatial_operacije.py — Interaktivna mapa prostornih operacija
Vizuelizuje lokacije, buffer zone (10km), clip zonu Vojvodine
i linije distanci između lokacija na folium mapi.
"""

import geopandas as gpd
import pandas as pd
import psycopg2
import os
from shapely.geometry import Point
import folium
from dotenv import load_dotenv

# Učitava DB_URL iz .env fajla
load_dotenv()
DB_URL = os.environ.get("DB_URL")

def get_connection():
    """Otvara konekciju na PostgreSQL/PostGIS bazu."""
    return psycopg2.connect(DB_URL)

def ucitaj_podatke():
    """Učitava lokacije iz baze (naziv i koordinate)."""
    conn = get_connection()
    lokacije_df = pd.read_sql("""
        SELECT id, naziv, ST_X(geom) as lon, ST_Y(geom) as lat FROM lokacije
    """, conn)
    conn.close()
    return lokacije_df

def kreiraj_mapu_spatial(lokacije_df):
    """
    Kreira interaktivnu folium mapu sa 4 sloja:
    1. Lokacije — plavi markeri
    2. Buffer zone (10km) — zeleni poligoni oko svake lokacije
    3. Clip zona — žuti kvadrat koji predstavlja granice Vojvodine
    4. Distanca — crvene linije između susednih lokacija
    Svi slojevi se mogu uključiti/isključiti putem LayerControl-a.
    """
    print("Pravljenje mape sa spatial operacijama...")

    mapa = folium.Map(
        location=[45.25, 20.0],  # Centar nad Vojvodinom
        zoom_start=8,
        tiles='OpenStreetMap'
    )

    # ── Kreiraj buffer zone oko lokacija ──
    # Konverzija u UTM za tačan buffer u metrima, pa nazad u WGS84 za folium
    geometry = [Point(xy) for xy in zip(lokacije_df['lon'], lokacije_df['lat'])]
    gdf = gpd.GeoDataFrame(lokacije_df, geometry=geometry, crs='EPSG:4326')
    gdf_utm = gdf.to_crs('EPSG:32634')
    gdf_buffer = gdf_utm.copy()
    gdf_buffer['geometry'] = gdf_utm.geometry.buffer(10000)  # 10km radius
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

    # ── Sloj 2: Buffer zone 10km (zeleni poligoni) ──
    fg_buffer = folium.FeatureGroup(name='Buffer zone (10km)', show=True)
    for _, row in gdf_buffer.iterrows():
        # exterior.coords vraća koordinate granice poligona
        # folium koristi (lat, lon) redosled — zato swap lon,lat
        folium.Polygon(
            locations=[(lat, lon) for lon, lat in row.geometry.exterior.coords],
            popup=f"<b>Buffer: {row['naziv']}</b><br>Radijus: 10km",
            color='green',
            fill=True,
            fillColor='lightgreen',
            fillOpacity=0.3,
            weight=2
        ).add_to(fg_buffer)
    fg_buffer.add_to(mapa)

    # ── Sloj 3: Clip zona — granice Vojvodine (narandžasti kvadrat) ──
    fg_clip = folium.FeatureGroup(name='Clip zona', show=True)
    clip_coords = [
        [44.6, 18.8],  # donji levi ugao
        [44.6, 21.7],  # donji desni ugao
        [46.2, 21.7],  # gornji desni ugao
        [46.2, 18.8],  # gornji levi ugao
        [44.6, 18.8]   # zatvaranje poligona
    ]
    folium.Polygon(
        locations=clip_coords,
        popup="<b>Clip zona</b><br>Područje Vojvodine",
        color='orange',
        fill=True,
        fillColor='yellow',
        fillOpacity=0.2,
        weight=2
    ).add_to(fg_clip)
    fg_clip.add_to(mapa)

    # ── Sloj 4: Linije distanci između susednih lokacija (crvene linije) ──
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

     <b style="color: green;">◾ Buffer zone (10km)</b><br>
     Zaštitne zone od 10km<br><br>

     <b style="color: orange;">◾ Clip zona</b><br>
     Kvadrat oblasti od interesa<br><br>

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
    lokacije_df = ucitaj_podatke()
    print("\nLOKACIJE:")
    print(lokacije_df)

    kreiraj_mapu_spatial(lokacije_df)
    print("\nSPATIAL MAPA GOTOVA!")
