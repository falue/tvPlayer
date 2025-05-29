let client;
let hasReceivedSettings = false;
let raspi_available = false;
let raspi_available_timer = null;
let settings = {};
let lastPlaystate = "";
let currentFile = {};
let blockTimerUpdate = false;
let isShowingFillColor = false;
let lastThumbnail = ""

function init() {
  logging("start!");
  const mqttHost = location.hostname; // returns "10.3.141.1"
  logging(mqttHost);
  client = mqtt.connect(`ws://${mqttHost}:9001`);
  logging(`ws://${mqttHost}:9001`);
  logging(`scripts.js loaded`);
  logging(`mqtt: ` + typeof mqtt);
  logging(`Using MQTT host: ` + mqttHost);

  client.on("error", (err) => {
    logging(`MQTT connection error: ${err.message}`);
  });

  client.on("connect", () => {
    logging("Connected to MQTT broker.");
    client.subscribe("tvPlayer/#");
    sendCommand({ cmd: "give_settings" }, true);
  });

  client.on("message", (topic, message) => {
    const data = JSON.parse(message.toString());
    if (topic === "tvPlayer/heartbeat") {
      logging(`Received heartbeat: <pre>${JSON.stringify(data)}</pre>`);
      handleHeartbeat();

    } else if (topic === "tvPlayer/settings") {
      logging(`Received settings: <pre>${JSON.stringify(data)}</pre>`);
      hasReceivedSettings = true;
      handleSettings(data.payload);

    } else if (topic === "tvPlayer/command") {
      logging(`Acknowledged command: <pre>${JSON.stringify(data)}</pre>`);

    } else {
      logging(
        `Received message on ${topic}: <pre>${JSON.stringify(data)}</pre>`
      );
      if (data.command == "createThumbnails") {
        gebi("filelist").innerHTML = "Creating thumbnails..";

      } else if (data.command == "state") {
        handleState(data.payload);

      } else if (data.command == "fillcolor") {
        handleFillColor(data.payload);
      }
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

function sendCommand(data, ignore_availability = false) {
  if (!raspi_available && !ignore_availability) {
    alert("Cannot connect to tvPlayer. Go closer.");
    return;
  }
  client.publish(
    "tvPlayer/command",
    JSON.stringify({
      command: data.cmd,
      value: data.value ? data.value : 0,
    })
  );
}

function gebi(id) {
  return document.getElementById(id);
}

function handleHeartbeat() {
  raspi_available = true;
  clearTimeout(raspi_available_timer);
  // Add green class
  gebi("heartbeat").classList.add("active");
  // remove green class after 1s (+css-fadeout)
  setTimeout(() => {
    gebi("heartbeat").classList.remove("active");
  }, 1000);
  raspi_available_timer = setTimeout(() => {
    logging("CONNECTION LOST AFTER 8s");
    // Enable warning-alerts on button presses and siable them after 8s
    raspi_available = false;
    setTimeout(() => {
      // Warn the user anyhow out of the blue after total 16s of loss of connection
      alert("Connection lost after 16s. Go closer or turn tvPlayer on.");
    }, 8000);
  }, 8000);
}

function showState() {
  if(raspi_available) {
    alert("The system is currently up and running");
  } else {
    alert("The system is currently not available. (Re-) start the tvPlayer or go closer until circle turns green.\n\nAlso re-check if you're in the correct wifi! Should be: 'tvPlayer'!");
  }
}

function handleSettings(data) {
  logging(data.filelist);

  const filelistContainer = gebi("filelist");
  filelistContainer.innerHTML = ""; // Clear previous entries

  if (data.filelist.length == 0) {
    filelistContainer.innerHTML = "No valid files on USB or no USB plugged.";
    return;
  }

  data.filelist.forEach((filepath, index) => {
    const filename = filepath.split("/").pop();
    const dotIndex = filename.lastIndexOf(".");
    const basename = filename.slice(0, dotIndex);
    const suffix = filename.slice(dotIndex + 1);

    const container = document.createElement("div");
    container.classList.add("button-row");
    const button = document.createElement("button");
    button.className = "filelistButton";
    button.onclick = () => sendCommand({ cmd: "go_to_channel", value: index });

    const img = document.createElement("img");
    img.className = "thumbnails";
    img.src = `./thumbnails/${basename}.png`;

    const label = document.createTextNode(`#${index + 1}: ${basename}`);
    const span = document.createElement("span");
    span.className = "grey";
    span.textContent = `.${suffix}`;

    button.appendChild(img);
    const divText = document.createElement("div");
    divText.appendChild(label);
    divText.appendChild(span);
    button.appendChild(divText);
    container.appendChild(button);
    filelistContainer.appendChild(container);
  });
}

function handleState(data) {
  // Check if data changed, if yes..
  if (lastPlaystate != md5(JSON.stringify(data))) {
    lastPlaystate = md5(JSON.stringify(data));
    if (data.isPlaying) {
      gebi("playstate").src = "./assets/icons/pause.svg";
    } else {
      gebi("playstate").src = "./assets/icons/play.svg";
    }
    if (data.currentFile.length > 0 && !isShowingFillColor) {
      let name = splitFileName(data.currentFile);
      let basename = name.basename;
      let suffix = name.suffix;
      gebi("currentFile").innerHTML = `#${data.tvChannel + 1} - ${basename}<span class='grey'>.${suffix}</span>`;
      let timeline = gebi("timeline");
      if(data.duration>0){
        show("timeline");
        if(!blockTimerUpdate) {
          timeline.value=data.position;
          timeline.max=data.duration;
          gebi("timecode").innerHTML = `${secondsToTimecode(data.position)}/${secondsToTimecode(data.duration)}`;
        }
      } else {
        hide("timeline");
        gebi("timecode").innerHTML = "";
      }
      gebi("display").style.backgroundImage = `url("thumbnails/${basename}.png")`;
    } else {
      gebi("currentFile").innerHTML = "No current file. Insert USB with valid video or image files.";
      gebi("display").style.backgroundImage = ``;
    }
    currentFile = data;
  }
}

function handleFillColor(data) {
  let display = gebi("display");
  if(data.show) {
    isShowingFillColor = true;
    lastThumbnail = display.style.backgroundImage;
    display.style.backgroundImage = `url('assets/screens/${data.type}${data.index ? data.index : ''}.png')`
  } else {
    isShowingFillColor = false;
    display.style.backgroundImage = lastThumbnail;
  }
}

function skipper(value) {
  blockTimerUpdate = false;
  sendCommand({'cmd': 'jump', 'value': value})
}

function skipperPreviewTime(element) {
  blockTimerUpdate = true;
  gebi("timecode").innerHTML = `${secondsToTimecode(element.value)}/${secondsToTimecode(element.max)}`;
}

function requestSettingsLoop() {
  if (hasReceivedSettings) return; // stop if already received
  logging("Wait for settings..");

  sendCommand({ cmd: "give_settings" }, true);
  setTimeout(requestSettingsLoop, 1000); // try again in 1 second
}

function splitFileName(path) {
  const full = path.split("/").pop(); // Get "file.name.with.dots.ext"
  const lastDot = full.lastIndexOf("."); // Find the last dot
  if (lastDot === -1) return { basename: full, suffix: "" };
  return {
    basename: full.slice(0, lastDot),
    suffix: full.slice(lastDot + 1),
  };
}

function secondsToTimecode(seconds, fps = 25) {
  const totalSeconds = Math.floor(seconds);
  const frames = Math.round((seconds - totalSeconds) * fps);

  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60)
    .toString()
    .padStart(2, "0");
  const secs = (totalSeconds % 60).toString().padStart(2, "0");
  const frameStr = frames.toString().padStart(2, "0");

  if (hours > 0) {
    return `${hours
      .toString()
      .padStart(2, "0")}:${minutes}:${secs}.${frameStr}`;
  } else {
    return `${minutes}:${secs}.${frameStr}`;
  }
}

function logging(text) {
  console.log(text);
  document.getElementById("console").innerHTML =
    text + "<br>" + document.getElementById("console").innerHTML;
}


function hide(id) {
	for(i=0; i< arguments.length; i++) { 
		document.getElementById(arguments[i]).style.display = 'none';
	}
}

function show(id) {
	for(i=0; i< arguments.length; i++) { 
		document.getElementById(arguments[i]).style.display = 'block';
	}
}

function toggle(id) {
  let element = document.getElementById(id);
  let display = window.getComputedStyle(element, null).display;
  if(display == "" || display == "none") {
    show(id);
  } else {
    hide(id);
  }
}

// Start the whole mqtt shenanigans
init();
