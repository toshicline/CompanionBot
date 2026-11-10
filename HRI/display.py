import tkinter as tk
import time
import json
import queue
import tkinter.simpledialog as simpledialog

class RobotDisplay:

    def __init__(self):
        # Colors
        self.BACKGROUND_COLOR = "#000"
        self.ROUTINE_SCREEN_BACKGROUND_COLOR = "#222"
        self.NAV_SCREEN_BACKGROUND_COLOR = "#335cff"
        self.FOREGROUND_COLOR = "#FFF"

        # Orchestrator setup
        self.orchestrator = None

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
    #                Orchestrator Link                 #
    ####################################################

    def set_orchestrator(self,orchestrator):
        self.orchestrator = orchestrator

    def close(self):
        """Safely shutdown background threads and then closes GUI"""

        print("[Display] Close call issued.")

        if self.orchestrator:
            print("[Display] Stopping orchestrator...")
            self.orchestrator.stop()

        print("[Display] Stopping GUI...")
        self.root.destroy()



    ####################################################
    #                  Helper Methods                  #
    ####################################################
        
    class ScrollingLabel(tk.Canvas):
        def __init__(self, master, text="", font=("Arial", 36, "bold"), bg="#222", fg="#FFF", width=760, height=90, speed=2, pause_time=1500, **kwargs):
            super().__init__(master, width=width, height=height, bg=bg, highlightthickness=0, **kwargs)
            self.original_text = text
            self.max_width = width
            self.speed = speed
            self.pause_time = pause_time
            self.after_id = None

            # Create text item on canvas, vertically centered
            self.text_item = self.create_text(5, height // 2, text=text, font=font, fill=fg, anchor="w")

            # Measure total text width
            bbox = self.bbox(self.text_item)
            self.text_width = (bbox[2] - bbox[0]) if bbox else 0

            self.x_pos = 0
            # Only start scrolling if text exceeds the 760px viewport width
            if self.text_width > self.max_width:
                self.max_scroll = self.text_width - self.max_width + 30 # buffer at the end
                self.direction = 1  # 1 = scrolling left, -1 = scrolling right
                self.start_scroll()

        def start_scroll(self):
            def scroll_step():
                self.x_pos += self.direction * self.speed
                
                # Move the text item horizontally inside the canvas viewport
                self.coords(self.text_item, 5 - self.x_pos, self.winfo_height() // 2)
                
                next_delay = 30  # Smooth animation frame rate (~30ms)

                # Hit the end of the text
                if self.x_pos >= self.max_scroll:
                    self.direction = -1
                    next_delay = self.pause_time

                # Hit back to the start
                elif self.x_pos <= 0:
                    self.direction = 1
                    next_delay = self.pause_time

                self.after_id = self.after(next_delay, scroll_step)

            self.after_id = self.after(self.pause_time, scroll_step)

        def stop_scroll(self):
            if self.after_id:
                self.after_cancel(self.after_id)
                self.after_id = None

        def destroy(self):
            self.stop_scroll()
            super().destroy()

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

    def get_debug_input(self, prompt_text="Type simulated response:"):
        """Safely opens a Tkinter input dialog from a background thread."""
        q = queue.Queue()
        
        def ask_on_main():
            val = simpledialog.askstring("Debug Input", prompt_text, parent=self.root)
            q.put(val if val is not None else "")
            
        # Schedule the dialog creation on the main Tkinter thread
        self.root.after(0, ask_on_main)
        
        # Block the background thread until the user submits the input box
        return q.get()


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

    def show_routine_step(self,routine_info,step_number):
        self.set_active_frame(self.routine_frame)
        self.ScrollingLabel(self.routine_frame,text=f"{routine_info["steps"][step_number-1]["name"]}",font="f 48 bold",bg=self.ROUTINE_SCREEN_BACKGROUND_COLOR).place(x=20,y=200,anchor="w")
        tk.Label(self.routine_frame,text=f"{routine_info["name"]} Routine",font="f 16",bg=self.ROUTINE_SCREEN_BACKGROUND_COLOR).place(x=20,y=160,anchor="sw")
        tk.Label(self.routine_frame,text=f"Step {step_number}/{len(routine_info["steps"])}",font="f 16",bg=self.ROUTINE_SCREEN_BACKGROUND_COLOR).place(x=20,y=240,anchor="nw")

    def show_navigating(self,location):
        self.set_active_frame(self.nav_frame)
        tk.Label(self.nav_frame,text="Navigating to:",font="f 16",bg=self.NAV_SCREEN_BACKGROUND_COLOR).place(x=20,y=160,anchor="sw")
        tk.Label(self.nav_frame,text=f"{location.upper()}",font="f 48 bold",bg=self.NAV_SCREEN_BACKGROUND_COLOR).place(x=20,y=200,anchor="w")
    
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