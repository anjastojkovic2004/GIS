import pandas as pd
import psycopg2
import numpy as np
import folium
from datetime import datetime

DB_URL = "postgresql://postgres.vtmpqdgrtntctvbusxec:NoviSad2024!@aws-0-eu-west-1.pooler.supabase.com:6543/postgres"

def get_connection():
    return psycopg2.connect(DB_URL)

# Simulacija ML detekcije divljih deponija
def simuliraj_ml_deponije(lokacije_df, num_deponije=8):
    print("🤖 ML detekcija divljih deponija (simulacija)...")
    
    deponije_ml = []
    np.random.seed(42)
    
    for i in range(num_deponije):
        base_loc = lokacije_df.sample(1).iloc[0]
        
        offset_lat = np.random.uniform(-0.02, 0.02)
        offset_lon = np.random.uniform(-0.02, 0.02)
        
        nova_lat = base_loc['lat'] + offset_lat
        nova_lon = base_loc['lon'] + offset_lon
        povrsina = np.random.uniform(50, 1000)
        confidence = np.random.uniform(0.65, 0.99)
        
        deponije_ml.append({
            'naziv': f"ML Deponija #{i+1}",
            'lat': nova_lat,
            'lon': nova_lon,
            'povrsina_m2': povrsina,
            'tip_otpada': np.random.choice(['komunalni', 'građevinski', 'mešoviti', 'industrijski']),
            'status': 'detektovana',
            'confidence': confidence,
            'datum_detekcije': datetime.now().strftime('%Y-%m-%d')
        })
    
    return pd.DataFrame(deponije_ml)

# Upisivanje u bazu
def upisi_deponije_u_bazu(deponije_df):
    print("💾 Upisivanje u bazu podataka...")
    
    conn = get_connection()
    cursor = conn.cursor()
    
    for idx, depo in deponije_df.iterrows():
        try:
            cursor.execute("""
                SELECT id FROM lokacije 
                ORDER BY ST_Distance(geom, ST_SetSRID(ST_MakePoint(%s, %s), 4326)) 
                LIMIT 1
            """, (depo['lon'], depo['lat']))
            
            rezultat = cursor.fetchone()
            lokacija_id = rezultat[0] if rezultat else 1
            
            cursor.execute("""
                INSERT INTO deponije (naziv, povrsina_m2, tip_otpada, status, datum_otkrivanja, lokacija_id, geom)
                VALUES (%s, %s, %s, %s, %s, %s, 
                ST_Buffer(ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, %s)::geometry)
            """, (
                depo['naziv'],
                depo['povrsina_m2'],
                depo['tip_otpada'],
                depo['status'],
                depo['datum_detekcije'],
                lokacija_id,
                depo['lon'],
                depo['lat'],
                int(depo['povrsina_m2'] ** 0.5 / 2)
            ))
            conn.commit()
        except Exception as e:
            print(f"Greška pri upisu deponije {depo['naziv']}: {e}")
            conn.rollback()
    
    cursor.close()
    conn.close()
    print("✅ Deponije upisane!")

# Čitanje iz baze
def ucitaj_sve_deponije():
    conn = get_connection()
    df = pd.read_sql("""
        SELECT id, naziv, povrsina_m2, tip_otpada, status, 
        ST_X(ST_Centroid(geom)) as lon, ST_Y(ST_Centroid(geom)) as lat FROM deponije
    """, conn)
    conn.close()
    return df

# Mapa sa svim deponijama
def kreiraj_mapu_sa_deponijama(originalne_deponije, ml_deponije):
    print("🗺️ Pravljenje mape...")
    
    mapa = folium.Map(
        location=[45.2552, 19.8362],
        zoom_start=12,
        tiles='OpenStreetMap'
    )
    
    # Originalne deponije
    fg_original = folium.FeatureGroup(name='Originalne deponije', show=True)
    for idx, depo in originalne_deponije.iterrows():
        folium.Marker(
            location=[depo['lat'], depo['lon']],
            popup=f"<b>{depo['naziv']}</b><br>Površina: {depo['povrsina_m2']:.0f} m²<br>Tip: {depo['tip_otpada']}<br>Status: {depo['status']}",
            icon=folium.Icon(color='orange', icon='trash'),
            tooltip=depo['naziv']
        ).add_to(fg_original)
    fg_original.add_to(mapa)
    
    # ML detektovane deponije
    fg_ml = folium.FeatureGroup(name='ML Detektovane deponije', show=True)
    for idx, depo in ml_deponije.iterrows():
        popup_text = f"<b>{depo['naziv']}</b><br>Površina: {depo['povrsina_m2']:.0f} m²<br>Tip: {depo['tip_otpada']}<br>Status: {depo['status']}"
        folium.Marker(
            location=[depo['lat'], depo['lon']],
            popup=popup_text,
            icon=folium.Icon(color='red', icon='exclamation'),
            tooltip=depo['naziv']
        ).add_to(fg_ml)
    fg_ml.add_to(mapa)
    
    folium.LayerControl().add_to(mapa)
    mapa.save('mapa_ml_rezultati.html')
    print("✅ Mapa sačuvana kao 'mapa_ml_rezultati.html'")

# Analiza rezultata
def analiza_rezultata(originalne_deponije, ml_deponije_df):
    print("\n" + "="*60)
    print("📊 ANALIZA REZULTATA ML DETEKCIJE")
    print("="*60)
    
    print(f"\n📍 Originalne deponije u bazi: {len(originalne_deponije)}")
    print(f"🤖 ML Detektovane deponije: {len(ml_deponije_df)}")
    print(f"📈 Ukupno u sistemu: {len(originalne_deponije) + len(ml_deponije_df)}")
    
    if len(ml_deponije_df) > 0:
        print("\n🎯 Statistika ML detekcije:")
        print(f"  • Prosečna površina: {ml_deponije_df['povrsina_m2'].mean():.0f} m²")
        print(f"  • Prosečni confidence: {ml_deponije_df['confidence'].mean():.1%}")
        print(f"  • Min confidence: {ml_deponije_df['confidence'].min():.1%}")
        print(f"  • Max confidence: {ml_deponije_df['confidence'].max():.1%}")
        
        print("\n📋 Distribuacija ML deponija po tipu otpada:")
        print(ml_deponije_df['tip_otpada'].value_counts())
    
    print("\n" + "="*60)

if __name__ == "__main__":
    # Učitaj lokacije
    conn = get_connection()
    lokacije_df = pd.read_sql("""
        SELECT id, naziv, ST_X(geom) as lon, ST_Y(geom) as lat FROM lokacije
    """, conn)
    conn.close()
    
    print("\n📍 LOKACIJE U SISTEMU:")
    print(lokacije_df)
    
    # ML detekcija
    ml_deponije_df = simuliraj_ml_deponije(lokacije_df, num_deponije=8)
    
    print("\n🤖 DETEKTOVANE DEPONIJE:")
    print(ml_deponije_df)
    
    # Upiši u bazu
    upisi_deponije_u_bazu(ml_deponije_df)
    
    # Čitaj sve iz baze
    sve_deponije = ucitaj_sve_deponije()
    
    # Odvoji originalne od ML detektovanih
    originalne = sve_deponije[~sve_deponije['naziv'].str.contains('ML', na=False)]
    detektovane = sve_deponije[sve_deponije['naziv'].str.contains('ML', na=False)]
    
    # Kreiraj mapu
    kreiraj_mapu_sa_deponijama(originalne, detektovane)
    
    # Analiza
    analiza_rezultata(originalne, ml_deponije_df)
    
    print("\n✅ DEO 3 ZAVRŠEN!")