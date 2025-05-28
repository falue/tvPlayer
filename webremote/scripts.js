let client
let hasReceivedSettings = false;
let raspi_available = false;
let raspi_available_timer = null;
let settings = {}

function init() {
    logging("start!");
    const mqttHost = location.hostname;  // returns "10.3.141.1"
    logging(mqttHost);
    client = mqtt.connect(`ws://${mqttHost}:9001`);
    logging(`ws://${mqttHost}:9001`);
    logging(`scripts.js loaded`);
    logging(`mqtt: `+(typeof mqtt));
    logging(`Using MQTT host: ` + mqttHost);

    client.on('error', (err) => {
        logging(`MQTT connection error: ${err.message}`);
    });

    client.on('connect', () => {
        logging("Connected to MQTT broker.");
        client.subscribe('tvPlayer/#');
        sendCommand({"cmd": "give_settings"}, true)
    });

    client.on('message', (topic, message) => {
        const data = JSON.parse(message.toString());
        if(topic === 'tvPlayer/heartbeat') {
            logging(`Received heartbeat: <pre>${JSON.stringify(data)}</pre>`);
            handleHeartbeat()

        } else if(topic === 'tvPlayer/settings')  {
            logging(`Received settings: <pre>${JSON.stringify(data)}</pre>`);
            hasReceivedSettings = true;
            handleSettings(data)

        } else if(topic === 'tvPlayer/command') {
            logging(`Acknowledged command: <pre>${JSON.stringify(data)}</pre>`);

        } else {
            logging(`Received message on ${topic}: <pre>${JSON.stringify(data)}</pre>`);
        }
    });
    requestSettingsLoop();

    window.addEventListener("blur", () => {
        logging("Window lost focus — clearing timeouts");
        clearTimeout(raspi_available_timer);
    });

    /* window.addEventListener("focus", () => {
        console.log("Window regained focus — restarting timeouts");
        startHeartbeatTimeouts();
    }); */
}

function sendCommand(data, ignore_availability=false) {
    if(!raspi_available && !ignore_availability) {
        alert("Cannot connect to tvPlayer. Go closer.");
        return;
    }
    logging("Message maybe sent to python..");
    client.publish('tvPlayer/command', JSON.stringify({
        command: data.cmd,
        value: data.value ? data.value : 0
    }));
}

function gebi(id) {
    return document.getElementById(id);
}

function handleHeartbeat() {
    raspi_available = true;
    clearTimeout(raspi_available_timer);
    // Add green class
    gebi('heartbeat').classList.add('active');
    // remove green class after 1s (+css-fadeout)
    setTimeout(() => {
        gebi('heartbeat').classList.remove('active');
    }, 1000);
    raspi_available_timer = setTimeout(() => {
        logging("CONNECTION LOST AFTER 8s");
        // Enable warning-alerts on button presses and siable them after 8s
        raspi_available = false;
        setTimeout(() => {
            // Warn the user anyhow out of the blue after total 16s of loss of connection
            alert("Connection lost after 16s. Go closer or turn tvPlayer on.")
        }, 8000);
    }, 8000);
}

function handleSettings(data) {
    logging(data)
}

function requestSettingsLoop() {
    if (hasReceivedSettings) return; // stop if already received
    logging("Wait for settings..");

    sendCommand({"cmd": "give_settings"}, true);
    setTimeout(requestSettingsLoop, 1000); // try again in 1 second
}

function logging(text) {
    console.log(text);
    document.getElementById('console').innerHTML = text + "<br>" + document.getElementById('console').innerHTML;
}

init();
  

