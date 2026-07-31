let client;
let hasReceivedSettings = false;
let raspi_available = false;
let raspi_available_timer = null;
let raspi_alert_timer = null;
let shownCriticalHeatAlert = false;
let settings = {};
let lastThumbnail = "";
let lastPlaystate = "";
let lastSettings = "";
let lastCurrentVideoState = ""
let currentFile = "";
let blockTimerUpdate = false;
// let fill_color_active = false;
let tvChannel = 0;
let thumbnailMtimes = {};
const ALERT_THROTTLE_MS = 222;
let lastAlertTime = 0;

function init() {
  logging("start!");
  const mqttHost = location.hostname; // returns "10.3.141.1"
  logging(mqttHost);
  try {
    client = mqtt.connect(`ws://${mqttHost}:9001`);
  } catch (e) {
    console.log(e);
    gebi('error').innerHTML = 'Cannot connect to websocket - system is running?';
  }
  logging(`ws://${mqttHost}:9001`);
  logging(`scripts.js loaded`);
  logging(`mqtt: ` + typeof mqtt);
  logging(`Using MQTT host: ` + (mqttHost ? mqttHost : 'error'));

  client.on("error", (err) => {
    logging(`MQTT connection error: ${err.message}`);
  });

  client.on("connect", () => {
    logging("Connected to MQTT broker.");
    client.subscribe("tvPlayer/#");
    sendCommand({ cmd: "give_settings" }, true);

    // If user retries update, catch it, send command again and redirect
    const params = new URLSearchParams(window.location.search);
    if (params.get("update") === "true") {
      console.log("Try update again, auto reddirecting..")
      sendCommand({ cmd: "update" }, true);
      window.location.href = "update.html";
    }
  });

  client.on("message", (topic, message) => {
    const data = JSON.parse(message.toString());
    if (topic === "tvPlayer/heartbeat") {
      logging(`Received heartbeat`, false);
      handleHeartbeat(data.temp ? data.temp : false);

    } else if (topic === "tvPlayer/settings") {
      logging(`Received settings`, false);
      hasReceivedSettings = true;
      handleSettings(data.payload);
      handleHeartbeat();  // Treat as heartbeat because it comes every second

    } else if (topic === "tvPlayer/command") {
      logging(`Acknowledged command: <pre>${JSON.stringify(data)}</pre>`, false);

    } else {
      logging(
        `Received message on ${topic}: <pre>${JSON.stringify(data)}</pre>`,
        false
      );
      if (data.command == "createThumbnails") {
        gebi("filelist").innerHTML = "Creating thumbnails..";

      } else if (data.command == "error") {
        logging(data.payload);
        alert(`Oh snap, the tvPlayer crashed.\nTrying to restart program.\n\nIf this persists, reboot the tvPlayer!\n\nError:\n${data.payload.error}\n\nTraceback:\n${data.payload.traceback}`);

      }
    }
  });

  requestSettingsLoop();

  window.addEventListener("blur", () => {
    logging("Window lost focus — clearing timeouts");
    clearTimeout(raspi_available_timer);
  });

  window.addEventListener("focus", () => {
    logging("Window gained focus — clearing timeouts");
    clearTimeout(raspi_available_timer);
  });

  displayVersionUpdateDate();
  setupTriggers();
}

function maybeAlertUnavailable() {
  const now = Date.now();
  if (now - lastAlertTime > ALERT_THROTTLE_MS) {
    alert("Cannot connect to tvPlayer. Go closer.");
    lastAlertTime = now;
  }
}

function sendCommand(data, ignore_availability=false, giveFeedback=false) {
  if (!raspi_available && !ignore_availability) {
    maybeAlertUnavailable();
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

function showTemperatureData(temp) {
  // Set CPU temp
  if(temp > 90) {
    gebi('body').style.backgroundColor = 'rgb(255, 68, 0)';
    gebi('note-temp').innerHTML = `!!! ${temp.toFixed(1)}°C !!!`;
    gebi('note-temp').style.color= "rgb(255, 68, 0)";
    gebi('error').innerHTML = `<h2 style="margin:0">${temp.toFixed(1)}°C - TURN OFF NOW</h2>`;
    if(!shownCriticalHeatAlert) {
      alert('tvPlayer is INCREDIBLY hot - turn off NOW!');
      alert(`I'm serious. Its ${temp.toFixed(1)}°C, max before damage is 85°C.`);
      shownCriticalHeatAlert = true;
    }
  } else if(temp > 85) {
    gebi('note-temp').innerHTML = `!!! ${temp.toFixed(1)}°C !!!`;
    gebi('note-temp').style.color= "rgb(255, 68, 0)";
    gebi('error').innerHTML = `tvPlayer is VERY hot - <strong>${temp.toFixed(1)}°C</strong> - turn off NOW - CPU throttling`;
    gebi('body').style.backgroundColor = '#121212'; // Revert red background if okay-ish
  } else if(temp >= 80) {
    gebi('note-temp').innerHTML = `${temp.toFixed(1)}°C!`;
    gebi('note-temp').style.color= "rgb(255, 115, 0)";
    gebi('error').innerHTML = `tvPlayer is hot - <strong>${temp.toFixed(1)}°C</strong> - cool down`;
    gebi('body').style.backgroundColor = '#121212'; // Revert red background if okay-ish
  } else {
    gebi('note-temp').innerHTML = `${temp.toFixed(1)}°C`;
    gebi('note-temp').style.color= "inherit";
    gebi('error').innerHTML = '';
    gebi('body').style.backgroundColor = '#121212'; // Revert red background if okay-ish
    shownCriticalHeatAlert = false;  // Show next time when the temp reaches a lot of deg
  }
}

function handleHeartbeat(temp=false) {
  raspi_available = true;
  clearTimeout(raspi_available_timer);
  clearTimeout(raspi_alert_timer);
  if(temp !== false) {
    showTemperatureData(temp);
  }

  // Add green heartbeat class
  gebi("heartbeat").classList.add("active");

  // Remove green class after 1s (+ CSS fadeout)
  setTimeout(() => {
    gebi("heartbeat").classList.remove("active");
  }, 1000);

  // Mark Raspberry Pi unavailable after 8 seconds without a heartbeat
  raspi_available_timer = setTimeout(() => {
    logging("CONNECTION LOST AFTER 8s");
    raspi_available = false;
  }, 8000);

  // Warn once after 24 seconds without a heartbeat
  raspi_alert_timer = setTimeout(() => {
    alert("Connection lost after 24s. Go closer or turn tvPlayer on.");
  }, 24000);
}

function showState() {
  if(raspi_available) {
    alert("The system is currently up and running");
  } else {
    alert("The system is currently not available. (Re-) start the tvPlayer or go closer until the icon turns green.\n\nAlso re-check if you're in the correct wifi! Should be: 'tvPlayer'!");
  }
}

function handleSettings(data) {
  handleState(data.state, data.settings.general_settings.fill_color_active ? {
    "fill_color_active": true,
    "fill_color_index": data.settings.general_settings.fill_color_index,
    "fill_color_type": data.settings.general_settings.fill_color_type
  } : false)

  // remove so lastSettings is not dependent on the state of ..state
  delete data.state

  if (lastSettings != md5(JSON.stringify(data))) {
    // update currentfile
    lastSettings = md5(JSON.stringify(data));

    // SET SOME GUI ELEMENTS OF GENERAL_SETTINGS
    let settings = data.settings.general_settings;
    gebi('note-brightness').innerHTML = parseInt((settings.brightness+100)/2);  // Range from -100 - 100
    gebi('note-contrast').innerHTML = parseInt((settings.contrast+100)/2);  // Range from -100 - 100
    gebi('note-saturation').innerHTML = parseInt((settings.saturation+100)/2);  // Range from -100 - 100
    if(settings.show_tv_gui) {
      gebi('note-show_tv_gui').innerHTML = "On";
      show('channel_number');
      gebi('channel_number').src=`assets/channel_numbers/${tvChannel}.png`;
    } else {
      gebi('note-show_tv_gui').innerHTML = "Off";
      hide('channel_number');
    }
    gebi('note-white_noise_on_channel_change').innerHTML = settings.show_whitenoise_channel_change ? "On" : "Off";

    // Fill color previews
    /* let enabled_green = settings.fill_color_active && settings.fill_color_type == 'green';
    let enabled_noise = settings.fill_color_active && settings.fill_color_type == 'noise';
    class="${enabled_green ? '' : 'disabled'}" 
    class="${enabled_noise ? '' : 'disabled'}"  */
    gebi('note-cycle_green_screen').innerHTML = `<img src="assets/fill_colors/green${settings.fill_color_index['green']+1}.png" title="Fill Color with markers # ${settings.fill_color_index['green']+1}">`;
    gebi('note-cycle_white_noise').innerHTML = `<img src="assets/fill_colors/noise${settings.fill_color_index['noise']+1}.png" title="Fill Color: Noise # ${settings.fill_color_index['noise']+1} without markers">`;

    // GENERAL
    gebi('note-zoom').innerHTML = ((settings.zoom_level+1)*100).toFixed(0)+"%";  // 0 = normal
    gebi('note-pan-x').innerHTML = (settings.pan_offsets.x*100).toFixed(1);
    gebi('note-pan-y').innerHTML = (settings.pan_offsets.y*100).toFixed(1);
    gebi('note-volume').innerHTML = settings.volume+"%";  // 0 to 100

    // HANDLE FILE LIST
    const filelistContainer = gebi("filelist");
    filelistContainer.innerHTML = ""; // Clear previous entries

    gebi('filelistLength').innerHTML = `${data.filelist.length} ${data.filelist.length == 1 ? 'file' : 'files'}`;

    if (data.filelist.length == 0) {
      filelistContainer.innerHTML = "No <a href='#' onclick='showValidFiles()'>valid files</a> on USB or no USB plugged.";
      return;
    }

    thumbnailMtimes = {};
    data.filelist.forEach((filepath, index) => {
      const filename = filepath.split("/").pop();
      const dotIndex = filename.lastIndexOf(".");
      const basename = filename.slice(0, dotIndex);
      const suffix = filename.slice(dotIndex + 1);
      const mtime = data.filelist_mtimes ? data.filelist_mtimes[index] : 0;
      thumbnailMtimes[filename] = mtime;

      const container = document.createElement("div");
      container.classList.add("button-row");
      const button = document.createElement("button");
      button.className = "filelistButton";
      button.onclick = () => sendCommand({ cmd: "go_to_channel", value: index }, false, true);

      const img = document.createElement("img");
      img.className = "thumbnails";
      img.src = `./thumbnails/${basename}_${mtime}.png`;

      const channelNumber = document.createElement("img");
      channelNumber.src = `./assets/channel_numbers/${index + 1}.png`;
      channelNumber.style.height = "1.25em";
      channelNumber.style.paddingRight = "0.5em";
      const label = document.createTextNode(`${basename}`);
      const span = document.createElement("span");
      span.className = "grey";
      span.textContent = `.${suffix}`;

      button.appendChild(img);
      const divText = document.createElement("div");
      divText.appendChild(channelNumber);
      divText.appendChild(label);
      divText.appendChild(span);
      button.appendChild(divText);
      container.appendChild(button);
      filelistContainer.appendChild(container);
    });
    if(data.settings.filelist_ignored.length) {
      gebi("filelistIgnored").innerHTML = `${data.settings.filelist_ignored.length} ignored files or folders on USB (?)`;
      gebi("filelistIgnored").onclick = () => alert(`Some files where ignored. Check the specifications if you need them to play:\n\n${data.settings.filelist_ignored.join('\n')}`);
    } else {
      gebi("filelistIgnored").innerHTML = ``;
    }
  }
}

function handleState(data, fillColor=false) {
  // Check if data changed, if yes, update GUI
  if (lastPlaystate != md5(JSON.stringify(data))) {
    lastPlaystate = md5(JSON.stringify(data));
    // console.log("handleState", data, fillColor);

    // FIXME: WHEN REPLUGGING USB:
    // scripts.js?v=250611c:262 Uncaught (in promise) TypeError: Cannot read properties of undefined (reading 'tvChannel')
    tvChannel = data.tvChannel;
    if (data.isPlaying) {
      gebi("playstate").src = "./assets/icons/pause.svg";
    } else {
      gebi("playstate").src = "./assets/icons/play.svg";
    }

    if (data.currentFileName.length > 0 && !fillColor) {
      let name = splitFileName(data.currentFileName);
      gebi("currentFile").innerHTML = `#${data.tvChannel + 1} - ${name.basename}<span class='grey'>.${name.suffix}</span>`;
      let timeline = gebi("timeline");
      if(data.duration > 1){  // somehow, images have a duration of 1
        show("timeline", "togglePlayBtn", "abLoop");
        showFlex("seeking", "speed", "speedNoteRow");
        if(!blockTimerUpdate) {
          timeline.value=data.position;
          timeline.max=data.duration;
          gebi("timecode").innerHTML = `${secondsToTimecode(data.position, {"showFrames": false})}/${secondsToTimecode(data.duration, {"showFrames": false})}`;
        }
      } else {
        hide("timeline", "seeking", "speed", "speedNoteRow", "togglePlayBtn", "abLoop");
        gebi("timecode").innerHTML = "";
      }
      const mtime = thumbnailMtimes[data.currentFileName] || 0;
      gebi("display").style.backgroundImage = `url("thumbnails/${name.basename}_${mtime}.png")`;
    } else if(fillColor) {
      gebi("currentFile").innerHTML = `Showing a fill color with markers # ${(fillColor.fill_color_index[fillColor.fill_color_type])+1} in fullscreen.`;
      gebi("display").style.backgroundImage = `url("assets/fill_colors/${fillColor.fill_color_type}${(fillColor.fill_color_index[fillColor.fill_color_type])+1}.png")`;
    } else {
      gebi("currentFile").innerHTML = "No current file. Insert USB with <a href='#' onclick='showValidFiles()'>valid video or image files</a>.";
      gebi("display").style.backgroundImage = ``;
    }

    // Only update video-specific settings (fitting, inpoints, etc) this if they or the file changed
    let thisVideo = data.currentFileSettings;
    let currentCurrentVideoState = md5(data.currentFileName + JSON.stringify(data.currentFileSettings));
    if(thisVideo && currentCurrentVideoState != lastCurrentVideoState) {
      console.log("fitting, inpoints, etc changed")
      lastCurrentVideoState = md5(data.currentFileName + JSON.stringify(data.currentFileSettings));

      let fitting_modes = ['contain', 'stretch', 'cover']
      if(Object.keys(thisVideo).length) {  // Greenscreen etc has no values here
        gebi('note-speed').innerHTML = `${thisVideo.video_speeds.toFixed(2)}&times;`;  // 1 = normal
        gebi('note-videoFitting').innerHTML = `<img src="assets/icons/fitting-${fitting_modes[thisVideo.video_fittings]}.svg"><br>${fitting_modes[thisVideo.video_fittings]}`
      } else {
        gebi('note-speed').innerHTML = `1.00&times;`;
        gebi('note-videoFitting').innerHTML = `[no fitting modes for color overlays]`
      }

      if(thisVideo.inpoints && thisVideo.inpoints > 0) {
        show('inpoint');
        gebi('inpoint').style.left = `${(thisVideo.inpoints / parseFloat(gebi("timeline").max)) * 100}%`;
        gebi('note-inpoint').innerHTML = secondsToTimecode(thisVideo.inpoints);
      } else {
        hide('inpoint');
        gebi('note-inpoint').innerHTML = "-";
      }
      if(thisVideo.outpoints && thisVideo.outpoints > 0) {
        show('outpoint');
        gebi('outpoint').style.left = `${(thisVideo.outpoints / parseFloat(gebi("timeline").max)) * 100}%`;
        gebi('note-outpoint').innerHTML = secondsToTimecode(thisVideo.outpoints);
      } else {
        hide('outpoint');
        gebi('note-outpoint').innerHTML = "-";
      }
    }

    currentFile = data.currentFileName;  /// ???? needed
  }
}

/* function handleFillColor(data) {
  // FIXME: DOES NOT PROPERLY WORK YET
  let display = gebi("display");
  if(data.show) {
    fill_color_active = true;
    lastThumbnail = display.style.backgroundImage;
    display.style.backgroundImage = `url('assets/screens/${data.type}${data.index ? data.index : ''}.png')`
  } else {
    fill_color_active = false;
    display.style.backgroundImage = lastThumbnail;
  }
} */

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

function secondsToTimecode(seconds, { fps = 25, showFrames = true } = {}) {
  const totalSeconds = Math.floor(seconds);
  const frames = Math.round((seconds - totalSeconds) * fps);

  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60)
    .toString()
    .padStart(2, "0");
  let secs = (totalSeconds % 60).toString().padStart(2, "0");
  const frameStr = frames.toString().padStart(2, "0");
  
  if (showFrames) {
    secs = `${secs}.${frameStr}`;
  }

  if (hours > 0) {
    return `${hours.toString().padStart(2, "0")}:${minutes}:${secs}`;
  } else {
    return `${minutes}:${secs}`;
  }
}

function logging(text, showInDevConsole=true) {
  if(showInDevConsole) console.log(text);
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
  alert("Valid video files are: .mp4, .mkv, .avi, .mxf, .m4v or .mov.\nValid image files are: .jpg, .jpeg, .png, .gif, .tiff or .bmp.\n\nBest practice is .mp4 container with a h264 codec.\n\nDo NOT use 4K or other heavy files, they will not play smoothly.\n\nNote that .png files do not work when it has a color mode of “indexed colors”.\n\nBe sure to use an EXFat USB drive, not a MAC formatted one!")
}

async function displayVersionUpdateDate() {
  const data = await (await fetch('./update_metadata.json?v=' + Date.now())).json();

  gebi('zip_hash').textContent = data.zip_hash.slice(0, 7);

  const d = new Date(data.installed_at).toLocaleString('de-CH', {
    timeZone: 'Europe/Zurich',
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
    hour12: false
  });

  const [date, time] = d.split(', ');
  gebi('installed_at').textContent = `${date} - ${time}`;
}

// Fully generic funcMap using Proxy
const funcMap = new Proxy({}, {
  get: (_, funcName) => (...args) => {
    const value = args.length === 1 ? args[0] : args;
    sendCommand({ cmd: funcName, value }, false, true);
  }
});

// Robust press-and-hold with state machine:
//   idle → pointerdown → pending
//   pending → release < HOLD_DELAY → fire once (tap) → idle
//   pending → HOLD_DELAY elapsed → fire once + start repeating → holding
//   pending → move > MOVE_THRESHOLD → cancelled → idle
//   holding → release/cancel/blur → idle
const HOLD_DELAY = 222;
const MOVE_THRESHOLD = 10; // CSS pixels

function setupTriggers() {
  document.querySelectorAll('[data-trigger]').forEach(el => {
    const funcName = el.dataset.func;
    const args = JSON.parse(el.dataset.args);
    const label = "note-" + funcName;
    const interval = 75;
    const fn = funcMap[funcName];
    const fnArgs = Array.isArray(args) ? args : [args];
    const hasLabel = !!gebi(label);

    // Per-button state
    let state = 'idle'; // 'idle' | 'pending' | 'holding'
    let holdTimer = null;
    let repeatInterval = null;
    let startX = 0;
    let startY = 0;

    function fire() {
      if (hasLabel) setToWait(label);
      fn(...fnArgs);
    }

    function reset() {
      state = 'idle';
      clearTimeout(holdTimer);
      clearInterval(repeatInterval);
      holdTimer = null;
      repeatInterval = null;
    }

    function onPointerDown(e) {
      if (state !== 'idle') return; // ignore overlapping sequences
      e.preventDefault();
      state = 'pending';
      startX = e.clientX;
      startY = e.clientY;

      if (el.setPointerCapture) {
        try { el.setPointerCapture(e.pointerId); } catch(_) {}
      }

      holdTimer = setTimeout(() => {
        if (state !== 'pending') return;
        state = 'holding';
        fire();
        repeatInterval = setInterval(fire, interval);
      }, HOLD_DELAY);
    }

    function onPointerMove(e) {
      if (state !== 'pending') return;
      const dx = e.clientX - startX;
      const dy = e.clientY - startY;
      if (dx * dx + dy * dy > MOVE_THRESHOLD * MOVE_THRESHOLD) {
        reset(); // scroll/drag detected — cancel entirely
      }
    }

    function onPointerUp(e) {
      if (state === 'pending') {
        // Released before hold threshold — treat as tap
        reset();
        fire();
      } else if (state === 'holding') {
        reset();
      }
      // If idle, nothing to do
    }

    function onCancel() {
      reset();
    }

    el.addEventListener('pointerdown', onPointerDown);
    el.addEventListener('pointermove', onPointerMove);
    el.addEventListener('pointerup', onPointerUp);
    el.addEventListener('pointercancel', onCancel);
    el.addEventListener('lostpointercapture', onCancel);

    // Emergency stops: window blur / page hidden
    window.addEventListener('blur', onCancel);
    document.addEventListener('visibilitychange', () => {
      if (document.hidden) onCancel();
    });

    // Prevent context menu on long-press (mobile)
    el.addEventListener('contextmenu', e => e.preventDefault());

    // Disable touch-action so pointer events work properly on mobile
    el.style.touchAction = 'none';
  });
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
