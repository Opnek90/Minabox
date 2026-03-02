#!/usr/bin/env python3
import Adafruit_SSD1306
from PIL import Image, ImageDraw, ImageFont

# Display initialisieren (128x64, I2C Bus 1)
disp = Adafruit_SSD1306.SSD1306_128_64(rst=None, i2c_bus=1, gpio=1)
disp.begin()
disp.clear()
disp.display()

# Text zeichnen
width = disp.width
height = disp.height
img = Image.new('1', (width, height))
draw = ImageDraw.Draw(img)
font = ImageFont.load_default()  # Oder truetype-Font laden

draw.text((0, 0), "Hallo Welt!", font=font, fill=255)
draw.text((0, 20), "RPi OLED OK!", font=font, fill=255)

disp.image(img)
disp.display()
print("OLED läuft!")

import time
while True:
    draw.rectangle((0, 0, width, height), outline=0, fill=0)  # Clear
    draw.text((0, 0), f"Uhr: {time.strftime('%H:%M:%S')}", fill=255)
    disp.image(img)
    disp.display()
    time.sleep(1)
