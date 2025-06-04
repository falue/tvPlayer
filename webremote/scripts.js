let client;
let hasReceivedSettings = false;
let raspi_available = false;
let raspi_available_timer = null;
let settings = {};
let lastPlaystate = "";
let lastSettings = "";
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
      logging(`Received heartbeat`);
      handleHeartbeat(data.temp ? data.temp : false);

    } else if (topic === "tvPlayer/settings") {
      logging(`Received settings`);
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
        handleHeartbeat();  // Treat as heartbeat because it comes every second

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
}

function sendCommand(data, ignore_availability=false, giveFeedback=false) {
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
  if(giveFeedback) {
    sendCommand({ cmd: "give_settings" }, true);
  }
}

function gebi(id) {
  return document.getElementById(id);
}

function handleHeartbeat(temp=false) {
  raspi_available = true;
  clearTimeout(raspi_available_timer);
  if(temp !== false) {
    // Set CPU temp
    if(temp > 90) {
      alert('tvPlayer is INCREDIBLY hot - turn off NOW!')
    }
    if(temp > 85) {
      gebi('note-temp').innerHTML = `!!! ${temp.toFixed(1)}°C !!!`;
      gebi('note-temp').style.color= "rgb(255, 68, 0)";
      gebi('error').innerHTML = 'tvPlayer is VERY hot - turn off NOW'
    } else if(temp >= 80) {
      gebi('note-temp').innerHTML = `${temp.toFixed(1)}°C!`;
      gebi('note-temp').style.color= "rgb(255, 115, 0)";
      gebi('error').innerHTML = 'tvPlayer is hot - turn off'
    } else {
      gebi('note-temp').innerHTML = `${temp.toFixed(1)}°C`;
      gebi('note-temp').style.color= "inherit";
      gebi('error').innerHTML = ''
    }
  }

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
  if (lastSettings != md5(JSON.stringify(data))) {
    lastSettings = md5(JSON.stringify(data));
    // update currentfile?
    // SET SOME GUI ELEMENTS OF GENERAL_SETTINGS
    let settings = data.settings.general_settings;
    gebi('note-brightness').innerHTML = parseInt((settings.brightness+100)/2);  // Range from -100 - 100
    gebi('note-contrast').innerHTML = parseInt((settings.contrast+100)/2);  // Range from -100 - 100
    gebi('note-saturation').innerHTML = parseInt((settings.saturation+100)/2);  // Range from -100 - 100

    gebi('note-show_tv_gui').innerHTML = settings.show_tv_gui ? "On" : "Off";
    gebi('note-white_noise_on_channel_change').innerHTML = settings.show_whitenoise_channel_change ? "On" : "Off";
    gebi('note-cycle_green_screen').innerHTML = `<img src="assets/screens/green${settings.current_green_index}.png">`;
    gebi('note-cycle_white_noise').innerHTML = `<img src="assets/screens/noise${settings.white_noise_index}.png">`;

    // GENERAL
    gebi('note-zoom').innerHTML = ((settings.zoom_level+1)*100).toFixed(0);  // 0 = normal
    gebi('note-pan').innerHTML = `X ${(settings.pan_offsets.x*100).toFixed(1)} / Y ${(settings.pan_offsets.y*100).toFixed(1)}`;  // 0.0/0.0
    gebi('note-volume').innerHTML = settings.volume;  // 0 to 100
    
    // PER VIDEO FILE
    let fileSettings = data.settings.file_dependent_settings;
    if(fileSettings[currentFile.filename]) {
      let thisVideo = fileSettings[currentFile.filename];
      gebi('note-speed').innerHTML = `${thisVideo.video_speeds.toFixed(2)}&times;`;  // 1 = normal
      let fitting_modes = ['contain', 'stretch', 'cover']
      gebi('note-videoFitting').innerHTML = `<img src="assets/icons/fitting-${fitting_modes[thisVideo.video_fittings]}.svg"><br>${fitting_modes[thisVideo.video_fittings]}`
      if(thisVideo.inpoints > 0) {
        show('inpoint');
        gebi('inpoint').style.left = `${(thisVideo.inpoints / parseFloat(gebi("timeline").max)) * 100}%`;
        gebi('note-inpoint').innerHTML = secondsToTimecode(thisVideo.inpoints);
      } else {
        hide('inpoint');
        gebi('note-inpoint').innerHTML = "-";
      }
      if(thisVideo.outpoints > 0) {
        show('outpoint');
        gebi('outpoint').style.left = `${(thisVideo.outpoints / parseFloat(gebi("timeline").max)) * 100}%`;
        gebi('note-outpoint').innerHTML = secondsToTimecode(thisVideo.outpoints);
      } else {
        hide('outpoint');
        gebi('note-outpoint').innerHTML = "-";
      }
    }
  }

  // HANDLE FILE LIST
  const filelistContainer = gebi("filelist");
  filelistContainer.innerHTML = ""; // Clear previous entries

  gebi('filelistLength').innerHTML = `${data.filelist.length} ${data.filelist.length == 1 ? 'file' : 'files'}`;

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
      data.basename = name.basename;
      data.suffix = name.suffix;
      data.filename = `${name.basename}.${name.suffix}`;
      gebi("currentFile").innerHTML = `#${data.tvChannel + 1} - ${data.basename}<span class='grey'>.${data.suffix}</span>`;
      let timeline = gebi("timeline");
      if(data.duration>1){  // somehow, images have a duration of 1
        show("timeline", "togglePlayBtn", "abLoop");
        showFlex("seeking", "speed", "speedNoteRow");
        if(!blockTimerUpdate) {
          timeline.value=data.position;
          timeline.max=data.duration;
          gebi("timecode").innerHTML = `${secondsToTimecode(data.position)}/${secondsToTimecode(data.duration)}`;
        }
      } else {
        hide("timeline", "seeking", "speed", "speedNoteRow", "togglePlayBtn", "abLoop");
        gebi("timecode").innerHTML = "";
      }
      gebi("display").style.backgroundImage = `url("thumbnails/${data.basename}.png")`;
    } else {
      gebi("currentFile").innerHTML = "No current file. Insert USB with <a href='#' onclick='showValidFiles()'>valid video or image files</a>.";
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

function setToWait(id) {
  if(gebi(id).src) {
    gebi(id).src = 'assets/icons/timer-sand.svg';
  } else {
    const img = document.createElement("img");
    img.className = "wait";
    img.src = 'assets/icons/timer-sand.svg';
    gebi(id).replaceChildren(img);
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

function startPan(e, axis, value) {
  if (e) e.preventDefault(); // prevent touch scrolling
  setToWait('note-pan'); 
  sendCommand({ cmd: 'pan', value: [value, axis] }, false, true);
  panInterval = setInterval(() => {
    sendCommand({ cmd: 'pan', value: [value, axis] }, false, true);
  }, 75);
}

function stopPan() {
  clearInterval(panInterval);
}

function logging(text) {
  console.log(text);
  const consoleDiv = document.getElementById("console");

  const newLine = document.createElement("div");
  newLine.innerHTML = text;
  consoleDiv.prepend("\n");
  consoleDiv.prepend(newLine); // adds to the top

  // limit to 100 lines
  while (consoleDiv.children.length > 333) {
    consoleDiv.removeChild(consoleDiv.lastChild);
  }
}

function sendConsole() {
  alert("Make shure you have internet access before sending");
  window.location = `mailto:info@fluescher.ch?body=${encodeURI(gebi('console').textContent)}`
}

function showValidFiles() {
  alert("Valid video files are: .mp4, .mkv, .avi, .mxf, .m4v or .mov.\nValid image files are: .jpg, .jpeg, .png, .gif, .tiff or .bmp.\n\nBest practice is .mp4 container with a h264 codec.\n\nDo NOT use 4K or other heavy files, they will not play smoothly.\n\nNote that .png files do not work when it has a color mode of “indexed colors”.")
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

function showFlex(id) {
	for(i=0; i< arguments.length; i++) { 
		document.getElementById(arguments[i]).style.display = 'flex';
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
