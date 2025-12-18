import ee
import pandas as pd

import json
import os
import math
from dotenv import load_dotenv

# 1. Initialize Earth Engine
# --- CONFIGURATION ---
load_dotenv()
PROJECT_ID = os.getenv("PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")

if not PROJECT_ID:
    raise ValueError("PROJECT_ID not found in environment variables. Please check your .env file.")

try:
    ee.Initialize(project=PROJECT_ID)
except Exception as e:
    print("Authentication needed. Follow the link in the logs if running interactively.")
    ee.Authenticate()
    ee.Initialize(project=PROJECT_ID)



_STATS_CACHE = {}

def haversine(lat1, lon1, lat2, lon2):
    """
    Calculate the great circle distance between two points 
    on the earth (specified in decimal degrees)
    """
    # Convert decimal degrees to radians 
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])

    # Haversine formula 
    dlon = lon2 - lon1 
    dlat = lat2 - lat1 
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a)) 
    r = 6371 # Radius of earth in kilometers. Use 3956 for miles
    return c * r

def get_stats(lat, lon, radius_km, year):
    """
    Calculates stats using TWO definitions of the city:
    1. STRICT (Concrete Only): Good for finding oil fields/industry.
    2. METRO (Dilated): Good for counting total human residents (suburbs).
    """
    # 0. CHECK CACHE
    cache_key = (lat, lon, radius_km, year)
    if cache_key in _STATS_CACHE:
        return _STATS_CACHE[cache_key]

    point = ee.Geometry.Point([lon, lat])
    search_area = point.buffer(radius_km * 1000)

    # --- A. DEFINE MASKS ---
    landcover = ee.ImageCollection("ESA/WorldCover/v200").first()
    
    # 1. Strict Mask (Class 50 = Built-up)
    strict_mask = landcover.eq(50).clip(search_area)
    
    # 2. Metro Mask (Dilated)
    # We inflate the concrete shape by 2000 meters to catch suburbs/shantytowns
    metro_mask = strict_mask.focalMax(2000, 'circle', 'meters')

    # --- B. GET LIGHT (VIIRS) ---
    # We still use STRICT mask for light because economic output 
    # comes from the factories/offices, not the dark suburbs.
    viirs = ee.ImageCollection("NOAA/VIIRS/DNB/MONTHLY_V1/VCMCFG") \
        .filterDate(f'{year}-01-01', f'{year}-12-31') \
        .select('avg_rad')
    
    annual_lights = viirs.mean().clip(search_area)
    urban_light = annual_lights.updateMask(strict_mask)
    
    light_stats = urban_light.reduceRegion(
        reducer=ee.Reducer.sum(),
        geometry=search_area,
        scale=500, 
        maxPixels=1e10
    )
    light_val = light_stats.get('avg_rad').getInfo()
    light_val = light_val if light_val else 0

    # --- C. GET POPULATION (WorldPop) ---
    pop_img = ee.ImageCollection("WorldPop/GP/100m/pop") \
        .filter(ee.Filter.equals('year', 2020)) \
        .select('population').mosaic().clip(search_area)
    
    # Count 1: Strict (People living on concrete)
    pop_strict_img = pop_img.updateMask(strict_mask)
    stats_strict = pop_strict_img.reduceRegion(
        reducer=ee.Reducer.sum(),
        geometry=search_area,
        scale=100, 
        maxPixels=1e10
    )
    pop_strict_val = stats_strict.get('population').getInfo()
    pop_strict_val = pop_strict_val if pop_strict_val else 1

    # Count 2: Metro (People living within 2km of concrete)
    pop_metro_img = pop_img.updateMask(metro_mask)
    stats_metro = pop_metro_img.reduceRegion(
        reducer=ee.Reducer.sum(),
        geometry=search_area,
        scale=100,
        maxPixels=1e10
    )
    pop_metro_val = stats_metro.get('population').getInfo()
    pop_metro_val = pop_metro_val if pop_metro_val else 1

    # --- D. GET AREA ---
    area_image = ee.Image.pixelArea().updateMask(strict_mask)
    area_stats = area_image.reduceRegion(
        reducer=ee.Reducer.sum(),
        geometry=search_area,
        scale=100, 
        maxPixels=1e10
    )
    area_sqm = area_stats.get('area').getInfo()
    area_sqkm = (area_sqm if area_sqm else 0) / 1e6

    # CACHE RESULT
    result = (light_val, pop_strict_val, pop_metro_val, area_sqkm)
    _STATS_CACHE[cache_key] = result
    return result

# --- CONFIGURATION ---
YEAR = 2023
RADIUS = 100 # Smart radius search

# Format: "Country": {"Capital": [Lat, Lon], "City": [Lat, Lon], "City_Name": "Name"}
# Load targets from JSON file
try:
    with open('targets.json', 'r') as f:
        targets = json.load(f)
except FileNotFoundError:
    print("Error: targets.json not found.")
    exit(1)

results_data = []

print(f"--- Processing Cities ({YEAR} Data) ---\n")

for country, data in targets.items():
    print(f"Analyzing {country}...")
    

    # Determine radius (use city-specific if available, else default)
    radius = data.get("Radius", RADIUS)
    cap_radius = data.get("Cap_Radius", RADIUS)

    # 1. Get Capital Data
    cap_coords = data["Capital"]
    cap_light, cap_pop_strict, cap_pop_metro, cap_area = get_stats(cap_coords[0], cap_coords[1], cap_radius, YEAR)
    
    # 2. Get City Data
    cand_name = data["City_Name"]
    cand_coords = data["City"]
    cand_light, cand_pop_strict, cand_pop_metro, cand_area = get_stats(cand_coords[0], cand_coords[1], radius, YEAR)

    # 3. Calculate Economic Score
    score = (cand_light / cap_light) * 100 if cap_light > 0 else 0
    
    # 4. Calculate Distance
    dist_km = haversine(cap_coords[0], cap_coords[1], cand_coords[0], cand_coords[1])

    # 5. FALSE POSITIVE CHECK (Light Intensity Per Person)
    # A normal city usually has a ratio between 0.05 and 0.5.
    # Industrial/Oil sites are often > 1.0 (High Light, Low People)
    # Using STRICT population for this check as it relates to industrial density
    light_per_capita = cand_light / cand_pop_strict if cand_pop_strict > 0 else 0
    
    results_data.append({
        "Country": country,

        "Capital_SOL": cap_light,
        "Capital_Pop_Strict": cap_pop_strict,
        "Capital_Pop_Metro": cap_pop_metro,
        "City_City": cand_name,
        "City_SOL": cand_light,
        "City_Pop_Strict": cand_pop_strict,
        "City_Pop_Metro": cand_pop_metro,
        "City_Area": cand_area,
        "Distance_km": dist_km,
        "Score (%)": round(score, 1),
        "Light/Cap": round(light_per_capita, 3)
    })

# --- DISPLAY RESULTS ---
# print("(SOL = light intensity of an area in nanoWatts / cm^2 / steradian)")
print("\n" + "="*170)
print(f"{'COUNTRY':<15} {'CITY':<20} {'POP(Strict)':<12} {'POP(Metro)':<12} {'CITY SOL':<12} {'AREA km2':<10} {'CAP SOL':<12} {'CAP POP(S)':<12} {'CAP POP(M)':<12} {'DIST km':<10} {'% of CAP':<10} {'LIGHT/CAP'}")
print("="*170)

for row in results_data:
    print(f"{row['Country']:<15} {row['City_City']:<20} {row['City_Pop_Strict']:<12.0f} {row['City_Pop_Metro']:<12.0f} {row['City_SOL']:<12.0f} {row['City_Area']:<10.1f} {row['Capital_SOL']:<12.0f} {row['Capital_Pop_Strict']:<12.0f} {row['Capital_Pop_Metro']:<12.0f} {row['Distance_km']:<10.0f} {row['Score (%)']:<10} {row['Light/Cap']}")
print("="*170)

# --- EXPORT TO CSV ---
df = pd.DataFrame(results_data)
csv_filename = "light_analysis_results.csv"
df.to_csv(csv_filename, index=False)
print(f"\nResults saved to {csv_filename}")