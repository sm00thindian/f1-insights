import requests
import paho.mqtt.client as mqtt
import ssl
import json
from dotenv import load_dotenv
import os
import platform  # For BeeWare async

load_dotenv()

class OpenF1Client:
    def __init__(self):
        self.base_url = "https://api.openf1.org/v1/"
        self.token_url = "https://api.openf1.org/token"
        self.mqtt_broker = "mqtt.openf1.org"
        self.mqtt_port = 8883
        self.username = os.getenv("OPENF1_USERNAME")
        self.password = os.getenv("OPENF1_PASSWORD")
        self.access_token = None
        self.client = None
        self.data_queues = {}  # Dict to store incoming data by topic
        self.connected = False

    def get_access_token(self):
        if not self.username or not self.password:
            print("Warning: No credentials provided. Historical mode only.")
            return
        payload = {
            "username": self.username,
            "password": self.password
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        response = requests.post(self.token_url, data=payload, headers=headers)
        if response.status_code == 200:
            token_data = response.json()
            self.access_token = token_data.get("access_token")
            print("Access token obtained successfully.")
        else:
            raise Exception(f"Error obtaining token: {response.status_code} - {response.text}")

    def fetch_historical(self, endpoint, params=None):
        url = f"{self.base_url}{endpoint}"
        headers = {"accept": "application/json"}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        response = requests.get(url, headers=headers, params=params)
        if response.status_code == 200:
            return response.json()
        else:
            raise Exception(f"Error fetching data: {response.status_code} - {response.text}")

    # Specific fetch methods (unchanged)
    def fetch_intervals(self, session_key):
        params = {"session_key": session_key}
        return self.fetch_historical("intervals", params)

    # ... (all other fetch methods unchanged, as in previous version)

    def on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            self.connected = True
            topics = [
                "v1/intervals", "v1/position", "v1/laps", "v1/pit", "v1/race_control",
                "v1/car_data", "v1/weather", "v1/stints", "v1/tyres", "v1/team_radio"
            ]
            for topic in topics:
                client.subscribe(topic)
                self.data_queues[topic] = []
        else:
            print(f"Failed to connect, return code {rc}")

    def on_message(self, client, userdata, msg):
        payload = json.loads(msg.payload.decode())
        topic = msg.topic
        if topic in self.data_queues:
            self.data_queues[topic].append(payload)
            if len(self.data_queues[topic]) > 500:
                self.data_queues[topic] = self.data_queues[topic][-500:]

    async def start_mqtt_stream(self):
        if not self.access_token:
            self.get_access_token()
        if not self.access_token:
            raise Exception("Access token required for live mode.")
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.client.username_pw_set(username=self.username, password=self.access_token)
        self.client.tls_set(cert_reqs=ssl.CERT_REQUIRED, tls_version=ssl.PROTOCOL_TLS_CLIENT)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.connect(self.mqtt_broker, self.mqtt_port, 60)
        self.client.loop_start()  # Run in background for async

    def stop_mqtt_stream(self):
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()

    def get_latest_data(self, topic):
        return self.data_queues.get(f"v1/{topic}", [])
