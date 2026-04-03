import tkinter as tk
from tkinter import ttk,messagebox
import requests
import threading
import json
import base64
import re
from PIL import Image, ImageDraw, ImageOps
import io
import subprocess
import time
import socket
import sys

OLLAMA_URL="http://localhost:11434"
GUESS_IMAGE_SIZE=224
RESAMPLE_LANCZOS=getattr(Image,"Resampling",Image).LANCZOS

def ensure_ollama_running():
    def is_running():
        try:
            with socket.create_connection(("127.0.0.1",11434),timeout=1):
                return True
        except:
            print("Ollama is not running.")
            return False

    if is_running():
        print("Ollama is already running.")
        return

    subprocess.Popen(
        ["ollama","serve"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    for _ in range(30):
        if is_running():
            print("Ollama started successfully.")
            return
        time.sleep(1)

    print("Failed to start Ollama after 30 seconds.\nPlease ensure Ollama is installed and can be started with 'ollama serve'.")
    sys.exit(1)

def lang_text(lang,key):
    TEXT={
        "title":{
            "CN":"AI 你画我猜",
            "EN":"AI Draw & Guess"
        },
        "btn_lang":{
            "CN":"English",
            "EN":"中文"
        },
        "model_label":{
            "CN":"视觉模型:",
            "EN":"vision model(s):"
        },
        "model_not_found":{
            "CN":"暂无",
            "EN":"not found"
        },
        "undo":{
            "CN":"撤销",
            "EN":"Undo"
        },
        "redo":{
            "CN":"重做",
            "EN":"Redo"
        },
        "clear":{
            "CN":"清空",
            "EN":"Clear"
        },
        "guess":{
            "CN":"开始猜测",
            "EN":"Guess"
        },
        "stop":{
            "CN":"终止",
            "EN":"Stop"
        },
        "result_title":{
            "CN":"模型猜测结果",
            "EN":"Model Prediction"
        },
        "instruction":{
            "CN":"说明：\n\n"
                 "1. 在中间画布中绘制黑白草图\n"
                 "2. 点击“开始猜测”让AI识别\n"
                 "3. 可使用撤销/重做\n"
                 "4. 推理时按钮将被锁定",
            "EN":"Instructions:\n\n"
                 "1. Draw a black & white sketch\n"
                 "2. Click 'Guess' to let AI predict\n"
                 "3. Use Undo/Redo if needed\n"
                 "4. Controls lock during inference"
        },
        "IDLE":{
            "CN":"空闲",
            "EN":"Idle"
        },
        "THINKING":{
            "CN":"推理中",
            "EN":"Thinking"
        },
        "STOPPED":{
            "CN":"已终止",
            "EN":"Stopped"
        },
        "guessing":{
            "CN":"猜测中...",
            "EN":"Guessing..."
        },
        "na":{
            "CN":"暂无",
            "EN":"N/A"
        },
        "unknown":{
            "CN":"猜不到",
            "EN":"Unknown"
        },
        "error":{
            "CN":"错误",
            "EN":"Error"
        },
        "error_no_model":{
            "CN":"未在Ollama中找到支持视觉的模型",
            "EN":"No vision-capable models found in Ollama."
        },
        "system_prompt":{
            "CN":"你是一个你画我猜AI。\n用户会画一张黑白草图（展现的可能是特定文本、标志、人物、生物、物体、风景、场所及其他）。\n你需要根据图片内容猜测物体是什么。\n只输出JSON格式:\n{\"guess\":\"物体名称\"}\n请务必用中文回答。",
            "EN":"You are a draw-and-guess AI.\nThe user will draw a black-and-white sketch that may depict specific text, logos, people, creatures, objects, scenes, places, or other content.\nYou need to guess what the object is based on the image.\nOnly output JSON:\n{\"guess\":\"object name\"}\nPlease answer in English."
        }, 
        "user_prompt":{
            "CN":"请根据图片猜测物体",
            "EN":"Please guess the object based on the image"
        }
    }
    return TEXT[key][lang]

class DrawGuessGUI:
    def __init__(self,root):
        self.root=root
        self.root.geometry("1100x720")
        self.root.configure(bg="#f4f6f9")
        self.root.title("AI Draw & Guess")

        self.language="EN"
        self.state="IDLE"
        self.ai_thinking=False
        self.stop_flag=False
        self.model_available=False
        self.http=requests.Session()

        self.undo_stack=[]
        self.redo_stack=[]
        self.image=Image.new("RGB",(600,600),"white")
        self.undo_stack.append(self.image.copy())
        self.draw_image=ImageDraw.Draw(self.image)
        self.cached_image_base64=""
        self.image_dirty=True

        self.system_prompt="""你是一个你画我猜AI。
只输出JSON格式:
{"guess":"物体名称"}"""
        self.request_id = 0

        self.build_layout()
        self.update_undo_redo_buttons()
        self.load_models()
        self.update_language()

    def build_layout(self):

        top_frame=ttk.Frame(self.root)
        top_frame.pack(fill="x",padx=10,pady=8)

        self.model_label=ttk.Label(top_frame)
        self.model_label.pack(side="left",padx=(0,5))

        self.model_var=tk.StringVar()
        self.model_box=ttk.Combobox(top_frame,textvariable=self.model_var,width=25,state="readonly")
        self.model_box.pack(side="left",padx=5)

        self.lang_btn=ttk.Button(top_frame,command=self.toggle_language)
        self.lang_btn.pack(side="left",padx=5)

        self.undo_btn=ttk.Button(top_frame,command=self.undo)
        self.undo_btn.pack(side="left",padx=5)

        self.redo_btn=ttk.Button(top_frame,command=self.redo)
        self.redo_btn.pack(side="left",padx=5)

        self.clear_btn=ttk.Button(top_frame,command=self.clear_canvas)
        self.clear_btn.pack(side="left",padx=5)

        self.guess_btn=ttk.Button(top_frame,command=self.start_ai)
        self.guess_btn.pack(side="left",padx=5)

        self.stop_btn=ttk.Button(top_frame,command=self.stop_ai)
        self.stop_btn.pack(side="left",padx=5)
        self.stop_btn.config(state="disabled")

        status_frame=ttk.Frame(top_frame)
        status_frame.pack(side="right",padx=10)

        self.status_canvas=tk.Canvas(status_frame,width=16,height=16,highlightthickness=0,bg="#f4f6f9")
        self.status_canvas.pack(side="left")

        self.status_text=tk.StringVar()
        self.status_label=ttk.Label(status_frame,textvariable=self.status_text,font=("Arial",11))
        self.status_label.pack(side="left",padx=5)

        main_frame=ttk.Frame(self.root)
        main_frame.pack(fill="both",expand=True,padx=10,pady=5)

        left_panel=ttk.Frame(main_frame,width=200)
        left_panel.pack(side="left",fill="y")

        self.instruction_label=tk.Label(left_panel,wraplength=180,justify="left",bg="#ffffff",relief="groove")
        self.instruction_label.pack(fill="x",pady=5,ipadx=5,ipady=5)

        canvas_frame=ttk.Frame(main_frame)
        canvas_frame.pack(side="left",padx=15)

        self.canvas=tk.Canvas(canvas_frame,width=600,height=600,bg="white",bd=2,relief="ridge")
        self.canvas.pack()

        self.canvas.bind("<B1-Motion>",self.draw)
        self.canvas.bind("<ButtonRelease-1>",self.reset_last)

        right_panel=ttk.Frame(main_frame,width=250)
        right_panel.pack(side="left",fill="y")

        self.result_title=tk.Label(right_panel,font=("Arial",13,"bold"))
        self.result_title.pack(pady=5)

        self.result_var=tk.StringVar()
        self.result_label=tk.Label(right_panel,textvariable=self.result_var,
                                   wraplength=220,
                                   font=("Arial",14),
                                   bg="#ffffff",
                                   relief="groove",
                                   height=8)
        self.result_label.pack(fill="x",ipadx=5,ipady=10)

        self.update_status("IDLE")

    def toggle_language(self):
        self.language="EN" if self.language=="CN" else "CN"
        self.update_language()

    def update_language(self):
        self.root.title(lang_text(self.language,"title"))
        self.lang_btn.config(text=lang_text(self.language,"btn_lang"))
        self.model_label.config(text=lang_text(self.language,"model_label"))
        self.undo_btn.config(text=lang_text(self.language,"undo"))
        self.redo_btn.config(text=lang_text(self.language,"redo"))
        self.clear_btn.config(text=lang_text(self.language,"clear"))
        self.guess_btn.config(text=lang_text(self.language,"guess"))
        self.stop_btn.config(text=lang_text(self.language,"stop"))
        self.result_var.set(lang_text(self.language,"na"))
        self.result_title.config(text=lang_text(self.language,"result_title"))
        self.instruction_label.config(
            text=lang_text(self.language,"instruction")
        )
        if not self.model_available:
            placeholder=lang_text(self.language,"model_not_found")
            self.model_box["values"]=(placeholder,)
            self.model_var.set(placeholder)
        self.update_status(self.state)

    def update_status(self,state):
        self.state=state
        self.status_canvas.delete("all")
        match state:
            case "IDLE":color="#4caf50"
            case "THINKING":color="#ff9800"
            case "STOPPED":color="#f44336"

        text=lang_text(self.language,state)
        self.status_canvas.create_oval(2,2,14,14,fill=color,outline=color)
        self.status_text.set(text)

    def set_controls_state(self,state):
        for w in [self.clear_btn,self.undo_btn,self.redo_btn,self.lang_btn]:
            w.config(state=state)
        if state=="disabled":
            self.guess_btn.config(state="disabled")
            self.model_box.config(state="disabled")
        else:
            self.guess_btn.config(state="normal" if self.model_available else "disabled")
            self.model_box.config(state="readonly" if self.model_available else "disabled")
            self.update_undo_redo_buttons()

    def draw(self,event):
        if hasattr(self,"last_x") and self.last_x is not None:
            self.canvas.create_line(self.last_x,self.last_y,event.x,event.y,
                                    width=5,fill="black",capstyle=tk.ROUND,smooth=True)
            self.draw_image.line([self.last_x,self.last_y,event.x,event.y],fill="black",width=5)
            self.image_dirty=True
        self.last_x=event.x
        self.last_y=event.y

    def reset_last(self,event):
        self.last_x=None
        self.last_y=None
        self.undo_stack.append(self.image.copy())
        self.redo_stack.clear()
        self.update_undo_redo_buttons()

    def refresh_canvas(self):
        self.canvas.delete("all")
        buf=io.BytesIO()
        self.image.save(buf,format="PNG")
        tk_img=tk.PhotoImage(data=base64.b64encode(buf.getvalue()))
        self.canvas.create_image(0,0,image=tk_img,anchor="nw")
        self.tk_img=tk_img

    def undo(self):
        if len(self.undo_stack)<=1:
            return
        self.redo_stack.append(self.image.copy())
        self.undo_stack.pop()
        self.image=self.undo_stack[-1].copy()
        self.draw_image=ImageDraw.Draw(self.image)
        self.image_dirty=True
        self.refresh_canvas()
        self.update_undo_redo_buttons()

    def redo(self):
        if not self.redo_stack:
            return
        state=self.redo_stack.pop()
        self.undo_stack.append(state.copy())
        self.image=state.copy()
        self.draw_image=ImageDraw.Draw(self.image)
        self.image_dirty=True
        self.refresh_canvas()
        self.update_undo_redo_buttons()

    def update_undo_redo_buttons(self):
        if len(self.undo_stack) <= 1:
            self.undo_btn.config(state="disabled")
        else:
            self.undo_btn.config(state="normal")

        if len(self.redo_stack) == 0:
            self.redo_btn.config(state="disabled")
        else:
            self.redo_btn.config(state="normal")

    def clear_canvas(self):
        self.canvas.delete("all")
        self.image=Image.new("RGB",(600,600),"white")
        self.draw_image=ImageDraw.Draw(self.image)
        self.undo_stack=[self.image.copy()]
        self.redo_stack=[]
        self.image_dirty=True
        self.result_var.set(lang_text(self.language,"na"))
        self.update_undo_redo_buttons()

    def encode_guess_image(self,img):
        img=img.convert("L")
        bbox=ImageOps.invert(img).getbbox()
        if bbox:
            pad=24
            left=max(0,bbox[0]-pad)
            top=max(0,bbox[1]-pad)
            right=min(img.width,bbox[2]+pad)
            bottom=min(img.height,bbox[3]+pad)
            img=img.crop((left,top,right,bottom))
        img=ImageOps.contain(img,(GUESS_IMAGE_SIZE,GUESS_IMAGE_SIZE),RESAMPLE_LANCZOS)
        canvas=Image.new("L",(GUESS_IMAGE_SIZE,GUESS_IMAGE_SIZE),"white")
        offset=((GUESS_IMAGE_SIZE-img.width)//2,(GUESS_IMAGE_SIZE-img.height)//2)
        canvas.paste(img,offset)
        buf=io.BytesIO()
        canvas.save(buf,format="PNG",optimize=True)
        return base64.b64encode(buf.getvalue()).decode("utf-8")

    def get_image_base64(self):
        if self.image_dirty or not self.cached_image_base64:
            self.cached_image_base64=self.encode_guess_image(self.image)
            self.image_dirty=False
        return self.cached_image_base64

    def parse_guess_text(self,content,language):
        content=(content or "").strip()
        if not content:
            return lang_text(language,"unknown")

        try:
            data=json.loads(content)
            if isinstance(data,dict):
                guess=data.get("guess","")
                if isinstance(guess,str) and guess.strip():
                    return guess.strip()
        except:
            pass

        match=re.search(r'"guess"\s*:\s*"([^"]+)"',content,re.IGNORECASE)
        if match:
            guess=match.group(1).strip()
            if guess:
                return guess

        cleaned=content.replace("```json","").replace("```","").strip()
        if cleaned.startswith("{") and cleaned.endswith("}"):
            cleaned=cleaned[1:-1].strip()
        if cleaned:
            first_line=cleaned.splitlines()[0].strip().strip('"')
            if first_line:
                return first_line

        return lang_text(language,"unknown")

    def start_ai(self):
        if self.ai_thinking:
            return
        if not self.model_available:
            return
        model_name=self.model_var.get().strip()
        if not model_name:
            return

        self.request_id += 1
        current_id = self.request_id
        language=self.language
        image_base64=self.get_image_base64()
        self.ai_thinking=True
        self.stop_flag=False
        self.set_controls_state("disabled")
        self.stop_btn.config(state="normal")
        self.update_status("THINKING")
        self.result_var.set(lang_text(self.language,"guessing"))
        threading.Thread(
            target=self.ai_turn,
            args=(current_id,model_name,language,image_base64),
            daemon=True
        ).start()

    def stop_ai(self):
        if not self.ai_thinking:
            return

        self.stop_flag=True

        try:
            self.http.post(f"{OLLAMA_URL}/api/stop",timeout=2)
        except:
            pass

        self.ai_thinking=False
        self.set_controls_state("normal")
        self.stop_btn.config(state="disabled")
        self.update_status("STOPPED")
        self.result_var.set(lang_text(self.language,"na"))

    def ai_turn(self,req_id,model_name,language,image_base64):
        guess_text=""
        try:
            r=self.http.post(
                f"{OLLAMA_URL}/api/chat",
                json={
                    "model":model_name,
                    "messages":[
                    {"role":"system","content":lang_text(language,"system_prompt")},
                    {
                        "role":"user",
                        "content":lang_text(language,"user_prompt"),
                        "images":[image_base64]
                    }
                ],
                    "stream":False,
                    "think":False,
                    "format":"json",
                    "keep_alive":-1,
                    "options":{
                        "temperature":0.3
                    }
                },
                timeout=(3,600)
            ).json()
            if self.stop_flag:
                return
            content=r["message"]["content"]
            guess_text=self.parse_guess_text(content,language)
        except:
            guess_text=lang_text(language,"unknown")

        def update():
            if req_id != self.request_id:
                 return
            if not self.stop_flag:
                self.result_var.set(guess_text)
                self.update_status("IDLE")
            self.ai_thinking=False
            self.set_controls_state("normal")
            self.stop_btn.config(state="disabled")

        self.root.after(0,update)

    def load_models(self):
        try:
            r=self.http.get(f"{OLLAMA_URL}/api/tags",timeout=5)
            data=r.json()
            vision_models=[]
            for m in data["models"]:
                name=m["name"]
                try:
                    detail=self.http.post(
                        f"{OLLAMA_URL}/api/show",
                        json={"name":name}
                        ,
                        timeout=10
                    ).json()
                    modelfile=detail.get("modelfile","").lower()
                    if "vision" in modelfile or "multimodal" in modelfile or "llava" in name.lower() or "vl" in name.lower():
                        vision_models.append(name)
                except:
                    pass
            if vision_models:
                self.model_available=True
                self.model_box["values"]=vision_models
                self.model_var.set(vision_models[0])
            else:
                self.model_available=False
                placeholder=lang_text(self.language,"model_not_found")
                self.model_box["values"]=(placeholder,)
                self.model_var.set(placeholder)
            self.set_controls_state("normal")
        except:
            self.model_available=False
            placeholder=lang_text(self.language,"model_not_found")
            self.model_box["values"]=(placeholder,)
            self.model_var.set(placeholder)
            self.set_controls_state("normal")

ensure_ollama_running()
root=tk.Tk()
app=DrawGuessGUI(root)
root.mainloop()
