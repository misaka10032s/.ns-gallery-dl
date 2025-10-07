from flask import Flask, request, jsonify, send_from_directory
from .fetch import try_download
from .tokens import load_tokens
from .history import add_to_history, filter_by_history
import threading
from queue import Queue
import json
import os

app = Flask(__name__, static_folder=os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'frontend')), static_url_path='/frontend')

# Queue to hold download tasks
download_queue = Queue()
tokens = load_tokens()
is_remain = False

def worker():
    """Worker thread that processes the download queue."""
    while True:
        link = download_queue.get()
        if link is None:
            if is_remain:
                print("[*] No more tasks in the queue. Worker is exiting.\n\n")
            is_remain = False
            break
        else:
            is_remain = True

        links = filter_by_history([link])
        if not links:
            print(f"[*] Skipping already downloaded: {link}")
            download_queue.task_done()
            continue
        else:
            link = links[0]  # Get the first link after filtering

        print(f"[*] Starting download for: {link}")
        result = try_download(link)

        print(f"[*] Download result for {link}: {result}")
        add_to_history([{"url": link, "result": result}])
        
        download_queue.task_done()

@app.route('/', methods=['GET'])
def index():
    return app.redirect('/history', code=302)

@app.route('/history', methods=['GET'])
def history_page():
    return send_from_directory(os.path.join(app.static_folder, 'history'), 'index.html')

@app.route('/api/history', methods=['GET'])
def get_history():
    history_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'history.json'))
    if not os.path.exists(history_path):
        return jsonify({})
    with open(history_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return jsonify(data)

@app.route('/download', methods=['POST'])
def download():
    data = request.get_json()
    if not data or 'links' not in data:
        return jsonify({'error': 'Invalid request. "links" key is missing.'}), 400

    links = data['links']
    if not isinstance(links, list):
        return jsonify({'error': '"links" must be a list of strings.'}), 400

    for link in links:
        download_queue.put(link)
    
    print(f"[*] Queued {len(links)} links for download.")
    return jsonify({'message': f'Queued {len(links)} links for download.'}), 202

# Start the worker thread
threading.Thread(target=worker, daemon=True).start()

if __name__ == '__main__':
    print(f"[*] Starting Flask server...")
    app.run(host='127.0.0.1', port=7601)

