let client
let hasReceivedSettings = false

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
        sendCommand("give_settings")
    });

    client.on('message', (topic, message) => {
        const data = JSON.parse(message.toString());
        if(topic === 'tvPlayer/heartbeat') {
            logging(`Received heartbeat: <pre>${JSON.stringify(data)}</pre>`);
        } else if(topic === 'tvPlayer/settings')  {
            logging(`Received settings: <pre>${JSON.stringify(data)}</pre>`);
            hasReceivedSettings = true;
        } else if(topic === 'tvPlayer/command') {
            logging(`Acknowledged command: <pre>${JSON.stringify(data)}</pre>`);
        } else {
            logging(`Received message on ${topic}: <pre>${JSON.stringify(data)}</pre>`);
        }
    });

    requestSettingsLoop();
}

function requestSettingsLoop() {
    if (hasReceivedSettings) return; // stop if already received
    logging("Wait for settings..");

    sendCommand("give_settings");
    setTimeout(requestSettingsLoop, 1000); // try again in 1 second
}

function sendCommand(cmd) {
    logging("Message maybe sent to python..");
    client.publish('tvPlayer/command', JSON.stringify({
        command: cmd,
        value: null
    }));
}

function logging(text) {
    console.log(text);
    document.getElementById('console').innerHTML = text + "<br>" + document.getElementById('console').innerHTML;
}

init();
  

