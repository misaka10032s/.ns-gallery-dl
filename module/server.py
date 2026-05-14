from flask import Flask, request, jsonify, send_from_directory
from .tokens import load_tokens
from .downloader import enqueue, get_state, start_worker
import json
import os
import cloudscraper

app = Flask(__name__, static_folder=os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'frontend')), static_url_path='/frontend')

tokens = load_tokens()

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

@app.route('/api/history', methods=['DELETE'])
def delete_history():
    data = request.get_json()
    date = data.get('date')
    url = data.get('url')
    if not all([date, url]):
        return jsonify({'error': 'Missing date or url'}), 400
    from .history import delete_from_history
    if delete_from_history(date, url):
        return jsonify({'message': 'Deleted'}), 200
    else:
        return jsonify({'error': 'History item not found'}), 404

@app.route('/api/history', methods=['PUT'])
def update_history():
    data = request.get_json()
    date = data.get('date')
    url = data.get('url')
    status = data.get('status')

    if not all([date, url, status]):
        return jsonify({'error': 'Missing date, url, or status'}), 400

    from .history import update_history_status
    if update_history_status(date, url, status):
        return jsonify({'message': 'History updated successfully'}), 200
    else:
        return jsonify({'error': 'History item not found'}), 404

@app.route('/api/fetch_status', methods=['POST'])
def fetch_status():
    data = request.get_json()
    url = data.get('url')
    if not url:
        return jsonify({'error': 'URL is missing'}), 400

    scraper = cloudscraper.create_scraper()
    try:
        resp = scraper.get(url, timeout=10)
        return jsonify({
            'status_code': resp.status_code,
            'text': resp.text[:500]  # Truncate to avoid sending huge responses
        })
    except cloudscraper.exceptions.CloudflareChallengeError as e:
        return jsonify({'error': str(e)}), 403
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/download', methods=['POST'])
def download():
    data = request.get_json()
    if not data or 'links' not in data:
        return jsonify({'error': 'Invalid request. "links" key is missing.'}), 400

    links = data['links']
    if not isinstance(links, list):
        return jsonify({'error': '"links" must be a list of strings.'}), 400

    enqueue(links)
    
    print(f"[*] Queued {len(links)} links for download.")
    return jsonify({'message': f'Queued {len(links)} links for download.'}), 202

@app.route('/queue', methods=['GET'])
def queue_page():
    return send_from_directory(os.path.join(app.static_folder, 'queue'), 'index.html')

@app.route('/api/queue', methods=['GET'])
def get_queue():
    return jsonify(get_state())

# Start the worker thread
start_worker()

if __name__ == '__main__':
    print(f"[*] Starting Flask server...")
    app.run(host='127.0.0.1', port=7601)

