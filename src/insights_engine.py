import pandas as pd

class InsightsEngine:
    def __init__(self):
        self.drivers = {}  # {driver_number: full_name}
        self.teams = {}    # {driver_number: team_name}

    def load_drivers(self, client, session_key):
        params = {"session_key": session_key}
        drivers_data = client.fetch_historical("drivers", params)
        for driver in drivers_data:
            num = driver["driver_number"]
            self.drivers[num] = driver.get("full_name", f"Driver {num}")
            self.teams[num] = driver.get("team_name", "Unknown")

    def generate_insights(self, data_queues, mode="live"):
        insights = {}

        # (Unchanged -full code as in previous version)

        return insights
