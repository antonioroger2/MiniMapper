from flask import Flask, request, jsonify
import requests
import paho.mqtt.client as mqtt
import ssl
from bs4 import BeautifulSoup
from geopy.distance import geodesic

app = Flask(__name__)

# Google Maps API Configuration
GOOGLE_MAPS_API_URL = "https://maps.googleapis.com/maps/api/directions/json"
GOOGLE_MAPS_API_KEY = "YOUR_GOOGLE_MAPS_API_KEY"

# MQTT Configuration
MQTT_BROKER = "2df5030af7634175a5de7b701ae3b138.s1.eu.hivemq.cloud"
MQTT_PORT = 8883
MQTT_USERNAME = "harishjanarth"
MQTT_PASSWORD = "Harish@123"
MQTT_TOPIC_INSTRUCTIONS = "esp32/route/instructions"

mqtt_client = mqtt.Client()

def setup_mqtt():
    mqtt_client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    mqtt_client.tls_set_context(ssl.create_default_context())
    mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
setup_mqtt()

# Helper to extract instructions and waypoints
def extract_route_data(directions):
    steps = directions["routes"][0]["legs"][0]["steps"]
    instructions = [BeautifulSoup(step["html_instructions"], "html.parser").get_text() for step in steps]
    waypoints = [(step["end_location"]["lat"], step["end_location"]["lng"]) for step in steps]
    return instructions, waypoints

@app.route('/r', methods=['GET'])
def get_route():
    current_location = request.args.get('c')
    destination = request.args.get('d')

    if not current_location or not destination:
        return jsonify({"error": "Current location and destination are required"}), 400

    lat, lon = map(float, current_location.split(','))
    source = f"{lat},{lon}"
    params = {"origin": source, "destination": destination, "key": GOOGLE_MAPS_API_KEY}
    response = requests.get(GOOGLE_MAPS_API_URL, params=params)

    if response.status_code == 200:
        directions = response.json()
        instructions, waypoints = extract_route_data(directions)
        polyline = directions["routes"][0]["overview_polyline"]["points"]

        return jsonify({
            "instructions": instructions,
            "waypoints": waypoints,
            "polyline": polyline
        })
    else:
        return jsonify({"error": "Failed to fetch route", "details": response.text}), response.status_code

@app.route('/update-instructions', methods=['POST'])
def update_instructions():
    data = request.json
    current_location = data.get('current_location')
    waypoints = data.get('waypoints')
    instructions = data.get('instructions')
    current_step = data.get('current_step', 0)

    if not current_location or not waypoints or not instructions:
        return jsonify({"error": "Invalid data provided"}), 400

    next_waypoint = waypoints[current_step]
    distance = geodesic((current_location["lat"], current_location["lng"]), next_waypoint).meters

    if distance < 50:  # Threshold in meters
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
    app.run(debug=True)
