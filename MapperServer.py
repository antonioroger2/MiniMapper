from flask import Flask, request, jsonify
import requests
import paho.mqtt.client as mqtt
import ssl
from geopy.distance import geodesic
from bs4 import BeautifulSoup
import json
import base64

app = Flask(__name__)

# Google Maps API Configuration
GOOGLE_MAPS_API_URL = "https://maps.googleapis.com/maps/api/directions/json"
GOOGLE_MAPS_API_KEY = "AIzaSyDMVIak8Nds7TPq-57bFlHguCL5g043wUE"

# MQTT Configuration
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

def encode_route_data(instructions, waypoints):
    route_data = {"instructions": instructions, "waypoints": waypoints}
    json_data = json.dumps(route_data)
    base64_data = base64.b64encode(json_data.encode()).decode()
    return base64_data

@app.route('/r', methods=['GET'])
def get_route():
    current_location = request.args.get('c')
    destination = request.args.get('d')

    if not current_location or not destination:
        return jsonify({"error": "Current location (c) and destination (d) are required"}), 400

    source = current_location
    params = {"origin": source, "destination": destination, "key": GOOGLE_MAPS_API_KEY}

    response = requests.get(GOOGLE_MAPS_API_URL, params=params)

    if response.status_code == 200:
        directions = response.json()
        instructions, waypoints = extract_route_data(directions)
        encoded_data = encode_route_data(instructions, waypoints)

        total_distance = directions["routes"][0]["legs"][0]["distance"]["text"]
        total_duration = directions["routes"][0]["legs"][0]["duration"]["text"]

        return jsonify({
            "success": True,
            "route": {
                "instructions": instructions,
                "waypoints": waypoints,
                "total_distance": total_distance,
                "total_duration": total_duration,
                "encoded_data": encoded_data
            },
            "origin": {"location": source},
            "destination": {"location": destination}
        })
    else:
        return jsonify({
            "success": False,
            "error": "Failed to fetch route",
            "status_code": response.status_code
        }), response.status_code

@app.route('/update-progress', methods=['POST'])
def update_progress():
    data = request.json
    current_location = data.get('current_location')
    current_step = data.get('current_step', 0)
    encoded_data = data.get('encoded_data')

    if not current_location or encoded_data is None:
        return jsonify({"success": False, "error": "Invalid data"}), 400

    try:
        json_data = base64.b64decode(encoded_data).decode()
        route_data = json.loads(json_data)
        instructions = route_data.get('instructions', [])
        waypoints = route_data.get('waypoints', [])

        if current_step < len(waypoints):
            next_waypoint = waypoints[current_step]
            distance = geodesic((current_location["lat"], current_location["lng"]), next_waypoint).meters

            if distance < 50:
                current_step += 1
                if current_step < len(instructions):
                    next_instruction = instructions[current_step]
                    if mqtt_client.is_connected():
                        mqtt_client.publish(MQTT_TOPIC_INSTRUCTIONS, next_instruction)

                    return jsonify({
                        "success": True,
                        "current_step": current_step,
                        "instruction": next_instruction,
                        "waypoint_reached": True
                    })
                else:
                    return jsonify({
                        "success": True,
                        "message": "Route completed",
                        "waypoint_reached": True,
                        "route_completed": True
                    })

            return jsonify({
                "success": True,
                "current_step": current_step,
                "distance_to_next": distance,
                "waypoint_reached": False
            })
        else:
            return jsonify({
                "success": True,
                "message": "Route already completed",
                "route_completed": True
            })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"Error processing route data: {str(e)}"
        }), 400

if __name__ == '__main__':
    mqtt_client.loop_start()
    app.run(host='0.0.0.0', port=10000, debug=True)
