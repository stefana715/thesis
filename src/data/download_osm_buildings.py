import osmnx as ox
import geopandas as gpd
import os

# Set the place name for Changsha, China
place_name = 'Changsha, Hunan, China'

# Download building geometries from OpenStreetMap
print("Downloading building data from OpenStreetMap for Changsha...")
buildings = ox.geometries_from_place(place_name, tags={'building': True})

# Ensure the output directory exists
output_dir = 'data/raw'
os.makedirs(output_dir, exist_ok=True)

# Save the buildings data to a GeoJSON file
output_file = os.path.join(output_dir, 'buildings.geojson')
buildings.to_file(output_file, driver='GeoJSON')

print(f"Building data saved to {output_file}")
print(f"Downloaded {len(buildings)} building features.")