import toga
from toga.style import Pack
from toga.constants import COLUMN
import plotly.express as px
import pandas as pd
import platform
import asyncio
import webbrowser
import requests
import json
import geopandas as gpd
import folium
from io import StringIO
from dotenv import load_dotenv
import os
from .api_client import OpenF1Client
from .insights_engine import InsightsEngine

load_dotenv()

class OpenF1LiveInsights(toga.App):
    # ... (startup, load_data, live_update_loop, filter_data methods unchanged from previous full code)

    def refresh_ui(self):
        # ... (previous refresh_ui code for other tabs)

        # Track Map Tab - New
        try:
            # Get circuit from session (fetch if not cached)
            if not hasattr(self, 'circuit_name'):
                session_data = self.client.fetch_historical("sessions", params={"session_key": self.session_key.value})
                if session_data:
                    circuit_key = session_data[0].get("circuit_key")
                    circuit_data = self.client.fetch_historical("circuits", params={"circuit_key": circuit_key})
                    self.circuit_name = circuit_data[0].get("circuit_name") if circuit_data else "Unknown"
                else:
                    self.circuit_name = "Unknown"

            if self.circuit_name != "Unknown":
                file_name = self.get_geojson_filename(self.circuit_name)
                if file_name:
                    geojson = self.fetch_geojson(file_name)
                    if geojson:
                        # Parse and visualize
                        gdf = gpd.GeoDataFrame.from_features(geojson["features"])
                        self.track_properties_label.text = f"Name: {gdf['name'][0]}\nLocation: {gdf['location'][0]}, {gdf['country'][0]}\nAltitude: {gdf['altitude'][0]}m"

                        # Interactive Map with Folium
                        m = folium.Map(location=[gdf.centroid.y.mean(), gdf.centroid.x.mean()], zoom_start=14)
                        folium.GeoJson(gdf.to_json(), name="Track Layout").add_to(m)
                        html = m._repr_html_()
                        self.track_map_view.set_content('about:blank', html)

                        # Elevation (single value; for profile, optional API)
                        elevation_text = f"Altitude: {gdf['altitude'][0]}m"
                        if os.getenv("GOOGLE_API_KEY"):
                            # Optional: Query Google for profile (simplified; expand for full line sampling)
                            elevation_text += "\nDetailed profile available with API (implement sampling)."
                        self.track_elevation_label.text = elevation_text

                        # Turns Table (placeholder; repo lacks structured turns)
                        turns_data = []  # If properties have 'turns', parse here
                        self.track_turns_table.data = turns_data or [("No detailed turns available",)]
                    else:
                        self.track_map_view.set_content('about:blank', '<p>No GeoJSON found</p>')
                else:
                    self.track_map_view.set_content('about:blank', '<p>No matching GeoJSON file</p>')
        except Exception as e:
            print(f"Track refresh error: {e}")

    def get_geojson_filename(self, circuit_name):
        # Hardcoded mapping from OpenF1 circuit names to repo file names (based on repo listings)
        mapping = {
            "Albert Park Grand Prix Circuit": "au-1953.geojson",
            "Baku City Circuit": "az-2016.geojson",
            "Circuit de Barcelona-Catalunya": "es-1991.geojson",
            "Autódromo Oscar y Juan Gálvez": "ar-1952.geojson",
            "Hungaroring": "hu-1986.geojson",
            "Watkins Glen": "us-1956.geojson",
            "Autódromo do Estoril": "pt-1972.geojson",
            "Hockenheimring": "de-1932.geojson",
            "Autodromo Enzo e Dino Ferrari": "it-1953.geojson",
            "Indianapolis Motor Speedway": "us-1909.geojson",
            "Istanbul Park": "tr-2005.geojson",
            "Autódromo Internacional Nelson Piquet": "br-1977.geojson",
            "Jeddah Corniche Circuit": "sa-2021.geojson",
            "Kyalami": "za-1961.geojson",
            "Las Vegas Street Circuit": "us-2023.geojson",
            "Circuit Paul Ricard": "fr-1969.geojson",
            "Losail International Circuit": "qa-2004.geojson",
            "Madrid Street Circuit": "es-2026.geojson",
            "Circuit de Nevers Magny-Cours": "fr-1960.geojson",
            "Autódromo Hermanos Rodríguez": "mx-1962.geojson",
            "Miami International Autodrome": "us-2022.geojson",
            "Circuit de Monaco": "mc-1929.geojson",
            "Circuit Gilles Villeneuve": "ca-1978.geojson",
            # Additional from repo (complete list ~70; add more as needed, e.g.)
            "Autodromo Nazionale di Monza": "it-1922.geojson",
            "Circuit de Spa-Francorchamps": "be-1924.geojson",
            "Silverstone Circuit": "gb-1948.geojson",
            "Suzuka International Racing Course": "jp-1962.geojson",
            "Red Bull Ring": "at-1969.geojson",
            "Circuit of the Americas": "us-2012.geojson",  # Duplicate example
            # ... (extend with full list from repo; user can add)
        }
        return mapping.get(circuit_name)

    def fetch_geojson(self, file_name):
        url = f"https://raw.githubusercontent.com/bacinger/f1-circuits/master/circuits/{file_name}"
        try:
            response = requests.get(url)
            if response.status_code == 200:
                return response.json()
        except:
            pass
        return None

    # New build method for Track Tab
    def build_track_tab(self):
        self.track_properties_label = toga.Label("Circuit Details: N/A")
        self.track_elevation_label = toga.Label("Elevation: N/A")
        self.track_map_view = toga.WebView(style=Pack(flex=1))
        self.track_turns_table = toga.Table(headings=["Turn", "Details"], data=[], style=Pack(flex=0.3))
        return toga.Box(children=[self.track_properties_label, self.track_elevation_label, self.track_map_view, self.track_turns_table], style=Pack(direction=COLUMN, flex=1))

    # In startup: Add the tab
    # self.tabs.add("Track Map", self.build_track_tab())

# ... (rest of class unchanged)

def main():
    return OpenF1LiveInsights()
