import geopandas as gpd
import pandas as pd
import psycopg2
import os
from shapely.geometry import Point, box
import folium
from dotenv import load_dotenv

load_dotenv()
DB_URL = os.environ.get("DB_URL")

def get_connection():
    return psycopg2.connect(DB_URL)

def ucitaj_podatke():
    conn = get_connection()
    lokacije_df = pd.read_sql("""
        SELECT id, naziv, ST_X(geom) as lon, ST_Y(geom) as lat FROM lokacije
    """, conn)
    conn.close()
    return lokacije_df

def kreiraj_mapu_spatial(lokacije_df):
    print("🗺️ Pravljenje mape sa spatial operacijama...")
    
    # Osnovna mapa
    mapa = folium.Map(
        location=[45.25, 20.0],
        zoom_start=8,
        tiles='OpenStreetMap'
    )
    
    # Kreiraj GeoDataFrame za buffer zone
    geometry = [Point(xy) for xy in zip(lokacije_df['lon'], lokacije_df['lat'])]
    gdf = gpd.GeoDataFrame(lokacije_df, geometry=geometry, crs='EPSG:4326')
    gdf_utm = gdf.to_crs('EPSG:32634')
    gdf_buffer = gdf_utm.copy()
    gdf_buffer['geometry'] = gdf_utm.geometry.buffer(10000)  # 10km
    gdf_buffer = gdf_buffer.to_crs('EPSG:4326')
    
    # Sloj 1: Lokacije
    fg_lokacije = folium.FeatureGroup(name='Lokacije', show=True)
    for idx, row in lokacije_df.iterrows():
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
    
    # Sloj 2: Buffer zone (10km)
    fg_buffer = folium.FeatureGroup(name='Buffer zone (10km)', show=True)
    for idx, row in gdf_buffer.iterrows():
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
    
    # Sloj 3: Clip zona (kvadrat oko Novog Sada)
    fg_clip = folium.FeatureGroup(name='Clip zona', show=True)
    clip_coords = [
        [44.6, 18.8],
        [44.6, 21.7],
        [46.2, 21.7],
        [46.2, 18.8],
        [44.6, 18.8]
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
    
    # Sloj 4: Linije između lokacija (distance)
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
    
    # Dodaj legenda
    legend_html = '''
    <div style="position: fixed; 
     bottom: 50px; right: 50px; width: 250px; height: 250px; 
     background-color: white; border:2px solid grey; z-index:9999; 
     font-size:14px; padding: 10px">
     
     <b style="color: blue;">● Lokacije</b><br>
     Tačke sa lokalacijama<br><br>
     
     <b style="color: green;">◾ Buffer zone (10km)</b><br>
     Zaštitne zone od 10km<br><br>
     
     <b style="color: orange;">◾ Clip zona</b><br>
     Kvadrat oblasti od interesa<br><br>
     
     <b style="color: red;">— Distanca</b><br>
     Linije između lokacija<br>
    </div>
    '''
    mapa.get_root().html.add_child(folium.Element(legend_html))
    
    # Sačuvaj
    out_path = os.path.join(os.path.dirname(__file__), 'mapa_spatial_operacije.html')
    mapa.save(out_path)
    print(f"✅ Mapa sačuvana kao '{out_path}'")

if __name__ == "__main__":
    lokacije_df = ucitaj_podatke()
    print("\n📍 LOKACIJE:")
    print(lokacije_df)
    
    kreiraj_mapu_spatial(lokacije_df)
    print("\n✅ SPATIAL MAPA GOTOVA!")