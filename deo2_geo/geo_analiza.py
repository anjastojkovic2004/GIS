import geopandas as gpd
import folium
import pandas as pd
import psycopg2
from shapely.geometry import Point, Polygon
import urllib.request
import zipfile
import os

DB_URL = "postgresql://postgres.vtmpqdgrtntctvbusxec:NoviSad2024!@aws-0-eu-west-1.pooler.supabase.com:6543/postgres"

def get_connection():
    return psycopg2.connect(DB_URL)

# Preuzimanje SHP podataka
def preuzmi_shp_podatke():
    print("Preuzimanje SHP podataka za Srbiju...")
    if not os.path.exists("serbia_shp"):
        url = "https://download.geofabrik.de/europe/serbia-latest-free.shp.zip"
        print(f"Preuzimanje sa {url}...")
        urllib.request.urlretrieve(url, "serbia.zip")
        print("Raspakivanje...")
        with zipfile.ZipFile("serbia.zip", 'r') as zip_ref:
            zip_ref.extractall("serbia_shp")
        os.remove("serbia.zip")
        print("✅ Gotovo!")
    else:
        print("✅ SHP fajlovi već postoje!")

# Učitavanje podataka iz baze
def ucitaj_podatke_iz_baze():
    conn = get_connection()
    cursor = conn.cursor()
    
    # Lokacije sa koordinatama
    cursor.execute("SELECT id, naziv, opstina, ST_X(geom) as lon, ST_Y(geom) as lat FROM lokacije")
    lokacije_data = cursor.fetchall()
    df_lokacije = pd.DataFrame(lokacije_data, columns=['id', 'naziv', 'opstina', 'lon', 'lat'])
    
    # Kontejneri
    df_kontejneri = pd.read_sql(
        "SELECT k.id, k.tip, k.stanje, l.naziv as lokacija, l.id as lokacija_id FROM kontejneri k JOIN lokacije l ON k.lokacija_id = l.id",
        conn
    )
    
    # Deponije sa koordinatama
    cursor.execute("""
        SELECT id, naziv, povrsina_m2, tip_otpada, status, 
        ST_AsText(geom) as geom_text FROM deponije
    """)
    deponije_data = cursor.fetchall()
    
    conn.close()
    
    return df_lokacije, df_kontejneri, deponije_data

# Kreiranje mape
def kreiraj_mapu(df_lokacije, df_kontejneri, deponije_data):
    print("Kreiranje mape...")
    
    # Centar mape — Novi Sad
    mapa = folium.Map(
        location=[45.2552, 19.8362],
        zoom_start=12,
        tiles='OpenStreetMap'
    )
    
    # Sloj 1: Lokacije
    fg_lokacije = folium.FeatureGroup(name='Lokacije', show=True)
    for _, row in df_lokacije.iterrows():
        folium.CircleMarker(
            location=[row['lat'], row['lon']],
            radius=6,
            popup=f"{row['naziv']} ({row['opstina']})",
            color='blue',
            fill=True,
            fillColor='lightblue',
            fillOpacity=0.7
        ).add_to(fg_lokacije)
    fg_lokacije.add_to(mapa)
    
    # Sloj 2: Kontejneri
    fg_kontejneri = folium.FeatureGroup(name='Kontejneri', show=True)
    for _, row in df_kontejneri.iterrows():
        lokacija = df_lokacije[df_lokacije['id'] == row['lokacija_id']]
        if not lokacija.empty:
            lat, lon = lokacija.iloc[0][['lat', 'lon']]
            
            color = 'green' if row['stanje'] == 'dobro' else ('orange' if row['stanje'] == 'ostecen' else 'red')
            
            folium.Marker(
                location=[lat, lon],
                popup=f"<b>{row['tip']}</b><br>Stanje: {row['stanje']}<br>Lokacija: {row['lokacija']}",
                icon=folium.Icon(color=color, icon='trash'),
                tooltip=f"{row['tip']} - {row['stanje']}"
            ).add_to(fg_kontejneri)
    fg_kontejneri.add_to(mapa)
    
    # Sloj 3: Deponije
    fg_deponije = folium.FeatureGroup(name='Deponije', show=True)
    for deponija in deponije_data:
        id_d, naziv, povrsina, tip_otpada, status, geom_text = deponija
        
        color = 'red' if status == 'aktivna' else ('orange' if status == 'u sanaciji' else 'green')
        
        # Parsiranje geometrije
        if 'POLYGON' in geom_text:
            coords_str = geom_text.replace('POLYGON((', '').replace('))', '').strip()
            coords = [[float(y), float(x)] for x, y in [c.split() for c in coords_str.split(',')]]
            
            folium.Polygon(
                locations=coords,
                popup=f"<b>{naziv}</b><br>Površina: {povrsina} m²<br>Tip: {tip_otpada}<br>Status: {status}",
                color=color,
                fill=True,
                fillColor=color,
                fillOpacity=0.5,
                weight=2
            ).add_to(fg_deponije)
    fg_deponije.add_to(mapa)
    
    # Kontrola slojeva
    folium.LayerControl().add_to(mapa)
    
    # Sačuvaj
    mapa.save('mapa_novi_sad.html')
    print("✅ Mapa sačuvana kao 'mapa_novi_sad.html'")

if __name__ == "__main__":
    preuzmi_shp_podatke()
    df_lokacije, df_kontejneri, deponije_data = ucitaj_podatke_iz_baze()
    
    print("\n=== Lokacije ===")
    print(df_lokacije)
    print("\n=== Kontejneri ===")
    print(df_kontejneri)
    
    kreiraj_mapu(df_lokacije, df_kontejneri, deponije_data)
    print("\n=== DEO 2 ZAVRŠEN! ===")