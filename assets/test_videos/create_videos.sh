#!/bin/bash

# Loop to create 13pcs of 5s videos
for i in {00..12}
do
  # Generate the number text (e.g., 01, 02, etc.)
  number=$(printf "%02d" $i)
  #filename=$i
  filename=$(printf "%02d" $i)
  
  # Create the video with white noise background and centered number
  ffmpeg -f lavfi -i nullsrc=s=1024x576 -f lavfi -i "aevalsrc=-2+random(0)" -filter_complex \
  "[0:v]geq=random(1)*255:128:128,drawtext=fontfile=./W95FA.ttf:text='${number}':x=(w-text_w)/2:y=(h-text_h)/2:fontsize=200:fontcolor=red" \
  -t 5 -shortest "${filename}.mp4"
done
