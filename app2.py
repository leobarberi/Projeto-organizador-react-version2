from datetime import datetime
from flask import Flask, jsonify, request, abort, url_for, make_response
from flask_sqlalchemy import SQLAlchemy
import pandas as pd
import os
from flasgger import Swagger
from flask_cors import CORS
import numpy as np

app = Flask(__name__)
CORS(app)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///arquivos.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Modelo para armazenar arquivos Excel
class ArquivoExcel(db.Model):
  id = db.Column(db.Integer, primary_key=True)
  nome = db.Column(db.String(255), nullable=False)
  data_upload = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
  conteudo = db.Column(db.LargeBinary, nullable=False)

# Cria a tabela se não existir
with app.app_context():
  db.create_all()

template = {
  "swagger": "2.0",
  "info": {
    "title": "Items API",
    "description": "API de exemplo com endpoints para itens e upload de Excel.",
    "version": "1.0.0"
  },
  "basePath": "/"
}
swagger = Swagger(app, template=template)

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Endpoint para listar todos os arquivos Excel salvos
@app.route('/arquivos', methods=['GET'])
def listar_arquivos():
  arquivos = ArquivoExcel.query.order_by(ArquivoExcel.data_upload.desc()).all()
  lista = [
    {
      'id': arq.id,
      'nome': arq.nome,
      'data_upload': arq.data_upload.strftime('%Y-%m-%d %H:%M:%S')
    }
    for arq in arquivos
  ]
  return jsonify({'arquivos': lista})

# Endpoint para limpar todos os arquivos Excel do banco
@app.route('/limpar_arquivos', methods=['POST'])
def limpar_arquivos():
  ArquivoExcel.query.delete()
  db.session.commit()
  return jsonify({'mensagem': 'Todos os arquivos foram removidos do banco de dados.'})

# Endpoint para excluir um arquivo Excel pelo ID
@app.route('/arquivos/<int:arquivo_id>', methods=['DELETE'])
def excluir_arquivo(arquivo_id):
  arq = ArquivoExcel.query.get(arquivo_id)
  if not arq:
    return jsonify({'erro': 'Arquivo não encontrado'}), 404
  db.session.delete(arq)
  db.session.commit()
  return jsonify({'mensagem': f'Arquivo {arq.nome} excluído com sucesso!'})

# Endpoint para gerar resumo consolidado por período
@app.route('/resumo_periodo', methods=['GET', 'POST'])
def resumo_periodo():
  # Recebe datas do frontend (GET ou POST)
  data_inicial = request.args.get('data_inicial') or request.json.get('data_inicial') if request.is_json else None
  data_final = request.args.get('data_final') or request.json.get('data_final') if request.is_json else None

  # Busca todos os arquivos Excel salvos

  arquivos = ArquivoExcel.query.all()
  import io
  import pandas as pd
  dfs = []
  for arq in arquivos:
    buffer = io.BytesIO(arq.conteudo)
    try:
      df = pd.read_excel(buffer)
    except Exception:
      buffer.seek(0)
      try:
        df = pd.read_csv(buffer)
      except Exception:
        continue
    df['__plataforma'] = arq.nome.lower()
    dfs.append(df)

  if not arquivos or not dfs:
    return jsonify({"resumo": [], "mensagem": "Nenhum dado encontrado."})

  # Junta todos os dados
  df_all = pd.concat(dfs, ignore_index=True)

  # Detecta plataforma por nome do arquivo
  def detecta_plataforma(nome):
    nome = nome.lower()
    if "shopee" in nome:
      return "Shopee"
    elif "mercadolivre" in nome or "mercado livre" in nome:
      return "Mercado Livre"
    elif "tiktok" in nome:
      return "TikTok"
    elif "shein" in nome:
      return "Shein"
    else:
      return "Outro"
  df_all['plataforma'] = df_all['__plataforma'].apply(detecta_plataforma)

  # Padroniza nomes de colunas para facilitar
  colunas_map = {
    'Shopee': {'sku': 'Número de referência SKU', 'qtd': 'Quantidade', 'valor': 'Subtotal do produto', 'status': 'Status do pedido', 'data': 'Hora do pagamento do pedido'},
    'Mercado Livre': {'sku': 'SKU', 'qtd': 'Unidades', 'valor': 'Total (BRL)', 'status': 'Status', 'data': 'Data da venda'},
    'TikTok': {'sku': 'Seller sku input by the seller in the product system.', 'qtd': 'SKU sold quantity in the order.', 'valor': 'It equals SKU Subtotal Before Discount - SKU Platform Discount - SKU Seller Discount.', 'status': 'Order status', 'data': 'Order paid time.'},
    'Shein': {'sku': 'SKU do vendedor', 'qtd': 'Quantidade', 'valor': 'Receita estimada de mercadorias', 'status': 'Status do pedido', 'data': 'Data e hora de criação do pedido'}
  }

  # Filtra por data se informado
  # import numpy as np já está no topo
  resumo_final = []
  for plataforma, colunas in colunas_map.items():
    dfp = df_all[df_all['plataforma'] == plataforma].copy()
    if dfp.empty:
      continue
    # Converte coluna de data
    if colunas['data'] in dfp.columns:
      try:
        dfp[colunas['data']] = pd.to_datetime(dfp[colunas['data']], errors='coerce')
      except Exception:
        pass
      if data_inicial:
        dt_ini = pd.to_datetime(data_inicial)
        dfp = dfp[dfp[colunas['data']] >= dt_ini]
      if data_final:
        dt_fim = pd.to_datetime(data_final)
        dfp = dfp[dfp[colunas['data']] <= dt_fim]
    # Remove cancelados
    if colunas['status'] in dfp.columns:
      dfp = dfp[~dfp[colunas['status']].astype(str).str.lower().str.contains('cancel', na=False)]
    # Agrupa por SKU
    if colunas['sku'] in dfp.columns and colunas['qtd'] in dfp.columns and colunas['valor'] in dfp.columns:
      dfp[colunas['qtd']] = pd.to_numeric(dfp[colunas['qtd']], errors='coerce').fillna(0)
      dfp[colunas['valor']] = pd.to_numeric(dfp[colunas['valor']], errors='coerce').fillna(0)
      resumo = dfp.groupby(colunas['sku']).agg({colunas['qtd']: 'sum', colunas['valor']: 'sum'}).reset_index()
      for _, row in resumo.iterrows():
        resumo_final.append({
          'plataforma': plataforma,
          'sku': row[colunas['sku']],
          'quantidade': int(row[colunas['qtd']]),
          'valor_total': float(row[colunas['valor']])
        })

  return jsonify({"resumo": resumo_final})
  # ...existing code...

# --- NOVO ENDPOINT: Upload e leitura de Excel ---
@app.route('/upload_excel', methods=['POST'])
def upload_excel():
  """
  Faz upload de um arquivo Excel e retorna as colunas e primeiras linhas
  ---
  tags:
    - Excel
  consumes:
    - multipart/form-data
  parameters:
    - name: file
      in: formData
      type: file
      required: true
      description: Arquivo Excel (.xlsx, .xls, .csv)
  responses:
    200:
      description: Colunas e amostra dos dados
      schema:
        type: object
        properties:
          columns:
            type: array
            items:
              type: string
          preview:
            type: array
            items:
              type: object
    400:
      description: Arquivo inválido
  """
  def gerar_resumo_texto(plataforma, resumo):
    if plataforma == "Shopee":
      return f"Shopee: {resumo.get('pedidos', 0)} pedidos, {resumo.get('total_itens', 0)} itens, valor total R$ {resumo.get('valor_total', 0):.2f}"
    elif plataforma == "Mercado Livre":
      return f"Mercado Livre: {resumo.get('vendas', 0)} vendas, {resumo.get('total_unidades', 0)} unidades, valor total R$ {resumo.get('valor_total', 0):.2f}"
    elif plataforma == "TikTok":
      return f"TikTok: {resumo.get('pedidos', 0)} pedidos, {resumo.get('total_itens', 0)} itens, valor total R$ {resumo.get('valor_total', 0):.2f}"
    elif plataforma == "Shein":
      return f"Shein: {resumo.get('pedidos', 0)} pedidos, {resumo.get('total_itens', 0)} itens, valor total R$ {resumo.get('valor_total', 0):.2f}"
    else:
      return "Plataforma não reconhecida ou sem resumo."

  if 'file' not in request.files:
    abort(400, description='Nenhum arquivo enviado')
  file = request.files['file']
  if file.filename == '':
    abort(400, description='Nome de arquivo vazio')
  ext = file.filename.rsplit('.', 1)[-1].lower()
  conteudo = file.read()
  # Salva o arquivo no banco de dados
  novo_arquivo = ArquivoExcel(nome=file.filename, conteudo=conteudo)
  db.session.add(novo_arquivo)
  db.session.commit()
  # Lê o arquivo salvo (em memória)
  import io
  buffer = io.BytesIO(conteudo)
  if ext in ['xlsx', 'xls']:
    df = pd.read_excel(buffer)
  elif ext == 'csv':
    buffer.seek(0)
    df = pd.read_csv(buffer)
  else:
    abort(400, description='Formato de arquivo não suportado')
  columns = list(df.columns)
  preview = df.head(5).to_dict(orient='records')

  def detecta_plataforma(nome_arquivo):
    nome = nome_arquivo.lower()
    if "shopee" in nome:
      return "Shopee"
    elif "mercadolivre" in nome or "mercado livre" in nome:
      return "Mercado Livre"
    elif "tiktok" in nome:
      return "TikTok"
    elif "shein" in nome:
      return "Shein"
    else:
      return "Outro"

  plataforma = detecta_plataforma(file.filename)

  colunas_por_plataforma = {
      "Shopee": [
        "Hora do pagamento do pedido",
        "Número de referência SKU",
        "Nome da variação",
        "Subtotal do produto",
        "Quantidade"
      ],
      "Mercado Livre": [
        "Data da venda",
        "SKU",
        "Variação",
        "Total (BRL)",
        "Unidades"
      ],
      "TikTok": [
        "Order paid time.",
        "Seller sku input by the seller in the product system.",
        "Platform SKU variation",
        "It equals SKU Subtotal Before Discount - SKU Platform Discount - SKU Seller Discount.",
        "SKU sold quantity in the order."
      ],
      "Shein": [
        "SKU do vendedor",
        "Data e hora de criação do pedido",
        "Variação",
        "Receita estimada de mercadorias",
        "Quantidade"
      ]
    }

  resumo_personalizado = {"plataforma": plataforma}
  colunas_esperadas = colunas_por_plataforma.get(plataforma)
  if colunas_esperadas:
    colunas_existentes = [c for c in colunas_esperadas if c in df.columns]
    if len(colunas_existentes) >= 4:
      try:
        if plataforma == "Shopee":
          total_itens = int(df.get("Quantidade", 0).sum()) if "Quantidade" in df else None
          valor_total = float(df.get("Subtotal do produto", 0).sum()) if "Subtotal do produto" in df else None
          resumo_personalizado.update({
            "pedidos": len(df),
            "total_itens": total_itens,
            "valor_total": valor_total,
            "colunas_encontradas": colunas_existentes
          })
        elif plataforma == "Mercado Livre":
          total_unidades = int(df.get("Unidades", 0).sum()) if "Unidades" in df else None
          valor_total = float(df.get("Total (BRL)", 0).sum()) if "Total (BRL)" in df else None
          resumo_personalizado.update({
            "vendas": len(df),
            "total_unidades": total_unidades,
            "valor_total": valor_total,
            "colunas_encontradas": colunas_existentes
          })
        elif plataforma == "TikTok":
          total_itens = int(df.get('SKU sold quantity in the order.', 0).sum()) if 'SKU sold quantity in the order.' in df else None
          valor_total = float(df.get('It equals SKU Subtotal Before Discount - SKU Platform Discount - SKU Seller Discount.', 0).sum()) if 'It equals SKU Subtotal Before Discount - SKU Platform Discount - SKU Seller Discount.' in df else None
          resumo_personalizado.update({
            "pedidos": len(df),
            "total_itens": total_itens,
            "valor_total": valor_total,
            "colunas_encontradas": colunas_existentes
          })
        elif plataforma == "Shein":
          total_itens = int(df.get("Quantidade", 0).sum()) if "Quantidade" in df else None
          valor_total = float(df.get("Receita estimada de mercadorias", 0).sum()) if "Receita estimada de mercadorias" in df else None
          resumo_personalizado.update({
            "pedidos": len(df),
            "total_itens": total_itens,
            "valor_total": valor_total,
            "colunas_encontradas": colunas_existentes
          })
      except Exception as e:
        resumo_personalizado["erro"] = f"Erro ao calcular resumo: {str(e)}"
    else:
      resumo_personalizado["aviso"] = "Colunas principais não encontradas para esta plataforma."
  else:
    resumo_personalizado["aviso"] = "Plataforma não reconhecida ou não suportada."

  summary = {
    'num_rows': len(df),
    'num_columns': len(df.columns),
    'columns': columns,
    'dtypes': {col: str(dtype) for col, dtype in df.dtypes.items()},
    'plataforma': plataforma,
    'resumo_personalizado': resumo_personalizado
  }

  # Converter NaN/None para null no preview
  # import numpy as np já está no topo
  def clean_preview(val):
    if isinstance(val, float) and np.isnan(val):
      return None
    if isinstance(val, (np.generic, np.ndarray)):
      return val.item() if hasattr(val, 'item') else val.tolist()
    return val
  preview_clean = [
    {k: clean_preview(v) for k, v in row.items()} for row in preview
  ]

  resumo_texto = gerar_resumo_texto(plataforma, resumo_personalizado)


  import json
  response = make_response(
    json.dumps({
      'plataforma_detectada': plataforma,
      'resumo_personalizado': resumo_personalizado,
      'resumo_geral': summary,
      'colunas': columns,
      'preview': preview_clean,
      'resumo_texto': resumo_texto
    }, ensure_ascii=False)
  )
  response.headers['Content-Type'] = 'application/json; charset=utf-8'
  return response



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