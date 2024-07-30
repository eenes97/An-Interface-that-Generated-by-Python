import tkinter as tk
from tkinter import ttk
from tkinter import messagebox
from PIL import Image, ImageTk
import io
import json
import requests
from datetime import datetime, timedelta
from oauthlib.oauth2 import BackendApplicationClient
from requests_oauthlib import OAuth2Session
import cv2
import numpy as np
import os


client_id = 'your client id on sentinel hub'
client_secret = 'your secret id on sentinel hub'

def get_oauth_token(client_id, client_secret):
    client = BackendApplicationClient(client_id=client_id)
    oauth = OAuth2Session(client=client)
    token = oauth.fetch_token(token_url='https://services.sentinel-hub.com/auth/realms/main/protocol/openid-connect/token',
                              client_secret=client_secret, include_client_id=True)
    return token["access_token"]

class SentinelHubInterface(tk.Tk):
    def __init__(self): 
        super().__init__() 
        self.title("Sentinel Hub Interface") 
        self.geometry("1920x1680") 

        self.images_data = [] 

        
        coord_frame = tk.LabelFrame(self, text="Enter Location (lat, lon) as GeoJSON Polygon") 
        coord_frame.place(relx=0.75, rely=0.42, anchor='center') 

        self.coord_entry = tk.Text(coord_frame, height=5, width=50) 
        self.coord_entry.grid(row=0, column=0, padx=10, pady=10) 
        self.coord_entry.insert(tk.END, json.dumps({ 
            "type": "Polygon",
            "coordinates": [
                [
                    [39.53705, 36.78385],
                    [39.62563, 36.77973],
                    [39.62168, 36.72471],
                    [39.51920, 36.72980],
                    [39.52211, 36.76598],
                    [39.53705, 36.78385]
                ]
            ]
        }, indent=4))

        
        date_frame = tk.LabelFrame(self, text="Enter Date Range (YYYY-MM-DD)") 
        date_frame.place(relx=0.5, rely=0.48, anchor='center') 

        self.start_date_entry = tk.Entry(date_frame) 
        self.start_date_entry.grid(row=0, column=0, padx=5, pady=10) 
        self.start_date_entry.insert(0, "Start Date") 

        self.end_date_entry = tk.Entry(date_frame) 
        self.end_date_entry.grid(row=0, column=1, padx=5, pady=10) 
        self.end_date_entry.insert(0, "End Date") 

        submit_button = tk.Button(date_frame, text="Submit", command=self.submit)
        submit_button.grid(row=1, column=0, columnspan=2, pady=10) 

        extract_button = tk.Button(self, text="Extract", command=self.extract_images) 
        extract_button.place(relx=0.5, rely=0.85, anchor='center') 

        # Image Display Area
        image_display_frame = tk.LabelFrame(self, text="Satellite Images") 
        image_display_frame.place(relx=0.5, rely=0.15, anchor='center') 

        # Scrollable Frame for fetched images
        self.canvas = tk.Canvas(image_display_frame, width=750, height=250) 
        self.scrollable_frame = tk.Frame(self.canvas) 

        self.scrollbar = ttk.Scrollbar(image_display_frame, orient="horizontal", command=self.canvas.xview) 
        self.canvas.configure(xscrollcommand=self.scrollbar.set) 

        self.scrollbar.pack(side="bottom", fill="x") 
        self.canvas.pack(side="left") 
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw") 

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(
                scrollregion=self.canvas.bbox("all")
            )
        ) 

        # Scrollable Frame for extracted images
        extracted_display_frame = tk.LabelFrame(self, text="Extracted Images with Yellow Areas") 
        extracted_display_frame.place(relx=0.5, rely=0.7, anchor='center') 

        self.extracted_canvas = tk.Canvas(extracted_display_frame, width=750, height=250) 
        self.extracted_scrollable_frame = tk.Frame(self.extracted_canvas) 

        self.extracted_scrollbar = ttk.Scrollbar(extracted_display_frame, orient="horizontal", command=self.extracted_canvas.xview) 
        self.extracted_canvas.configure(xscrollcommand=self.extracted_scrollbar.set) 

        self.extracted_scrollbar.pack(side="bottom", fill="x") 
        self.extracted_canvas.pack(side="left") 
        self.extracted_canvas.create_window((0, 0), window=self.extracted_scrollable_frame, anchor="nw") 

        self.extracted_scrollable_frame.bind(
            "<Configure>",
            lambda e: self.extracted_canvas.configure(
                scrollregion=self.extracted_canvas.bbox("all")
            )
        ) 

    def submit(self):
        location = self.coord_entry.get("1.0", tk.END).strip() 
        start_date = self.start_date_entry.get() 
        end_date = self.end_date_entry.get() 

        if location and start_date and end_date: 
            self.process_images(location, start_date, end_date) 
        else: 
            messagebox.showwarning("Input Error", "Please enter all required fields.")

    def process_images(self, location, start_date, end_date): 
        try:
            token = get_oauth_token(client_id, client_secret) 
        except Exception as e: 
            messagebox.showerror("Authentication Error", f"Failed to fetch token: {e}")
            return

        date_format = "%Y-%m-%d" 
        try: 
            start_date_obj = datetime.strptime(start_date, date_format)
            end_date_obj = datetime.strptime(end_date, date_format)
        except ValueError: 
            messagebox.showerror("Date Error", "Please enter valid dates in YYYY-MM-DD format.")
            return

        current_date = start_date_obj 

        os.makedirs("satellite_images", exist_ok=True) 
        while current_date <= end_date_obj: 
            self.fetch_and_display_image(location, current_date.strftime(date_format), token) 
            current_date += timedelta(days=5) 

    def fetch_and_display_image(self, location, date, token):
        url = "http://services.sentinel-hub.com/api/v1/process" 
        access_token = token 

        payload = { 
            "input": { 
                "bounds": { 
                    "geometry": json.loads(location)
                },
                "data": [ 
                    {
                        "type": "S2L2A",
                        "dataFilter": {
                            "timeRange": {
                                "from": f"{date}T00:00:00Z",
                                "to": f"{date}T23:59:59Z"
                            }
                        }
                    }
                ]
            },
            "output": { 
                "width": 512,
                "height": 512
            }
        }

        evalscript = """
        let index = (1-((B06*B07*B8A)/B04)**0.5)*((B12-B8A)/((B12+B8A)**0.5)+1);
        let min = 0.99;
        let max = 5.99;
        let zero = 0.5;

        let underflow_color = [1, 1, 1];
        let low_color = [0/255, 0/255, 255/255];
        let high_color = [255/255, 20/255, 20/255];
        let zero_color = [250/255, 255/255, 10/255];
        let overflow_color = [255/255, 0/255, 255/255];

        return colorBlend(index, [min, min, zero, max],
        [
	    underflow_color,
	    low_color,
	    zero_color, // divergent step at zero
	    high_color,
	    overflow_color // uncomment to see overflows
        ]);
        """
        
        files = { 
            'request': ('', json.dumps(payload)),
            'evalscript': ('', evalscript)
        }

        headers = { 
            'Authorization': f'Bearer {access_token}'
        }

        response = requests.post(url, headers=headers, files=files) 

        if response.status_code == 200: 
            try:
                img_data = response.content 
                self.images_data.append((img_data, date)) 

                img_pil = Image.open(io.BytesIO(img_data)) 
                img = ImageTk.PhotoImage(img_pil.resize((200, 200), Image.Resampling.LANCZOS)) 

                # Save image to file
                img_pil.save(f"satellite_images/{date}.png") 

                container = tk.Frame(self.scrollable_frame) 
                container.pack(side="left", padx=10, pady=10) 

                panel = tk.Label(container, image=img) 
                panel.image = img 
                panel.pack() 

                date_label = tk.Label(container, text=date) 
                date_label.pack() 

            except Exception as e: 
                messagebox.showerror("Image Error", f"Failed to process image for {date}: {e}") 
        else: 
            messagebox.showerror("API Error", f"Failed to fetch image for {date}: {response.text}") 

    def extract_images(self):
        if not self.images_data: 
            messagebox.showinfo("Extraction Result", "No images to extract. Please submit images first.") 
            return 

        os.makedirs("extracted_images_with_yellow", exist_ok=True) 
        os.makedirs("extracted_images_without_yellow", exist_ok=True) 
        

        for widget in self.extracted_scrollable_frame.winfo_children(): 
            widget.destroy() 

        extracted_any = False 
        for img_data, date in self.images_data: 
            img_pil = Image.open(io.BytesIO(img_data)) 

            img_np = np.array(img_pil) 

            yellow_percentage = self.check_yellow_areas(img_np) 

            if yellow_percentage > 0.01: 
                extracted_any = True 

                img = ImageTk.PhotoImage(img_pil.resize((200, 200), Image.Resampling.LANCZOS)) 

                # Save image to file
                img_pil.save(f"extracted_images_with_yellow/{date}.png") 

                container = tk.Frame(self.extracted_scrollable_frame) 
                container.pack(side="left", padx=10, pady=10) 

                panel = tk.Label(container, image=img) 
                panel.image = img 
                panel.pack() 
                date_label = tk.Label(container, text=date) 
                date_label.pack() 
            else:
                img_pil.save(f"extracted_images_without_yellow/{date}.png") 

        if not extracted_any: 
            messagebox.showinfo("Extraction Result", "No images with yellow areas above 0.01% found.") 

    def check_yellow_areas(self, img):
        grid_HSV = cv2.cvtColor(img, cv2.COLOR_RGB2HSV) 

        lower_yellow = np.array([25, 150, 50]) 
        upper_yellow = np.array([35, 255, 255]) 
        

        mask = cv2.inRange(grid_HSV, lower_yellow, upper_yellow) 

        non_zero_count = np.count_nonzero(mask) 
        total_count = mask.size 
        percentage_non_zero = (non_zero_count / total_count) * 100 

        return percentage_non_zero

if __name__ == "__main__":
    app = SentinelHubInterface()
    app.mainloop()
