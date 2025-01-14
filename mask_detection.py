import os
import argparse
import cv2
import numpy as np
from tflite_runtime.interpreter import Interpreter
import colors as color
import draw_utils as draw
import time
import RPi.GPIO as GPIO
from pydub import AudioSegment
from pydub.playback import play

# Define and parse input arguments
parser = argparse.ArgumentParser()
parser.add_argument('--modeldir', help='Folder the .tflite file is located in',
                    required=True)

args = parser.parse_args()

MODEL_NAME = args.modeldir
GRAPH_NAME = 'detect.tflite'
LABELMAP_NAME = 'labelmap.txt'
min_conf_threshold = float(0.7)

# Get path to current working directory
CWD_PATH = os.getcwd()

# Path to .tflite file, which contains the model that is used for object detection
PATH_TO_CKPT = os.path.join(CWD_PATH, MODEL_NAME, GRAPH_NAME)

# Path to label map file
PATH_TO_LABELS = os.path.join(CWD_PATH, MODEL_NAME, LABELMAP_NAME)

# Load the label map
with open(PATH_TO_LABELS, 'r') as f:
    labels = [line.strip() for line in f.readlines()]

# Load the Tensorflow Lite model.
interpreter = Interpreter(model_path=PATH_TO_CKPT)
interpreter.allocate_tensors()

# Get model details
input_details = interpreter.get_input_details()
output_details = interpreter.get_output_details()
height = input_details[0]['shape'][1]
width = input_details[0]['shape'][2]

floating_model = (input_details[0]['dtype'] == np.float32)

input_mean = 127.5
input_std = 127.5



# Open video file
video = cv2.VideoCapture(0)
imW = video.get(cv2.CAP_PROP_FRAME_WIDTH)
imH = video.get(cv2.CAP_PROP_FRAME_HEIGHT)

# Initialize frame rate calculation
frame_rate_calc = 1
freq = cv2.getTickFrequency()


def inference(frame):
    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    frame_resized = cv2.resize(frame_rgb, (width, height))
    input_data = np.expand_dims(frame_resized, axis=0)

    # Normalize pixel values if using a floating model (i.e. if model is non-quantized)
    if floating_model:
        input_data = (np.float32(input_data) - input_mean) / input_std

    # Perform the actual detection by running the model with the image as input
    interpreter.set_tensor(input_details[0]['index'], input_data)
    interpreter.invoke()

    # Retrieve detection results
    boxes = interpreter.get_tensor(output_details[0]['index'])[0]  # Bounding box coordinates of detected objects
    classes = interpreter.get_tensor(output_details[1]['index'])[0]  # Class index of detected objects
    scores = interpreter.get_tensor(output_details[2]['index'])[0]  # Confidence of detected objects

    hub_color = color.white
    res = -1

    if (scores[0] > min_conf_threshold) and (scores[0] <= 1.0):


        # Draw label
        object_name = labels[int(classes[0])]  # Look up object name from "labels" array using class index
        label = '%s: %d%%' % (object_name, int(scores[0] * 100))  # Example: 'person: 72%'

        if object_name == 'no mask':
            res = 0
            hub_color = color.red
        if object_name == 'mask':
            res = 1
            hub_color = color.green
        # Get bounding box coordinates and draw box. Interpreter can return coordinates that are outside of image
        # dimensions, need to force them to be within image using max() and min()
        ymin = int(max(1, (boxes[0][0] * imH))) - 40
        xmin = int(max(1, (boxes[0][1] * imW)))
        ymax = int(min(imH, (boxes[0][2] * imH))) + 10
        xmax = int(min(imW, (boxes[0][3] * imW)))

        topLeft = xmin, ymin
        bottomRight = xmax, ymax
        draw.infoBoxLabel(frame, label, topLeft, bottomRight, hub_color)

    return res


def turn_on_light(detection_bit):  
    if detection_bit == 1:
        GPIO.output(23, GPIO.LOW)
        GPIO.output(18, GPIO.HIGH)
        play(welcome_sound)
    elif detection_bit == 0:
        GPIO.output(18, GPIO.LOW)
        GPIO.output(23, GPIO.HIGH)
        play(denied_sound)
    else:
        GPIO.output(18, GPIO.LOW)
        GPIO.output(23, GPIO.LOW)
        print('NO LIGHT')
        


# Setup LED breadboard
GPIO.setmode(GPIO.BCM)
GPIO.setup(18, GPIO.OUT)
GPIO.setup(23, GPIO.OUT)


welcome_sound = AudioSegment.from_file('media/granted.flac')
denied_sound = AudioSegment.from_file('media/denied.flac')

LED_output = -1
total_time = 0
timer_start = time.time()

while video.isOpened():
    # Start timer (for calculating frame rate)
    t1 = cv2.getTickCount()

    # Acquire frame and resize to expected shape [1xHxWx3]
    _, frame = video.read()

    # Draw frame rate in corner of frame
    cv2.putText(frame, 'FPS: {0:.2f}'.format(frame_rate_calc), (30, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, color.blue_green,
                2, cv2.LINE_AA)
    
    draw.create_hud(frame, color=color.white)


    detection_bit = inference(frame)
    if detection_bit == 0 or 1:
        if total_time > 2.0 and detection_bit != LED_output:
            LED_output = detection_bit
            turn_on_light(detection_bit)
            timer_start = time.time()

    # All the results have been drawn on the frame, so it's time to display it.
    cv2.imshow('Object detector', frame)

    # Calculate frame rate
    t2 = cv2.getTickCount()
    time1 = (t2 - t1) / freq
    frame_rate_calc = 1 / time1

    timer_end = time.time()
    total_time = timer_end - timer_start

    # Listen the inpuyr from keyboard
    k = cv2.waitKey(1)
    # Exit if press 'q' or 'Esc' from keyboard
    if k == ord('q') or k == 27:
        break

# Clean up
GPIO.cleanup()
video.release()
cv2.destroyAllWindows()
