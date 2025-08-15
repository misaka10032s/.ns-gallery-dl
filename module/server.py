from flask import Flask, request, jsonify
import os

app = Flask(__name__)

# Assuming the script is run from the project root
INPUT_FILE = os.path.abspath('dl.txt')

@app.route('/download', methods=['POST'])
def download():
    data = request.get_json()
    if not data or 'links' not in data:
        return jsonify({'error': 'Invalid request. "links" key is missing.'}), 400

    links = data['links']
    if not isinstance(links, list):
        return jsonify({'error': '"links" must be a list of strings.'}), 400

    try:
        with open(INPUT_FILE, 'a', encoding='utf-8') as f:
            for link in links:
                f.write(f"{link}\n")
        print(f"[*] Received {len(links)} links. Added to {INPUT_FILE}.")
        return jsonify({'message': f'Successfully added {len(links)} links to {INPUT_FILE}.'}), 200
    except Exception as e:
        print(f"[!] Error writing to file: {e}")
        return jsonify({'error': f'Failed to write to file: {e}'}), 500

if __name__ == '__main__':
    print(f"[*] Starting Flask server...")
    print(f"[*] Listening for links to add to {INPUT_FILE}")
    app.run(host='127.0.0.1', port=7601)

