from flask import Flask, send_from_directory
import os
import subprocess

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(SCRIPT_DIR, "webremote")
app = Flask(__name__, static_folder=WEB_DIR)

# Kill any process using port 8080 (adjust if you use another port)
try:
    output = subprocess.check_output("lsof -t -i:8080", shell=True)
    pids = output.decode().strip().split('\n')
    for pid in pids:
        print(f"[server] Killing previous server on port 8080 (PID {pid})")
        os.kill(int(pid), 9)
except subprocess.CalledProcessError:
    pass  # nothing was running

@app.route("/")
def index():
    return send_from_directory(WEB_DIR, "index.html")

@app.route("/<path:path>")
def static_files(path):
    return send_from_directory(WEB_DIR, path)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
