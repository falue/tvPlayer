# tvPlayer as digital props for film and TV
WIP.

## things to do to get this up and running
1. run the install `sudo bash install.sh` script to:
    - apt-get update
    - install dependencies
    - run `python3 tvPlayer.py` on autostart
    - disable window "removable medium is inserted" [BUG!]
    - create a desktop shortcut to the program
```
bash install.sh
```

2. disable (move/remove) autostart file for Eddy-G (if available) from folder `~/.config/autostart`

#### old notes
2. ~~on the desktop, open any folder, go to `edit` > `preferences` > `volume management`~~
3. ~~something something LXDE autostart script `nano ~/.config/lxsession/LXDE-pi/autostart`~~
3. ~~install script takes care of autostart and creates a file here: `~/.config/autostart`~~


## MPV player: Playable media
The media player [MPV](https://mpv.io/) ([doc wiki](https://github.com/mpv-player/mpv/wiki)) can play pretty much everything -
*however*, filename-endings are fixed to work with `.mp4`, `.mkv`, `.avi`, `.mxf` and `.mov` (case insensitive).

it uses ffmpeg to decode, so the [list of playable media](https://ffmpeg.org/general.html#Supported-File-Formats_002c-Codecs-or-Features) is huge.
According to the mpv.io website:
> File Formats: mpv supports a wide variety of media formats, including popular video files (e.g., MP4, MKV), audio codecs (e.g., AAC, MP3), and subtitles.

Some cherry picked examples:
- Containers: MP4, MKV, AVI, WebM, OGG, FLV, and more.
- Video Codecs: H.264, HEVC, VP8, VP9, AV1, MPEG-4, MPEG-2, and others.
- Audio Codecs: AAC, MP3, Vorbis, FLAC, Opus, AC3, and DTS.
Subtitle Formats: SRT, ASS, SSA, VTT, and embedded subtitle tracks in containers like MKV.

Manually tested:
- [x] `.mp4` MPEG-4 AAC, H264
- [x] `.avi` MPEG-4 mp3
- [x] `.mkv` h264, yuv420p
- [x] `.mxf` mpeg2video (4:2:2), yuv422p
- [x] `.mp4` HEVC, H265
- [x] `.mov` H264
- [x] `.mkv` "4k UHD" h264 yuv420p works (but stuttering on raspberry pi4 @8gb) 

## Also works with images
Filetypes for images: `.png`, `.gif`, `.tiff`, `.bmp`
> *NOTICE:* Does ***not*** work with `.jpg`!

## Keyboard controls

| Keypress        | Action                                                 | Note |
| --------------- | ------------------------------------------------------ | ---- |
| UP              | next channel (next file)                               |      |
| DOWN            | prev channel (next file)                               |      |
| LEFT            | jump -5 seconds                                        |      |
| RIGHT           | jump 5 seconds                                         |      |
| LEFT and SHIFT  | pause and one frame backwards                          |      |
| RIGHT and SHIFT | pause and one frame forwards                           |      |
| p *or* space    | toggle play / pause                                    |      |
| ESC             | toggle fullscreen                                      |      |
| q               | shutdown raspberry pi                                  |      |
| b               | toggle black screen                                    |      |
| c               | video fitting (contain, stretch or cover)              |      |
| i               | set inpoint (where the file starts to play)            |      |
| I (i and SHIFT) | clear inpoint on this video                            |      |
| a               | toggle tv-animations (*pause in between channel changes*, *channel number*, *vol bars*) |      |
| w               | if tv-animations: toggle color of pause in between channel changes: *white noise* or *black*  |      |
| ,               | reduce video brightness by 5%                          |      |
| .               | increase video brightness by 5%                        |      |
| +               | reduce volume by 10%                                   |      |
| -               | increase volume by 10%                                 |      |
| number          | go to channel nr                                       |      |
| else            | ignored                                                |      |



## SSH stuff
scp ./tvPlayer/* dp@192.168.1.209:~/Desktop/tvPlayer

ssh dp@192.168.1.209 'DISPLAY=:0 python ~/Desktop/tvPlayer/tvPlayer.py'

### Copy folder to raspi via ssh & run script on raspi with script and output THERE but log HERE
```
scp -r ./tvPlayer/* dp@192.168.1.209:~/Desktop/tvPlayer && ssh dp@192.168.1.209 'DISPLAY=:0 python -u ~/Desktop/tvPlayer/tvPlayer.py'
```