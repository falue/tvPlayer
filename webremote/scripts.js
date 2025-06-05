// Wait for the DOM to be fully loaded before executing code
document.addEventListener('DOMContentLoaded', function() {
    // Helper function to send commands to the MPV player via the API
    function sendCommand(command, value = null) {
        fetch('/api/command', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ command: command, value: value }),
        })
        .then(response => response.json())
        .then(data => {
            document.getElementById('status').textContent = 'Command sent: ' + command;
            setTimeout(() => {
                document.getElementById('status').textContent = 'Ready';
            }, 1000);
        })
        .catch((error) => {
            document.getElementById('status').textContent = 'Error: ' + error;
        });
    }
    
    // Function to refresh the playlist display
    function refreshPlaylist() {
        fetch('/api/playlist')
        .then(response => response.json())
        .then(data => {
            const playlistElement = document.getElementById('playlist');
            playlistElement.innerHTML = '';
            
            if (data.playlist && data.playlist.length > 0) {
                data.playlist.forEach(item => {
                    const itemElement = document.createElement('div');
                    itemElement.className = 'playlist-item';
                    if (item.current) {
                        itemElement.className += ' active';
                    }
                    itemElement.textContent = item.filename;
                    
                    // Add click handler to play this item
                    itemElement.addEventListener('click', function() {
                        sendCommand('load', item.path);
                    });
                    
                    playlistElement.appendChild(itemElement);
                });
            } else {
                playlistElement.innerHTML = '<div class="playlist-item">No files in playlist</div>';
            }
        })
        .catch(error => {
            console.error('Error fetching playlist:', error);
            document.getElementById('status').textContent = 'Error fetching playlist';
        });
    }
    
    // Function to load available videos
    function loadAvailableVideos() {
        fetch('/api/videos')
        .then(response => response.json())
        .then(data => {
            const videosElement = document.getElementById('available-videos');
            if (!videosElement) return;  // Early return if element doesn't exist
            
            videosElement.innerHTML = '';
            
            if (data.videos && data.videos.length > 0) {
                data.videos.forEach(video => {
                    const videoElement = document.createElement('div');
                    videoElement.className = 'playlist-item';
                    videoElement.textContent = video.filename;
                    
                    // Add click handler to load this video
                    videoElement.addEventListener('click', function() {
                        sendCommand('load', video.path);
                        // Update status
                        document.getElementById('status').textContent = 'Loading video: ' + video.filename;
                        // Refresh playlist after a delay
                        setTimeout(refreshPlaylist, 1000);
                    });
                    
                    videosElement.appendChild(videoElement);
                });
            } else {
                videosElement.innerHTML = '<div class="playlist-item">No videos found</div>';
            }
        })
        .catch(error => {
            console.error('Error loading videos:', error);
            document.getElementById('status').textContent = 'Error loading videos';
        });
    }
    
    // Initial playlist load
    refreshPlaylist();
    
    // Load available videos
    loadAvailableVideos();
    
    // Set up button click handlers for all player controls
    document.getElementById('play-pause').addEventListener('click', function() {
        sendCommand('play_pause');
    });
    
    document.getElementById('seek-backward').addEventListener('click', function() {
        sendCommand('seek', -10);
    });
    
    document.getElementById('seek-backward-small').addEventListener('click', function() {
        sendCommand('seek', -5);
    });
    
    document.getElementById('seek-forward-small').addEventListener('click', function() {
        sendCommand('seek', 5);
    });
    
    document.getElementById('seek-forward').addEventListener('click', function() {
        sendCommand('seek', 10);
    });
    
    document.getElementById('volume-up').addEventListener('click', function() {
        sendCommand('volume', 5);
    });
    
    document.getElementById('volume-down').addEventListener('click', function() {
        sendCommand('volume', -5);
    });
    
    document.getElementById('fullscreen').addEventListener('click', function() {
        sendCommand('fullscreen');
    });
    
    document.getElementById('stop').addEventListener('click', function() {
        sendCommand('stop');
    });
    
    document.getElementById('load-video').addEventListener('click', function() {
        const videoPath = document.getElementById('video-path').value;
        if (videoPath) {
            sendCommand('load', videoPath);
            // Refresh the playlist after a short delay
            setTimeout(refreshPlaylist, 1000);
        } else {
            document.getElementById('status').textContent = 'Please enter a video path';
        }
    });
    
    // Refresh playlist button
    document.getElementById('refresh-playlist').addEventListener('click', function() {
        refreshPlaylist();
    });
    
    // Setup periodic refresh of playlist (every 10 seconds)
    setInterval(refreshPlaylist, 10000);
});
