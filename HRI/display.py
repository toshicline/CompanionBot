import tkinter as tk
import time
import json

class RobotDisplay:

    def __init__(self):
        # Colors
        self.BACKGROUND_COLOR = "#000"
        self.ROUTINE_SCREEN_BACKGROUND_COLOR = "#222"
        self.NAV_SCREEN_BACKGROUND_COLOR = "#335cff"
        self.FOREGROUND_COLOR = "#FFF"

        # Window Setup
        self.root = tk.Tk()
        self.root.geometry("800x480")
        self.root.configure(bg=self.BACKGROUND_COLOR)

        # frames that are currently visible
        self.active_frames = []

        # Frames setup
        self.routine_frame = tk.Frame(self.root,bg=self.ROUTINE_SCREEN_BACKGROUND_COLOR)
        self.nav_frame = tk.Frame(self.root,bg=self.NAV_SCREEN_BACKGROUND_COLOR)

        # Eyes
        self.canvas_eyes = tk.Canvas(self.root,width=350,height=100,background=self.BACKGROUND_COLOR,highlightthickness=0)
        self.canvas_eyes.place(anchor="s",x=400,y=200)

        # Mouth
        self.canvas_mouth = tk.Canvas(self.root,width=400,height=150,background=self.BACKGROUND_COLOR,highlightthickness=0)
        self.canvas_mouth.place(anchor="n",x=400,y=240)

        # Set up initial state
        self.eyes_normal()
        self.mouth_smile()
        self.blink_loop()



    ####################################################
    #                  Helper Methods                  #
    ####################################################
        
    def set_active_frame(self,frame):
        """Set 'frame' as the active frame and place_forget all others
        
        Args:
            frame: tk.Frame()
        
        Returns:
            None
        """

        for f in self.active_frames:
            for widget in f.winfo_children():
                widget.destroy()
            f.place_forget()

        self.active_frames.append(frame)
        frame.place(relx=0.5,rely=0.5,relwidth=1,relheight=1,anchor="center")
        frame.lift()



    ####################################################
    #                     GRAPHICS                     #
    ####################################################

    def eyes_normal(self,event=None):
        self.canvas_eyes.delete("all")
        eye_padding = 12
        self.canvas_eyes.create_oval(0+eye_padding,0+eye_padding,100-eye_padding,100-eye_padding,fill=self.FOREGROUND_COLOR)
        self.canvas_eyes.create_oval(350-eye_padding,0+eye_padding,350-100+eye_padding,100-eye_padding,fill=self.FOREGROUND_COLOR)

    def eyes_blink(self,return_to_normal=True,event=None):
        self.canvas_eyes.delete("all")
        eye_padding = 12
        self.canvas_eyes.create_line(0+eye_padding,50,100-eye_padding,50,capstyle="round",width=12,fill=self.FOREGROUND_COLOR)
        self.canvas_eyes.create_line(350-eye_padding,50,350-100+eye_padding,50,capstyle="round",width=12,fill=self.FOREGROUND_COLOR)

        if return_to_normal:
            self.root.after(300,self.eyes_normal)

    def blink_loop(self):
        self.eyes_blink()
        self.root.after(5000,self.blink_loop)

    def mouth_smile(self,event=None):
        self.canvas_mouth.delete("all")
        self.canvas_mouth.create_arc(10,-100,390,140,width=20,outline=self.FOREGROUND_COLOR,start=200,extent=140,style=tk.ARC)

    def mouth_flat(self,event=None):
        self.canvas_mouth.delete("all")
        self.canvas_mouth.create_line(40,100,360,100,width=20,fill=self.FOREGROUND_COLOR,capstyle="round")

    def mouth_speak(self,event=None):
        self.canvas_mouth.delete("all")
        self.canvas_mouth.create_arc(10,-160,390,140,width=20,outline=self.FOREGROUND_COLOR,start=200,extent=140,style=tk.CHORD)



    ####################################################
    #                     SCREENS                      #
    ####################################################

    def show_routine_title(self,routine_info):
        self.set_active_frame(self.routine_frame)
        tk.Label(self.routine_frame,text=f"{routine_info["name"]} Routine",font="f 48 bold",bg=self.ROUTINE_SCREEN_BACKGROUND_COLOR).place(x=20,y=200,anchor="w")
        tk.Label(self.routine_frame,text=f"{len(routine_info["steps"])} steps",font="f 24",bg=self.ROUTINE_SCREEN_BACKGROUND_COLOR).place(x=20,y=240,anchor="nw")

    def show_routine_step(self,step_info):
        self.set_active_frame(self.routine_frame)
        tk.Label(self.routine_frame,text=f"{step_info["step_name"]}",font="f 48 bold",bg=self.ROUTINE_SCREEN_BACKGROUND_COLOR).place(x=20,y=200,anchor="w")
        tk.Label(self.routine_frame,text=f"{step_info["routine_name"]} Routine",font="f 16",bg=self.ROUTINE_SCREEN_BACKGROUND_COLOR).place(x=20,y=160,anchor="sw")
        tk.Label(self.routine_frame,text=f"Step {step_info["step_number"]}/{step_info["total_steps"]}",font="f 16",bg=self.ROUTINE_SCREEN_BACKGROUND_COLOR).place(x=20,y=240,anchor="nw")

    def show_navigating(self,location):
        self.set_active_frame(self.nav_frame)
        tk.Label(self.nav_frame,text=f"Navigating to:",font="f 16",bg=self.NAV_SCREEN_BACKGROUND_COLOR).place(x=20,y=200,anchor="w")
        tk.Label(self.nav_frame,text=f"{location.upper()}",font="f 48 bold",bg=self.NAV_SCREEN_BACKGROUND_COLOR).place(x=20,y=160,anchor="sw")
    
    def clear(self):
        for f in self.active_frames:
            for widget in f.winfo_children():
                widget.destroy()
            f.place_forget()

    ####################################################
    #                       MAIN                       #
    ####################################################

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    display = RobotDisplay()
    display.run()