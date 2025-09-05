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
from math import radians, sin, cos, sqrt, atan2
import numpy as np
import googlemaps  # If key set
from .api_client import OpenF1Client
from .insights_engine import InsightsEngine

load_dotenv()

class OpenF1LiveInsights(toga.App):
    def startup(self):
        self.client = OpenF1Client()
        self.engine = InsightsEngine()
        self.insights = {}
        self.live_task = None

        # Inputs
        session_label = toga.Label("Session Key:")
        self.session_key = toga.TextInput(placeholder="e.g., 9161")
        meeting_label = toga.Label("Meeting Key:")
        self.meeting_key = toga.TextInput(placeholder="e.g., 1219")
        mode_label = toga.Label("Mode:")
        self.mode = toga.Selection(items=["historical", "live"])

        # Selections
        self.selected_driver = toga.Selection(items=["All"], on_change=self.filter_data)
        self.selected_team = toga.Selection(items=["All"], on_change=self.filter_data)
        self.selected_tire = toga.Selection(items=["All", "Soft", "Medium", "Hard", "Intermediate", "Wet"], on_change=self.filter_data)

        # Load button
        load_button = toga.Button("Load Data", on_press=self.load_data)

        # OptionContainer for tabs
        self.tabs = toga.OptionContainer(style=Pack(flex=1))
        self.tabs.add("Standings", self.build_standings_tab())
        self.tabs.add("Laps", self.build_laps_tab())
        self.tabs.add("Telemetry", self.build_telemetry_tab())
        self.tabs.add("Stints & Tires", self.build_stints_tab())
        self.tabs.add("Pits & Events", self.build_pits_tab())
        self.tabs.add("Weather & Radio", self.build_weather_tab())
        self.tabs.add("Track Map", self.build_track_tab())  # Inserted here

        # Main box
        main_box = toga.Box(
            children=[
                session_label, self.session_key,
                meeting_label, self.meeting_key,
                mode_label, self.mode,
                self.selected_driver, self.selected_team, self.selected_tire,
                load_button,
                self.tabs
            ],
            style=Pack(direction=COLUMN, padding=10, flex=1)
        )

        self.main_window = toga.MainWindow(size=(800, 600))
        self.main_window.content = main_box
        self.main_window.show()

    async def load_data(self, widget):
        session_key = self.session_key.value
        meeting_key = self.meeting_key.value
        mode = self.mode.value

        try:
            self.engine.load_drivers(self.client, session_key)

            # Update selections
            self.selected_driver.items = ["All"] + list(self.engine.drivers.values())
            self.selected_team.items = ["All"] + list(set(self.engine.teams.values()))

            if mode == "live":
                await self.client.start_mqtt_stream()
                self.live_task = self.add_background_task(self.live_update_loop)
            else:
                data_queues = {
                    "v1/intervals": self.client.fetch_intervals(session_key),
                    "v1/position": self.client.fetch_positions(session_key),
                    "v1/laps": self.client.fetch_laps(session_key),
                    "v1/pit": self.client.fetch_pits(session_key),
                    "v1/race_control": self.client.fetch_race_control(session_key),
                    "v1/car_data": self.client.fetch_car_data(session_key),
                    "v1/weather": self.client.fetch_weather(session_key),
                    "v1/stints": self.client.fetch_stints(session_key),
                    "v1/tyres": self.client.fetch_tyres(session_key),
                    "v1/team_radio": self.client.fetch_team_radio(session_key),
                }
                self.insights = self.engine.generate_insights(data_queues, mode="historical")
                self.refresh_ui()
        except Exception as e:
            self.main_window.info_dialog("Error", str(e))

    async def live_update_loop(self):
        while True:
            self.insights = self.engine.generate_insights(self.client.data_queues, mode="live")
            await asyncio.sleep(10)
            platform.loop.call_soon(self.refresh_ui)

    def filter_data(self, widget):
        self.refresh_ui()

    def refresh_ui(self):
        # Extract filters
        selected_driver = self.selected_driver.value
        selected_team = self.selected_team.value
        selected_tire = self.selected_tire.value

        selected_driver_num = next((k for k, v in self.engine.drivers.items() if v == selected_driver), None) if selected_driver != "All" else None
        selected_team_drivers = [k for k, v in self.engine.teams.items() if v == selected_team] if selected_team != "All" else None

        def filter_df(df, col="driver_number"):
            if selected_driver_num:
                df = df[df[col] == selected_driver_num]
            elif selected_team_drivers:
                df = df[df[col].isin(selected_team_drivers)]
            return df

        try:
            # Standings Tab
            if "standings" in self.insights:
                df_standings = filter_df(self.insights["standings"])
                df_standings["driver"] = df_standings["driver_number"].map(self.engine.drivers)
                data = []
                for _, row in df_standings.iterrows():
                    data.append((row["driver"], str(row.get("gap_to_leader", row.get("position", "N/A"))), str(row.get("interval", "N/A"))))
                self.standings_table.data = data

            # Laps Tab
            if "laps" in self.insights:
                df_laps = filter_df(self.insights["laps"]).head(50)  # Limit for performance
                lap_data = []
                for _, row in df_laps.iterrows():
                    lap_data.append((row["lap_number"], row["lap_duration"], row.get("duration_sector_1", "N/A"), row.get("duration_sector_2", "N/A"), row.get("duration_sector_3", "N/A")))
                self.laps_table.data = lap_data

                if not df_laps.empty:
                    fig = px.line(df_laps, x="lap_number", y="lap_duration", color="driver_number", title="Lap Times")
                    html = fig.to_html(include_plotlyjs='cdn')
                    self.laps_chart.set_content('about:blank', html)
                else:
                    self.laps_chart.set_content('about:blank', '<p>No lap data available</p>')

            if "fastest_lap" in self.insights:
                fl = self.insights["fastest_lap"]
                driver = self.engine.drivers.get(fl["driver_number"], "Unknown")
                self.fastest_lap_label.text = f"Fastest Lap: {driver} - {fl['time']}s"

            if "average_lap_times" in self.insights:
                avg_laps = self.insights["average_lap_times"]
                avg_text = "Average Lap Times:\n"
                for num, avg in avg_laps.items():
                    driver = self.engine.drivers.get(num, f"#{num}")
                    avg_text += f"- {driver}: {avg:.3f}s\n"
                self.avg_laps_label.text = avg_text
            else:
                self.avg_laps_label.text = "Average laps: N/A (Live mode only)"

            # Telemetry Tab
            if "telemetry" in self.insights:
                df_tele = filter_df(self.insights["telemetry"]).head(500)  # Limit for performance
                if not df_tele.empty:
                    fig_speed = px.line(df_tele, x="date", y="speed", title="Speed Over Time")
                    self.telemetry_speed_chart.set_content('about:blank', fig_speed.to_html(include_plotlyjs='cdn'))

                    fig_rpm = px.line(df_tele, x="date", y="rpm", title="RPM Over Time")
                    self.telemetry_rpm_chart.set_content('about:blank', fig_rpm.to_html(include_plotlyjs='cdn'))

                    fig_throttle = px.line(df_tele, x="date", y=["throttle", "brake"], title="Throttle/Brake")
                    self.telemetry_throttle_chart.set_content('about:blank', fig_throttle.to_html(include_plotlyjs='cdn'))
                else:
                    self.telemetry_speed_chart.set_content('about:blank', '<p>No telemetry data</p>')
                    # Similarly for others

            # Stints & Tires Tab
            if "stints" in self.insights:
                stints_dict = self.insights["stints"]
                if selected_driver_num:
                    stints_dict = {selected_driver_num: stints_dict.get(selected_driver_num)}
                elif selected_team_drivers:
                    stints_dict = {k: v for k, v in stints_dict.items() if k in selected_team_drivers}

                stint_data = []
                for num, data in stints_dict.items():
                    driver = self.engine.drivers.get(num, f"#{num}")
                    df_stint = pd.DataFrame(data)
                    if selected_tire != "All":
                        df_stint = df_stint[df_stint["compound"] == selected_tire.upper()]
                    for _, row in df_stint.iterrows():
                        stint_data.append((driver, row["lap_start"], row["lap_end"], row["compound"], row["tyre_age_at_start"]))
                self.stints_table.data = stint_data

            if "tyres" in self.insights:
                df_tyres = filter_df(self.insights["tyres"])
                if selected_tire != "All":
                    df_tyres = df_tyres[df_tyres["compound"] == selected_tire.upper()]
                tyre_data = [(row["driver_number"], row["compound"], row["fresh_tyre"]) for _, row in df_tyres.iterrows()]
                self.tyres_table.data = tyre_data

            # Pits & Events Tab
            if "pits" in self.insights:
                df_pits = filter_df(self.insights["pits"]).head(50)
                pits_data = [(row["driver_number"], row["lap_number"], row["pit_duration"]) for _, row in df_pits.iterrows()]
                self.pits_table.data = pits_data

            if "pit_counts" in self.insights:  # Historical
                pit_counts = self.insights["pit_counts"]
                counts_data = [(self.engine.drivers.get(num, f"#{num}"), count) for num, count in pit_counts.items()]
                self.pit_counts_table.data = counts_data
            elif "recent_pits" in self.insights:  # Live
                df_recent = self.insights["recent_pits"]
                recent_data = [(row["driver_number"], row["lap_number"], row["pit_duration"]) for _, row in df_recent.iterrows()]
                self.pit_counts_table.data = recent_data

            if "race_events" in self.insights:
                df_events = self.insights["race_events"].head(50)
                events_data = [(row.get("category", "N/A"), row.get("flag", "N/A"), row.get("message", "N/A")) for _, row in df_events.iterrows()]
                self.events_table.data = events_data

            # Weather & Radio Tab
            if "weather" in self.insights:
                w = self.insights["weather"]
                self.air_temp_label.text = f"Air Temp: {w.get('air_temp', 'N/A')}°C"
                self.track_temp_label.text = f"Track Temp: {w.get('track_temp', 'N/A')}°C"
                self.rainfall_label.text = f"Rainfall: {w.get('rainfall', 'N/A')}"
                self.wind_speed_label.text = f"Wind Speed: {w.get('wind_speed', 'N/A')} m/s"

            if "team_radio" in self.insights:
                df_radio = filter_df(self.insights["team_radio"]).head(20)
                radio_data = []
                for _, row in df_radio.iterrows():
                    driver = self.engine.drivers.get(row["driver_number"], f"#{row['driver_number']}")
                    url = row.get('recording_url', 'No URL')
                    radio_data.append((driver, row['date'], url))
                self.radio_table.data = radio_data
                # Add on_activate to open URL
                self.radio_table.on_activate = self.open_radio_url

            # Track Map Tab
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

                            # Elevation (single value; for profile if key set)
                            elevation_text = f"Altitude: {gdf['altitude'][0]}m"
                            self.track_elevation_label.text = elevation_text

                            if os.getenv("GOOGLE_API_KEY"):
                                gmaps = googlemaps.Client(key=os.getenv("GOOGLE_API_KEY"))
                                # Get path (swap lon/lat to lat/lon)
                                if gdf.geometry.iloc[0].type == 'LineString':
                                    path = [(lat, lon) for lon, lat in gdf.geometry.iloc[0].coords]
                                    elevations = gmaps.elevation_along_path(path=path, samples=50)
                                    # Compute cumulative distances
                                    distances = np.cumsum([0] + [self.haversine(elevations[i]['location'], elevations[i+1]['location']) for i in range(len(elevations)-1)])
                                    fig = px.line(x=distances, y=[e['elevation'] for e in elevations], title="Elevation Profile (m)")
                                    self.track_elevation_chart.set_content('about:blank', fig.to_html(include_plotlyjs='cdn'))
                                else:
                                    self.track_elevation_chart.set_content('about:blank', '<p>No LineString geometry for profile</p>')
                            else:
                                self.track_elevation_chart.set_content('about:blank', '<p>Set GOOGLE_API_KEY for profile</p>')

                            # Turns Table (placeholder)
                            turns_data = []  # Expand if 'turns' property added in future
                            self.track_turns_table.data = turns_data or [("No detailed turns available",)]

                        else:
                            self.track_map_view.set_content('about:blank', '<p>No GeoJSON found</p>')
                    else:
                        self.track_map_view.set_content('about:blank', '<p>No matching GeoJSON file</p>')
            except Exception as e:
                print(f"Track refresh error: {e}")

    def haversine(self, loc1, loc2):
        lat1, lon1 = loc1['lat'], loc1['lng']
        lat2, lon2 = loc2['lat'], loc2['lng']
        R = 6371  # km
        dlat = radians(lat2 - lat1)
        dlon = radians(lon2 - lon1)
        a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
        c = 2 * atan2(sqrt(a), sqrt(1-a))
        return R * c * 1000  # meters

    def get_geojson_filename(self, circuit_name):
        # Hardcoded mapping (extended from previous)
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
            "Autodromo Nazionale di Monza": "it-1922.geojson",
            "Circuit de Spa-Francorchamps": "be-1924.geojson",
            "Silverstone Circuit": "gb-1948.geojson",
            "Suzuka International Racing Course": "jp-1962.geojson",
            "Red Bull Ring": "at-1969.geojson",
            "Circuit of the Americas": "us-2012.geojson",
            # Add more from repo as needed (e.g., "Bahrain International Circuit": "bh-2004.geojson", etc.)
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

    def open_radio_url(self, widget, row, **kwargs):
        url = row.url
        if url != 'No URL':
            webbrowser.open(url)

    # Build methods (unchanged except track)
    def build_standings_tab(self):
        self.standings_table = toga.Table(headings=["Driver", "Gap", "Interval"], data=[], style=Pack(flex=1))
        return toga.Box(children=[self.standings_table], style=Pack(flex=1))

    def build_laps_tab(self):
        self.laps_table = toga.Table(headings=["Lap", "Duration", "S1", "S2", "S3"], data=[], style=Pack(flex=0.5))
        self.laps_chart = toga.WebView(style=Pack(flex=0.5))
        self.fastest_lap_label = toga.Label("Fastest Lap: N/A")
        self.avg_laps_label = toga.Label("Average Laps: N/A")
        return toga.Box(children=[self.laps_table, self.laps_chart, self.fastest_lap_label, self.avg_laps_label], style=Pack(direction=COLUMN, flex=1))

    def build_telemetry_tab(self):
        self.telemetry_speed_chart = toga.WebView(style=Pack(flex=1/3))
        self.telemetry_rpm_chart = toga.WebView(style=Pack(flex=1/3))
        self.telemetry_throttle_chart = toga.WebView(style=Pack(flex=1/3))
        return toga.Box(children=[self.telemetry_speed_chart, self.telemetry_rpm_chart, self.telemetry_throttle_chart], style=Pack(direction=COLUMN, flex=1))

    def build_stints_tab(self):
        self.stints_table = toga.Table(headings=["Driver", "Start Lap", "End Lap", "Compound", "Age"], data=[], style=Pack(flex=0.5))
        self.tyres_table = toga.Table(headings=["Driver", "Compound", "Fresh"], data=[], style=Pack(flex=0.5))
        return toga.Box(children=[self.stints_table, self.tyres_table], style=Pack(direction=COLUMN, flex=1))

    def build_pits_tab(self):
        self.pits_table = toga.Table(headings=["Driver", "Lap", "Duration"], data=[], style=Pack(flex=0.4))
        self.pit_counts_table = toga.Table(headings=["Driver", "Count/Duration"], data=[], style=Pack(flex=0.3))
        self.events_table = toga.Table(headings=["Category", "Flag", "Message"], data=[], style=Pack(flex=0.3))
        return toga.Box(children=[self.pits_table, self.pit_counts_table, self.events_table], style=Pack(direction=COLUMN, flex=1))

    def build_weather_tab(self):
        self.air_temp_label = toga.Label("Air Temp: N/A")
        self.track_temp_label = toga.Label("Track Temp: N/A")
        self.rainfall_label = toga.Label("Rainfall: N/A")
        self.wind_speed_label = toga.Label("Wind Speed: N/A")
        weather_box = toga.Box(children=[self.air_temp_label, self.track_temp_label, self.rainfall_label, self.wind_speed_label], style=Pack(direction=COLUMN))
        self.radio_table = toga.Table(headings=["Driver", "Date", "URL"], data=[], on_activate=self.open_radio_url, style=Pack(flex=1))
        return toga.Box(children=[weather_box, self.radio_table], style=Pack(direction=COLUMN, flex=1))

    def build_track_tab(self):
        self.track_properties_label = toga.Label("Circuit Details: N/A")
        self.track_elevation_label = toga.Label("Elevation: N/A")
        self.track_map_view = toga.WebView(style=Pack(flex=0.5))
        self.track_elevation_chart = toga.WebView(style=Pack(flex=0.5))
        self.track_turns_table = toga.Table(headings=["Turn", "Details"], data=[], style=Pack(flex=0.3))
        return toga.Box(children=[self.track_properties_label, self.track_elevation_label, self.track_map_view, self.track_elevation_chart, self.track_turns_table], style=Pack(direction=COLUMN, flex=1))

def main():
    return OpenF1LiveInsights()
