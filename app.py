# app.py - VERSÃO FINAL 100% FUNCIONAL
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import os
from werkzeug.utils import secure_filename
from dateutil.relativedelta import relativedelta
from flask import send_from_directory

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///escola_futsal.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'sua_chave_secreta_aqui'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}

import os
from flask import send_from_directory

# Garante que a pasta uploads existe e serve arquivos estáticos
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


# Injeta a função now() nos templates (pra data do recibo)
@app.context_processor
def inject_now():
    return {'now': lambda: datetime.now(ZoneInfo("America/Sao_Paulo"))}

db = SQLAlchemy(app)

# ---------- PASTA DE UPLOAD ----------
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# ---------- MODELOS ----------
class Aluno(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome_completo = db.Column(db.String(100), nullable=False)
    data_nascimento = db.Column(db.Date, nullable=False)
    nome_responsavel = db.Column(db.String(100), nullable=False)
    foto_path = db.Column(db.String(200))
    posicao = db.Column(db.String(50))

class Pagamento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    aluno_id = db.Column(db.Integer, db.ForeignKey('aluno.id'), nullable=False)
    data_vencimento = db.Column(db.Date, nullable=False)
    valor = db.Column(db.Float, nullable=False)
    pago = db.Column(db.Boolean, default=False)
    data_pagamento = db.Column(db.Date)
    forma_pagamento = db.Column(db.String(20))
    tipo_plano = db.Column(db.String(20), nullable=False)

# ---------- CÁLCULO DE JUROS ----------
def calcular_juros(pagamento):
    if pagamento.pago:
        return 0.0
    hoje = datetime.now().date()
    if hoje > pagamento.data_vencimento:
        dias = (hoje - pagamento.data_vencimento).days
        return round(pagamento.valor * 0.01 * dias, 2)
    return 0.0

# ---------- GERA RECORRÊNCIAS (COM DESCONTO E 36 MESES) ----------
def gerar_recorrencias(aluno_id, data_inicio, tipo_plano, valor_mensal, meses_gerar=36):
    pagamentos = []

    if tipo_plano == 'mensal':
        valor_parcela = valor_mensal
        for i in range(meses_gerar):
            vencimento = data_inicio + relativedelta(months=i)
            p = Pagamento(
                aluno_id=aluno_id,
                data_vencimento=vencimento,
                valor=valor_parcela,
                tipo_plano=tipo_plano
            )
            pagamentos.append(p)

    elif tipo_plano == 'semestral':
        valor_parcela = round(valor_mensal * 6 * 0.9, 2)  # -10%
        for i in range(0, meses_gerar, 6):
            vencimento = data_inicio + relativedelta(months=i)
            p = Pagamento(
                aluno_id=aluno_id,
                data_vencimento=vencimento,
                valor=valor_parcela,
                tipo_plano=tipo_plano
            )
            pagamentos.append(p)

    elif tipo_plano == 'anual':
        valor_parcela = round(valor_mensal * 12 * 0.8, 2)  # -20%
        for i in range(0, meses_gerar, 12):
            vencimento = data_inicio + relativedelta(months=i)
            p = Pagamento(
                aluno_id=aluno_id,
                data_vencimento=vencimento,
                valor=valor_parcela,
                tipo_plano=tipo_plano
            )
            pagamentos.append(p)

    # ESSES DOIS CARAS NUNCA PODEM FALTAR!!!
    db.session.add_all(pagamentos)
    db.session.commit()

    print(f">>> GERADAS {len(pagamentos)} PARCELAS PARA ALUNO {aluno_id} - PLANO {tipo_plano}")  # pra tu ver no console

# ---------- ROTAS ----------
@app.route('/')
def index():
    # Parâmetros do filtro
    mes = request.args.get('mes', datetime.now().month, type=int)
    ano = request.args.get('ano', datetime.now().year, type=int)

    # Define início e fim do mês selecionado
    inicio_mes = datetime(ano, mes, 1).date()
    if mes == 12:
        fim_mes = datetime(ano + 1, 1, 1).date() - timedelta(days=1)
    else:
        fim_mes = datetime(ano, mes + 1, 1).date() - timedelta(days=1)

    # Estatísticas do mês selecionado
    total_alunos = Aluno.query.count()

    em_aberto_mes = db.session.query(db.func.sum(Pagamento.valor))\
        .filter(Pagamento.pago == False,
                Pagamento.data_vencimento.between(inicio_mes, fim_mes))\
        .scalar() or 0.0

    recebido_mes = db.session.query(db.func.sum(Pagamento.valor))\
        .filter(Pagamento.pago == True,
                Pagamento.data_pagamento.between(inicio_mes, fim_mes))\
        .scalar() or 0.0

    inadimplentes_mes = db.session.query(db.distinct(Pagamento.aluno_id))\
        .filter(Pagamento.pago == False,
                Pagamento.data_vencimento.between(inicio_mes, fim_mes))\
        .count()

    return render_template('index.html',
                           total_alunos=total_alunos,
                           em_aberto=em_aberto_mes,
                           recebido_mes=recebido_mes,
                           inadimplentes=inadimplentes_mes,
                           mes_atual=mes,
                           ano_atual=ano)

@app.route('/cadastro_aluno', methods=['GET', 'POST'])
def cadastro_aluno():
    if request.method == 'POST':
        nome = request.form['nome_completo']
        nasc = datetime.strptime(request.form['data_nascimento'], '%Y-%m-%d').date()
        resp = request.form['nome_responsavel']
        pos = request.form.get('posicao', '')
        foto = request.files.get('foto')

        aluno = Aluno(nome_completo=nome, data_nascimento=nasc, nome_responsavel=resp, posicao=pos)

        if foto and allowed_file(foto.filename):
            fn = secure_filename(foto.filename)
            foto.save(os.path.join(app.config['UPLOAD_FOLDER'], fn))
            aluno.foto_path = fn

        db.session.add(aluno)
        db.session.commit()
        flash('Aluno cadastrado com sucesso!', 'success')
        return redirect(url_for('index'))
    return render_template('cadastro_aluno.html')

@app.route('/cadastro_financeiro', methods=['GET', 'POST'])
def cadastro_financeiro():
    if request.method == 'POST':
        aluno_id = request.form['aluno_id']
        data_venc_str = request.form['data_vencimento']
        plano = request.form['tipo_plano']
        valor_mensal = float(request.form['valor_mensal'])
        data_venc = datetime.strptime(data_venc_str, '%Y-%m-%d').date()

        # === ALUNO NOVO ===
        if aluno_id == 'novo':
            nome = request.form['nome_completo']
            nasc = datetime.strptime(request.form['data_nascimento'], '%Y-%m-%d').date()
            resp = request.form['nome_responsavel']
            pos = request.form.get('posicao', '')
            foto = request.files.get('foto')

            novo_aluno = Aluno(nome_completo=nome, data_nascimento=nasc, nome_responsavel=resp, posicao=pos)
            if foto and allowed_file(foto.filename):
                fn = secure_filename(foto.filename)
                foto.save(os.path.join(app.config['UPLOAD_FOLDER'], fn))
                novo_aluno.foto_path = fn

            db.session.add(novo_aluno)
            db.session.commit()
            aluno_id_final = novo_aluno.id
            flash('Novo aluno cadastrado e parcelas geradas!', 'success')

        # === ALUNO JÁ EXISTENTE ===
        else:
            aluno_id_final = int(aluno_id)
            flash('Parcelas geradas para aluno existente!', 'success')

        # AQUI É OBRIGATÓRIO: GERA AS PARCELAS NOS DOIS CASOS!!!
        gerar_recorrencias(aluno_id_final, data_venc, plano, valor_mensal, meses_gerar=36)

        return redirect(url_for('index'))

    # GET - mostrar formulário
    alunos = Aluno.query.order_by(Aluno.nome_completo).all()
    return render_template('cadastro_financeiro.html', alunos=alunos)

    ########################

@app.route('/cobranca')
def cobranca():
    # filtros
    mes = request.args.get('mes')
    ano = request.args.get('ano')
    data_inicio = request.args.get('data_inicio')
    data_fim = request.args.get('data_fim')

    query = Pagamento.query.filter(Pagamento.pago == False)

    if mes and ano:
        try:
            mes_int = int(mes)
            ano_int = int(ano)
            inicio = datetime(ano_int, mes_int, 1).date()
            if mes_int < 12:
                fim = datetime(ano_int, mes_int + 1, 1).date() - timedelta(days=1)
            else:
                fim = datetime(ano_int + 1, 1, 1).date() - timedelta(days=1)
            query = query.filter(Pagamento.data_vencimento.between(inicio, fim))
        except:
            pass
    elif data_inicio and data_fim:
        try:
            inicio = datetime.strptime(data_inicio, '%Y-%m-%d').date()
            fim = datetime.strptime(data_fim, '%Y-%m-%d').date()
            query = query.filter(Pagamento.data_vencimento.between(inicio, fim))
        except:
            pass

    pagamentos = query.order_by(Pagamento.data_vencimento).all()
    dados = []
    for p in pagamentos:
        aluno = Aluno.query.get(p.aluno_id)
        juros = calcular_juros(p)
        total = p.valor + juros
        dados.append({'pagamento': p, 'aluno': aluno, 'juros': juros, 'total': total})

    return render_template('cobranca.html', dados=dados, mes=mes, ano=ano, data_inicio=data_inicio, data_fim=data_fim)

@app.route('/pagar/<int:pagamento_id>', methods=['GET', 'POST'])
def pagar(pagamento_id):
    pagamento = Pagamento.query.get_or_404(pagamento_id)
    aluno = Aluno.query.get(pagamento.aluno_id)
    juros = calcular_juros(pagamento)
    total = pagamento.valor + juros

    if request.method == 'POST':
        pagamento.pago = True
        pagamento.data_pagamento = datetime.now().date()
        pagamento.forma_pagamento = request.form['forma_pagamento']
        db.session.commit()
        flash(f'Pagamento de {aluno.nome_completo} registrado com sucesso!', 'success')
        return redirect(url_for('index'))

    return render_template('pagar.html', pagamento=pagamento, aluno=aluno, juros=juros, total=total)

@app.route('/relatorio_alunos')
def relatorio_alunos():
    alunos = Aluno.query.all()
    return render_template('relatorio_alunos.html', alunos=alunos)

@app.route('/relatorio_alunos_aberto')
def relatorio_alunos_aberto():
    hoje = datetime.now().date()
    pendentes = Pagamento.query.filter(Pagamento.pago == False).all()
    dados = {}
    for p in pendentes:
        a = Aluno.query.get(p.aluno_id)
        if a.id not in dados:
            dados[a.id] = {'aluno': a, 'pagamentos': []}
        j = calcular_juros(p)
        dados[a.id]['pagamentos'].append({'pagamento': p, 'juros': j, 'total': p.valor + j})
    return render_template('relatorio_alunos_aberto.html', alunos_aberto=dados.values())

@app.route('/editar_parcela/<int:pagamento_id>', methods=['GET', 'POST'])
def editar_parcela(pagamento_id):
    pagamento = Pagamento.query.get_or_404(pagamento_id)
    aluno = Aluno.query.get(pagamento.aluno_id)

    if request.method == 'POST':
        pagamento.data_vencimento = datetime.strptime(request.form['data_vencimento'], '%Y-%m-%d').date()
        pagamento.valor = float(request.form['valor'])
        pagamento.tipo_plano = request.form['tipo_plano']
        db.session.commit()
        flash('Parcela atualizada com sucesso!', 'success')
        return redirect(url_for('cobranca'))

    return render_template('editar_parcela.html', pagamento=pagamento, aluno=aluno)

@app.route('/excluir_parcela/<int:pagamento_id>', methods=['POST'])
def excluir_parcela(pagamento_id):
    pagamento = Pagamento.query.get_or_404(pagamento_id)
    db.session.delete(pagamento)
    db.session.commit()
    flash('Parcela excluída com sucesso!', 'success')
    return redirect(url_for('cobranca'))

@app.route('/editar_aluno/<int:aluno_id>', methods=['GET', 'POST'])
def editar_aluno(aluno_id):
    aluno = Aluno.query.get_or_404(aluno_id)
    if request.method == 'POST':
        aluno.nome_completo = request.form['nome_completo']
        aluno.data_nascimento = datetime.strptime(request.form['data_nascimento'], '%Y-%m-%d').date()
        aluno.nome_responsavel = request.form['nome_responsavel']
        aluno.posicao = request.form.get('posicao', '')

        foto = request.files.get('foto')
        if foto and allowed_file(foto.filename):
            if aluno.foto_path:
                old_path = os.path.join(app.config['UPLOAD_FOLDER'], aluno.foto_path)
                if os.path.exists(old_path):
                    os.remove(old_path)
            fn = secure_filename(foto.filename)
            foto.save(os.path.join(app.config['UPLOAD_FOLDER'], fn))
            aluno.foto_path = fn

        db.session.commit()
        flash('Aluno atualizado com sucesso!', 'success')
        return redirect(url_for('relatorio_alunos'))

    return render_template('editar_aluno.html', aluno=aluno)

@app.route('/excluir_aluno/<int:aluno_id>', methods=['POST'])
def excluir_aluno(aluno_id):
    aluno = Aluno.query.get_or_404(aluno_id)
    if aluno.foto_path:
        foto_path = os.path.join(app.config['UPLOAD_FOLDER'], aluno.foto_path)
        if os.path.exists(foto_path):
            os.remove(foto_path)
    Pagamento.query.filter_by(aluno_id=aluno_id).delete()
    db.session.delete(aluno)
    db.session.commit()
    flash('Aluno e todas as parcelas excluídos!', 'success')
    return redirect(url_for('relatorio_alunos'))

@app.route('/recibos')
def relatorio_recibos():
    mes = request.args.get('mes', datetime.now().month, type=int)
    ano = request.args.get('ano', datetime.now().year, type=int)

    inicio = datetime(ano, mes, 1).date()
    if mes == 12:
        fim = datetime(ano + 1, 1, 1).date() - timedelta(days=1)
    else:
        fim = datetime(ano, mes + 1, 1).date() - timedelta(days=1)

    pagamentos = Pagamento.query.filter(
        Pagamento.pago == True,
        Pagamento.data_pagamento.between(inicio, fim)
    ).order_by(Pagamento.data_pagamento.desc()).all()

    dados = {}
    for p in pagamentos:
        aluno = Aluno.query.get(p.aluno_id)
        if aluno.id not in dados:
            dados[aluno.id] = {'aluno': aluno, 'pagamentos': []}
        dados[aluno.id]['pagamentos'].append(p)

    total_mes = db.session.query(db.func.sum(Pagamento.valor)).filter(
        Pagamento.pago == True,
        Pagamento.data_pagamento.between(inicio, fim)
    ).scalar() or 0

    return render_template('relatorio_recibos.html',
                           dados=dados.values(),
                           mes=mes, ano=ano, total_mes=total_mes)

# ---------- INICIALIZAÇÃO ----------
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)