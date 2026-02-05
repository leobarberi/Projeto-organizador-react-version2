from datetime import datetime
from flask import Flask, jsonify, request, abort, url_for
from flasgger import Swagger

app = Flask(__name__)

# Swagger template básico
template = {
    "swagger": "2.0",
    "info": {
        "title": "Items API",
        "description": "API de exemplo com 5 endpoints (health, list, get, create, update).",
        "version": "1.0.0"
    },
    "basePath": "/"
}
swagger = Swagger(app, template=template)

# Armazenamento em memória (exemplo)
_items = {
    1: {"id": 1, "name": "Caneta", "description": "Caneta azul"},
    2: {"id": 2, "name": "Caderno", "description": "Caderno A4"}
}


def next_id():
    return max(_items.keys(), default=0) + 1


@app.route("/health", methods=["GET"])
def health():
    """
    Health check
    ---
    tags:
      - Health
    responses:
      200:
        description: API está saudável
        schema:
          type: object
          properties:
            status:
              type: string
              example: ok
            timestamp:
              type: string
              example: "2026-02-05T12:00:00Z"
    """
    return jsonify({"status": "ok", "timestamp": datetime.utcnow().isoformat() + "Z"})


@app.route("/items", methods=["GET"])
def list_items():
    """
    Lista itens
    ---
    tags:
      - Items
    responses:
      200:
        description: Lista de itens
        schema:
          type: array
          items:
            type: object
            properties:
              id:
                type: integer
                example: 1
              name:
                type: string
                example: Caneta
              description:
                type: string
                example: Caneta azul
    """
    return jsonify(list(_items.values()))


@app.route("/items/<int:item_id>", methods=["GET"])
def get_item(item_id):
    """
    Obter item por id
    ---
    tags:
      - Items
    parameters:
      - name: item_id
        in: path
        type: integer
        required: true
        description: ID do item
    responses:
      200:
        description: Item encontrado
        schema:
          type: object
          properties:
            id:
              type: integer
              example: 1
            name:
              type: string
              example: Caneta
            description:
              type: string
              example: Caneta azul
      404:
        description: Item não encontrado
    """
    item = _items.get(item_id)
    if item is None:
        abort(404, description="Item não encontrado")
    return jsonify(item)


@app.route("/items", methods=["POST"])
def create_item():
    """
    Criar um novo item
    ---
    tags:
      - Items
    consumes:
      - application/json
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - name
          properties:
            name:
              type: string
              example: Lápis
            description:
              type: string
              example: Lápis HB
    responses:
      201:
        description: Item criado
        schema:
          type: object
          properties:
            id:
              type: integer
            name:
              type: string
            description:
              type: string
      400:
        description: JSON inválido ou campo 'name' ausente
    """
    data = request.get_json(silent=True)
    if not data or "name" not in data:
        abort(400, description="JSON inválido ou campo 'name' ausente")

    item_id = next_id()
    item = {
        "id": item_id,
        "name": data["name"],
        "description": data.get("description", "")
    }
    _items[item_id] = item
    return jsonify(item), 201, {"Location": url_for("get_item", item_id=item_id)}


@app.route("/items/<int:item_id>", methods=["PUT"])
def update_item(item_id):
    """
    Atualizar um item existente
    ---
    tags:
      - Items
    parameters:
      - name: item_id
        in: path
        type: integer
        required: true
        description: ID do item
      - in: body
        name: body
        required: true
        schema:
          type: object
          properties:
            name:
              type: string
              example: Caneta Azul
            description:
              type: string
              example: Caneta azul (atualizado)
    responses:
      200:
        description: Item atualizado
        schema:
          type: object
          properties:
            id:
              type: integer
            name:
              type: string
            description:
              type: string
      400:
        description: JSON inválido
      404:
        description: Item não encontrado
    """
    if item_id not in _items:
        abort(404, description="Item não encontrado")

    data = request.get_json(silent=True)
    if not data:
        abort(400, description="JSON inválido")

    item = _items[item_id]
    if "name" in data:
        item["name"] = data["name"]
    if "description" in data:
        item["description"] = data["description"]

    _items[item_id] = item
    return jsonify(item)


# Tratamento simples de erros para devolver JSON
@app.errorhandler(400)
@app.errorhandler(404)
@app.errorhandler(500)
def handle_error(error):
    response = jsonify({
        "error": getattr(error, "name", "Error"),
        "message": getattr(error, "description", str(error))
    })
    response.status_code = error.code if hasattr(error, "code") else 500
    return response


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)