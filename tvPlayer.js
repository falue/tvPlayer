const { exec } = require('child_process');
const fs = require('fs');
const path = require('path');

let tv_animations = true;
let tv_white_noise_on_channel_change = true;
let tv_channel = 0;
let tv_channel_offset = 4;  // Only for displaying number on screen
let playing = false;
let filelist = [];
let inpoints = [];

// Function to update files from any USB drive
function updateFilesFromUSB() {
    // Check for USB drive (mounted at '/media/pi' on RPi)
    const usbPath = '/media/pi/';
    try {
        let devices = fs.readdirSync(usbPath);
        if (devices.length > 0) {
            // Read the root folder of each connected USB device
            filelist = [];
            inpoints = [];
            devices.forEach(device => {
                let files = fs.readdirSync(path.join(usbPath, device));
                files.forEach(file => {
                    if (file.endsWith('.mp4') || file.endsWith('.mkv')) {
                        filelist.push(path.join(usbPath, device, file));
                        inpoints.push(0); // Initial inpoint at 0
                    }
                });
            });
        } else {
            filelist = [];
            inpoints = [];
        }
    } catch (err) {
        console.error('Error accessing USB drive: ', err);
        filelist = [];
        inpoints = [];
    }
}

// Function to handle keypresses
function checkKeypresses() {
    // You can bind keyboard events using Electron's globalShortcut API or through direct key events
    document.onkeydown = function (e) {
        switch (e.code) {
            case 'ArrowRight':
                nextChannel();
                break;
            case 'ArrowLeft':
                prevChannel();
                break;
            case 'Space':
            case 'KeyP':
                togglePlay();
                break;
            case 'Escape':
                toggleFullscreen();
                break;
            case 'KeyI':
                setInpoint();
                break;
            default:
                if (!isNaN(e.key)) {
                    goToChannel(parseInt(e.key));
                }
        }
    };
}

// Previous Channel function
function prevChannel() {
    tv_channel--;
    goToChannel(tv_channel);
}

// Next Channel function
function nextChannel() {
    tv_channel++;
    goToChannel(tv_channel);
}

// Function to go to a specific channel
function goToChannel(number) {
    // Loop around channel
    if (number >= filelist.length) {
        number = 0;
    }
    if (number < 0) {
        number = filelist.length - 1;
    }

    // TV animations (white noise or blank screen)
    if (tv_animations) {
        if (tv_white_noise_on_channel_change) {
            showWhiteNoise(200);  // 200ms
        } else {
            showBlankScreen(200);  // 200ms
        }
        // Show the channel number on the screen
        showChannelNumber(number + tv_channel_offset);
    }

    playVideoGaplessLoopingFullscreen(filelist[number], inpoints[number]);
}

// Play video in a gapless looping mode using MPV
function playVideoGaplessLoopingFullscreen(file, inpoint = 0) {
    playing = true;
    exec(`mpv --loop-file --start=${inpoint} --fs ${file}`, (error, stdout, stderr) => {
        if (error) {
            console.error(`Error playing video: ${error.message}`);
        }
    });
}

// Toggle fullscreen using Electron API
function toggleFullscreen() {
    const { remote } = require('electron');
    let win = remote.getCurrentWindow();
    win.setFullScreen(!win.isFullScreen());
}

// Toggle play/pause
function togglePlay() {
    exec('mpv --input-ipc-server=/tmp/mpv-socket pause', (error, stdout, stderr) => {
        if (error) {
            console.error(`Error toggling play/pause: ${error.message}`);
        }
    });
}

// Show white noise (using a blank video as a placeholder)
function showWhiteNoise(duration) {
    exec(`mpv --fs white_noise.mp4 --pause --end=${duration}`, (error, stdout, stderr) => {
        if (error) {
            console.error(`Error showing white noise: ${error.message}`);
        }
    });
}

// Show blank screen
function showBlankScreen(duration) {
    exec(`mpv --fs blank.mp4 --pause --end=${duration}`, (error, stdout, stderr) => {
        if (error) {
            console.error(`Error showing blank screen: ${error.message}`);
        }
    });
}

// Display the channel number on screen (e.g., overlay image)
function showChannelNumber(number) {
    exec(`mpv --fs channel_${number}.png --pause --end=1`, (error, stdout, stderr) => {
        if (error) {
            console.error(`Error displaying channel number: ${error.message}`);
        }
    });
}

// Update filelist and inpoints if files change
function updateInpoints() {
    inpoints = Array(filelist.length).fill(0);
}

// Main loop
function main() {
    toggleFullscreen();
    showBlankScreen(0);
    updateFilesFromUSB();

    setInterval(() => {
        checkKeypresses();
        let currentFilelist = updateFilesFromUSB();
        if (filelist !== currentFilelist) {
            updateInpoints();
        }
        if (filelist.length === 0) {
            if (tv_animations) {
                showWhiteNoise(0);
            } else {
                showBlankScreen(0);
            }
        } else if (!playing) {
            goToChannel(0);
        }
    }, 1000);
}

// Run the main function on startup
main();
