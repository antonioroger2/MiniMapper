from flask import Flask, request, jsonify
import requests
import paho.mqtt.client as mqtt
import ssl
from geopy.distance import geodesic
from bs4 import BeautifulSoup

app = Flask(__name__)

# Static Configuration
GOOGLE_MAPS_API_URL = "https://maps.googleapis.com/maps/api/directions/json"
GOOGLE_MAPS_API_KEY = "AIzaSyDMVIak8Nds7TPq-57bFlHguCL5g043wUE"

MQTT_BROKER = "2df5030af7634175a5de7b701ae3b138.s1.eu.hivemq.cloud"
MQTT_PORT = 8883
MQTT_USERNAME = "harishjanarth"
MQTT_PASSWORD = "Harish@123"
MQTT_TOPIC_INSTRUCTIONS = "esp32/route/instructions"

mqtt_client = mqtt.Client()

def setup_mqtt():
    def on_connect(client, userdata, flags, rc):
        print("MQTT connected!" if rc == 0 else f"MQTT connection failed: {rc}")

    mqtt_client.on_connect = on_connect
    mqtt_client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    mqtt_client.tls_set_context(ssl.create_default_context())
    mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)

setup_mqtt()

def extract_route_data(directions):
    steps = directions["routes"][0]["legs"][0]["steps"]
    instructions = [BeautifulSoup(step["html_instructions"], "html.parser").get_text() for step in steps]
    waypoints = [(step["end_location"]["lat"], step["end_location"]["lng"]) for step in steps]
    return instructions, waypoints

@app.route('/ABC/1/route', methods=['POST'])
def get_route():
    data = request.json
    destination = data.get('destination')
    current_location = data.get('current_location')

    if not current_location or not destination:
        return jsonify({"error": "Current location and destination are required"}), 400

    source = f"{current_location['lat']},{current_location['lng']}"
    params = {"origin": source, "destination": destination, "key": GOOGLE_MAPS_API_KEY}
    response = requests.get(GOOGLE_MAPS_API_URL, params=params)

    if response.status_code == 200:
        directions = response.json()
        instructions, waypoints = extract_route_data(directions)
        return jsonify({"instructions": instructions, "waypoints": waypoints})
    else:
        return jsonify({"error": "Failed to fetch route"}), response.status_code

@app.route('/ABC/1/update-instructions', methods=['POST'])
def update_instructions():
    data = request.json
    current_location = data.get('current_location')
    waypoints = data.get('waypoints')
    instructions = data.get('instructions')
    current_step = data.get('current_step', 0)

    if not current_location or not waypoints or not instructions:
        return jsonify({"error": "Invalid data"}), 400

    next_waypoint = waypoints[current_step]
    distance = geodesic((current_location["lat"], current_location["lng"]), next_waypoint).meters

    if distance < 50:
        current_step += 1
        if current_step < len(instructions):
            next_instruction = instructions[current_step]
            if mqtt_client.is_connected():
                mqtt_client.publish(MQTT_TOPIC_INSTRUCTIONS, next_instruction)
            return jsonify({"current_step": current_step, "instruction": next_instruction})
        else:
            return jsonify({"message": "Route completed"}), 200

    return jsonify({"current_step": current_step})

if __name__ == '__main__':
    mqtt_client.loop_start()
    app.run(debug=True, host='0.0.0.0', port=10000)
