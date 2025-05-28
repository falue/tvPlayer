import paho.mqtt.client as mqtt
import json
import threading
import time

on_command_callback = None
client = None  # global client

def set_command_handler(callback):
    global on_command_callback
    on_command_callback = callback

def on_connect(client, userdata, flags, rc, properties=None):
    print("[MQTT] Connected")
    client.subscribe("tvPlayer/command")

def on_message(client, userdata, msg):
    try:
        data = json.loads(msg.payload.decode())
        # print("[MQTT] Received:", data)
        if on_command_callback:
            on_command_callback(data)
    except Exception as e:
        print("[MQTT] Error parsing message:", e)


def send(topic="general", command="", payload=None):
    if client:
        message = {"command": command}
        if payload:
            message["payload"] = payload
        client.publish(f"tvPlayer/{topic}", json.dumps(message))

def start():
    def mqtt_loop():
        global client
        client = mqtt.Client()
        client.on_connect = on_connect
        client.on_message = on_message
        client.connect("localhost", 1883, 60)
        client.loop_start()

        try:
            while True:
                heartbeat = json.dumps({"msg": "heartbeat from tvPlayer"})
                client.publish("tvPlayer/heartbeat", heartbeat)
                time.sleep(5)
        except KeyboardInterrupt:
            client.loop_stop()
            client.disconnect()

    thread = threading.Thread(target=mqtt_loop, daemon=True)
    thread.start()
