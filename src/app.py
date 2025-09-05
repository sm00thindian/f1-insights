import toga
from toga.style import Pack
from toga.constants import COLUMN
import plotly.express as px
import pandas as pd
import platform  # For async
import asyncio
from .api_client import OpenF1Client
from .insights_engine import InsightsEngine

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
        meeting_key = self.meeting_key.value  # Used if needed
        mode = self.mode.value

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
                # ... (all fetches as in previous)
            }
            self.insights = self.engine.generate_insights(data_queues, mode="historical")
            self.refresh_ui()

    async def live_update_loop(self):
        while True:
            self.insights = self.engine.generate_insights(self.client.data_queues, mode="live")
            await asyncio.sleep(10)
            platform.loop.call_soon(self.refresh_ui)  # Update UI on main thread

    def filter_data(self, widget):
        self.refresh_ui()

    def refresh_ui(self):
        # Get filters
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

        # Update Standings
        if "standings" in self.insights:
            df_standings = filter_df(self.insights["standings"])
            df_standings["driver"] = df_standings["driver_number"].map(self.engine.drivers)
            data = [(row["driver"], str(row.get("gap_to_leader", "N/A"))) for _, row in df_standings.iterrows()]
            self.standings_table.data = data

        # Update Laps (table and chart)
        if "laps" in self.insights:
            df_laps = filter_df(self.insights["laps"])
            self.laps_table.data = [(row["lap_number"], row["lap_duration"]) for _, row in df_laps.iterrows()]  # Simplified
            if not df_laps.empty:
                fig = px.line(df_laps, x="lap_number", y="lap_duration", color="driver_number")
                self.laps_chart.set_content(root_url="about:blank", content=fig.to_html(include_plotlyjs="cdn"))

        # Similar updates for other tabs (telemetry, stints, pits, weather/radio)
        # For example, telemetry chart
        if "telemetry" in self.insights:
            df_tele = filter_df(self.insights["telemetry"])
            if not df_tele.empty:
                fig_speed = px.line(df_tele, x="date", y="speed")
                self.telemetry_speed_chart.set_content(root_url="about:blank", content=fig_speed.to_html(include_plotlyjs="cdn"))

        # ... (implement similar for other sections)

    def build_standings_tab(self):
        self.standings_table = toga.Table(headings=["Driver", "Gap"], data=[])
        return toga.Box(children=[self.standings_table], style=Pack(flex=1))

    def build_laps_tab(self):
        self.laps_table = toga.Table(headings=["Lap", "Duration"], data=[])
        self.laps_chart = toga.WebView(style=Pack(flex=1))
        return toga.Box(children=[self.laps_table, self.laps_chart], style=Pack(direction=COLUMN, flex=1))

    def build_telemetry_tab(self):
        self.telemetry_speed_chart = toga.WebView(style=Pack(flex=1))
        # Add more WebViews for RPM, etc.
        return toga.Box(children=[self.telemetry_speed_chart], style=Pack(flex=1))

    # Similar methods for other tabs (stints, pits, weather)
    def build_stints_tab(self):
        self.stints_label = toga.Label("Stints Data")
        return toga.Box(children=[self.stints_label], style=Pack(flex=1))

    def build_pits_tab(self):
        self.pits_table = toga.Table(headings=["Driver", "Pit Duration"], data=[])
        return toga.Box(children=[self.pits_table], style=Pack(flex=1))

    def build_weather_tab(self):
        self.weather_label = toga.Label("Weather Info")
        return toga.Box(children=[self.weather_label], style=Pack(flex=1))

def main():
    return OpenF1LiveInsights()
