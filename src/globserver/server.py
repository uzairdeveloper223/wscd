from flask import Flask, request, jsonify

app = Flask(__name__)

LINK_DATABASE = {
    "2026-AE-1234": "https://example.com/reports/ae-2026-v1",
    "2025-US-5678": "https://example.com/archive/us-5678"
}

@app.route('/get-link', methods=['POST'])
def get_link_by_id():
    data = request.get_json()
    
    id_dict = data.get("id")
    
    if not id_dict:
        return jsonify({"error": "No ID dictionary provided"}), 400

    try:
        formatted_id = f"{id_dict['year']}-{id_dict['region']}-{id_dict['number']}"
    except KeyError as e:
        return jsonify({"error": f"Missing key in ID dict: {str(e)}"}), 400

    # 4. Find the link
    link = LINK_DATABASE.get(formatted_id)

    if link:
        return jsonify({"status": "success", "link": link}), 200
    else:
        return jsonify({"error": "ID not found"}), 404

if __name__ == '__main__':
    app.run(debug=True)
