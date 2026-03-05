from flask import Flask, request, jsonify

app = Flask(__name__)
global LINK_DATABASE
LINK_DATABASE = {

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

    link = LINK_DATABASE.get(formatted_id)

    if link:
        return jsonify({"status": "success", "link": link}), 200
    else:
        return jsonify({"error": "ID not found"}), 404

@app.route("/add-server", methods=['POST'])
def add_server_id():
    data = request.get_json()
    idadd = data.get("id")

    if not idadd:
        return jsonify({"error": "No ID passed"}), 400

    tunnel = data.get("tunnel")

    if not tunnel:
        return jsonify({"error": "No tunnel passed"}), 400

    formatted_id = f"{idadd["year"]}-{idadd["region"]}-{idadd["number"]}"
    LINK_DATABASE[formatted_id] = tunnel
    return jsonify({"status": "success"}), 200





if __name__ == '__main__':
    app.run(debug=True)
