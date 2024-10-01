## tvPlayer as digital props for film and TV
WIP.

### things to do
1. run the install script to:
    - install dependencies
    - run `python tvPlayer.py` on autostart
    - disable window "removable medium is inserted"
```
bash install.sh
```

2. disable (move/remove) autostart file for Eddy-G (if available) from folder `~/.config/autostart`

#### old notes
2. ~~on the desktop, open any folder, go to `edit` > `preferences` > `volume management`~~
3. ~~something something LXDE autostart script `nano ~/.config/lxsession/LXDE-pi/autostart`~~
3. ~~install script takes care of autostart and creates a file here: `~/.config/autostart`~~


## SSH stuff
scp ./tvPlayer/* dp@192.168.1.209:~/Desktop/tvPlayer

ssh dp@192.168.1.209 'python ~/Desktop/tvPlayer/tvPlayer.py'

ssh dp@192.168.1.209 'DISPLAY=:0 python ~/Desktop/tvPlayer/tvPlayer.py'

```
scp -r ./tvPlayer/* dp@192.168.1.209:~/Desktop/tvPlayer && ssh dp@192.168.1.209 'DISPLAY=:0 python -u ~/Desktop/tvPlayer/tvPlayer.py'
```