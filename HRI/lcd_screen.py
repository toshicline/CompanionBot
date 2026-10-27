import tkinter as tk
import time
import json

# Colors
BACKGROUND_COLOR = "#000"
ROUTINE_SCREEN_BACKGROUND_COLOR = "#222"
NAV_SCREEN_BACKGROUND_COLOR = "#335cff"
FOREGROUND_COLOR = "#FFF"

# Window Setup
root = tk.Tk()
root.geometry("800x480")
root.configure(bg=BACKGROUND_COLOR)

# frames that are currently visible
active_frames = []



####################################################
#                  Helper Methods                  #
####################################################
def load_json(path):
    with open(path, "r") as file:
        return json.load(file)
    
def set_active_frame(frame):
    """Set 'frame' as the active frame and place_forget all others
    
    Args:
        frame: tk.Frame()
    
    Returns:
        None
    """
    global active_frames

    for f in active_frames:
        for widget in f.winfo_children():
            widget.destroy()
        f.place_forget()

    active_frames.append(frame)
    frame.place(relx=0.5,rely=0.5,relwidth=1,relheight=1,anchor="center")
    frame.lift()



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



####################################################
#                     SCREENS                      #
####################################################
def clear():
    """Clears all frames and leaves the face showing

    Returns:
        None
    """
    global active_frames

    for f in active_frames:
        for widget in f.winfo_children():
            widget.destroy()
        f.place_forget()


def show_routine_title(routine_info):
    """Displays the beginning of a routine.

    Args:
        routine_info: the routine json object
            {
            "name":"Morning",
            "steps":[
                    {
                        "name":"Make your bed",
                        "reminder_time_s":30,
                        "skippable":false
                    },
                    ...
                ]
            }
    
    """

    set_active_frame(routine_frame)

    label_routine_name = tk.Label(routine_frame,text=f"{routine_info["name"]} Routine",font="f 48 bold",bg=ROUTINE_SCREEN_BACKGROUND_COLOR)
    label_stepcount = tk.Label(routine_frame,text=f"{len(routine_info["steps"])} steps",font="f 24",bg=ROUTINE_SCREEN_BACKGROUND_COLOR)

    label_routine_name.place(x=20,y=200,anchor="w")
    label_stepcount.place(x=20,y=240,anchor="nw")

def show_routine_step(step_info):
    """Displays the current step in an in-progress routine.

    Args:
        step_info: routine step information
            {
                "routine_name":str,
                "step_name":str,
                "step_number":int,
                "total_steps":int,
            }

    Returns:
        None
    """

    set_active_frame(routine_frame)

    label_routine_name = tk.Label(routine_frame,text=f"{step_info["routine_name"]} Routine",font="f 16",bg=ROUTINE_SCREEN_BACKGROUND_COLOR)
    label_step_name = tk.Label(routine_frame,text=f"{step_info["step_name"]}",font="f 48 bold",bg=ROUTINE_SCREEN_BACKGROUND_COLOR)
    label_progress = tk.Label(routine_frame,text=f"Step {step_info["step_number"]}/{step_info["total_steps"]}",font="f 16",bg=ROUTINE_SCREEN_BACKGROUND_COLOR)

    label_step_name.place(x=20,y=200,anchor="w")
    label_routine_name.place(x=20,y=160,anchor="sw")
    label_progress.place(x=20,y=240,anchor="nw")

def show_navigating(location):
    """Displays the current step in an in-progress routine.

    Args:
        location: where the robot is navigating to

    Returns:
        None
    """

    set_active_frame(nav_frame)
    
    label = tk.Label(nav_frame,text=f"Navigating to:",font="f 16",bg=NAV_SCREEN_BACKGROUND_COLOR)
    label_location = tk.Label(nav_frame,text=f"{location.upper()}",font="f 48 bold",bg=NAV_SCREEN_BACKGROUND_COLOR)

    label_location.place(x=20,y=200,anchor="w")
    label.place(x=20,y=160,anchor="sw")


# Frames setup
routine_frame = tk.Frame(root,bg=ROUTINE_SCREEN_BACKGROUND_COLOR)
nav_frame = tk.Frame(root,bg=NAV_SCREEN_BACKGROUND_COLOR)

# Eyes
canvas_eyes = tk.Canvas(root,width=350,height=100,background=BACKGROUND_COLOR,highlightthickness=0)
canvas_eyes.place(anchor="s",x=400,y=200)

# Mouth
canvas_mouth = tk.Canvas(root,width=400,height=150,background=BACKGROUND_COLOR,highlightthickness=0)
canvas_mouth.place(anchor="n",x=400,y=240)

# Set up initial state
eyes_normal()
mouth_smile()
blink_loop()

root.mainloop()
