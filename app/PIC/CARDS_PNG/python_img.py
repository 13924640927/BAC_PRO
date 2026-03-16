from tkinter import *  
from PIL import ImageTk,Image  
root = Tk()  
canvas = Canvas(root, width = 600, height = 600)  
canvas.pack()  
img = ImageTk.PhotoImage(Image.open("AS.png"))
canvas.create_image(100, 100, anchor=NW, image=img) 
root.mainloop() 