---

## Baza podataka

Baza podataka je hostovana na **Supabase** cloud platformi i koristi **PostgreSQL** sa **PostGIS** ekstenzijom koja omogućava skladištenje i obradu geografskih podataka (tačke, poligoni, linije).

### Šema baze

#### `lokacije`
Čuva geografske lokacije na teritoriji Novog Sada sa koordinatama.

| Kolona | Tip | Opis |
|---|---|---|
| id | SERIAL PK | Jedinstveni identifikator |
| naziv | VARCHAR | Naziv lokacije |
| opstina | VARCHAR | Naziv opštine |
| adresa | VARCHAR | Adresa lokacije |
| tip_podrucja | VARCHAR | Tip područja (park, stambeno, industrijsko...) |
| geom | GEOMETRY(Point) | Geografska koordinata |

#### `kontejneri`
Evidencija kontejnera za otpad postavljenih na lokacijama u gradu.

| Kolona | Tip | Opis |
|---|---|---|
| id | SERIAL PK | Jedinstveni identifikator |
| tip | VARCHAR | Tip kontejnera (komunalni, reciklažni, podzemni) |
| kapacitet_litara | INTEGER | Kapacitet u litrima |
| stanje | VARCHAR | Trenutno stanje (dobro, oštećen, loše) |
| datum_postavljanja | DATE | Datum postavljanja |
| lokacija_id | INTEGER FK | Veza sa tabelom lokacije |

#### `deponije`
Evidencija divljih deponija sa informacijama o površini, tipu otpada i statusu.

| Kolona | Tip | Opis |
|---|---|---|
| id | SERIAL PK | Jedinstveni identifikator |
| naziv | VARCHAR | Naziv deponije |
| povrsina_m2 | FLOAT | Površina u kvadratnim metrima |
| tip_otpada | VARCHAR | Tip otpada (komunalni, građevinski, mešoviti) |
| status | VARCHAR | Status (aktivna, u sanaciji, sanirana) |
| datum_otkrivanja | DATE | Datum otkrivanja |
| lokacija_id | INTEGER FK | Veza sa tabelom lokacije |
| geom | GEOMETRY(Polygon) | Geografski oblik deponije |

#### `komunalna_preduzeca`
Evidencija komunalnih preduzeća zaduženih za upravljanje otpadom.

| Kolona | Tip | Opis |
|---|---|---|
| id | SERIAL PK | Jedinstveni identifikator |
| naziv | VARCHAR | Naziv preduzeća |
| kontakt_telefon | VARCHAR | Broj telefona |
| email | VARCHAR | Email adresa |
| zona_pokrivenosti | VARCHAR | Zona kojom preduzeće upravlja |
| lokacija_id | INTEGER FK | Veza sa tabelom lokacije |

#### `inspekcije`
Evidencija inspekcijskih pregleda divljih deponija.

| Kolona | Tip | Opis |
|---|---|---|
| id | SERIAL PK | Jedinstveni identifikator |
| datum | DATE | Datum inspekcije |
| nalaz | TEXT | Opis nalaza na terenu |
| preporuka | TEXT | Preporuka inspektora |
| inspektor | VARCHAR | Ime i prezime inspektora |
| deponija_id | INTEGER FK | Veza sa tabelom deponije |

---

## DEO 1 – Python SQL

### Šta je urađeno

Kreirana je PostgreSQL baza podataka sa PostGIS ekstenzijom na Supabase cloud platformi. Konekcija na bazu ostvarena je iz Pythona korišćenjem biblioteke `psycopg2`.

**Tabele i podaci:**
- 5 tabela sa primarnim i stranim ključevima
- Lokacije: Liman park, Grbavica, Sajmiste, Detelinara, Klisa
- Kontejneri: različiti tipovi sa stanjem (dobro, oštećen, loše)
- Deponije: 5 originalne deponije sa površinama i statusima
- Komunalna preduzeća i inspekcije

**CRUD Operacije implementirane:**
- **CREATE** – Dodavanje novih kontejnera i deponija
- **READ** – Čitanje svih podataka u pandas DataFrame
- **UPDATE** – Ažuriranje stanja kontejnera
- **DELETE** – Brisanje zapisa iz baze

**6 JOIN upita sa WHERE filterima:**
1. Kontejneri sa nazivima lokacija
2. Samo aktivne deponije sa lokacijama
3. Inspekcije sa nazivima deponija sortirane po datumu
4. Komunalna preduzeća sa lokacijama i tipom područja
5. Oštećeni i loši kontejneri filtrirani po stanju
6. Deponije, inspekcije i lokacije spojene u jednom upitu

---

## DEO 2 – Python GEO

### Šta je urađeno

Geografska analiza i vizuelizacija podataka iz baze na interaktivnim mapama.

### Geo Analiza (`geo_analiza.py`)

**Učitavanje podataka:**
- Preuzimanje SHP (Shapefile) podataka za Srbiju sa Geofabrika
- Učitavanje lokacija, kontejnera i deponija iz PostGIS baze
- Konverzija geografskih podataka u GeoPandas GeoDataFrame

**Interaktivne mape sa 3 sloja:**
1. **Lokacije** — Plave tačke sa nazivima lokacija
2. **Kontejneri** — Markeri sa ikonama smeća, boje po stanju:
   - 🟢 Zeleni — dobro stanje
   - 🟠 Narandžasti — oštećeni
   - 🔴 Crveni — loše stanje
3. **Deponije** — Poligoni sa ispunom, boje po statusu:
   - 🔴 Crveni — aktivne deponije
   - 🟠 Narandžasti — u sanaciji
   - 🟢 Zeleni — sanirane

**Kontrola slojeva:**
- Omogućava prikaz/skrivanje svakog sloja nezavisno
- Kliktanje na markere prikazuje detaljne informacije

### Spatial Operacije (`spatial_operacije.py`)

Implementirane su sledeće **5 spatial operacija:**

#### 1. BUFFER — Zaštitne zone
Kreiraj buffer zone od 500m oko svake lokacije za zaštitu od zagađenja.
```python
# Primer: Lokacija sa buffer zonom od 500m
gdf_buffer = gdf.buffer(500)
```

#### 2. INTERSECTION — Pronalaženje preseka
Pronađi sve lokacije koje se nalaze u intersection (preseku) sa drugim geografskim podacima.
```python
# Pronađi lokacije u zaštitnoj zoni
intersections = gpd.sjoin(gdf_lokacije, buffer_zone, predicate='intersects')
```

#### 3. UNION — Spajanje zona
Spoji sve zaštitne zone u jedan veliki poligon.
```python
# Jedinstvena unija svih buffer zona
union_geom = buffer_zone.geometry.unary_union
```

#### 4. CLIP — Isecanje po granici
Iseci samo lokacije koje se nalaze u određenom području (npr. samo u Novom Sadu).
```python
# Clip zone — kvadrat oko Novog Sada
clipped = gpd.clip(gdf_lokacije, clip_box)
```

#### 5. DIFFERENCE — Razlika
Pronađi sve lokacije koje se nalaze IZVAN zaštitnih zona.
```python
# Lokacije koje se NE nalaze u buffer zonama
difference_result = gdf_lokacije[~gdf_lokacije.intersects(union_geom)]
```

### Spatial Upiti (`spatial_operacije.py`)

Implementirano je **5 spatial upita:**

#### 1. WITHIN — Unutar zone
Pronađi sve lokacije koje se nalaze UNUTAR određene zaštitne zone.
```python
result = gdf_lokacije[gdf_lokacije.geometry.within(buffer_zone)]
```

#### 2. OVERLAPS — Preklapanje
Pronađi sve lokacije koje se PREKLAPAJU sa zaštitnom zonom.
```python
overlaps = gpd.sjoin(gdf_lokacije, buffer_zone, predicate='overlaps')
```

#### 3. CONTAINS — Sadržavanje
Pronađi sve zaštitne zone koje SADRŽE lokacije.
```python
contains = gpd.sjoin(gdf_lokacije, buffer_zone, predicate='contains')
```

#### 4. DISTANCE — Distanca
Pronađi distancu između lokacija (u metrima).
```python
# Distanca između prve i druge lokacije
dist = gdf_utm.geometry.iloc[0].distance(gdf_utm.geometry.iloc[1])
```

#### 5. DISJOINT — Bez dodira
Pronađi sve lokacije koje se NE dodiruju sa zaštitnom zonom.
```python
disjoint = gdf_lokacije[~gdf_lokacije.intersects(union_geom)]
```

### Mapa Spatial Operacija (`mapa_spatial_operacije.py`)

Interaktivna HTML mapa sa vizuelizacijom svih spatial operacija:
- 🔵 **Lokacije** — Plave tačke
- 🟢 **Buffer zone (500m)** — Zelene zone zaštite
- 🟠 **Clip zona** — Žuti kvadrat područja od interesa
- 🔴 **Distanca** — Crvene linije između lokacija
- **Legenda** — Objašnjava sve slojeve

---

## DEO 3 – Python ML

### Šta je urađeno

Implementacija detekcije divljih deponija primenom algoritama mašinskog učenja.

### ML Detekcija (`ml_detekcija.py`)

**Simulacija ML detekcije:**
- Algoritam simulira detekciju novih (divljih) deponija blizu postojećih lokacija
- Svaka detektovana deponija ima:
  - **Naziv** — "ML Deponija #1", itd.
  - **Lokacija** — Geografske koordinate (lat, lon)
  - **Površina** — Nasumična između 50-1000 m²
  - **Tip otpada** — Komunalni, građevinski, mešoviti, industrijski
  - **Confidence score** — Sigurnost detekcije (65%-99%)
  - **Status** — "detektovana"

**Proces detekcije:**
1. Za svaku postojeću lokaciju, pronađi potencijalne divlje deponije u blizini
2. Dodelite nasumičnu poziciju, površinu i confidence score
3. Upiši u PostGIS bazu sa geometrijom

**Upisivanje u bazu:**
- ML detektovane deponije se automatski upisuju u tabelu `deponije`
- Kreiraj buffer (poligon) oko detektovane tačke
- Pronađi najbližu lokaciju i povežи sa foreign key

**Analiza rezultata:**
- Originalne deponije: 5
- ML detektovane deponije: 8
- Prosečna površina: 676 m²
- Prosečni confidence: 82%
- Distribuacija po tipu otpada

**Vizuelizacija:**
- Mapa sa originalnim (🟠 narandžasti) i ML detektovanim (🔴 crveni) markerima
- Prikaz confidence score-a za svaku detektovanu deponiju
- Detaljne informacije pri kliku na marker

---

## Rezultati i Statistika

### Lokacije
- **Ukupno:** 5 lokacija
- **Lokacije:** Liman park, Grbavica, Sajmiste, Detelinara, Klisa
- **Opština:** Svi u Novom Sadu

### Kontejneri
- **Ukupno:** 8 kontejnera
- **Po stanju:** 5 u dobrom stanju, 2 oštećena, 1 u lošem stanju
- **Po tipu:** Komunalni, reciklažni, podzemni

### Originalne Deponije
- **Ukupno:** 5 deponija
- **Prosečna površina:** 651 m²
- **Po statusu:** 2 aktivne, 1 u sanaciji, 2 sanirane

### ML Detektovane Deponije
- **Ukupno:** 8 deponija
- **Prosečna površina:** 676 m²
- **Prosečni confidence:** 82.0%
- **Min confidence:** 65.0%
- **Max confidence:** 98.4%

### Ukupno u Sistemu
- **Deponije:** 13 (5 originalnih + 8 ML detektovanih)
- **Lokacije:** 5
- **Kontejneri:** 8

---

## Mape i Vizuelizacije

Projekat generiše 3 interaktivne HTML mape:

1. **mapa_novi_sad.html** — Osnovna mapa sa lokacijama, kontejnerima i deponijama
2. **mapa_ml_rezultati.html** — Mapa sa originalnim i ML detektovanim deponijama
3. **mapa_spatial_operacije.html** — Mapa sa buffer zonama, clip zonom i distancama

Sve mape su interaktivne sa mogućnošću:
- Zumiranja i pomeranja
- Prikaz/skrivanja slojeva
- Kliktanja na markere za detaljne informacije
- Pregleda legendi



### 4. Pokreni Deo 1 — Baza
```bash
python deo1_sql/baza.py
python deo1_sql/crud.py
python deo1_sql/upiti.py
```

### 5. Pokreni Deo 2 — GEO Analiza
```bash
python deo2_geo/geo_analiza.py
python deo2_geo/spatial_operacije.py
python deo2_geo/mapa_spatial_operacije.py
```

### 6. Pokreni Deo 3 — ML Detekcija
```bash
python deo3_ml/ml_detekcija.py
```

### 7. Otvori Mape
- `mapa_novi_sad.html`
- `mapa_ml_rezultati.html`
- `mapa_spatial_operacije.html`

U browser-u (desni klik → "Open with Default Browser").

