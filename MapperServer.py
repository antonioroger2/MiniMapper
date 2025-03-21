from flask import Flask, request, jsonify
from flask_mqtt import Mqtt
import requests
from geopy.distance import geodesic

app = Flask(__name__)

# Google Maps API Configuration
ROUTES_API_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
GOOGLE_MAPS_API_KEY = "AIzaSyDMVIak8Nds7TPq-57bFlHguCL5g043wUE"

# MQTT Configuration
app.config['MQTT_BROKER_URL'] = "2df5030af7634175a5de7b701ae3b138.s1.eu.hivemq.cloud"
app.config['MQTT_BROKER_PORT'] = 8883
app.config['MQTT_USERNAME'] = "harishjanarth"
app.config['MQTT_PASSWORD'] = "Harish@123"
app.config['MQTT_TLS_ENABLED'] = True
app.config['MQTT_TLS_INSECURE'] = False
app.config['MQTT_CLEAN_SESSION'] = True

mqtt_client = Mqtt(app, connect_async=True)
MQTT_TOPIC_INSTRUCTIONS = "esp32/route/instructions"

@mqtt_client.on_connect()
def handle_connect(client, userdata, flags, rc):
    if rc == 0:
        print('Connected successfully to MQTT broker')
    else:
        print('Bad connection to MQTT broker. Code:', rc)

@mqtt_client.on_disconnect()
def handle_disconnect():
    print('Disconnected from MQTT broker')

# Helper to extract instructions and waypoints
def extract_route_data(route_response):
    try:
        # Access the steps in the first route's first leg
        steps = route_response["routes"][0]["legs"][0]["steps"]
        
        # Extract navigation instructions and waypoints
        instructions = [step.get("navigationInstruction", {}).get("instructions", "No instruction available") for step in steps]
        waypoints = [(step["endLocation"]["latLng"]["latitude"], step["endLocation"]["latLng"]["longitude"]) for step in steps]
        
        return instructions, waypoints
    except KeyError as e:
        raise ValueError(f"Missing expected key in Routes API response: {e}")

@app.route('/r', methods=['GET'])
def get_route():
    current_location = request.args.get('c')
    destination = request.args.get('d')

    if not current_location or not destination:
        return jsonify({"error": "Current location and destination are required"}), 400

    try:
        lat, lon = map(float, current_location.split(','))
        source = {"latitude": lat, "longitude": lon}
        dest_lat, dest_lon = map(float, destination.split(','))
        destination_coords = {"latitude": dest_lat, "longitude": dest_lon}

        payload = {
            "origin": {"location": {"latLng": source}},
            "destination": {"location": {"latLng": destination_coords}},
            "travelMode": "BICYCLE"
        }

        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": GOOGLE_MAPS_API_KEY,
            "X-Goog-FieldMask": "routes.legs.steps.navigationInstruction,routes.legs.steps.endLocation,routes.polyline.encodedPolyline"
        }

        response = requests.post(ROUTES_API_URL, json=payload, headers=headers)

        if response.status_code == 200:
            route_response = response.json()
            try:
                instructions, waypoints = extract_route_data(route_response)
                polyline = route_response["routes"][0]["polyline"]["encodedPolyline"]

                return jsonify({
                    "instructions": instructions,
                    "waypoints": waypoints,
                    "polyline": polyline
                })
            except ValueError as e:
                return jsonify({"error": str(e)}), 500
        else:
            return jsonify({"error": f"Failed to fetch route: {response.status_code}", 
                            "details": response.text}), response.status_code
    except Exception as e:
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

@app.route('/update-instructions', methods=['POST'])
def update_instructions():
    data = request.json
    current_location = data.get('current_location')
    waypoints = data.get('waypoints')
    instructions = data.get('instructions')
    current_step = data.get('current_step', 0)

    if not current_location or not waypoints or not instructions:
        return jsonify({"error": "Invalid data provided"}), 400

    try:
        next_waypoint = waypoints[current_step]
        distance = geodesic((current_location["lat"], current_location["lng"]), next_waypoint).meters

        if distance < 50:  # Threshold in meters
            current_step += 1
            if current_step < len(instructions):
                next_instruction = instructions[current_step]
                mqtt_client.publish(MQTT_TOPIC_INSTRUCTIONS, next_instruction)
                return jsonify({"current_step": current_step, "instruction": next_instruction})
            else:
                return jsonify({"message": "Route completed"}), 200

        return jsonify({"current_step": current_step})
    except Exception as e:
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500


if __name__ == '__main__':
    app.run(host="0.0.0.0", port=3000)
