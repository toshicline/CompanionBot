import tkinter as tk
import time

# Colors
BACKGROUND_COLOR = "#000"
FOREGROUND_COLOR = "#FFF"

# Window Setup
root = tk.Tk()
root.geometry("800x480")
root.configure(bg=BACKGROUND_COLOR)

####################################################
#                     GRAPHICS                     #
####################################################

def eyes_normal(event=None):
    canvas_eyes.delete("all")
    eye_padding = 12
    canvas_eyes.create_oval(0+eye_padding,0+eye_padding,100-eye_padding,100-eye_padding,fill=FOREGROUND_COLOR)
    canvas_eyes.create_oval(350-eye_padding,0+eye_padding,350-100+eye_padding,100-eye_padding,fill=FOREGROUND_COLOR)

def eyes_blink(return_to_normal=True,event=None):
    canvas_eyes.delete("all")
    eye_padding = 12
    canvas_eyes.create_line(0+eye_padding,50,100-eye_padding,50,capstyle="round",width=12,fill=FOREGROUND_COLOR)
    canvas_eyes.create_line(350-eye_padding,50,350-100+eye_padding,50,capstyle="round",width=12,fill=FOREGROUND_COLOR)

    if return_to_normal:
        root.after(300,eyes_normal)

def blink_loop():
    eyes_blink()
    root.after(5000,blink_loop)

def mouth_smile(event=None):
    canvas_mouth.delete("all")
    canvas_mouth.create_arc(10,-100,390,140,width=20,outline=FOREGROUND_COLOR,start=200,extent=140,style=tk.ARC)

def mouth_flat(event=None):
    canvas_mouth.delete("all")
    canvas_mouth.create_line(40,100,360,100,width=20,fill=FOREGROUND_COLOR,capstyle="round")

def mouth_speak(event=None):
    canvas_mouth.delete("all")
    canvas_mouth.create_arc(10,-160,390,140,width=20,outline=FOREGROUND_COLOR,start=200,extent=140,style=tk.CHORD)

# Eyes
canvas_eyes = tk.Canvas(root,width=350,height=100,background=BACKGROUND_COLOR,highlightthickness=0)
canvas_eyes.place(anchor="s",x=400,y=200)

# Mouth
canvas_mouth = tk.Canvas(root,width=400,height=150,background=BACKGROUND_COLOR,highlightthickness=0)
canvas_mouth.place(anchor="n",x=400,y=240)

eyes_normal()
mouth_flat()

blink_loop()

root.bind(1,mouth_flat)
root.bind(2,mouth_smile)
root.bind(3,mouth_speak)

root.mainloop()