# Sistem za upravljanje otpadom i divljim deponijama (Vojvodina)

Sistem evidentira lokacije, kontejnere, komunalna
preduzeća, deponije i inspekcije za Vojvodinu, sa ML detekcijom divljih
deponija iz simuliranog satelitskog snimka.

Baza: PostgreSQL/PostGIS na Supabase. Podaci: stvarni OSM/Geofabrik podaci za
Vojvodinu (gradovi, kontejneri, deponije).

---

## 1. Podešavanje okruženja

Projekat koristiti `uv` za upravljanje zavisnostima.

```bash
cd ~/Desktop/GIS
uv sync
```

Ovo kreira `.venv/` i instalira sve iz `pyproject.toml` (psycopg2, geopandas,
folium, streamlit, scikit-learn, rasterio, scipy...).

### `.env` fajl

U root folderu (`GIS/.env`) mora postojati:

```
DB_URL=postgresql://...supabase.com:6543/postgres
```

`.env` je u `.gitignore` — nikad se ne pushuje na GitHub.

### SHP podaci

`serbia_shp/` folder mora sadržati Geofabrik SHP fajlove za Srbiju
(`gis_osm_places_free_1.shp`, `gis_osm_landuse_a_free_1.shp`,
`gis_osm_pois_free_1.shp`, `gis_osm_adminareas_a_free_1.shp`, ...).
Ovaj folder je takođe u `.gitignore` (prevelik za git) — preuzima se ručno sa
[Geofabrik-a](https://download.geofabrik.de/europe/serbia.html) ako ga nema.

---

## 2. Redosled pokretanja

**Bitno:** `baza.py` mora biti prvi — briše i ponovo kreira sve tabele.
Ostalo može u bilo kom redosledu, ali ide smisleno DEO 1 → DEO 2 → DEO 3 → app.

```bash
# DEO 1 — SQL (baza, CRUD, upiti)
.venv/bin/python deo1_sql/baza.py
.venv/bin/python deo1_sql/crud.py
.venv/bin/python deo1_sql/upiti.py

# DEO 2 — GEO (spatial analiza + mape)
.venv/bin/python deo2_geo/geo_analiza.py
.venv/bin/python deo2_geo/spatial_operacije.py
.venv/bin/python deo2_geo/mapa_spatial_operacije.py

# DEO 3 — ML (detekcija iz rasterskog snimka)
.venv/bin/python deo3_ml/ml_detekcija.py

# Streamlit aplikacija (sve objedinjeno, kroz browser)
.venv/bin/streamlit run app/app.py
```

Ako je venv aktiviran (`source .venv/bin/activate`), `.venv/bin/python` može
da se skrati na `python`.

---

## 3. Šta svaki fajl radi

### DEO 1 — `deo1_sql/`

| Fajl | Šta radi |
|---|---|
| `baza.py` | Kreira 5 tabela (lokacije, komunalna_preduzeca, kontejneri, deponije, inspekcije), učitava stvarne podatke iz `serbia_shp/` — 10 gradova Vojvodine, 42 kontejnera/reciklažna mesta, 30 stvarnih OSM deponija |
| `crud.py` | Demonstrira Create/Read/Update/Delete za svih 5 tabela |
| `upiti.py` | 10 SQL upita sa JOIN, WHERE, GROUP BY — ispisuje rezultate u terminal kao pandas DataFrame |

### DEO 2 — `deo2_geo/`

| Fajl | Šta radi | Izlaz |
|---|---|---|
| `geo_analiza.py` | Učitava SHP slojeve (mesta, korišćenje zemljišta), spaja ih sa bazom (spatial join), pravi mapu sa svim slojevima | `deo2_geo/mapa_vojvodina.html` |
| `spatial_operacije.py` | 5 overlay operacija (buffer, intersection, union, clip, difference) + 5 prostornih upita (within, overlaps, contains, distance, disjoint) — ispis u terminal | — |
| `mapa_spatial_operacije.py` | Vizuelizuje buffer zone (10km), clip zonu i distance na mapi | `deo2_geo/mapa_spatial_operacije.html` |

### DEO 3 — `deo3_ml/`

| Fajl | Šta radi | Izlaz |
|---|---|---|
| `ml_detekcija.py` | Generiše sintetički GeoTIFF (simulacija Sentinel-2) sa spektralnim potpisima postavljenim na stvarne koordinate gradova/deponija iz baze, trenira Random Forest, klasifikuje ceo snimak, vektorizuje rezultate i upisuje nove "ML Deponija" zapise u bazu (vezane za najbližu lokaciju) | `deo3_ml/mapa_ml_rezultati.html`, `deo3_ml/vojvodina_snimak.tif` |

### `app/app.py` — Streamlit aplikacija

Web interfejs za ceo projekat. Otvara se na `http://localhost:8501`, meni sa
leve strane ima 8 stranica:

- **Dashboard** — statistike (broj lokacija/kontejnera/deponija), grafikoni po
  stanju/statusu, mapa svih lokacija
- **Lokacije / Komunalna Preduzeća / Kontejneri / Deponije / Inspekcije** —
  tabela svih zapisa + forme za dodavanje, ažuriranje i brisanje (CRUD).
  Lokaciju mora prvo postojati pre dodavanja kontejnera/deponije/preduzeća
  jer su povezani stranim ključem
- **ML Detekcija** — tabela ML detektovanih deponija (naziv sadrži "ML"),
  mogućnost izmene tipa otpada i statusa, mapa detekcija
- **Spatial Analiza** — distanca između dve lokacije, 5 overlay operacija
  (buffer/intersection/union/clip/difference) sa rezultatima u tabelama,
  mapa sa SHP slojevima i satelitskom podlogom + **color picker** za boje
  lokacija i deponija po statusu (simbologija)

---

## 4. Otvaranje generisanih mapa

HTML mape se ne mogu otvoriti direktno kao `file://` jer OpenStreetMap
blokira tile zahteve bez servera. Pokreni lokalni server iz `GIS/` foldera:

```bash
python -m http.server 8000
```

Pa otvori u browseru:
- `http://localhost:8000/deo2_geo/mapa_vojvodina.html`
- `http://localhost:8000/deo2_geo/mapa_spatial_operacije.html`
- `http://localhost:8000/deo3_ml/mapa_ml_rezultati.html`

---

## 5. Gašenje Streamlit-a

Ctrl+C u terminalu. Ako se ne ugasi:

```bash
kill -9 $(lsof -t -i:8501)
```
