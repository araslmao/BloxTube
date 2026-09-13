import http.server
import json
import subprocess
import threading
import tkinter as tk
from tkinter import scrolledtext
from urllib.parse import urlparse, parse_qs
import time
import yt_dlp
from PIL import Image
import io
# this is kind of vibecoded, though i still wrote some stuff manually too.
# it was literally 2 AM when i made this
latest_ascii = "Loading video..."
frame_lock = threading.Lock()
is_streaming = False
ffmpeg_process = None

WIDTH = 160 
ASCII_CHARS = " .:-=+*#%@"

def get_video_metadata(query):
    ydl_opts = {
        'skip_download': True,
        'extract_flat': 'in_playlist',
        'default_search': 'ytsearch5',
        'quiet': True
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(query, download=False)
            if 'entries' in info:
                results = []
                for entry in info['entries']:
                    results.append({
                        'id': entry.get('id'),
                        'title': entry.get('title'),
                        'channel': entry.get('uploader') or entry.get('channel'),
                        'views': entry.get('view_count', 0)
                    })
                return {"type": "search", "results": results}
            else:
                return {
                    "type": "video",
                    "id": info.get('id'),
                    'title': info.get('title'),
                    'channel': info.get('uploader'),
                    'views': info.get('view_count', 0)
                }
    except Exception as e:
        return {"error": str(e)}

def frame_to_ascii(image_bytes):
    try:
        image = Image.open(io.BytesIO(image_bytes)).convert("L")
        w, h = image.size
        aspect_ratio = h / w
        new_height = int(WIDTH * aspect_ratio * 0.55)
        image = image.resize((WIDTH, new_height))
        
        pixels = image.getdata()
        chars = "".join([ASCII_CHARS[pixel * len(ASCII_CHARS) // 256] for pixel in pixels])
        lines = [chars[i:i+WIDTH] for i in range(0, len(chars), WIDTH)]
        return "\n".join(lines)
    except Exception:
        return ""

def start_ascii_stream(video_id, log_callback):
    global latest_ascii, ffmpeg_process, is_streaming
    
    is_streaming = True
    url = f"https://www.youtube.com/watch?v={video_id}"
    
    while is_streaming:
        log_callback(f"Extracting direct URL for {video_id}...\n")
        
        try:
            with yt_dlp.YoutubeDL({'format': 'bestvideo[height<=360]/worst', 'quiet': True}) as ydl:
                info = ydl.extract_info(url, download=False)
                stream_url = info['url']
            
            log_callback(f"Starting stream...\n")
            
            # i really dont know what this does but i think it changes aspect ratioes, doesnt seem to work though not sure
            ffmpeg_cmd = [
                "ffmpeg", 
                "-re",
                "-i", stream_url,
                "-vf", "fps=5,scale=320:180",
                "-f", "image2pipe", "-vcodec", "mjpeg", "pipe:1"
            ]

            ffmpeg_process = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

            buffer_data = b""
            while is_streaming:
                chunk = ffmpeg_process.stdout.read(4096)
                if not chunk:
                    break 
                
                buffer_data += chunk
                
                while True:
                    start_idx = buffer_data.find(b'\xff\xd8')
                    end_idx = buffer_data.find(b'\xff\xd9')
                    
                    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                        jpeg_frame = buffer_data[start_idx:end_idx+2]
                        buffer_data = buffer_data[end_idx+2:]
                        
                        ascii_art = frame_to_ascii(jpeg_frame)
                        if ascii_art:
                            with frame_lock:
                                latest_ascii = ascii_art
                    else:
                        break
                            
        except Exception as e:
            log_callback(f"Stream Error: {e}\n")
            
        if is_streaming:
            log_callback("Video ended. Restarting video in 3 seconds...\n")
            time.sleep(3)

class RequestHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        parsed_path = urlparse(self.path)
        
        if parsed_path.path == "/api/search":
            query_params = parse_qs(parsed_path.query)
            q = query_params.get('q', [''])[0]
            app.log(f"Search: {q}\n")
            data = get_video_metadata(q)
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(data).encode())

        elif parsed_path.path == "/api/stream":
            query_params = parse_qs(parsed_path.query)
            video_id = query_params.get('id', [''])[0]

            if video_id:
                app.log(f"Loading video: {video_id}\n")
                global is_streaming
                is_streaming = False
                time.sleep(0.5)
                threading.Thread(target=start_ascii_stream, args=(video_id, app.log), daemon=True).start()
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"Started")
            else:
                with frame_lock:
                    frame_str = latest_ascii
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(frame_str.encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()

def run_server(log_callback):
    server_address = ('localhost', 8080)
    httpd = http.server.HTTPServer(server_address, RequestHandler)
    log_callback("Server listening on http://localhost:8080\n")
    httpd.serve_forever()

class AppGUI:
    def __init__(self, root):
        self.root = root
        root.title("BloxTube Server")
        root.geometry("400x330") 
        
        tk.Label(root, text="Server Running...", fg="green", font=("Arial", 12, "bold")).pack(pady=5)
        
        self.log_box = scrolledtext.ScrolledText(root, width=45, height=11, font=("Consolas", 9))
        self.log_box.pack(padx=10, pady=5)
        
        # credit label
        tk.Label(root, text="Made with <3 by youtube.com/@araslmao", fg="gray", font=("Arial", 9, "italic")).pack(side=tk.BOTTOM, pady=5)
        
        threading.Thread(target=run_server, args=(self.log,), daemon=True).start()

    def log(self, message):
        self.log_box.insert(tk.END, message)
        self.log_box.see(tk.END)

if __name__ == "__main__":
    root = tk.Tk()
    app = AppGUI(root)
    root.mainloop()
